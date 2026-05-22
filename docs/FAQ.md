# FAQ — Common Questions

> **Navigation:** [← README](../README.md) · [Setup](INSTALL.md) · [Runbook](RUNBOOK.md) · [Recovery](RECOVERY.md) · **FAQ**

---

# Questions from a first-time presenter or observer

---

## BEGINNER SECTION — If you only know Docker

### What is MCP?

MCP stands for Model Context Protocol. It is a standard way for AI models to call external
tools — things like "list pods", "query Prometheus", "restart a deployment". Instead of the
AI just generating text, it says: "I want to call this function with these arguments." The
host application runs the function and gives the result back to the model.

This demo uses Anthropic's Claude model calling tool functions defined in `agent/tools.py`.

### What is tool execution?

When an AI agent "calls a tool", it is asking the application to run a specific function.
For example:

```
AI: I want to call list_pods(namespace="production")
App: [runs the function, gets pod list from Kubernetes]
App: Here is the result: "payment-service Running, order-service Running..."
AI: I can see payment-service is crashing. I want to call describe_pod(...)
```

The AI does not run the function itself. The application does. This means the application
controls what the AI can and cannot do — which is exactly what this demo is about.

### Why security?

Without security, an AI agent with Kubernetes access can:
- Read all secrets (database passwords, API keys)
- Delete any deployment
- Scale any service to zero
- Read logs with sensitive data

The agent doesn't know it shouldn't do these things unless you tell it. A policy layer
is how you tell it.

### What happened in the demo?

1. **Act 1 (Dead Runbook):** A static runbook kept restarting a crashing service without
   understanding why. It failed because it couldn't diagnose — it could only act.

2. **Act 2 (AI Agent):** The AI agent called diagnostic tools, found the root cause
   (OOMKilled — ran out of memory), and asked a human to approve before restarting.
   The human approved. The restart worked. The incident was resolved in 2 minutes.

3. **Act 3 (Dangerous Agent):** The same agent, with security disabled, freely read all
   secrets when asked. No approval. No log entry. This is the "before" state.

4. **Contrast:** The same request with security enabled returned a DENY. That's the whole point.

### What was fixed?

The agent was given a policy layer with three outcomes for every tool call:
- **ALLOW:** Read operations (viewing pods, metrics, logs)
- **DENY:** Secrets access (never allowed, regardless of context)
- **REQUIRE_APPROVAL:** Write operations (restart, scale) — a human must approve

### Why trust restored?

The audit trail shows every decision: what was allowed, what was denied, who approved.
The token minted before each write has a scope and TTL. The postmortem was drafted automatically.
The agent's actions are visible, bounded, and accountable.

---

## TECHNICAL SECTION

### Is this real OPA (Open Policy Agent)?

No. The policy engine is a Python dict lookup in `agent/policy.py` that simulates OPA semantics.
It returns ALLOW, DENY, or REQUIRE_APPROVAL — the same outcomes a real OPA setup would produce.

A real production implementation would use OPA with Rego policy files, a policy sidecar,
mTLS between the agent and OPA, and policy decision logs shipped to a SIEM.

The demo's policy.py file has a 17-line disclosure header explaining this.

### Is this real MCP (the protocol)?

The demo uses FastAPI with Anthropic's function calling API directly — not the official
MCP SDK with `@mcp.tool` decorators and the MCP transport protocol.

The concepts demonstrated (tool calling, policy gates, approval flows, audit trails) apply
equally to the official MCP SDK. The architecture is what the talk teaches.

### Are the scoped tokens real Kubernetes tokens?

No. The token displayed (e.g., `tok-f1db6279 · TTL 300s`) is a UUID generated in server.py.
It is not a Kubernetes ServiceAccount token created via `v1/TokenRequest`.

The display teaches the concept correctly. Production path: Kubernetes TokenRequest API with
BoundObjectReference — a one-day engineering task.

### Does the audit log persist across restarts?

No. `_audit_log` in server.py is an in-memory Python list. It is cleared when the server
restarts. For the demo duration (one talk session), this is not a problem.

Production path: append-only file or SIEM sink.

### Why does smoke test fail after OOM injection?

`make smoke` checks whether payment-service has available replicas. After `make inject-oom`,
payment-service is intentionally crashing. The smoke test correctly reports this as a failure.
This is the expected state before Act 1. Run `make recover` to restore clean state.

### What Kubernetes version is this?

v1.33.1 running in kind (Kubernetes IN Docker). Kind version v0.29.0.

### What model does the agent use?

Default: `claude-3-5-haiku-latest`. Configurable in the browser UI sidebar under AI Engine.
The model is not hardcoded in server.py — it is set per-request based on sidebar selection.

### What if I don't have an Anthropic key?

Use the replay mode (F5 for cascade OOM, F6 for dangerous agent). The pre-recorded SSE streams
play back exactly as the live demo would appear. You can deliver the full talk on replay alone.

### How do I reset between rehearsal runs?

```bash
# In browser: Demo menu → ↺ Reset demo to start
make recover       # clean cluster state
make inject-oom    # re-inject fault for next run
```

### Can I run this on Linux?

Yes — the Makefile, scripts, and Python code are cross-platform. The only macOS-specific
commands are `lsof -ti :PORT` (used for port killing). On Linux, replace with
`fuser -k PORT/tcp` or `ss -tlnp | grep PORT`.

### What ports does the demo use?

| Port | Service |
|---|---|
| 8082 | Agent server (FastAPI/uvicorn) |
| 9092 | Prometheus (kubectl port-forward from :9090) |
| 9093 | Alertmanager (kubectl port-forward) |
| 3002 | Grafana (kubectl port-forward from :80) |

If any of these are in use by another process, `make agent` will kill whatever is on 8082.
For 9092/9093/3002, stop the conflicting process or change the port in start.sh.

---

## STAGE SECTION

### What if the agent doesn't call restart_deployment?

This happens with conservative models that prefer to narrate rather than act. Switch to
`claude-3-5-haiku-latest` in the AI Engine sidebar. If it still happens, press F5 for replay.

### What if the approval countdown reaches zero?

The action is cancelled automatically. A message appears: `⏱ Approval timed out after 600s`.
Say: *"The agent waited 10 minutes and cancelled safely. That's the fail-safe."* Then reset
and re-run from inject-oom.

### What if someone in the audience asks "is this real OPA?"

Yes — answer honestly. Say: *"This is a Python dict lookup that demonstrates the OPA interface.
A production implementation would use OPA with Rego files versioned in git. The architecture
is identical — we're showing the interface, not the enforcement binary."*

The policy.py disclosure header and README both document this explicitly.

### Can the dangerous agent actually delete data?

No. `list_secrets` (the tool shown) reads secret metadata only — names, types, and key counts.
It does not return actual secret values. This is by design and is tested (test_u19).

The demo's point is that the agent knows which secrets exist and can read their structure.
In a production cluster with full permissions, the agent could read the actual values too.
The demo teaches the concept without showing real credentials.

### What is the MTTR shown at the end?

The `AI Agent MTTR: 2m 14s` in the recovery overlay is calculated from the time the chat
started to the time the cluster recovered. It is measured from real execution timing in the
cascade replay. The live demo timing may vary slightly based on LLM response speed.

---

> **Navigation:** [← Recovery](RECOVERY.md) · **FAQ** · [← README](../README.md)
