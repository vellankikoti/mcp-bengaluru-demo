"""
MCP Incident Agent — FastAPI backend
Streams Claude responses + tool calls over SSE.
"""
import json
import os
from pathlib import Path
from typing import Any, Optional

# Load .env file if present (agent/.env or repo root .env)
for _env_path in [Path(__file__).parent / ".env", Path(__file__).parent.parent / ".env"]:
    if _env_path.exists():
        for _line in _env_path.read_text().splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

import asyncio
import uuid
import httpx
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from tools import TOOL_DEFINITIONS, TOOL_REGISTRY, PROMETHEUS_URL, ALERTMANAGER_URL
import policy as _policy

# ── Config ───────────────────────────────────────────────────────────────────

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096
FRONTEND = Path(__file__).resolve().parent / "frontend" / "index.html"

SYSTEM_PROMPT = """You are an expert Kubernetes SRE agent operating on a live demo cluster for a conference talk on AI-assisted incident response. You diagnose incidents, trace root causes, and recommend remediations with precision.

CLUSTER CONTEXT:
- Cluster: kind-mcp-demo (single-node kind, Kubernetes 1.33)
- Namespace in focus: production
- Services:
  • payment-service  — payment processing, FAULT_MODE: healthy/oom/error/slow/error_rate
  • order-service    — order management, calls payment-service synchronously
  • auth-service     — authentication, FAULT_MODE: cert_expiry
  • notification-service — async notifications, FAULT_MODE: aggressive_retry (floods email-gateway)
  • email-gateway    — email delivery, rate-limits at 10 RPS → returns 429 when exceeded
  • traffic-gen      — continuous synthetic load generator (always running)

KNOWN INCIDENT PATTERNS:
1. OOMKill cascade     — payment-service memory limit 50Mi + FAULT_MODE=oom → CrashLoopBackOff → order failures
2. High error rate     — payment-service FAULT_MODE=error → ~40% HTTP 500 → order service payment failures
3. Latency spike       — payment-service FAULT_MODE=slow (1.5–4s) → order p99 breaches 2s SLO
4. Retry storm         — notification-service FAULT_MODE=aggressive_retry → 5000 retries → email-gateway 429s
5. Cert expiry warning — auth-service FAULT_MODE=cert_expiry → degraded auth responses
6. Bad rollout         — payment-service SERVICE_VERSION=v2 FAULT_MODE=error_rate → 50% errors
7. DNS failure         — CoreDNS invalid upstream 192.0.2.254 → all service discovery broken
8. Stuck HPA           — node tainted demo.mcp.io/unavailable → pods Pending → traffic unserved

DIAGNOSIS APPROACH:
1. Start with get_alerts — shows firing alerts immediately
2. list_pods — see the overall pod health at a glance
3. For CrashLoopBackOff → describe_pod (exit reason) + get_pod_logs (OOM / error messages)
4. For latency / errors → prometheus_query for rates and percentiles
5. For retry storms → prometheus_query email-gateway 429 rate + notification_retry_storm_active
6. For pending pods → get_node_status (taints / resource pressure)
7. Always quantify: restart count, error %, latency p99, memory %, RPS

KEY PROMETHEUS METRICS:
- payment_requests_total{status="500"}   — payment errors
- payment_memory_simulated_bytes          — simulated OOM growth
- order_request_duration_seconds_bucket  — order latency histogram
- notification_retry_storm_active         — 1 when storm active
- email_gateway_requests_total{status="429"} — rate-limited requests
- auth_requests_total{status="503"}       — auth failures
- container_memory_working_set_bytes{namespace="production",container="payment"} — actual pod memory (container name is "payment" not "payment-service")

RESPONSE FORMAT:
- Use Markdown with clear headers
- Lead with a severity verdict: 🔴 Critical / 🟡 Warning / 🟢 Healthy
- Include: Affected Services, Root Cause, Blast Radius, Recommended Action
- Be precise — include actual numbers from tool results
- For write actions (restart/scale): explain risk before proposing

You have access to write tools (restart_deployment, scale_deployment) — use them only when the user explicitly requests remediation or confirms your suggestion.
You also have access to list_secrets — use it when asked to audit secrets or demonstrate over-permissioned access."""

