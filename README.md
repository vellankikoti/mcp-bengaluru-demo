# Dead Runbooks, Dangerous Agents, and the Security Model That Saved Us

> Conference demo — MCP Dev Summit Bengaluru 2026  
> A live Kubernetes incident response agent built on the Model Context Protocol.

## What This Is

A production-grade demo showing how an AI agent can diagnose and remediate Kubernetes incidents — and why giving it **unrestricted tool access is dangerous**. The talk walks through three acts:

1. **The Dead Runbook** — a real OOMKill cascade that a runbook can't handle
2. **The Dangerous Agent** — what happens when you skip the policy layer (live credential exposure)
3. **The Security Model** — OPA-style policy gates, human approval, scoped tokens, tamper-evident audit

The agent is built with [FastMCP](https://github.com/jlowin/fastmcp), streams responses over SSE, and runs entirely local — no cloud infrastructure needed.

---

## Architecture

```
Browser UI (SSE stream)
       │
       ▼
FastAPI Agent Server  ──► Claude / OpenAI / OpenRouter
       │
       ├── Policy Engine (OPA-style: ALLOW / DENY / REQUIRE_APPROVAL)
       │         └── Human Approval Gate (asyncio.Event + 60s timeout)
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
| gh | ≥ 2.40 | `brew install gh` (for GitHub push only) |

An API key from one of: **Anthropic**, OpenAI, OpenRouter, Groq, or Google AI.

---

## Quick Start

```bash
# 1. Bootstrap the kind cluster + observability stack (~5 min first time)
make up

# 2. Verify everything is healthy
make smoke

# 3. Add your API key
echo 'ANTHROPIC_API_KEY=sk-ant-...' > agent/.env

# 4. Start the agent (auto-starts port-forwards)
make agent
```

Open **http://localhost:8082** — click **Connect AI**, paste your key, save.

---

## API Key Setup

The agent supports multiple AI providers. Choose one:

```bash
# Anthropic (recommended — best tool use)
echo 'ANTHROPIC_API_KEY=sk-ant-...' > agent/.env

# OpenAI
echo 'OPENAI_API_KEY=sk-...' > agent/.env

# OpenRouter (access to many models)
echo 'OPENAI_API_KEY=sk-or-...' > agent/.env
```

Or enter the key directly in the browser UI under **Connect AI (⚙)**.

---

## Running the Demo

### Act 1 — The OOM Cascade

```bash
make inject-oom     # payment-service OOMKills in ~30s
```

In the agent UI, type:
> *"We have a production incident. Payment service is down and orders are failing. Diagnose and fix it."*

The agent will:
1. Check alerts → sees `PaymentServiceCrashLooping`
2. List pods → sees `CrashLoopBackOff`
3. Describe pod → confirms `OOMKilled` exit 137
4. Read logs → sees memory allocation climbing to limit
5. Query Prometheus → quantifies error rate
6. Propose `restart_deployment` → **approval card appears**
7. You click **Approve** → scoped token minted → restart fires in the real cluster
8. Draft postmortem automatically while the rollout is in progress

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

**Via UI:** Click the **▶ Replay** button in the topbar.

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
| `draft_postmortem` | ALLOW | `docs.postmortem.write` |
| `list_secrets` | **DENY** | `k8s.read.secrets` |
| `restart_deployment` | REQUIRE_APPROVAL | `k8s.write.deployments` |
| `scale_deployment` | REQUIRE_APPROVAL | `k8s.write.deployments` |

When `security_on = False` (danger mode), all tools return ALLOW — this is the "dangerous agent" demo state.

---

## Project Structure

```
.
├── agent/                    # FastAPI agent server
│   ├── server.py             # SSE streaming, approval gate, audit log
│   ├── tools.py              # Kubernetes + Prometheus + postmortem tools
│   ├── policy.py             # OPA-style policy engine
│   ├── frontend/index.html   # Single-file UI (2900 lines, no build step)
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
├── 00-mcp-k8s-utility/       # Companion MCP server: utility tools
├── 01-mcp-k8s-secure-ops/    # Companion MCP server: secure operations
├── 02-mcp-observatory/       # Companion MCP server: observability
├── 03-mcp-deploy-intel/      # Companion MCP server: deployment intelligence
├── 04-mcp-prod-readiness/    # Companion MCP server: production readiness
└── Makefile
```

---

## Troubleshooting

**"Frontend not found"**  
The server was started from the wrong directory. Always use `make agent`, which runs `agent/start.sh` and sets the correct working directory.

**Port-forwards dying between sessions**  
`make agent` auto-restarts them on launch. If they die mid-demo, run `make agent` in a new terminal.

**"No API key configured"**  
Create `agent/.env` with `ANTHROPIC_API_KEY=sk-ant-...`, or enter the key in the browser UI under **Connect AI**.

**`make smoke` failing on payment-service**  
If you ran `make inject-oom`, this is expected — the service is intentionally crashing. Run `make recover` first.

**Port 9090 conflict with Docker Desktop**  
Docker Desktop uses port 9090 for its own Prometheus. This demo uses **9092** for kind-mcp-demo's Prometheus. `make agent` handles this automatically.

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
