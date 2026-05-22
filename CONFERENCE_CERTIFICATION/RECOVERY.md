# RECOVERY.md
# Failure recovery guide — verified commands only

For every failure mode: symptoms, root cause, exact fix command, verify step.

---

## R-01: Cluster Dead / Deleted

**Symptoms:**
- `kind get clusters` doesn't show `mcp-demo`
- `kubectl get nodes` returns error
- `make smoke` shows cluster failures

**Root cause:** Cluster was deleted, Docker was restarted, or kind state was lost.

**Fix:**
```bash
make up
```
Expected time: 5–8 minutes

**Verify:**
```bash
make smoke
```
Expected: `✅  All 20 checks passed.`

**If make up fails partway through:**
```bash
make down && make up
```

---

## R-02: Pod Crash / Stuck in OOMKilled or Error State

**Symptoms:**
- `make smoke` shows `payment-service available: FAIL`
- `kubectl get pods -n production` shows CrashLoopBackOff or OOMKilled
- Not caused by intentional fault injection

**Root cause:** Lingering fault from previous demo run, or node pressure.

**Fix:**
```bash
make recover
```

**Verify (wait 30s):**
```bash
make smoke
```
Expected: `✅  All 20 checks passed.`

**If recover doesn't help:**
```bash
make emergency-reset
```
Expected time: ~30 seconds. Restarts all deployments, removes fault injections, restores CoreDNS.

---

## R-03: MCP Agent Server Not Running

**Symptoms:**
- `curl http://localhost:8082/health` → `Connection refused`
- Browser shows blank page or "connection refused"
- Preflight shows `⚠ WARN Agent server not running`

**Root cause:** `make agent` not started, or server crashed.

**Fix:**
```bash
make agent
```

**Verify:**
```bash
curl -s http://localhost:8082/health
```
Expected: `{"status": "ok", "model": "claude-3-5-haiku-latest"}`

---

## R-04: Port-Forwards Dead (Prometheus/Alertmanager/Grafana)

**Symptoms:**
- `curl http://localhost:9092/-/ready` → `Connection refused`
- Preflight shows `⚠ WARN Prometheus(9092) port-forward not responding`
- Agent starts but tools can't reach metrics

**Root cause:** kubectl port-forward processes died (common after laptop sleep, network switch).

**Fix:**
```bash
make agent
```
`start.sh` checks each port-forward before starting a new one. Re-running `make agent` is safe
and idempotent — it will restart only dead port-forwards.

**Verify:**
```bash
curl -s http://localhost:9092/-/ready && echo "prom ok"
curl -s http://localhost:9093/-/ready && echo "am ok"
curl -sf http://localhost:3002/api/health | python3 -m json.tool
```

---

## R-05: LLM API Error (Anthropic / OpenAI)

**Symptoms:**
- Agent sends messages but no tool calls appear
- Chat shows error: `API error`, `401 Unauthorized`, `rate limit exceeded`
- Agent narrates instead of calling tools

**Root cause:** API key missing, wrong key, rate limit, or provider outage.

**Fix — Step 1:** Check API key in sidebar: AI Engine → key field.

**Fix — Step 2:** Switch provider in sidebar: AI Engine → toggle between Anthropic and OpenRouter.

**Fix — Step 3:** If no provider works, switch to replay:
- Press **F5** (cascade OOM replay)
- Press **F6** (dangerous agent replay)

Say on stage: *"I'll use the pre-recorded version — this is exactly what happened in rehearsal."*

---

## R-06: Port 8082 Already in Use

**Symptoms:**
- `make agent` prints: `Port 8082 in use (pid XXXXX) — releasing it`
- (This is expected behavior — start.sh auto-kills it)
- OR: `python3 agent/server.py` fails with `Address already in use`

**Root cause:** Previous server process still running, or another process on 8082.

**Fix:** Both `make agent` and `python3 agent/server.py` now auto-kill whatever is on port 8082.
```bash
make agent
# OR
python3 agent/server.py
```

**Verify:**
```bash
curl -s http://localhost:8082/health
```

---

## R-07: Expired Token Displayed

**Symptoms:**
- Sidebar shows token with past `expires_at`
- Approval gate re-fires on next restart request

**Root cause:** Token TTL is 300s (5 minutes). This is cosmetic — the token ID is for display only.