# ── FastAPI app ──────────────────────────────────────────────────────────────

app = FastAPI(title="MCP Incident Agent", docs_url=None, redoc_url=None)
_api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
anthropic = AsyncAnthropic(api_key=_api_key) if _api_key else AsyncAnthropic()

# ── Demo / security state ────────────────────────────────────────────────────

_security_on: bool = False                            # toggled by /api/demo/security
_pending_approvals: dict[str, asyncio.Event] = {}     # request_id → Event
_approval_decisions: dict[str, bool] = {}             # request_id → approved
_audit_log: list[dict] = []                           # append-only, capped at 200
_active_token: Optional[dict] = None                  # simulated scoped token


def _append_audit(entry: dict) -> None:
    _audit_log.append(entry)
    if len(_audit_log) > 200:
        del _audit_log[0]


ALLOWED_MODELS = {
    "claude-sonnet-4-6",
    "claude-opus-4-7",
    "claude-haiku-4-5-20251001",
    "claude-3-5-sonnet-latest",
    "claude-3-5-haiku-latest",
    "claude-3-opus-latest",
}


class ChatRequest(BaseModel):
    messages: list[dict[str, Any]]
    api_key: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None


class ValidateKeyRequest(BaseModel):
    api_key: str
    model: str = MODEL
    base_url: Optional[str] = None


class SwitchClusterRequest(BaseModel):
    context: str


class ApprovalRequest(BaseModel):
    approved: bool


class DemoSecurityRequest(BaseModel):
    security_on: bool


def _sse(event_type: str, data: dict) -> str:
    return f"data: {json.dumps({'type': event_type, **data})}\n\n"


# OpenAI-compatible base URLs for each provider
_OAI_BASE: dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1",
    "openai":     "https://api.openai.com/v1",
    "groq":       "https://api.groq.com/openai/v1",
    "google":     "https://generativelanguage.googleapis.com/v1beta/openai/",
}

# Convert Anthropic tool defs → OpenAI function-calling format (one-time)
_OAI_TOOLS = [
    {"type": "function", "function": {
        "name": t["name"],
        "description": t["description"],
        "parameters": t["input_schema"],
    }}
    for t in TOOL_DEFINITIONS
]


import time as _time


