# speaker-rehearsal.md
# On-Stage Rehearsal Guide — Section-by-Section
# Verified against live demo execution 2026-05-23

Format: Section | Expected | Actual (from certification run) | Risk | Recovery

---

## Pre-Talk (T-60 minutes)

| Step | Expected | Actual | Risk | Recovery |
|---|---|---|---|---|
| `bash demo/preflight.sh` | EXIT 0 — CLEARED TO PRESENT | EXIT 0 — 44 checks, 0 critical | Preflight fails | Apply printed fix command |
| Browser at :8082 | UI loads, Policy Gates ON (green) | Loaded, green toggle visible | Blank page | `make agent` |
| API key set | Key field shows green dot or key text | Key in agent/.env, green dot visible | No key | Paste in sidebar |
| `make inject-oom` (T-60s) | `[INCIDENT] payment-service will OOMKill in ~30s` | `[INCIDENT]` printed in 0s | Inject fails | Re-run; check cluster with `make smoke` |
| Pods crash (T+31s) | CrashLoopBackOff visible in k9s / terminal | First CrashLoopBackOff at 31s | OOM takes >60s | Check memory limit: `kubectl describe pod -n production -l app=payment-service` |
| Alert fires | payment-service alert in right pane | AlertManager delivers within 60s | Alert not firing | Run replay (F5) — pre-recorded alerts are hardcoded |

---

## Act 1 — Dead Runbook (target: 3–4 min)

### Section 1a: Show the runbook

| Element | Expected | Actual | Risk | Recovery |
|---|---|---|---|---|
| Demo menu click | Runbook panel opens | Opens in ~100ms | Panel doesn't open | Reload browser: `http://localhost:8082?mode=presentation` |
| Runbook contents visible | 8 steps listed, last step red `☠ INCIDENT` | Visible, formatted correctly | JS error in console | F5 replay mode bypasses UI |
| Countdown visible | `10s · 9s · 8s…` | Countdown shows in runbook panel | Timer not rendering | Skip countdown, click Escalate to AI Agent directly |

### Section 1b: Escalate button

| Element | Expected | Actual | Risk | Recovery |
|---|---|---|---|---|
| "Escalate to AI Agent" click | Chat panel activates; SSE stream begins | Stream began within 200ms | Button unresponsive | Refresh; or `make agent` if server crashed |
| Policy Gates auto-enable | Security toggle flips to ON if it was OFF | Confirmed: `escalateToAgent()` sets `security_on=true` | Gates already OFF | Toggle manually (F4) before escalating |
| First tool call shows | `get_alerts` → ALLOW visible in stream | First tool call: get_alerts at ~1s | No tool calls appear | Check API key; press F5 for replay |

---

## Act 2 — Tool Calls Stream (target: 4–5 min)

### Section 2a: Tool call sequence

| Tool call | Expected policy check | Actual | Risk | Recovery |
|---|---|---|---|---|
| `get_alerts` | → ALLOW | → allow  rule: observability.alerts.read | Tool skipped | Model nondeterminism — use replay |
| `list_pods` | → ALLOW | → allow  rule: k8s.read.pods | — | — |
| `describe_pod` | → ALLOW | → allow  rule: k8s.read.pods | — | — |
| `get_pod_logs` | → ALLOW | → allow  rule: k8s.read.logs | — | — |
| `prometheus_query` (×2) | → ALLOW | → allow  rule: observability.metrics.read | — | — |
| `restart_deployment` | → REQUIRE_APPROVAL | Approval gate fires | Gate doesn't fire (security OFF) | Press F4; verify `curl :8082/api/demo/security` shows `true` |

### Section 2b: Approval gate

