# INSTALL.md
# From zero to demo-ready on a new machine

This document assumes you have never seen this repo. Every command is verified.
Follow every step in order. Do not skip.

---

## Prerequisites — install these first

| Tool | Install command | Verify |
|---|---|---|
| Docker Desktop | https://docs.docker.com/desktop/mac/install/ | `docker version` |
| Homebrew | `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"` | `brew --version` |
| kind | `brew install kind` | `kind version` |
| kubectl | `brew install kubectl` | `kubectl version --client` |
| helm | `brew install helm` | `helm version --short` |
| Python 3.9+ | Pre-installed on macOS, or `brew install python@3.11` | `python3 --version` |

**Expected after prerequisites:**
```
docker version → Client: 29.x.x  Server: 29.x.x
kind version   → kind v0.29.0 go1.24.3 darwin/arm64
kubectl        → Client Version: v1.34.x
helm version   → v3.19.x
python3        → Python 3.9.x (or newer)
```

---

## STEP 1 — Clone the repo

**Command:**
```bash
git clone <repo-url> mcp-bengaluru-demo
cd mcp-bengaluru-demo
```

**Expected output:**
```
Cloning into 'mcp-bengaluru-demo'...
remote: Counting objects: ...
```

**Verify:**
```bash
ls
```
**Expected:** You see `agent/`, `demo/`, `cluster/`, `tests/`, `Makefile`, `README.md`

**Troubleshoot:** If git fails, check your SSH key or use HTTPS URL.

---

## STEP 2 — Install Python dependencies

**Command:**
```bash
pip install -r agent/requirements.txt
```

**Expected output:**
```
Successfully installed anthropic-0.100.0 fastapi-0.128.8 httpx-0.28.1
kubernetes-33.1.0 pydantic-2.13.4 uvicorn-0.39.0 ...
```

**Verify:**
```bash
python3 -c "import fastapi, anthropic, uvicorn, httpx, kubernetes, pydantic; print('all good')"
```
**Expected:** `all good`

**Expected time:** 30–60 seconds

**Troubleshoot:**
- `pip: command not found` → use `pip3` or `python3 -m pip`
- Permission denied → add `--user` flag

---

## STEP 3 — Bootstrap the cluster

**Command:**
```bash
make up
```

**What this does:** Creates a kind cluster named `mcp-demo`, builds 6 Docker images,
installs kube-prometheus-stack via Helm, applies RBAC, deploys all services.

**Expected time:** 5–8 minutes

**Expected output (key lines):**
```
╔══════════════════════════════════════════════╗
║    MCP Demo Environment Bootstrap            ║
╚══════════════════════════════════════════════╝
[bootstrap] Checking prerequisites...
[ok] All prerequisites satisfied
[bootstrap] Creating kind cluster 'mcp-demo'...
[ok] Cluster created
[ok] KUBECONFIG exported to ~/.kube/mcp-demo.yaml
[ok] Namespaces and RBAC ready
[bootstrap] Building service images...
[ok] Observability stack installed
[ok] Alert rules applied
[ok] Dashboards loaded

╔══════════════════════════════════════════════════╗
║  Demo environment ready!                         ║
╚══════════════════════════════════════════════════╝
```

**Verify:**
```bash
make smoke
```
**Expected:**
```
✅  All 20 checks passed. Demo environment is ready.
```

**Troubleshoot:**
- `kind: command not found` → `brew install kind`
- `helm timeout` → re-run `make up` (Helm is idempotent)
- `Docker: permission denied` → make sure Docker Desktop is running
- `make smoke` shows `payment-service available: FAIL` → run `make recover && make smoke`

---

## STEP 4 — Set API key

You need an Anthropic API key (starts with `sk-ant-`).

**Option A — .env file (recommended for demo):**
```bash
echo 'ANTHROPIC_API_KEY=sk-ant-YOUR-KEY-HERE' > agent/.env
```

