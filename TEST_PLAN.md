# TEST PLAN — Dead Runbooks, Dangerous Agents, and the Security Model That Saved Us

Generated: 2026-05-22  
Status: ACTIVE — all tests must pass before stage.

---

## 1. UNIT TESTS (`tests/test_policy.py`)

Tests that run with no cluster, no LLM, no network.

| ID | Test | Pass Criterion |
|---|---|---|
| U-01 | Policy ALLOW for read tools (security_on=True) | action == ALLOW |
| U-02 | Policy DENY for list_secrets (security_on=True) | action == DENY |
| U-03 | Policy REQUIRE_APPROVAL for restart_deployment (security_on=True) | action == REQUIRE_APPROVAL |
| U-04 | All tools ALLOW when security_on=False | action == ALLOW for all tools |
| U-05 | Unknown tool → DENY (fail-closed) | action == DENY, rule == default.deny-unknown |
| U-06 | PolicyResult has request_id (UUID prefix) | len(request_id) == 8 |
| U-07 | blast_radius populated for write tools | blast_radius is not None for restart/scale |
| U-08 | blast_radius is None for read tools | blast_radius is None |
| U-09 | security_on=False: reason contains "DISABLED" | "DISABLED" in reason |
| U-10 | evaluated_at is a float (monotonic) | isinstance(evaluated_at, float) |

---

## 2. UNIT TESTS (`tests/test_tools_schema.py`)

Tests that tool definitions are valid and complete.

| ID | Test | Pass Criterion |
|---|---|---|
| U-11 | All 14 tools have name, description, input_schema | No missing fields |
| U-12 | All TOOL_REGISTRY entries have matching TOOL_DEFINITIONS | Sets are equal |
| U-13 | restart_deployment requires deployment_name | required field present |
| U-14 | scale_deployment replicas max=20 | maximum == 20 |
| U-15 | list_secrets description says "does NOT return secret values" | Substring in description |
| U-16 | draft_postmortem has all required fields | 5 required fields |

---

## 3. UNIT TESTS (`tests/test_recordings.py`)

Tests that pre-recorded files are valid and truthful.

| ID | Test | Pass Criterion |
|---|---|---|
| U-17 | cascade.jsonl parses as valid JSONL | All non-comment lines valid JSON |
| U-18 | dangerous-agent.jsonl parses as valid JSONL | All non-comment lines valid JSON |
| U-19 | dangerous-agent.jsonl contains no secret values | No password/key strings found |
| U-20 | dangerous-agent.jsonl tool_result matches list_secrets format | "key(s)" present, no ":" value patterns |
| U-21 | All recordings have delay_ms > 0 for non-first events | timing is non-negative |
| U-22 | All recordings end with done event | last event type == "done" |

---

## 4. INTEGRATION TESTS (`tests/test_server_api.py`)

Tests that run against a live agent server (no cluster required for most).

| ID | Test | Pass Criterion |
|---|---|---|
| I-01 | GET /health returns 200 | status == "ok" |
| I-02 | GET /api/demo/security returns security_on=True on fresh start | security_on == True |
| I-03 | POST /api/demo/security {security_on: false} → state changes | security_on == False |
| I-04 | POST /api/demo/security {security_on: true} → token created | token field not None |
| I-05 | GET /api/audit returns entries list | "entries" key present |
| I-06 | GET /api/replay returns available recordings | "recordings" list not empty |
| I-07 | GET /api/replay/cascade returns SSE stream | Content-Type: text/event-stream |
| I-08 | GET /api/replay/dangerous-agent returns SSE stream | Content-Type: text/event-stream |
| I-09 | GET /api/replay/nonexistent returns 404 | status_code == 404 |
| I-10 | POST /api/approval/nonexistent returns 404 | status_code == 404 |

---

## 5. E2E SCENARIOS (`tests/test_e2e_scenarios.py`)

Full end-to-end tests. Require running agent server + kind cluster + Prometheus.

| ID | Scenario | Success Criterion |
|---|---|---|
| E-01 | Healthy diagnosis | Agent calls get_alerts + list_pods, returns structured report |
| E-02 | Dangerous action blocked | restart_deployment with security_on=True → approval_required event |
| E-03 | Approval path | approval_required → POST approve → token_minted → tool_result |
| E-04 | Approval timeout | POST to /api/approval after 301s → handled gracefully |
| E-05 | Replay mode cascade | /api/replay/cascade streams all events in order |
| E-06 | Replay dangerous-agent | /api/replay/dangerous-agent streams, no secret values |
| E-07 | Secrets blocked (policy on) | list_secrets with security_on=True → DENY, tool not executed |
| E-08 | Secrets allowed (policy off) | list_secrets with security_on=False → ALLOW, names returned |
| E-09 | Multiple alerts | get_alerts with OOM injected → at least 1 alert returned |
| E-10 | Demo reset | Security toggle ON/OFF/ON, audit log captures all three |

---

## 6. CHAOS TESTS

Manual tests — run the night before the talk.

| ID | Test | Recovery |
|---|---|---|
| C-01 | Kill Prometheus port-forward mid-demo | `make agent` restarts; replay as fallback |
| C-02 | Kill kind cluster mid-demo | `make up` → 5 min; use replay |
| C-03 | Revoke API key mid-demo | Switch to backup provider in UI |
| C-04 | Sleep laptop during demo | Port-forwards die; `make agent` restores |
| C-05 | Run `make inject-cascade` instead of `inject-oom` | `make recover` → 30s reset |

---

## 7. SECURITY TESTS

| ID | Test | Pass Criterion |
|---|---|---|
| S-01 | Server starts with security_on=True | GET /api/demo/security → true |
| S-02 | list_secrets DENY fires without executing tool | No k8s API call when denied |
| S-03 | restart_deployment requires approval | approval_required event before execution |
| S-04 | Unknown tool denied | POST /api/chat with unknown tool → deny event |
| S-05 | API key not logged | Audit log contains no api_key field |

---

## 8. PERFORMANCE TARGETS

| Metric | Target | Measurement |
|---|---|---|
| Server cold start | < 3s | time from `python server.py` to first HTTP response |
| Tool execution (read) | < 5s | list_pods response time |
| Tool execution (Prometheus) | < 3s | prometheus_query response time |
| Replay stream start | < 500ms | time to first SSE event |
| UI load (warm) | < 1s | browser DOMContentLoaded |

---

## 9. RECOVERY TESTS

| ID | Test | Pass Criterion |
|---|---|---|
| R-01 | `make recover` resets all faults | payment-service Running within 60s |
| R-02 | `make emergency-reset` completes in < 60s | All pods Running |
| R-03 | Checkpoint + restore | make checkpoint → inject fault → restore → cluster matches checkpoint |
| R-04 | Smoke test passes after recovery | `make smoke` → all checks pass |

---

## PASS / FAIL DEFINITION

The demo may proceed if:
- All U-* tests pass (automated, in CI)
- All I-* tests pass (automated, local server)
- E-01, E-02, E-03, E-05, E-07, E-08 pass (critical path)
- S-01, S-02, S-03 pass (security gates verified)
- R-01, R-02 pass (recovery verified)

The demo must NOT proceed if:
- S-01 fails (`_security_on` not True at startup)
- S-02 fails (list_secrets executes when denied)
- S-03 fails (restart fires without approval)
- Any U-* test fails (fundamental logic broken)