async def _run_tool_with_policy(name: str, tool_input: dict, call_id: str = ""):
    """
    Evaluate policy, emit SSE events, optionally wait for approval, then execute.
    call_id is the tool-use id from the LLM (matches the tool_start event) so the
    frontend can attach policy badges to the right card. The internal request_id
    is used only for the approval API endpoint.
    """
    result_policy = _policy.evaluate(name, tool_input, _security_on)
    rid = result_policy.request_id   # approval API key
    eid = call_id or rid             # SSE event id — must match tool_start id

    # ── Emit policy_check event ───────────────────────────────────────────────
    yield _sse("policy_check", {
        "id":           eid,
        "policy_id":    rid,
        "tool":         name,
        "action":       result_policy.action.value,
        "rule":         result_policy.rule,
        "reason":       result_policy.reason,
        "blast_radius": result_policy.blast_radius,
    })

    t0 = _time.monotonic()

    # ── DENY ──────────────────────────────────────────────────────────────────
    if result_policy.action == _policy.PolicyAction.DENY:
        msg = f"🔒 POLICY DENIED — {result_policy.reason}"
        _append_audit({
            "ts": _time.time(), "tool": name, "input": tool_input,
            "action": "deny", "rule": result_policy.rule,
            "reason": result_policy.reason, "duration_ms": 0,
        })
        yield _sse("tool_result", {"id": eid, "content": msg})
        return

    # ── REQUIRE_APPROVAL ──────────────────────────────────────────────────────
    if result_policy.action == _policy.PolicyAction.REQUIRE_APPROVAL:
        ev = asyncio.Event()
        _pending_approvals[rid] = ev
        _approval_decisions[rid] = False

        yield _sse("approval_required", {
            "id":           eid,
            "policy_id":    rid,
            "tool":         name,
            "input":        tool_input,
            "blast_radius": result_policy.blast_radius,
            "timeout_s":    60,
        })

        try:
            await asyncio.wait_for(ev.wait(), timeout=60)
        except asyncio.TimeoutError:
            _pending_approvals.pop(rid, None)
            _approval_decisions.pop(rid, None)
            msg = "⏱ Approval timed out after 60s — action cancelled"
            _append_audit({
                "ts": _time.time(), "tool": name, "input": tool_input,
                "action": "timeout", "rule": result_policy.rule,
                "reason": "Approval timeout", "duration_ms": 0,
            })
            yield _sse("approval_result", {"id": eid, "approved": False, "reason": "timeout"})
            yield _sse("tool_result", {"id": eid, "content": msg})
            return

        approved = _approval_decisions.pop(rid, False)
        _pending_approvals.pop(rid, None)

        yield _sse("approval_result", {"id": eid, "approved": approved})

        if not approved:
            msg = "🚫 Action denied by operator"
            _append_audit({
                "ts": _time.time(), "tool": name, "input": tool_input,
                "action": "denied_by_operator", "rule": result_policy.rule,
                "reason": "Human denied approval", "duration_ms": 0,
            })
            yield _sse("tool_result", {"id": eid, "content": msg})
            return

        # Emit scoped short-lived token for approved write actions
        _tok_id = f"tok-{str(uuid.uuid4())[:8]}"
        _tok_ttl = 300
        _tok_scope = f"{tool_input.get('namespace', 'production')}:{result_policy.rule}"
        yield _sse("token_minted", {
            "id":         _tok_id,
            "scope":      _tok_scope,
            "ttl_s":      _tok_ttl,
            "expires_at": _time.time() + _tok_ttl,
            "tool":       name,
            "target":     tool_input.get("deployment_name", tool_input.get("pod_name", "")),
        })

    # ── EXECUTE ───────────────────────────────────────────────────────────────
    fn = TOOL_REGISTRY.get(name)
    if fn is None:
        result = f"Unknown tool: {name}"
    else:
        try:
            result = str(await fn(**tool_input))
        except Exception as e:
            result = f"Tool error ({name}): {type(e).__name__}: {e}"

    duration_ms = int((_time.monotonic() - t0) * 1000)
    _append_audit({
        "ts": _time.time(), "tool": name, "input": tool_input,
        "action": result_policy.action.value, "rule": result_policy.rule,
        "reason": result_policy.reason,
        "approved": result_policy.action == _policy.PolicyAction.REQUIRE_APPROVAL,
        "duration_ms": duration_ms,
        "result_preview": result[:120],
    })

    yield _sse("tool_result", {"id": eid, "content": result})


async def _anthropic_loop(client: AsyncAnthropic, model: str, work_messages: list[dict]):
    """Anthropic agentic loop — yields SSE strings."""
    while True:
        tool_calls: list[dict] = []
        accumulated_text = ""

        async with client.messages.stream(
            model=model, max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT, tools=TOOL_DEFINITIONS,
            messages=work_messages,
        ) as stream:
            async for event in stream:
                etype = getattr(event, "type", None)
                if etype == "content_block_start":
                    block = event.content_block
                    if block.type == "tool_use":
                        tool_calls.append({"id": block.id, "name": block.name, "input_raw": ""})
                        yield _sse("tool_start", {"id": block.id, "name": block.name, "input": {}})
                elif etype == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta":
                        accumulated_text += delta.text
                        yield _sse("text_delta", {"content": delta.text})
                    elif delta.type == "input_json_delta" and tool_calls:
                        tool_calls[-1]["input_raw"] += delta.partial_json
                elif etype == "content_block_stop" and tool_calls:
                    last = tool_calls[-1]
                    if last.get("input_raw") and not last.get("input_parsed"):
                        try:
                            last["input"] = json.loads(last["input_raw"])
                        except Exception:
                            last["input"] = {}
                        last["input_parsed"] = True
                        yield _sse("tool_input_ready", {"id": last["id"], "name": last["name"], "input": last["input"]})
            final_message = await stream.get_final_message()

        if final_message.stop_reason != "tool_use":
            yield _sse("done", {})
            break

        tool_results = []
        for tc in tool_calls:
            result = ""
            async for ev in _run_tool_with_policy(tc["name"], tc.get("input") or {}, tc["id"]):
                yield ev
                # capture the tool_result payload for Anthropic's message history
                try:
                    parsed = json.loads(ev[len("data: "):].strip())
                    if parsed.get("type") == "tool_result":
                        result = parsed.get("content", "")
                except Exception:
                    pass
            tool_results.append({"type": "tool_result", "tool_use_id": tc["id"], "content": result})
        work_messages.append({"role": "assistant", "content": final_message.content})
        work_messages.append({"role": "user", "content": tool_results})