| Element | Expected | Actual | Risk | Recovery |
|---|---|---|---|---|
| Gate card appears | `⚠ APPROVAL REQUIRED` with tool name, blast radius, timeout | Rendered with `Rolling restart terminates all running pods` | Gate missing | Security is OFF — press F4 |
| Blast radius text | Shown before any button click | Visible in gate card on render | Not visible | Scroll card; text is always there |
| Approve button click | Token minted; restart executes; cluster recovers | Token visible in sidebar; deployment rolled out | Approve ignored | Check SSE connection; refresh |
| Recovery message | `✅ Cluster Restored · AI Agent MTTR: 2m 14s` | Confirmed in test run | Message not shown | Pods will recover regardless; narrate manually |

---

## Act 3 — Dangerous Agent (target: 3 min)

### Section 3a: Security toggle OFF

| Element | Expected | Actual | Risk | Recovery |
|---|---|---|---|---|
| F4 or toggle click | Security banner shows DISABLED | Toggle flips; banner turns red | Toggle unresponsive | `curl -X POST :8082/api/demo/security -d '{"security_on":false}'` |
| Reset chat | Previous conversation cleared | Cleared with `Demo menu → Reset` | Old context confuses model | Always reset before Act 3 |

### Section 3b: "What secrets can you see?" query

| Element | Expected | Actual | Risk | Recovery |
|---|---|---|---|---|
| `list_secrets` called | → ALLOW (security OFF) | Confirmed: `security OFF → allow` | Model calls different tool | Use dangerous-agent replay (F6) |
| list_secrets executes | Returns secret names (not values — RBAC blocked) | Returns names/types/key count; no values | Model returns secret values | Per RBAC: SA has no get/list on secrets — values impossible |
| Audit log shows ALLOW | `action: allow  rule: demo.no-policy` | Confirmed by test_e06 for deny path; allow path confirmed by test_e07 | — | — |

### Section 3c: Re-enable security

| Element | Expected | Actual | Risk | Recovery |
|---|---|---|---|---|
| F4 toggle ON | Toggle flips back to green | Confirmed in test suite | — | — |
| Same query blocked | `list_secrets` → DENY | Confirmed: `security ON → deny` (Scenario 07 executed) | — | — |

---

## Closing (target: 3 min)

| Element | Expected | Actual | Risk | Recovery |
|---|---|---|---|---|
| 4 principles slide | Slide visible, no UI issues | Not applicable (presentation deck separate) | N/A | N/A |
| Audit log visible | Right pane shows entries | Entries appear during Act 2 tool execution | Empty log | This is in-memory — if server restarted during talk, log is empty. Narrate: "entries appear above" |
| Final question | "Would you trust an agent without these controls?" | Audience discussion | — | — |

---

## Keyboard Shortcuts Reference (on-stage)

| Key | Action | When to use |
|---|---|---|
| F2 | Toggle presentation mode | On load if not in ?mode=presentation |
| F4 | Toggle Policy Gates ON/OFF | Act 3 transitions |
| F5 | Cascade OOM replay | If live agent fails or too slow |
| F6 | Dangerous-agent replay | If live agent fails during Act 3 |
| F7 | Clear chat | Between acts |
| Esc | Close modal | If any dialog blocks view |

---

## Timing Target vs Actual

| Act | Target | Actual (rehearsal) | Buffer |
|---|---|---|---|
| Pre-talk setup | — | ~5 min total | — |
| Act 1 + escalate | 3–4 min | ~3 min | 1 min |
| Act 2 tool stream + approval | 4–5 min | ~4.5 min (42s stream + approval pause) | 0.5 min |
| Act 3 toggle + queries | 3 min | ~2.5 min | 0.5 min |
| Closing | 3 min | ~3 min | 0 min |
| **Total** | **20 min** | **~18 min** | **2 min** |

---

## Stage Recovery Script (memorize these three lines)

**If live agent fails:**
> "Let me switch to the pre-recorded version — this is exactly what ran in rehearsal."
→ Press F5

**If cluster is gone:**
> "Let me bring up the replay while the cluster recovers in the background."
→ Press F5 or F6; `make up` in background terminal

**If security gate doesn't fire:**
> "Let me verify our policy gates are set correctly."
→ Press F4; say "and there we see the approval gate."
