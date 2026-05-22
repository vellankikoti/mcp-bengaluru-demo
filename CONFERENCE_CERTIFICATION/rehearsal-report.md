# rehearsal-report.md
# Dress Rehearsal — Certification Run
# 2026-05-23 00:10 IST

All timings from actual execution.

---

## Timeline

| Phase | Target | Actual | Delta |
|---|---|---|---|
| Agent health check | < 1s | 0s | on target |
| Security default verified (True) | < 1s | 0s | on target |
| `make inject-oom` fault injection | < 5s | 0s (command) | on target |
| Time to first CrashLoopBackOff | 30–60s | **31s** | on target |
| Replay stream (cascade, full) | 45s | **42s** | on target |
| Security toggle OFF→ON | < 1s | 0s | on target |
| `make recover` (command only) | < 15s | **10s** | on target |
| All pods Ready after recover | 30–60s | ~40s | on target |
| `make smoke` (20 checks) | < 10s | ~5s | on target |

---

## Full Talk Timing Estimate

Based on replay stream (42s for tool call sequence), approval gate (presenter-controlled),
and act structure:

| Section | Based on | Estimate |
|---|---|---|
| Intro + framing | Presenter | 3 min |
| Act 1 (Dead Runbook) | Script + 10s countdown pause | 4 min |
| Act 2 (tool calls stream) | ~42s of SSE + 30s approval + narration | 5 min |
| Act 3 (Dangerous agent) | F4 toggle + 2 queries + narration | 3 min |
| Closing principles | 4 principles + closing lines | 3 min |
| **Total** | | **18 min** |

**Within the 20-minute target with 2-minute buffer for Q&A.**

---

## Issues Found and Resolutions

### Issue 1: port conflict scenario
**Observation:** When running `python3 agent/server.py` directly (not via `make agent`),
port 8082 already in use causes a hard fail: `ERROR: [Errno 48] address already in use`.

**Resolution:** Documented clearly in RECOVERY.md R-06 and SCENARIOS.md Scenario 16.
`make agent` (via start.sh) handles this automatically. Presenter must use `make agent`, not
`python3 server.py` directly.

**Action:** Added explicit callout in INSTALL.md Step 5.

### Issue 2: smoke test expected failure state
**Observation:** Running `make smoke` while OOM is injected shows 3 failures. This confused
the first read — is the demo broken or is this correct?

**Resolution:** Documented in EXPECTED_OUTPUTS.md with explicit "Meaning: Demo fault is working
correctly. This is the intended pre-Act-1 state." entry.

### Issue 3: API key not in environment
**Observation:** ANTHROPIC_API_KEY not in shell env. Preflight shows as WARN.

**Resolution:** Documented in INSTALL.md Step 4 (three options: .env, env var, browser UI).
WARN does not block the demo.

---

## Confusing Moments for New Presenter

1. **Smoke test failure looks like a bug** — it's correct behavior after inject-oom.
   RUNBOOK.md explicitly says "do not recover before Act 1".

2. **Security toggle via F4** — not obvious that F4 is the keyboard shortcut. Documented in
   RUNBOOK.md keyboard shortcuts table and in Act 3 Step 3a.

3. **Two kind clusters** — `desktop` and `mcp-demo` both exist on this machine. The demo
   uses `kind-mcp-demo` exclusively. Documented in environment-report.md.

4. **Port-forward restart** — if laptop sleeps and port-forwards die, the fix is simply
   `make agent`. Documented in RECOVERY.md R-04.

5. **cascade replay takes 42 seconds** — the SSE stream has timing built in. Do not interrupt it.
   The silence is intentional. Documented in RUNBOOK.md Act 1 fallback note.

---

## Improvements Made During Certification

1. Created all 9 certification documents with verified outputs
2. Documented port conflict behavior difference between `make agent` vs `python3 server.py`
3. Added explicit "this is correct" note for smoke test failure after OOM injection
4. Documented that `lsof -v` produces "illegal option" on macOS (harmless — different lsof flags)

---

## Certification Decision

All timing targets met. All recovery paths verified. All scenario outputs documented.

**CLEARED FOR STAGE.**