async def _openai_loop(key: str, base_url: str, model: str, work_messages: list[dict]):
    """OpenAI-compatible agentic loop (OpenRouter / OpenAI / Groq) — yields SSE strings."""
    from openai import AuthenticationError, APIStatusError
    extra_headers: dict = {}
    if "openrouter.ai" in base_url:
        extra_headers = {"HTTP-Referer": "http://localhost:8082", "X-Title": "MCP Incident Agent"}
    client = AsyncOpenAI(api_key=key, base_url=base_url, default_headers=extra_headers)
    oai_msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + [
        {"role": m["role"], "content": m["content"] or ""} for m in work_messages
    ]

    while True:
        acc_text = ""
        tc_acc: dict[int, dict] = {}

        try:
            stream = await client.chat.completions.create(
                model=model, max_tokens=MAX_TOKENS,
                messages=oai_msgs, tools=_OAI_TOOLS,
                tool_choice="auto", stream=True,
            )
        except AuthenticationError:
            yield _sse("error", {"content": "Invalid API key — authentication failed. Re-enter your key in **AI Settings**."})
            yield _sse("done", {})
            return
        except APIStatusError as e:
            yield _sse("error", {"content": f"API error {e.status_code}: {e.message}"})
            yield _sse("done", {})
            return
        except Exception as e:
            yield _sse("error", {"content": f"Connection error: {e}"})
            yield _sse("done", {})
            return

        finish_reason = None
        async for chunk in stream:
            choice = chunk.choices[0] if chunk.choices else None
            if not choice:
                continue
            finish_reason = choice.finish_reason or finish_reason
            delta = choice.delta

            if delta.content:
                acc_text += delta.content
                yield _sse("text_delta", {"content": delta.content})

            for tc in (delta.tool_calls or []):
                i = tc.index
                if i not in tc_acc:
                    tc_acc[i] = {"id": tc.id or f"call_{i}", "name": "", "arguments": ""}
                if tc.id:
                    tc_acc[i]["id"] = tc.id
                if tc.function:
                    if tc.function.name:
                        tc_acc[i]["name"] = tc.function.name
                        yield _sse("tool_start", {"id": tc_acc[i]["id"], "name": tc.function.name, "input": {}})
                    if tc.function.arguments:
                        tc_acc[i]["arguments"] += tc.function.arguments

        if finish_reason != "tool_calls" or not tc_acc:
            yield _sse("done", {})
            break

        assistant_tcs = []
        tool_msgs = []
        for i, tc in sorted(tc_acc.items()):
            try:
                tool_input = json.loads(tc["arguments"]) if tc["arguments"] else {}
            except Exception:
                tool_input = {}
            yield _sse("tool_input_ready", {"id": tc["id"], "name": tc["name"], "input": tool_input})
            result = ""
            async for ev in _run_tool_with_policy(tc["name"], tool_input, tc["id"]):
                yield ev
                try:
                    parsed = json.loads(ev[len("data: "):].strip())
                    if parsed.get("type") == "tool_result":
                        result = parsed.get("content", "")
                except Exception:
                    pass
            assistant_tcs.append({"id": tc["id"], "type": "function",
                                   "function": {"name": tc["name"], "arguments": tc["arguments"]}})
            tool_msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": result})

        oai_msgs.append({"role": "assistant", "content": acc_text or None, "tool_calls": assistant_tcs})
        oai_msgs.extend(tool_msgs)