**Option B — environment variable:**
```bash
export ANTHROPIC_API_KEY=sk-ant-YOUR-KEY-HERE
```

**Option C — enter in browser UI during demo:**
Sidebar → AI Engine → paste key → Save & Test

**Verify (if using .env):**
```bash
grep -c ANTHROPIC_API_KEY agent/.env
```
**Expected:** `1`

**Note:** The .env file is gitignored. It will not be committed.

---

## STEP 5 — Start the agent server

**Command:**
```bash
make agent
```

**Expected output:**
```
[agent] Loaded ANTHROPIC_API_KEY from .env
[agent] Starting Prometheus port-forward → localhost:9092
[agent] Starting Alertmanager port-forward → localhost:9093
[agent] Starting Grafana port-forward → localhost:3002
[agent] Starting MCP Incident Agent on http://localhost:8082
[agent] Cluster:  kind-mcp-demo (kubeconfig: ~/.kube/mcp-demo.yaml:...)
[agent] Model:    configurable in browser UI (default: claude-3.5-haiku via OpenRouter)
[agent] Prometheus   → http://localhost:9092
[agent] Alertmanager → http://localhost:9093
[agent] Grafana      → http://localhost:3002

[agent] Open http://localhost:8082 in your browser

INFO:     Started server process [XXXXX]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8082 (Press CTRL+C to quit)
```

**Expected time:** 3–5 seconds

**Verify:**
```bash
curl -s http://localhost:8082/health
```
**Expected:**
```json
{"status": "ok", "model": "claude-3-5-haiku-latest"}
```

**Verify security default:**
```bash
curl -s http://localhost:8082/api/demo/security
```
**Expected:**
```json
{"security_on": true, "token": null}
```

**Troubleshoot:**
- `Address already in use` → `make agent` via start.sh auto-kills port 8082. If running server.py directly, kill manually: `kill $(lsof -ti :8082)`
- Port-forwards fail → check cluster is running: `kind get clusters`

---

## STEP 6 — Run preflight check

**Command:**
```bash
bash demo/preflight.sh
```

**Expected final output:**
```
✅  PREFLIGHT PASSED
   44 checks passed · 1 warnings · 0 critical failures

  You are CLEARED TO PRESENT.
```

**The one expected warning:**
```
⚠ WARN No ANTHROPIC_API_KEY set — you will need to enter it in the browser UI
```
This warning is fine if you plan to enter the key in the browser UI.
If you set agent/.env, this warning will not appear.

**Troubleshoot:** Any CRITICAL failure will print the exact fix command.

---

## STEP 7 — Run automated tests

**Command:**
```bash
make test
```

**Expected output:**
```
82 passed in 50.xx s
```

Note: E2E metrics tests (test_e01–e05) require port-forwards running.
If port-forwards are not running, these 5 tests skip automatically.

**Troubleshoot:**
- `ModuleNotFoundError: kubernetes` → re-run `pip install -r agent/requirements.txt`
- `asyncio` errors → ensure pytest-asyncio is installed: `pip install pytest-asyncio`

---

## STEP 8 — Open the browser

**Command:** Open in browser:
```
http://localhost:8082?mode=presentation
```

**Expected:** Full-screen demo UI with:
- Left sidebar: Demo Controls (Policy Gates toggle), AI Engine (key field)
- Center: Chat interface
- Right: Alert feed / Audit log

**Verify policy gates are ON:** Sidebar → Demo Controls → Policy Gates should show green ON.

---

## Clean install time summary

| Step | Expected time |
|---|---|
| Prerequisites | 10–15 min (once per machine) |
| `make up` (bootstrap) | 5–8 min |
| `pip install` | 1 min |
| `make agent` | 5 sec |
| `bash demo/preflight.sh` | 30 sec |
| **Total (after prerequisites)** | **~10 min** |

---

## Uninstall / cleanup

```bash
make down         # delete kind cluster
# optionally:
docker system prune -f   # reclaim Docker space
```
