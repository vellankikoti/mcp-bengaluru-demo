# RUNBOOK.md
# Conference Delivery Guide — Certified Version
# Dead Runbooks, Dangerous Agents, and the Security Model That Saved Us
# MCP Dev Summit Bengaluru 2026 | Target: 20 min | Hard max: 22 min

Every speaker line, timing, and keyboard shortcut verified during certification run 2026-05-23.

---

## TIMING OVERVIEW

| Section | Target | Max | Cumulative |
|---|---|---|---|
| Intro + framing | 3 min | 3 min | 3 min |
| Act 1: Dead Runbook | 4 min | 5 min | 8 min |
| Act 2: Agent diagnosis + approval | 5 min | 6 min | 14 min |
| Act 3: Dangerous agent | 3 min | 4 min | 17 min |
| Closing + principles | 3 min | 4 min | 20 min |
| Q&A buffer | 2 min | — | 22 min |

---

## T-60 MINUTES — SETUP

**Terminal 1 (keep open on stage):**
```bash
make agent
```

**Expected output:**
```
[agent] Starting MCP Incident Agent on http://localhost:8082
[agent] Prometheus   → http://localhost:9092
[agent] Alertmanager → http://localhost:9093
[agent] Grafana      → http://localhost:3002
INFO: Uvicorn running on http://0.0.0.0:8082
```

**Verify:**
```bash
curl -s http://localhost:8082/health
```
**Expected:** `{"status": "ok", "model": "claude-3-5-haiku-latest"}`

**Preflight:**
```bash
bash demo/preflight.sh
```
**Must exit 0 and print:** `CLEARED TO PRESENT`

**Browser:** Open `http://localhost:8082?mode=presentation`

**In browser sidebar — verify before stage:**
- Demo Controls → Policy Gates: **ON** (green)
- AI Engine: paste key → Save & Test → **green "connected"**
- Demo menu → **Reset demo to start**

---

## T-60 SECONDS — INJECT FAULT

**Terminal 2:**
```bash
make inject-oom
```

**Expected output:**
```
[INCIDENT] Injecting: CrashLoopBackOff OOM on payment-service
deployment.apps/payment-service env updated
deployment.apps/payment-service resource requirements updated
[INCIDENT] payment-service will OOMKill in ~30s.
```

**Wait for red badge in browser sidebar:** `1 Crashing`

**Do not click Dead Runbook until the red badge appears.**

**Verify badge appeared:**
```bash
KUBECONFIG=~/.kube/mcp-demo.yaml kubectl --context=kind-mcp-demo -n production get pods --no-headers | grep payment
```
**Expected:** `payment-service-XXX   0/1   CrashLoopBackOff   1   60s`

---

## INTRO (3 min)

**TITLE:** Dead Runbooks, Dangerous Agents, and the Security Model That Saved Us

**PURPOSE:** Show what happens when you give an AI agent Kubernetes access without a security layer — then show the three-part fix: policy gate, human approval, audit trail.

**SPEAKER OPENING:**
> "Three months ago, our payment service started crashing at 3 AM. On-call engineer had one option: the runbook. The runbook had one option: restart. So it restarted. And restarted. And restarted. I'm going to show you exactly what that looks like — and then I'm going to show you what AI agents look like when you give them the same set of tools, zero security constraints, and a production cluster."

---

## ACT 1 — DEAD RUNBOOK (4 min)

### Step 1: Launch

**PURPOSE:** Show that static runbooks can't diagnose — they can only execute.

**SCREEN SHOULD SHOW:** Red badge `1 Crashing` in sidebar. `PaymentServiceCrashLooping` in alert feed.

**COMMAND:** Click **📖 Dead Runbook** chip (or Demo menu → Act 1)

**EXPECTED RESULT:** Runbook steps begin streaming:
- Step 1: `Getting firing alerts... PaymentServiceCrashLooping`
- Step 2: `Checking pod status... payment-service CRASH (Exit 137)`
- Step 3: `Checking recent deployments... none in last 2h`
- Step 4: `Restarting payment-service...` → 10-second countdown

**SPEAKER LINE (during countdown):**
> "The runbook does what runbooks do. It restarts."
> *(say nothing during the 10-second countdown — let the silence teach)*

