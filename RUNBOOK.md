# Conference Demo Runbook
# Dead Runbooks, Dangerous Agents, and the Security Model That Saved Us

MCP Dev Summit Bengaluru 2026 | 20–22 minutes

---

## SETUP (Night Before)

```bash
# 1. Full bootstrap from scratch (skip if cluster already exists)
make up        # ~5 min: creates kind cluster + observability + services

# 2. Verify everything
make smoke     # must show "All 20 checks passed"

# 3. Install Python deps
pip install -r agent/requirements.txt

# 4. Set API key
echo 'ANTHROPIC_API_KEY=sk-ant-...' > agent/.env

# 5. Save cluster checkpoint
make checkpoint
```

Test the full flow once:
```bash
make inject-oom     # inject fault
make agent          # start server
# Open http://localhost:8082 — run through all 3 acts
make recover        # clean up
```

---

## DAY-OF CHECKLIST (T-60 minutes)

```
□ Laptop charged, plugged in
□ Docker running (check Docker Desktop taskbar)
□ make up  — if cluster was off since yesterday
□ make smoke  — must pass all 20 checks
□ pip install -r agent/requirements.txt  — if deps may have changed
□ agent/.env has ANTHROPIC_API_KEY (or have key ready to paste)
```

---

## LAUNCH (T-30 minutes)

```bash
# Terminal 1 — start agent (keep this terminal visible)
make agent
# Expect: "Starting MCP Incident Agent on http://localhost:8082"
# Expect: 3 port-forwards start (Prometheus 9092, Alertmanager 9093, Grafana 3002)

# Run preflight check
bash demo/preflight.sh
# Must exit 0 with "CLEARED TO PRESENT"
```

Open browser: `http://localhost:8082?mode=presentation`

In sidebar:
- AI Engine: connect key → should show green "connected"
- Demo Controls: Policy Gates **ON** (check)
- Click "Reset demo to start" in Demo menu

---

## T-60 SECONDS BEFORE ACT 1

```bash
# Terminal 1 (or new Terminal 2)
make inject-oom
```

Wait 30–60 seconds. Watch sidebar:
- "1 Crashing" badge appears
- Alert: `PaymentServiceCrashLooping` in alert feed

**Do not click Dead Runbook until the sidebar shows the red badge.**

---

## ACT 1 — DEAD RUNBOOK (4 min)

1. Click **📖 Dead Runbook** chip (or Demo menu → Act 1)
2. Narrate as steps stream:
   - Steps 1–3: alert, pods, no recent deploys
   - Step 4: restart triggered — narrate: "The runbook does what runbooks do. It restarts."
   - Step 5: 10-second countdown — say nothing. Let the timer run. The silence teaches.
   - Step 5 result: OOMKilled again — "Exit code 137. Same reason. Every restart."
   - Step 6: second restart — "It tries again because that's all it knows how to do."
   - Step 7: escalation — "And then it gives up."
3. Read the failure card aloud: *"Root cause: UNKNOWN. The runbook can't ask WHY."*
4. **Pause 3 seconds.**
5. "This isn't a design flaw. This is the fundamental limit of static automation."
6. Click **Escalate to AI Agent →**

**FALLBACK if cluster has no OOMKill visible:**
- Press `F5` — replay mode starts
- Say: "I'm using a pre-recorded run so the timing is reliable. Every event you see is real."

---

## ACT 2 — AGENT DIAGNOSES (3 min)

The escalation auto-fills the chat. Do not type anything.

Watch tool calls stream with green ALLOW badges. Narrate:

- `get_alerts` fires → "ALLOW. Reads are permitted."
- `list_pods` → "It sees the crashing pod."
- `describe_pod` → "Exit code 137. Memory limit 50Mi."
- `get_pod_logs` → "It's reading the crash logs."
- `prometheus_query` (×2) → "Now it's quantifying — real Prometheus data."

When `restart_deployment` triggers:

**STOP TALKING. Wait 3 seconds.**

Then: "There it is. The agent found the root cause AND stopped itself. It's asking for permission."

Point to the approval card:
- "Blast radius: rolling restart, brief disruption. The agent computed this before asking."
- "Countdown: you have 10 minutes to decide."

---

## ACT 2 CONTINUED — APPROVAL GATE (2 min)