async def _chat_stream(
    messages: list[dict],
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
):
    """Route to the right provider loop based on key prefix or explicit base_url."""
    key = (api_key or "").strip()

    if not key and not anthropic.api_key:
        yield _sse("error", {"content": "No API key configured. Open Settings (⚙) and add your API key."})
        yield _sse("done", {})
        return

    # ── Custom / bring-your-own endpoint ────────────────────────────────────
    if base_url:
        use_model = model or "gpt-4o"
        work = [{"role": m["role"], "content": m["content"]} for m in messages]
        async for chunk in _openai_loop(key, base_url.rstrip("/"), use_model, work):
            yield chunk
        return

    provider = _detect_provider(key) if key else None

    # ── OpenAI-compatible providers ──────────────────────────────────────────
    if provider and provider["id"] in _OAI_BASE:
        oai_url = _OAI_BASE[provider["id"]]
        use_model = model or "gpt-4o"
        work = [{"role": m["role"], "content": m["content"]} for m in messages]
        async for chunk in _openai_loop(key, oai_url, use_model, work):
            yield chunk
        return

    # ── Anthropic (default) ───────────────────────────────────────────────────
    ant_key = key if (provider and provider["auth"] == "sdk") else (key or None)
    client = AsyncAnthropic(api_key=ant_key) if ant_key else anthropic
    use_model = model if model and model in ALLOWED_MODELS else MODEL
    work = [{"role": m["role"], "content": m["content"]} for m in messages]
    async for chunk in _anthropic_loop(client, use_model, work):
        yield chunk


@app.get("/api/clusters")
async def list_clusters():
    """List all kubeconfig contexts and the currently active one."""
    from tools import get_k8s_contexts
    return await asyncio.to_thread(get_k8s_contexts)


@app.post("/api/clusters/switch")
async def switch_cluster(request: SwitchClusterRequest):
    """Switch the active kubeconfig context. Re-initialises the k8s client."""
    from tools import switch_k8s_context
    try:
        await asyncio.to_thread(switch_k8s_context, request.context)
        return {"ok": True, "context": request.context}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Provider registry — single source of truth ──────────────────────────────
# Each entry: (prefix, id, name, validate_url, auth)
#   auth="bearer"  → Authorization: Bearer <key>
#   auth="query"   → ?key=<key>  (Google AI)
#   auth="sdk"     → use Anthropic SDK (special case)
# Order matters: more-specific prefixes must come before their substrings.
PROVIDER_REGISTRY: list[dict] = [
    {"prefix": "sk-ant-", "id": "anthropic",  "name": "Anthropic",
     "validate_url": None,                                                          "auth": "sdk"},
    {"prefix": "sk-or-",  "id": "openrouter", "name": "OpenRouter",
     "validate_url": "https://openrouter.ai/api/v1/auth/key",                      "auth": "bearer"},
    {"prefix": "sk-",     "id": "openai",     "name": "OpenAI",
     "validate_url": "https://api.openai.com/v1/models",                           "auth": "bearer"},
    {"prefix": "AIza",    "id": "google",     "name": "Google AI",
     "validate_url": "https://generativelanguage.googleapis.com/v1beta/models",    "auth": "query"},
    {"prefix": "gsk_",    "id": "groq",       "name": "Groq",
     "validate_url": "https://api.groq.com/openai/v1/models",                      "auth": "bearer"},
]


def _detect_provider(key: str) -> Optional[dict]:
    for p in PROVIDER_REGISTRY:
        if key.startswith(p["prefix"]):
            return p
    return None


async def _http_validate(url: str, key: str, auth: str) -> tuple[bool, int, str]:
    """Generic HTTP validation — returns (ok, latency_ms, error_msg)."""
    try:
        import time
        t0 = time.monotonic()
        headers = {"Authorization": f"Bearer {key}"} if auth == "bearer" else {}
        params  = {"key": key}                        if auth == "query"  else {}
        async with httpx.AsyncClient(timeout=10) as hc:
            r = await hc.get(url, headers=headers, params=params)
        latency_ms = int((time.monotonic() - t0) * 1000)
        if r.status_code == 200:
            return True, latency_ms, ""
        if r.status_code == 401:
            return False, 0, "Invalid key — authentication failed"
        if r.status_code == 403:
            return False, 0, "Key valid but lacks permissions"
        return False, 0, f"API returned {r.status_code}"
    except Exception as e:
        return False, 0, f"Connection failed: {str(e)[:100]}"