**Fix:** A new token is minted automatically on the next approved write action.

**Alternative:** Toggle security OFF and ON to force a new token:
```bash
curl -s -X POST http://localhost:8082/api/demo/security \
  -H "Content-Type: application/json" -d '{"security_on": false}'
curl -s -X POST http://localhost:8082/api/demo/security \
  -H "Content-Type: application/json" -d '{"security_on": true}'
```

---

## R-08: Approval Gate Not Appearing

**Symptoms:**
- Agent calls `restart_deployment` but no approval card appears
- Tool executes immediately without waiting for approval

**Root cause:** Security gates are OFF (security_on=false).

**Fix:**
```bash
curl -s http://localhost:8082/api/demo/security
```
If `security_on: false`:
- In browser: Press **F4** to toggle ON
- Or in Demo Controls sidebar: Policy Gates → ON
- Or: `curl -s -X POST http://localhost:8082/api/demo/security -H "Content-Type: application/json" -d '{"security_on": true}'`

**Verify:**
```bash
curl -s http://localhost:8082/api/demo/security
```
Expected: `{"security_on": true, "token": null}`

---

## R-09: Recording Corrupt or Missing

**Symptoms:**
- F5 or F6 replay produces error
- `/api/replay` returns empty list
- Preflight shows `✗ CRITICAL cascade.jsonl missing`

**Root cause:** File deleted, corrupted, or accidentally edited.

**Fix:**
```bash
git checkout agent/demo-recordings/cascade.jsonl
git checkout agent/demo-recordings/dangerous-agent.jsonl
```

**Verify:**
```bash
grep -c "^{" agent/demo-recordings/cascade.jsonl
grep -c "^{" agent/demo-recordings/dangerous-agent.jsonl
```
Expected: `42` and `10`

---

## R-10: Bad Environment / Wrong Python

**Symptoms:**
- `import fastapi` fails
- Tests fail with `ModuleNotFoundError`
- Agent fails to start

**Root cause:** Wrong Python environment, packages not installed.

**Fix:**
```bash
python3 -m pip install -r agent/requirements.txt
```

**Verify:**
```bash
python3 -c "import fastapi, anthropic, uvicorn, httpx, kubernetes, pydantic; print('ok')"
```
Expected: `ok`

---

## R-11: Missing Dependency (tool-specific)

**Symptoms:**
- Preflight shows `✗ CRITICAL helm not found`
- `make up` fails at Helm install step

**Fix:**
```bash
brew install kind kubectl helm
```

---

## R-12: Security Invariant Fails

**Symptoms:**
- Preflight shows `✗ CRITICAL _security_on is not True`
- `test_security_invariant_server_default` FAILS

**Root cause:** `_security_on` default was accidentally changed in server.py.

**Fix:**
```bash
git diff agent/server.py | grep "_security_on"
# If shows False:
git checkout agent/server.py
```

**Verify:**
```bash
grep "_security_on" agent/server.py | head -3
```
Expected: `_security_on: bool = True`

---

## R-13: Nuclear Reset (30 seconds, everything)

Use when: cluster in unknown state, multiple failures, T-5 minutes to stage.

```bash
make emergency-reset
```

Then:
```bash
make smoke
bash demo/preflight.sh
make inject-oom   # if needed
```

---

## R-14: Full Rebuild (5–8 minutes)

Use when: cluster gone, Docker images deleted, complete environment loss.

```bash
make down && make up
python3 -m pip install -r agent/requirements.txt
make smoke
make agent
bash demo/preflight.sh
```

---

## Decision Tree

```
Something is wrong
│
├── Can't reach http://localhost:8082?
│   └── make agent
│
├── Pods crashing (not OOM injection)?
│   └── make recover  →  wait 30s  →  make smoke
│
├── Port-forwards dead (9092/9093/3002)?
│   └── make agent
│
├── Security gates off unexpectedly?
│   └── Press F4 in browser  OR  toggle in Demo Controls sidebar
│
├── LLM returning errors?
│   └── Switch provider in AI Engine  OR  press F5/F6 for replay
│
├── Cluster missing?
│   └── make up  (5–8 min)
│
└── Everything broken?
    └── make emergency-reset  (30s)
        OR
        make down && make up  (5–8 min)
```