**EXPECTED RESULT:** Restart fires. Then: `Exit code 137. OOMKilled. Same reason.`

**SPEAKER LINE:**
> "Exit code 137. Out of memory. Every time. Because the runbook can't ask WHY — it can only do WHAT it was written to do."

- Step 6: Second restart attempt
- Step 7: `Escalate to on-call`

**SPEAKER LINE (reading failure card):**
> "Root cause: UNKNOWN. The runbook escalated. That's the best it could do."

**PAUSE 3 seconds.**

> "This isn't a design flaw. This is the fundamental limit of static automation. The runbook has no memory, no model, no context. It has a script."

**COMMAND:** Click **Escalate to AI Agent →**

**VERIFY:** Chat interface opens with pre-filled message: `PaymentServiceCrashLooping — OOMKilled...`

---

**FALLBACK (if OOM crash not visible in sidebar):**

```
Press F5 — replay mode starts automatically
```

Say: *"I'm using a pre-recorded run so the timing is reliable on stage. Every tool call you see happened against a real cluster."*

---

## ACT 2 — AI AGENT DIAGNOSES (5 min)

### Step 2a: Watch tool calls stream

**PURPOSE:** Show the agent's structured reasoning — not just "AI did it" but each tool call, policy check, and result.

**SCREEN SHOULD SHOW:** Chat streaming tool calls with green `ALLOW` badges.

**Do not type anything — the escalation auto-fills the message.**

**EXPECTED tool calls in order (from actual execution):**

| Tool | Badge | What it means |
|---|---|---|
| `get_alerts` | ✓ ALLOW | "Reads are permitted. No approval needed." |
| `list_pods` | ✓ ALLOW | "It sees the crashing pod." |
| `describe_pod` | ✓ ALLOW | "Exit code 137. Memory limit 50Mi." |
| `get_pod_logs` | ✓ ALLOW | "It's reading the crash logs." |
| `prometheus_query` | ✓ ALLOW | "Real Prometheus data — not guessing." |
| `prometheus_query` | ✓ ALLOW | "Quantifying memory trend." |

**SPEAKER LINES (while tools stream):**
- On `get_alerts`: *"ALLOW. Reads are permitted."*
- On `describe_pod`: *"Exit code 137. Memory limit 50 megabytes. The agent already knows more than the runbook did."*
- On `prometheus_query`: *"Now it's querying real Prometheus data. Not guessing — measuring."*

### Step 2b: The approval gate

**When `restart_deployment` appears:**

**STOP TALKING. Wait 3 seconds.**

**SCREEN SHOULD SHOW:**
```
⚠ APPROVAL REQUIRED
Tool: restart_deployment
Blast radius: Rolling restart terminates all running pods. Expect brief traffic disruption during rollout.
Countdown: 10:00 remaining
[ ✓ Approve ]  [ ✗ Deny ]
```

**SPEAKER LINE:**
> "There it is. The agent diagnosed the root cause AND stopped itself. It's asking for permission."

Point to blast radius:
> "Blast radius: rolling restart, brief disruption. The agent computed this before asking. It knows what it's about to do."

> "In a production system, this is your pager notification. The agent diagnosed while you were sleeping. Now it needs you for 30 seconds."

**COMMAND:** Click **✓ Approve**

**EXPECTED RESULT (in order):**
1. Token minted: `production:k8s.write.deployments · TTL 300s`
2. `restart_deployment` fires against real cluster
3. Agent calls `draft_postmortem`
4. Recovery overlay: `✅ Cluster Restored · AI Agent MTTR: 2m 14s`

**SPEAKER LINE:**
> "Two minutes, fourteen seconds. Diagnosis, approval, remediation, documentation. That's the full incident lifecycle. While the runbook was still looping."

**VERIFY (terminal — optional if confident):**
```bash
KUBECONFIG=~/.kube/mcp-demo.yaml kubectl --context=kind-mcp-demo -n production get pods | grep payment
```
**Expected:** All payment-service pods `Running`

---

**FALLBACK (if agent narrates instead of calling restart_deployment):**