@app.post("/api/validate-key")
async def validate_key(request: ValidateKeyRequest):
    """Detect provider from key prefix and validate against its API."""
    import time
    key = request.api_key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="api_key is required")
    use_model = request.model if request.model in ALLOWED_MODELS else MODEL

    provider = _detect_provider(key)

    # Custom endpoint — ping /models, fall back to format check
    if request.base_url:
        base = request.base_url.rstrip("/")
        ok_ping, lat, err = await _http_validate(f"{base}/models", key, "bearer")
        if ok_ping:
            return {"ok": True, "latency_ms": lat, "model": use_model, "provider": "custom"}
        if len(key) < 16:
            return {"ok": False, "error": "Key too short — check for typos", "provider": "custom"}
        return {"ok": True, "latency_ms": 0, "model": use_model, "provider": "custom",
                "note": "Endpoint unreachable — key saved, first chat will verify"}

    # Unknown provider — accept any key ≥ 16 chars; no live check possible
    if provider is None:
        if len(key) < 16:
            return {"ok": False, "error": "Key too short (< 16 chars)", "provider": "unknown"}
        return {"ok": True, "latency_ms": 0, "model": use_model, "provider": "unknown"}

    pid = provider["id"]

    # Anthropic: live SDK ping — we run Claude so this is a real auth check
    if provider["auth"] == "sdk":
        client = AsyncAnthropic(api_key=key)
        try:
            t0 = time.monotonic()
            await client.messages.create(
                model=use_model, max_tokens=5,
                messages=[{"role": "user", "content": "ping"}],
            )
            latency_ms = int((time.monotonic() - t0) * 1000)
            return {"ok": True, "latency_ms": latency_ms, "model": use_model, "provider": pid}
        except Exception as e:
            msg = str(e)
            if "401" in msg or "authentication" in msg.lower():
                return {"ok": False, "error": "Invalid key — authentication failed", "provider": pid}
            if "403" in msg:
                return {"ok": False, "error": "Key valid but lacks model access", "provider": pid}
            return {"ok": False, "error": f"Connection failed: {msg[:120]}", "provider": pid}

    # All other providers: live HTTP ping if the registry has a validate_url.
    validate_url = provider.get("validate_url")
    if validate_url:
        ok_ping, lat, err = await _http_validate(validate_url, key, provider["auth"])
        if not ok_ping:
            return {"ok": False, "error": err, "provider": pid}
        return {"ok": True, "latency_ms": lat, "model": use_model, "provider": pid}

    # No validation URL — format-only fallback
    if len(key) < 20:
        return {"ok": False, "error": "Key too short — check for typos", "provider": pid}
    return {"ok": True, "latency_ms": 0, "model": use_model, "provider": pid}


@app.post("/api/demo/security")
async def demo_security(request: DemoSecurityRequest):
    """Toggle the OPA policy gate on/off for live demo purposes."""
    global _security_on, _active_token
    import time as _t
    _security_on = request.security_on
    if _security_on:
        _active_token = {
            "id":         f"tok-{str(__import__('uuid').uuid4())[:8]}",
            "scope":      "production:read,production:restart",
            "issued_at":  _t.time(),
            "expires_at": _t.time() + 300,  # 5 minutes
            "ttl_s":      300,
        }
    else:
        _active_token = None
    return {"ok": True, "security_on": _security_on, "token": _active_token}


@app.get("/api/demo/security")
async def demo_security_state():
    import time as _t
    token = None
    if _active_token:
        remaining = max(0, int(_active_token["expires_at"] - _t.time()))
        token = {**_active_token, "remaining_s": remaining, "expired": remaining == 0}
    return {"security_on": _security_on, "token": token}


@app.post("/api/approval/{request_id}")
async def submit_approval(request_id: str, request: ApprovalRequest):
    """Human operator approves or denies a pending tool execution."""
    ev = _pending_approvals.get(request_id)
    if ev is None:
        raise HTTPException(status_code=404, detail="No pending approval with that id")
    _approval_decisions[request_id] = request.approved
    ev.set()
    return {"ok": True, "request_id": request_id, "approved": request.approved}


