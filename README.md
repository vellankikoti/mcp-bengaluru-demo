# Dead Runbooks, Dangerous Agents, and the Security Model That Saved Us

> Conference demo — MCP Dev Summit Bengaluru 2026  
> A live Kubernetes incident response agent built on the Model Context Protocol.

## What This Is

A production-grade demo showing how an AI agent can diagnose and remediate Kubernetes incidents — and why giving it **unrestricted tool access is dangerous**. The talk walks through three acts:

1. **The Dead Runbook** — a real OOMKill cascade that a runbook can't handle
2. **The Dangerous Agent** — what happens when you skip the policy layer (live credential exposure)
3. **The Security Model** — OPA-style policy gates, human approval, scoped tokens, tamper-evident audit

The agent is built with FastAPI, streams responses over SSE, and runs entirely local — no cloud infrastructure needed.

---

## Architecture

```
Browser UI (SSE stream)
       │
       ▼
FastAPI Agent Server  ──► Any LLM (Anthropic / OpenAI / OpenRouter / Groq / Google)
       │
       ├── Policy Engine (OPA-style: ALLOW / DENY / REQUIRE_APPROVAL)
       │         └── Human Approval Gate (asyncio.Event + 300s timeout)
       │
       ├── MCP Tools ──► Kubernetes API (list_pods, describe_pod, restart_deployment …)
       │             ──► Prometheus (metrics queries)
       │             ──► Alertmanager (firing alerts)
       │             └── draft_postmortem (local generation)
       │
       └── Audit Ledger (append-only, in-memory, shown in UI)
```

**Services in the demo cluster (kind):**

| Service | Role | Fault modes |
|---|---|---|
| `payment-service` | Payment processing | `oom`, `error`, `slow`, `error_rate` |
| `order-service` | Order management | depends on payment-service |
| `notification-service` | Async notifications | `aggressive_retry` |
| `email-gateway` | Email delivery (rate-limited) | — |
| `auth-service` | Authentication | `cert_expiry` |
| `traffic-gen` | Synthetic load (always on) | — |