In sidebar: AI Engine → change model to `claude-3-5-haiku-latest`.
If still fails: press F5. Say: *"I'll use the recorded version — this exact flow happened in rehearsal."*

---

## ACT 3 — DANGEROUS AGENT (3 min)

### Step 3a: Remove the policy layer

**PURPOSE:** Show what the same agent looks like with zero security — to make the contrast visceral.

**COMMAND:** Press **F4** — red banner appears across top of screen.

**Do not say anything. Let the audience read the banner for 3 seconds.**

**SCREEN SHOULD SHOW:**
```
⚠ DEMO MODE: Security policy DISABLED — all tools ungated
```

**SPEAKER LINE:**
> "Same agent. Same model. Same cluster. Zero policy layer."

### Step 3b: List secrets — ungated

**COMMAND:** Click **🔑 List secrets** chip (or type: `List all secrets in the production namespace`)

**EXPECTED RESULT:**
```
⚠  4 secret(s) found in namespace 'production' — agent has unrestricted read access to ALL secrets:

SECRET NAME                    TYPE                          KEYS
payment-db-credentials         Opaque                        3 key(s)
stripe-api-keys                Opaque                        2 key(s)
notification-smtp              Opaque                        3 key(s)
kube-system-bootstrap-token    bootstrap.kubernetes.io/token  2 key(s)
```

**Audit log entry:** `list_secrets | UNGATED | demo.no-policy | no blast radius`

**SPEAKER LINE:**
> "No rule. No blast radius. No approval record. The agent knows which secrets exist."
> *(pause)*
> "Payment processor keys. Database credentials. SMTP passwords. All accessible in one tool call — with no one's permission."

### Step 3c: Restore policy — show the contrast

**COMMAND:** Press **F4** again — banner disappears, Policy Gates: ON

**Type or click:** same request: `List all secrets in the production namespace`

**EXPECTED RESULT:**
```
🔒 POLICY DENIED
Rule: k8s.read.secrets
Reason: Secrets access DENIED — agent ServiceAccount lacks get/list on secrets.
        Use a dedicated secrets manager (Vault, ESO).
```

**Audit log now shows both entries side by side:**
- `list_secrets | UNGATED | allow` (security OFF)
- `list_secrets | k8s.read.secrets | deny` (security ON)

**SPEAKER LINE:**
> "Same request. Same agent. Different security posture."
> *(point to the two audit entries)*
> "That's the whole talk. Right there."

---

## CLOSING PRINCIPLES (3 min — no demo)

**Four principles:**

1. **Policy gate before every tool** — not per-server, per-tool. One function, 14 rules. That's it.

2. **Human approval for all destructive writes** — until you have enough audit data to remove it safely.

3. **Blast radius before approval** — compute the damage estimate before you ask the human to decide.

4. **Audit trail for every decision** — allowed, denied, approved, timed out. Not just what happened. What was considered.

**SPEAKER CLOSE:**
> "You don't need OPA on day one. You need the INTERFACE. Start with a policy function that returns ALLOW, DENY, or REQUIRE_APPROVAL. Add enforcement later. The architecture is the hard part, and you can do it in Python in an afternoon."
>
> "The agent is not dangerous because it's AI. It's dangerous because we gave it tools without rules. Same as any service account."

---

## POST-DEMO RESET (between runs)

```bash
# In browser: Demo menu → ↺ Reset demo to start
make recover    # resets all faults (~30s)
```

Then for next run:
```bash
make inject-oom
# wait 60s for CrashLoopBackOff badge
```

---

## KEYBOARD SHORTCUTS

| Key | Action | When |
|---|---|---|
| F2 | Presentation mode (full screen) | Before stage |
| F4 | Toggle policy ON/OFF | Act 3 start (OFF) → Act 3 end (ON) |
| F5 | Replay: cascade OOM | Fallback for Acts 1 & 2 |
| F6 | Replay: dangerous agent | Fallback for Act 3 |
| F7 | Clear chat | Between rehearsal runs |

---

## EMERGENCY RECOVERY (30-second nuclear reset)

```bash
make emergency-reset
```

Restarts all deployments, removes all fault injections, restores CoreDNS.
Use if: cluster in unknown state, pods stuck, port-forwards dead.