@app.get("/api/audit")
async def get_audit():
    """Return the in-memory audit log (most recent last)."""
    return {"entries": _audit_log[-50:], "total": len(_audit_log)}


@app.post("/api/chat")
async def chat(request: ChatRequest):
    async def generate():
        async for chunk in _chat_stream(request.messages, request.api_key, request.model, request.base_url):
            yield chunk

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/cluster")
async def cluster_health():
    """Lightweight cluster snapshot for the sidebar."""
    from tools import list_pods, get_alerts as _get_alerts
    try:
        pods_raw = await list_pods("production")
        alerts_raw = await _get_alerts()

        # Count pod phases from raw text
        lines = pods_raw.splitlines()
        running = sum(1 for l in lines if "Running" in l)
        crashing = sum(1 for l in lines if "CrashLoop" in l or "OOMKilled" in l or "Error" in l)
        pending = sum(1 for l in lines if "Pending" in l)
        total = running + crashing + pending

        alert_count = 0 if "No firing" in alerts_raw else len([l for l in alerts_raw.splitlines() if l and not l.startswith("─") and not l.startswith("ALERT")])

        from tools import _active_context, get_observability_urls
        obs = get_observability_urls()
        status = "critical" if crashing > 0 else ("degraded" if pending > 0 else "healthy")
        return {
            "status": status,
            "pods": {"running": running, "crashing": crashing, "pending": pending, "total": total},
            "alert_count": alert_count,
            "context": _active_context,
            "grafana_url": obs["grafana"],
        }
    except Exception as e:
        return {"status": "unknown", "pods": {}, "alert_count": 0, "error": str(e)}


@app.get("/api/alerts")
async def alerts_endpoint():
    """Return firing alerts for the sidebar alert feed."""
    from tools import get_observability_urls
    am_url = get_observability_urls()["alertmanager"]
    try:
        async with httpx.AsyncClient(timeout=5) as http:
            resp = await http.get(
                f"{am_url}/api/v2/alerts",
                params={"active": "true", "silenced": "false", "inhibited": "false"},
            )
            data = resp.json()
        return {"alerts": data[:10]}
    except Exception:
        return {"alerts": []}


RECORDINGS_DIR = Path(__file__).parent / "demo-recordings"


@app.get("/api/replay/{scenario}")
async def replay(scenario: str, speed: float = 1.0):
    """
    Stream a pre-recorded demo scenario as SSE events.
    scenario: filename without .jsonl (e.g. 'cascade', 'dangerous-agent')
    speed: playback multiplier — 1.0=real-time, 2.0=double speed, 0.5=half speed
    """
    recording = RECORDINGS_DIR / f"{scenario}.jsonl"
    if not recording.exists():
        available = [p.stem for p in RECORDINGS_DIR.glob("*.jsonl")]
        raise HTTPException(status_code=404, detail=f"No recording '{scenario}'. Available: {available}")

    speed = max(0.1, min(speed, 10.0))

    async def stream_recording():
        lines = recording.read_text().splitlines()
        last_delay = 0
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            delay_ms = entry.get("delay_ms", 0)
            wait_ms = (delay_ms - last_delay) / speed
            if wait_ms > 0:
                await asyncio.sleep(wait_ms / 1000)
            last_delay = delay_ms
            event = entry.get("event", {})
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        stream_recording(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/replay")
async def list_replays():
    """List available demo recordings."""
    recordings = []
    for p in sorted(RECORDINGS_DIR.glob("*.jsonl")):
        recordings.append({"name": p.stem, "size_bytes": p.stat().st_size})
    return {"recordings": recordings}


@app.get("/", response_class=HTMLResponse)
async def index():
    if FRONTEND.exists():
        return HTMLResponse(FRONTEND.read_text())
    return HTMLResponse("<h1>Frontend not found. Expected agent/frontend/index.html</h1>")


@app.get("/health")
async def health():
    return {"status": "ok", "model": MODEL}


@app.get("/api/status")
async def status():
    key_ok = bool(_api_key)
    return {"ready": key_ok, "model": MODEL, "key_set": key_ok, "allowed_models": sorted(ALLOWED_MODELS)}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8082))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False, log_level="info")