Say: "In a production system, this is your pager. The agent diagnosed while you were sleeping. Now it needs you for 30 seconds."

Click **✓ Approve**

Watch:
- Token minted: `production:k8s.write.deployments · TTL 600s`
- Restart fires against real cluster
- Agent calls `draft_postmortem`
- Recovery overlay appears: `✅ Cluster Restored · AI Agent MTTR: 2m 14s`

Say: "Two minutes fourteen seconds. Diagnosis, approval, remediation, documentation. While the runbook was still looping."

---

## ACT 3 — DANGEROUS AGENT (3 min)

1. "Let me show you what your agent looks like today — before you add any of this."

2. Press **F4** — red banner appears across top
   - Say nothing. Let the audience read the banner.
   - Then: "Same agent. Same model. Zero policy layer."

3. Click **🔑 List secrets** chip (or type: *"List all secrets in the production namespace"*)

4. Watch `list_secrets` execute — `UNGATED` in audit log, no approval, no blast radius

5. Point to the audit log: "No rule. No blast radius. No approval record."

6. **Pause.** Then: "This is not a hypothetical. This is a real Kubernetes API call. The agent knows which secrets exist. DB credentials. Payment processor keys. SMTP passwords. All accessible in one tool call — with no one's permission."

7. Press **F4** again — policy ON

8. Ask the same question: `list_secrets` → **DENY** card appears with reason.

9. "Same request. Same agent. Different security posture."

Point to the two audit log entries side by side:
- "That's the whole talk. Right there."

---

## CLOSING SLIDE (3 min, no demo)

Four principles:
1. Policy gate before every tool — not per-server, per-tool
2. Human approval for all destructive writes — until you have audit data to remove it
3. Blast radius before approval — estimate damage before asking for permission
4. Audit trail for every decision — allowed, denied, approved, timed out

"You do not need OPA on day one. You need the INTERFACE. Start with a policy function. Add enforcement later. The architecture is the hard part."

"The agent is not dangerous because it's AI. It's dangerous because we gave it tools without rules. Same as any service account."

---

## RESET BETWEEN RUNS

```
Demo menu → ↺ Reset demo to start
```

Then in terminal:
```bash
make recover        # resets all faults (payment-service → healthy in ~30s)
```

---

## FALLBACK SCENARIOS

### "Agent narrates instead of calling restart_deployment"
Switch to claude-3.5-haiku in AI Engine sidebar. Conservative models describe instead of act.
If switching doesn't help: use F5 replay. Say: "I'll show you the recorded version — this is exactly what happened in rehearsal."

### "Port-forwards died mid-demo"
Open new terminal: `make agent`
It restarts all three port-forwards automatically.

### "kind cluster gone"
```bash
make up   # 5 min rebuild
make smoke
```
Use F5/F6 replays during the wait.

### "LLM API error"
In sidebar: AI Engine → switch provider (OpenRouter → OpenAI, or vice versa).
Or use F5 replay for the rest of the demo.

### "Need nuclear reset in 30 seconds"
```bash
make emergency-reset
```
Restarts all deployments, removes all fault injections, restores CoreDNS.

---

## KEYBOARD SHORTCUTS (memorize these)

| Key | Action | When to use |
|---|---|---|
| F2 | Presentation mode | Before going on stage |
| F4 | Toggle policy ON/OFF | Act 3 start (OFF) and end (ON) |
| F5 | Replay: cascade OOM | Fallback for Acts 1 & 2 |
| F6 | Replay: dangerous agent | Fallback for Act 3 |
| F7 | Clear chat | Between rehearsal runs |

---

## TIMING TARGET

| Section | Target | Hard Max |
|---|---|---|
| Act 1 (Dead Runbook) | 4 min | 5 min |
| Act 2 (Agent + Approval) | 5 min | 6 min |
| Act 3 (Dangerous Agent) | 3 min | 4 min |
| Closing + principles | 3 min | 4 min |
| Intro + context | 3 min | 3 min |
| Q&A buffer | 2 min | — |
| **Total** | **20 min** | **22 min** |

---

## POST-DEMO CHECKLIST

```bash
make recover        # reset all faults
# Demo menu → Reset demo to start (clears chat + audit log)
# Close browser tab
```

```bash
# For next run — inject fault fresh
make inject-oom
make agent
```
