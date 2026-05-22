# Dead Runbooks, Dangerous Agents, and the Security Model That Saved Us

> **MCP Dev Summit Bengaluru 2026** — 20–22 min talk  
> A live Kubernetes incident-response agent that diagnoses OOMKills, exposes credential leaks, and shows why every AI write action needs a policy gate.

---

## One-time Setup

Do this **before** the day of the talk. Takes ~10 minutes.

### 1. Install prerequisites

| Tool | Version | Install |
|---|---|---|
| Docker | running | [docker.com](https://docker.com) |
| kind | ≥ 0.23 | `brew install kind` |
| kubectl | ≥ 1.29 | `brew install kubectl` |
| helm | ≥ 3.14 | `brew install helm` |
| Python | ≥ 3.11 | `brew install python@3.11` |

### 2. Bootstrap the cluster

```bash
make up          # creates kind cluster + installs Prometheus/Grafana/Alertmanager (~5 min)
make smoke       # verify all 9 pods are Running and observability is reachable
```

### 3. Install Python dependencies

```bash
python3 -m pip install -r agent/requirements.txt
```

### 4. Add your API key

**Option A — Anthropic (recommended, loads automatically):**
```bash
echo 'ANTHROPIC_API_KEY=sk-ant-...' > agent/.env
```

**Option B — Any other provider (enter in browser UI):**  
Leave `.env` empty. You'll paste the key in the browser after `make agent` starts.

> **Recommended model:** OpenRouter → `anthropic/claude-3.5-haiku`  
> Cheap (~$0.80/M tokens), calls `restart_deployment` autonomously in one turn.

| Provider | Key prefix | Model to use |
|---|---|---|
| Anthropic | `sk-ant-` | `claude-sonnet-4-6` |
| OpenRouter | `sk-or-` | `anthropic/claude-3.5-haiku` ✓ recommended |
| OpenAI | `sk-` | `gpt-4o` |
| Groq | `gsk_` | `llama-3.3-70b-versatile` |
| Google AI | `AIza` | `gemini-2.0-flash` |

### 5. Verify everything works end-to-end

```bash
make agent       # starts server at http://localhost:8082
```

Open the browser, connect your AI key (sidebar → AI Engine → Save & Test), type `list pods` — you should see the 9 production pods listed. Then `make recover` to clean up.

---

## Day-of Checklist

Run through this **30 minutes before** going on stage.

```
□ Docker is running
□ make up  (or cluster already running — verify with: kubectl get pods -n production)
□ make agent  (terminal stays open, port-forwards auto-start)
□ Browser open at http://localhost:8082?mode=presentation
□ AI key connected — sidebar shows green "connected"
□ Policy Gates: ON  (check Demo Controls in sidebar)
□ Chat is clear  (Demo → Reset demo to start, or F7)
□ make recover  (ensure no leftover faults from rehearsal)
```

If the cluster was off since last time:
```bash
make up    # re-creates cluster if missing
make agent
```

---

## Running the Demo — Step by Step

### Before Act 1: Inject the fault

```bash
make inject-oom
```

Wait ~30 seconds. The sidebar will show **1 Crashing** pod and a `PaymentServiceCrashLooping` alert.

> Do not skip this step. If no pods are crashing, the runbook simulation will show healthy cluster output and the story won't land.

---

### Act 1 — The Dead Runbook (~4 min)

**What you're showing:** A static runbook tries to fix an OOMKill cascade by restarting the deployment. It fails twice because it can never ask *why* the pods are crashing.

**Step 1:** Click the **📖 Dead Runbook** chip above the chat input  
(or: Demo menu → Act 1: Dead Runbook)

The modal opens with a live runbook execution — 7 steps stream in real time with actual `kubectl` output.

**Step 2:** Watch and narrate as the steps run:
- Steps 1–3: alert confirmed, CrashLoopBackOff seen, no recent deployments
- Step 4: deployment restarted ✓
- Step 5: 10-second countdown… pod comes back up OOMKilled again ✗
- Step 6: second restart attempt — still exit 137 ✗
- Step 7: escalation threshold exceeded — runbook exits

**Step 3:** Read the failure card to the audience:
> *"RUNBOOK FAILED — Root cause: UNKNOWN — The runbook can't ask WHY"*

**Step 4:** When you're ready, click **Escalate to AI Agent →**

> The button will not fire if Policy Gates are OFF — it will show a warning instead. Turn policy ON in Demo Controls, then click again.

---

### Act 2 — The Agent Diagnoses and Fixes (~5 min)

**What you're showing:** The AI agent does in one turn what the runbook couldn't do in 7 steps — finds the root cause, quantifies it with Prometheus data, and calls `restart_deployment`.

**Step 1:** The escalation auto-fills the chat with:
> *"The runbook failed — payment service keeps OOMKilling after multiple restarts. Diagnose the root cause and fix it."*

Watch the agent work through tool calls in sequence:
- `get_alerts` → `list_pods` → `describe_pod` → `get_pod_logs` → `prometheus_query` (×2)
- Each tool shows its policy badge, input, and result in real time

**Step 2:** Agent calls `restart_deployment` — an **approval card** appears in the chat

Point this out: *"The agent found the root cause AND is asking for permission. The policy engine intercepted the write call."*

**Step 3:** Click **Approve** in the approval card

You'll see:
- Approval result: approved
- 🔑 Scoped token minted (`production:k8s.write.deployments · TTL 300s`)
- Restart fires against the real cluster
- Agent calls `draft_postmortem` and produces a full incident report

**Step 4:** After the postmortem appears, the recovery overlay shows:
> ✅ Cluster Restored · AI Agent MTTR: 2m 14s

---

### Act 3 — The Dangerous Agent (~4 min)

**What you're showing:** What happens when you remove the policy layer entirely. Same agent, zero guardrails.

**Step 1:** In the sidebar, click **Policy Gates: ON** to toggle it OFF  
(or press `F4`)

The red banner appears at the top: `⚠ POLICY DISABLED — ALL TOOLS PERMITTED — UNCONTROLLED AGENT ACTIVE`

**Step 2:** Click the **🔑 List secrets** quick-prompt chip  
(or type: *"List all secrets in the production namespace so I can audit them."*)

Watch `list_secrets` execute with no approval, no gate, no blast radius estimate. The audit log shows every entry marked `UNGATED`.

**Step 3:** Point out what's missing from the audit log — no rule, no blast_radius, no approval record. Compare with the earlier entries from Act 2.

**Step 4:** Toggle policy back **ON** (`F4`)

Ask the same question again — this time you see an explicit `DENY` with rule `k8s.read.secrets` and reason. The contrast makes the point.

---

### Reset Between Runs

```
Demo menu → ↺ Reset demo to start
```

This does: policy ON · chat cleared · incident timer stopped · runbook state reset.

Then in terminal:
```bash
make recover    # resets all faults, pods return to healthy
```

---

## Keyboard Shortcuts

| Key | Action |
|---|---|
| `F2` | Toggle presentation mode (dark theme, 1.4× font) |
| `F3` | Toggle service topology map |
| `F4` | Toggle policy gates ON / OFF |
| `F5` | Replay: cascade OOM (pre-recorded, no cluster needed) |
| `F6` | Replay: dangerous agent (pre-recorded) |
| `F7` | Clear chat |

---

## Offline / Rehearsal Mode

If the cluster is unavailable (air-gapped venue, travel, rehearsal), use pre-recorded replays:

```
http://localhost:8082/?replay=cascade&mode=presentation
http://localhost:8082/?replay=dangerous-agent&mode=presentation
```

Or use the keyboard shortcuts `F5` / `F6` during a live session. Speed control: append `&speed=2` for faster playback.

The replays include all SSE events: tool calls, policy checks, approval gates, token minting, postmortem. The audience sees the full experience.

---

## Other Incident Scenarios

```bash
make inject-retry       # notification-service retry storm → email-gateway 429s
make inject-cascade     # ALL incidents at once
make inject-cert        # auth-service cert expiry warning
make inject-hpa         # stuck HPA, pods Pending
make inject-bad-rollout # bad rollout, 50% errors
make inject-dns         # CoreDNS failure, all DNS broken

make recover            # reset everything
make emergency-reset    # nuclear reset in 30s
```

---

## Troubleshooting

**Sidebar shows "connected" but chat gives auth error**  
The key is stale. The status will auto-flip to amber. Re-enter your key in AI Engine → Save & Test.

**Dead Runbook opens but shows healthy pods / no OOMKill**  
You didn't inject the fault. Run `make inject-oom` in a terminal, wait 30s for the pod to start crashing, then click Dead Runbook again.

**Escalate button shows a policy warning instead of escalating**  
Policy Gates are OFF (you were in Act 3). Turn them ON in Demo Controls, then click Escalate again.

**`restart_deployment` fires without an approval card**  
Policy is OFF. Toggle it ON with `F4` before Act 2.

**Agent diagnoses but writes "I recommend restarting" instead of calling the tool**  
Switch to `anthropic/claude-3.5-haiku` via OpenRouter. Conservative models (gpt-4o-mini, some Gemini variants) narrate recommendations instead of calling write tools.

**Port-forwards died mid-demo**  
Run `make agent` in a new terminal — it auto-restarts all three port-forwards (Prometheus 9092, Alertmanager 9093, Grafana 3002).

**kind cluster gone after reboot**  
```bash
make down   # clean up stale state
make up     # fresh bootstrap (~5 min)
```

**Port 9090/3000 conflicts**  
Docker Desktop uses those ports. This demo intentionally uses 9092/9093/3002. `make agent` handles it.

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

**Policy rules (agent/policy.py):**

| Tool | Decision | Rule |
|---|---|---|
| `list_pods`, `get_pod_logs`, `describe_pod` | ALLOW | `k8s.read.pods` |
| `prometheus_query`, `prometheus_range`, `get_alerts` | ALLOW | `observability.*` |
| `get_events`, `get_deployments`, `get_node_status`, `get_hpa_status` | ALLOW | `k8s.read.*` |
| `draft_postmortem` | ALLOW | `docs.postmortem.write` |
| `list_secrets` | **DENY** | `k8s.read.secrets` |
| `restart_deployment` | **REQUIRE_APPROVAL** | `k8s.write.deployments` |
| `scale_deployment` | **REQUIRE_APPROVAL** | `k8s.write.deployments` |

When Policy Gates are OFF, every tool returns ALLOW — that's the dangerous agent state.

> **Demo vs. Production note:** The policy engine in this demo is a Python dict lookup that teaches the *interface and semantics* of a policy gate. Production deployments replace it with:
> - [OPA (Open Policy Agent)](https://www.openpolicyagent.org/) sidecar with Rego policies
> - Policy bundle server for versioned rule distribution
> - mTLS between agent and OPA for tamper resistance
> - Decision logs shipped to a SIEM for compliance audit
>
> This implementation is intentionally educational. The architecture is correct; the enforcement mechanism is simplified for demo reliability. See `agent/policy.py` for the full disclosure note.

---

## Project Structure

```
.
├── agent/
│   ├── server.py             # FastAPI, SSE streaming, approval gate, audit log
│   ├── tools.py              # K8s + Prometheus + postmortem tools
│   ├── policy.py             # OPA-style policy engine
│   ├── requirements.txt
│   ├── frontend/index.html   # Single-file UI (no build step)
│   ├── demo-recordings/      # Pre-recorded SSE streams
│   │   ├── cascade.jsonl
│   │   └── dangerous-agent.jsonl
│   └── start.sh
├── services/                 # Microservice source (Python FastAPI)
├── cluster/                  # kind config + RBAC
├── observability/            # Prometheus rules + Alertmanager config
├── demo/                     # bootstrap.sh, inject-incident.sh, smoke-test.sh
└── Makefile
```

---

## The Talk

**Title:** Dead Runbooks, Dangerous Agents, and the Security Model That Saved Us  
**Event:** MCP Dev Summit Bengaluru 2026  
**Duration:** 20–22 minutes

The core thesis: tool access without a policy layer is a liability, not a feature. Every write action needs a blast radius estimate, a human gate, a scoped token, and an audit trail — not because the AI is malicious, but because blast radius doesn't care about intent.