---

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| Docker | running | [docker.com](https://docker.com) |
| kind | ≥ 0.23 | `brew install kind` |
| kubectl | ≥ 1.29 | `brew install kubectl` |
| helm | ≥ 3.14 | `brew install helm` |
| Python | ≥ 3.11 | `brew install python@3.11` |

An API key from one of: **Anthropic**, OpenAI, OpenRouter, Groq, or Google AI.

---

## Quick Start

```bash
# 1. Bootstrap the kind cluster + observability stack (~5 min first time)
make up

# 2. Verify everything is healthy
make smoke

# 3. Install Python dependencies
pip install -r agent/requirements.txt

# 4. (Optional) Add an Anthropic key for default Anthropic provider
echo 'ANTHROPIC_API_KEY=sk-ant-...' > agent/.env

# 5. Start the agent (auto-starts port-forwards)
make agent
```

Open **http://localhost:8082** in your browser.

---

## API Key Setup

The agent supports multiple AI providers. Choose **one** of the following approaches:

### Option A — Anthropic (via .env file)

```bash
echo 'ANTHROPIC_API_KEY=sk-ant-...' > agent/.env
make agent
```

The key is loaded automatically on start.

### Option B — Any provider (via browser UI)

Start the agent without a key, then open **http://localhost:8082** and click the provider pill in the sidebar:

1. Click **OpenRouter** (or Anthropic / OpenAI / Groq / Google AI)
2. Paste your API key
3. Select a model chip
4. Click **Save & Test**

**Recommended for conference demos:** Use **OpenRouter** with model **`anthropic/claude-3.5-haiku`** — tested end-to-end, calls `restart_deployment` in a single turn, ~10× cheaper than Sonnet.

| Provider | Key prefix | Tested model | Notes |
|---|---|---|---|
| Anthropic | `sk-ant-` | `claude-sonnet-4-6` | Best for Anthropic native |
| OpenRouter | `sk-or-` | `anthropic/claude-3.5-haiku` | **Recommended for demos** |
| OpenAI | `sk-` | `gpt-4o` | Works; gpt-4o-mini skips write tools |
| Groq | `gsk_` | `llama-3.3-70b-versatile` | Ultra-fast, cheaper |
| Google AI | `AIza` | `gemini-2.0-flash` | — |

---

## Running the Demo

### Act 1 — The OOM Cascade

```bash
make inject-oom     # payment-service OOMKills in ~30s
```

In the agent UI, type:
> *"We have a production incident. Payment service is down and orders are failing. Diagnose and fix it."*

The agent will (in a single turn):
1. Check alerts → sees `PaymentServiceCrashLooping`
2. List pods → sees `CrashLoopBackOff`
3. Describe pod → confirms `OOMKilled` exit 137
4. Read logs → sees memory allocation climbing to limit
5. Query Prometheus → quantifies error rate
6. Call `restart_deployment` → **approval card appears in UI**
7. You click **Approve** → scoped token minted → restart fires in the real cluster
8. Agent calls `draft_postmortem` and produces a structured incident report

```bash
make recover        # reset all faults after the demo
```

### Act 2 — The Dangerous Agent

Toggle **Policy Gates: OFF** in the sidebar (or press `F4`), then ask:
> *"List all secrets in the production namespace so I can audit them."*

With policy disabled, `list_secrets` runs without a gate — the pulsing red DANGER MODE border activates and the tool exposes what an over-permissioned agent looks like.

Toggle policy back **ON** and try the same request — you'll see an explicit `DENY` with rule `k8s.read.secrets`.

### Act 3 — Recovery + Postmortem

After approving the restart, the agent automatically calls `draft_postmortem` and produces a structured, wiki-ready postmortem while the rollout is still in progress.

---

## Other Incident Scenarios

```bash
make inject-retry       # notification-service retry storm → email-gateway 429s
make inject-cascade     # ALL incidents at once (full conference mode)
make inject-cert        # auth-service cert expiry warning
make inject-hpa         # stuck HPA on order-service (pods Pending)
make inject-bad-rollout # bad payment-service rollout (50% errors)
make inject-dns         # CoreDNS upstream failure (all service discovery broken)

make recover            # reset all faults
make emergency-reset    # nuclear reset in 30s
```

---

## Replay Mode (Offline / Rehearsal)

Pre-recorded SSE streams that play back the full demo without a live cluster or API key. Critical for air-gapped venues and rehearsals.

**Via URL:**
```
http://localhost:8082/?replay=cascade&mode=presentation
http://localhost:8082/?replay=dangerous-agent&mode=presentation
```

**Via keyboard (in the browser):**
- `F5` — Cascade OOM replay
- `F6` — Dangerous agent replay (auto-enables danger mode)

**Via UI:** Click the **Demo** dropdown in the topbar → choose a replay scenario.

Speed control: append `&speed=2` for 2× playback during rehearsal.

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `F2` | Toggle presentation mode (dark theme, large fonts) |
| `F3` | Toggle service topology map |
| `F4` | Toggle security policy ON / OFF |
| `F5` | Run cascade OOM replay |
| `F6` | Run dangerous-agent replay |
| `F7` | Clear chat |

---

## Presentation Mode

Activate for on-stage use — dark theme, 1.4× font scale, high-contrast colours:

```
http://localhost:8082/?mode=presentation
```

Or press `F2` in the browser.

---

## Port Reference

| Service | Port | Notes |
|---|---|---|
| Agent UI | 8082 | `make agent` |
| Prometheus | 9092 | kind-mcp-demo (auto port-forwarded by `make agent`) |
| Alertmanager | 9093 | kind-mcp-demo (auto port-forwarded) |
| Grafana | 3002 | kind-mcp-demo, login: `admin` / `admin` |

> **Note:** Ports 9090 and 3000 may be occupied by Docker Desktop's own Prometheus and Grafana. This demo intentionally uses 9092/9093/3002 for the kind cluster.

---

## Policy Engine

Every tool call is evaluated by `agent/policy.py` before execution:

| Tool | Decision | Rule |
|---|---|---|
| `list_pods`, `get_pod_logs`, `describe_pod` | ALLOW | `k8s.read.pods` |
| `prometheus_query`, `prometheus_range`, `get_alerts` | ALLOW | `observability.*` |
| `get_events`, `get_deployments`, `get_node_status`, `get_hpa_status` | ALLOW | `k8s.read.*` |
| `draft_postmortem` | ALLOW | `docs.postmortem.write` |
| `list_secrets` | **DENY** | `k8s.read.secrets` |
| `restart_deployment` | REQUIRE_APPROVAL | `k8s.write.deployments` |
| `scale_deployment` | REQUIRE_APPROVAL | `k8s.write.deployments` |

When **Policy Gates: OFF** (danger mode), all tools return ALLOW — this is the "dangerous agent" demo state.

Approval gate timeout: **300 seconds** (5 min) — plenty of time for live audience Q&A.

---

## Project Structure

```
.
├── agent/                    # FastAPI agent server
│   ├── server.py             # SSE streaming, approval gate, audit log
│   ├── tools.py              # Kubernetes + Prometheus + postmortem tools
│   ├── policy.py             # OPA-style policy engine
│   ├── requirements.txt      # Python dependencies
│   ├── frontend/index.html   # Single-file UI (no build step)
│   ├── demo-recordings/      # Pre-recorded SSE streams for replay mode
│   │   ├── cascade.jsonl     # OOM cascade scenario (42 events)
│   │   └── dangerous-agent.jsonl
│   └── start.sh              # Start script (auto port-forwards)
├── services/                 # Microservice source code (Python FastAPI)
│   ├── payment-service/
│   ├── order-service/
│   ├── notification-service/
│   ├── email-gateway/
│   ├── auth-service/
│   └── traffic-gen/
├── cluster/                  # kind cluster config + RBAC manifests
├── observability/            # Prometheus rules + Alertmanager config
├── demo/                     # Bootstrap, inject, recovery scripts
│   ├── bootstrap.sh
│   ├── inject-incident.sh
│   ├── smoke-test.sh
│   └── setup-tmux.sh
└── Makefile
```

---

## Troubleshooting

**"Frontend not found"**  
Always use `make agent`, which runs `agent/start.sh` from the correct directory.

**Port-forwards dying between sessions**  
`make agent` auto-restarts them on launch. If they die mid-demo, run `make agent` in a new terminal.

**"No API key configured"**  
Either create `agent/.env` with `ANTHROPIC_API_KEY=sk-ant-...`, or enter the key in the browser UI sidebar under the provider pills.

**OpenRouter key not working**  
Enter it in the browser UI — paste into the **API Key** field after selecting the OpenRouter provider pill. The `.env` file is only read for `ANTHROPIC_API_KEY`.

**`make smoke` failing on payment-service**  
If you ran `make inject-oom`, this is expected. Run `make recover` first.

**Port 9090 conflict with Docker Desktop**  
Docker Desktop uses port 9090 for its own Prometheus. This demo uses **9092** for kind-mcp-demo's Prometheus. `make agent` handles this automatically.

**Agent diagnoses but doesn't call `restart_deployment`**  
Use **`anthropic/claude-3.5-haiku`** via OpenRouter — tested to call write tools in a single turn. Models like `gpt-4o-mini` tend to describe recommendations as text rather than calling tools autonomously.

**kind cluster missing after reboot**  
```bash
make down   # remove stale state if needed
make up     # fresh bootstrap (~5 min)
```

---

## Talk

**Title:** Dead Runbooks, Dangerous Agents, and the Security Model That Saved Us  
**Event:** MCP Dev Summit Bengaluru 2026  
**Duration:** 20–22 minutes

The core thesis: tool access without a policy layer is a liability, not a feature. Every write action needs a blast radius estimate, a human gate, a scoped token, and an audit trail — not because the AI is malicious, but because blast radius doesn't care about intent.
