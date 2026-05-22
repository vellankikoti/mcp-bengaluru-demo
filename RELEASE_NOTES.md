# RELEASE_NOTES.md
# Conference Demo — Release Notes
# MCP Dev Summit Bengaluru 2026

---

## v1.0.0 — Conference Release (2026-05-23)

### Summary

Production-hardened conference demo for "Dead Runbooks, Dangerous Agents, and the Security
Model That Saved Us." 82 automated tests. Full certification package. Stage-ready.

### What's New (This Sprint)

**Security fixes:**
- Fixed path traversal vulnerability in `/api/replay/{scenario}` endpoint — `resolve()` +
  bounds check prevents escaping recordings directory
- Fixed `_security_on` default from `False` → `True` (critical invariant — guarded by AST test)
- Added `test_security_invariant_server_default`: AST-level verification that security
  cannot accidentally default to OFF

**Reliability fixes:**
- Fixed port conflict handling in `python3 agent/server.py` direct invocation (was only handled
  by `make agent`/start.sh) — both paths now auto-kill whatever occupies port 8082
- Approval timeout increased 300s → 600s to allow dramatic pause during live demo

**New tests (82 total, up from 75):**
- `test_e01`–`test_e03`: Live Prometheus queries against kind cluster
- `test_e04`–`test_e05`: Live Alertmanager queries; Watchdog alert present
- `test_e06`: Audit log writes entry on DENY
- `test_e07`: Audit log entry has `duration_ms` and `result_preview` on ALLOW

**New demo feature:**
- Dead Runbook UI: 8-step runbook with "Escalate to AI Agent" CTA replaces generic scenario picker

**Documentation fixes:**
- All `pip install` → `python3 -m pip install` (macOS system Python compatibility)
- `ls` command in INSTALL.md scoped to 6 specific paths (avoids confusing full ls output)
- `make recover` output corrected in EXPECTED_OUTPUTS.md and SCENARIOS.md
- Double prefix `python3 -m python3 -m pip` corrected in RUNBOOK.md
- Default model switched to `claude-3-5-haiku-latest` (cost reduction)

**Certification package (CONFERENCE_CERTIFICATION/):**
- 11 documents: INSTALL, PRECHECK, RUNBOOK, SCENARIOS (20), EXPECTED_OUTPUTS, RECOVERY (14),
  FAQ (25+ Q&A), rehearsal-report, speaker-rehearsal, e2e-final-report, FINAL_CERTIFICATION
- All outputs from actual execution — nothing extrapolated
- Preflight: 44 checks, 0 critical failures
- Full reset verified: `make recover` + `make smoke` → 20/20 in 45s

### Known Gaps (documented, none blocking)

| Gap | Production path |
|---|---|
| Policy is Python dict (not OPA/Rego) | OPA sidecar + Rego files |
| Scoped tokens are cosmetic UUIDs | Kubernetes `v1/TokenRequest` API |
| Audit log is in-memory (lost on restart) | Append-only file or SIEM |
| Agent uses user kubeconfig (not SA token) | Run agent inside cluster as ServiceAccount |
| MCP SDK not used (Anthropic function calling) | Official `@mcp.tool` SDK |

All gaps disclosed in `agent/policy.py` header comment.

### Commit History

```
419f992 Fix port conflict in server.py; update certification docs
44690b8 Add CONFERENCE_CERTIFICATION package — full stage certification
8ba0338 Add e2e metrics/audit tests (82 total, up from 75)
3fd4244 Production hardening + keynote readiness sprint (9.2/10)
9bfaf3f Switch default model to claude-3-5-haiku-latest (cheaper)
4fc06a1 Add Dead Runbook demo, fix UX journey, and rewrite README
```

### Test Results

```
82 passed in 50.85s — 0 failed — 0 errors
platform darwin -- Python 3.9.6, pytest-8.4.1
```

### Day-Of Command

```bash
bash demo/preflight.sh
# Must exit 0 with CLEARED TO PRESENT
```
