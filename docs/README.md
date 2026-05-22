# CONFERENCE_CERTIFICATION
# Dead Runbooks, Dangerous Agents, and the Security Model That Saved Us
# MCP Dev Summit Bengaluru 2026

This package certifies the demo for global-stage delivery.
All outputs are from actual execution on 2026-05-23.

---

## For a first-time presenter

Follow these documents in order:

1. **[INSTALL.md](INSTALL.md)** — Clone repo, install deps, bootstrap cluster, start agent.
   Estimated time from zero: 10 minutes (after prerequisites).

2. **[PRECHECK.md](PRECHECK.md)** — Run 30 minutes before stage.
   Single command: `bash demo/preflight.sh`. Must exit 0.

3. **[RUNBOOK.md](RUNBOOK.md)** — Talk script. Every speaker line, screen state, keyboard
   shortcut, and fallback is documented.

4. **[RECOVERY.md](RECOVERY.md)** — If anything breaks on stage, start here.

---

## For a reviewer or certifier

| Document | Purpose |
|---|---|
| [environment-report.md](environment-report.md) | All detected versions vs. requirements |
| [PRECHECK.md](PRECHECK.md) | All 44 preflight checks with pass/fail and recovery |
| [INSTALL.md](INSTALL.md) | Clean install from zero — every command verified |
| [RUNBOOK.md](RUNBOOK.md) | Full talk delivery guide |
| [SCENARIOS.md](SCENARIOS.md) | 20 scenarios executed and documented |
| [EXPECTED_OUTPUTS.md](EXPECTED_OUTPUTS.md) | Exact terminal output for every command |
| [RECOVERY.md](RECOVERY.md) | 14 failure modes with fix commands |
| [FAQ.md](FAQ.md) | 25+ questions including beginner section |
| [rehearsal-report.md](rehearsal-report.md) | Measured timing, issues found, resolution |
| [FINAL_CERTIFICATION.md](FINAL_CERTIFICATION.md) | Certification decision with risk matrix |

---

## Quickstart (after cluster is already running)

```bash
make agent                        # start server + port-forwards
bash demo/preflight.sh            # 44 checks — must exit 0
make inject-oom                   # 60s before Act 1
# Browser: http://localhost:8082?mode=presentation
```

---

## Test suite

```bash
make test                         # 82 tests, all must pass
```

Expected: `82 passed in ~51s`

---

## Emergency

```bash
make emergency-reset              # 30s nuclear reset
# OR
make down && make up              # 5–8 min full rebuild
```
