# Dead Runbooks, Dangerous Agents, and the Security Model That Saved Us

> A live Kubernetes incident-response agent that diagnoses OOMKills, requires human approval
> before write actions, and shows what happens when you remove all the guardrails.
> Built for MCP Dev Summit Bengaluru 2026.

---

## Documentation

| | |
|---|---|
| 🚀 **[Setup Guide](docs/INSTALL.md)** | Install on any cluster — kind, KillerCoda, GKE, EKS |
| 📋 **[Day-of Runbook](docs/RUNBOOK.md)** | Speaker delivery script with timing and fallbacks |
| 🔧 **[Recovery Guide](docs/RECOVERY.md)** | Something broke? Every failure mode with fix commands |
| ❓ **[FAQ](docs/FAQ.md)** | Common questions — setup, security, architecture |
| 🎬 **[20 Scenarios](docs/SCENARIOS.md)** | All demo scenarios with expected outputs |

---

## Quick Start

**Prerequisites:** a running Kubernetes cluster + an AI provider key (or Ollama).

```bash
# 1. Clone
git clone https://github.com/vellankikoti/mcp-bengaluru-demo.git
cd mcp-bengaluru-demo

# 2. Python env
python3 -m venv venv && source venv/bin/activate
pip install -r agent/requirements.txt

# 3. Bootstrap (uses your existing cluster, or creates a kind cluster)
make up

# 4. Verify
make smoke           # expect: ✅ All 20 checks passed

# 5. Set your AI provider (pick one — or configure in browser UI)
echo 'ANTHROPIC_API_KEY=sk-ant-...' > agent/.env   # Anthropic
echo 'OPENAI_API_KEY=sk-...' > agent/.env           # OpenAI
echo 'AI_BASE_URL=http://localhost:11434/v1' > agent/.env  # Ollama

# 6. Start the agent
make agent           # opens http://localhost:8082
```

> **New to this?** Follow the full step-by-step guide: [docs/INSTALL.md](docs/INSTALL.md)

---

## AI Providers

Works with any provider — no vendor lock-in.

| Provider | Key prefix | Good model |
|---|---|---|
| Anthropic | `sk-ant-` | `claude-3-5-haiku-latest` |
| OpenRouter | `sk-or-` | `anthropic/claude-3.5-haiku` |
| OpenAI | `sk-` | `gpt-4o-mini` |
| Groq | `gsk_` | `llama-3.3-70b-versatile` |
| Google AI | `AIza` | `gemini-2.0-flash` |
| **Ollama** | *(none)* | `llama3.2`, `qwen2.5`, etc. |

Configure via `agent/.env` or in the browser sidebar (AI Engine → pick provider → Save & Test).

---

## Running the Demo

### Before you start: inject the fault

```bash
make inject-oom      # payment-service OOMKills in ~30s
```

### Act 1 — The Dead Runbook (~4 min)

Click **📖 Dead Runbook** chip in the UI. A 7-step runbook runs live against the cluster —
restarts fail twice because it can't ask *why*. Click **Escalate to AI Agent** when it fails.

### Act 2 — The Agent Diagnoses and Fixes (~5 min)

The agent calls 6–7 tools in sequence (`get_alerts → list_pods → describe_pod →
get_pod_logs → prometheus_query × 2 → restart_deployment`). When it reaches
`restart_deployment`, an **approval card** appears — blast radius shown, human must click
**Approve**. Scoped token mints, restart fires, postmortem generated.

> **Key moment:** policy intercepted the write. Agent asked. You approved. That's the point.

### Act 3 — The Dangerous Agent (~4 min)

Press `F4` to toggle Policy Gates **OFF**. Red banner appears. Click **List secrets** — no gate,
no approval, no blast radius. Audit log shows entries marked `UNGATED`. Toggle back **ON**,
ask again — explicit `DENY`. Same agent, completely different outcome.

### Reset between runs

```bash
make recover         # reset cluster faults
# In browser: Demo menu → ↺ Reset demo to start
```

---

## Day-of Checklist

Run **30 minutes before** going on stage:

```bash
bash demo/preflight.sh   # 44 checks — must exit 0
make inject-oom          # 60s before Act 1
```

Then in browser:
- `http://localhost:8082?mode=presentation`
- Sidebar: AI Engine → key connected (green dot)
- Sidebar: Policy Gates → ON
- Demo menu → Reset demo to start

Full delivery script with speaker lines and timing: **[docs/RUNBOOK.md](docs/RUNBOOK.md)**

---

## Keyboard Shortcuts

| Key | Action |
|---|---|
| `F4` | Toggle Policy Gates ON / OFF |
| `F5` | Replay: cascade OOM (pre-recorded, works offline) |
| `F6` | Replay: dangerous agent (pre-recorded) |
| `F7` | Clear chat |
| `F2` | Presentation mode (dark, 1.4× font) |

**Offline / no cluster:** `F5` / `F6` replays include all tool calls, policy checks, approval
gates. Full demo works with no live cluster.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Pods crashing but no OOM injected | `make recover` |
| Port-forwards dead | `make agent` (restarts them) |
| Approval card missing | Policy is OFF — press `F4` |
| Agent narrates instead of calling tools | Switch to `claude-3.5-haiku` or use `F5` replay |
| `ImagePullBackOff` on pods | Docker not available; see [docs/INSTALL.md](docs/INSTALL.md) |
| Any critical preflight failure | Command printed next to failure — run it |

Full recovery guide: **[docs/RECOVERY.md](docs/RECOVERY.md)**

---

## Architecture

```
Browser UI  ──SSE──►  FastAPI Agent Server  ──►  Any LLM (Anthropic / OpenAI / Ollama / …)
                              │
                    Policy Engine (ALLOW / DENY / REQUIRE_APPROVAL)
                              │
                    ┌─────────┴──────────┐
                    │                    │
               K8s Tools           Observability
             (kubectl API)    (Prometheus / Alertmanager)
                    │
               Audit Ledger (in-memory, shown in UI)
```

**Policy decisions (all 14 tools):**

| Decision | Tools |
|---|---|
| **ALLOW** | `list_pods`, `describe_pod`, `get_pod_logs`, `get_deployments`, `get_events`, `get_node_status`, `get_hpa_status`, `prometheus_query`, `prometheus_range`, `get_alerts`, `draft_postmortem` |
| **REQUIRE_APPROVAL** | `restart_deployment`, `scale_deployment` |
| **DENY** | `list_secrets` |

When Policy Gates are OFF, every tool returns ALLOW — that's the dangerous agent.

> **Production path:** this demo uses a Python dict for policy. In production: OPA sidecar + Rego
> policies + mTLS. See `agent/policy.py` for the full disclosure.

---

## Project Layout

```
├── agent/
│   ├── server.py          # FastAPI, SSE, approval gate, audit log
│   ├── tools.py           # K8s + Prometheus + postmortem tools
│   ├── policy.py          # Policy engine (ALLOW/DENY/REQUIRE_APPROVAL)
│   ├── frontend/          # Single-file UI (no build step)
│   └── demo-recordings/   # Offline replay JSONLs
├── services/              # 6 demo microservices (Python)
├── cluster/               # RBAC manifests
├── observability/         # Prometheus rules, Grafana dashboards
├── demo/                  # bootstrap.sh, inject-incident.sh, smoke-test.sh
├── docs/                  # Full documentation
│   ├── INSTALL.md         # ← Start here for detailed setup
│   ├── RUNBOOK.md         # Day-of delivery script
│   ├── RECOVERY.md        # 14 failure modes
│   └── FAQ.md             # 25+ questions answered
└── Makefile
```
