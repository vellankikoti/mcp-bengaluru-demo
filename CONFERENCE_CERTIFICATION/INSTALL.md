# INSTALL.md
# From zero to demo-ready on any machine

This document works with any Kubernetes cluster — local (kind) or existing (kubeadm, GKE, EKS,
KillerCoda, etc.). Every command is verified. Follow every step in order.

---

## Prerequisites

### Required (always)

| Tool | Install — macOS | Install — Ubuntu/Debian | Verify |
|---|---|---|---|
| kubectl | `brew install kubectl` | `apt install kubectl` or via k8s docs | `kubectl version --client` |
| helm | `brew install helm` | `snap install helm --classic` | `helm version --short` |
| Python 3.9+ | `brew install python@3.11` | `apt install python3 python3-venv` | `python3 --version` |
| git | Pre-installed | `apt install git` | `git --version` |

### Required for a new cluster (skip if you have one already)

| Tool | Install — macOS | Install — Linux | Verify |
|---|---|---|---|
| Docker | Docker Desktop | `apt install docker.io` | `docker version` |
| kind | `brew install kind` | See kind.sigs.k8s.io | `kind version` |

> **KillerCoda / existing cluster**: you already have a cluster. You do NOT need kind or Docker.
> Jump straight to STEP 1.

### Your cluster

Any of these work:
- `kind` cluster (created by `make up` if kind is installed)
- KillerCoda playground (`kubectl get nodes` already works)
- kubeadm, GKE, EKS, AKS, minikube — any cluster where you have admin access

**Verify your cluster is reachable before proceeding:**
```bash
kubectl get nodes
```
Expected: at least one node in `Ready` state.

---

## STEP 1 — Clone the repo

**Command:**
```bash
git clone https://github.com/vellankikoti/mcp-bengaluru-demo.git mcp-bengaluru-demo
cd mcp-bengaluru-demo
```

**Expected output:**
```
Cloning into 'mcp-bengaluru-demo'...
remote: Counting objects: ...
```

**Verify:**
```bash
ls agent/ demo/ cluster/ tests/ Makefile README.md
```
**Expected:** No "No such file or directory" errors — all six must exist.

**Troubleshoot:** If git fails, check your SSH key or use HTTPS URL.

---

## STEP 2 — Create virtualenv and install Python dependencies

**Commands:**
```bash
python3 -m venv venv
source venv/bin/activate
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

> **IMPORTANT — activate the venv in every new terminal before running any commands:**
> ```bash
> source venv/bin/activate
> ```
> Your prompt will show `(venv)` when active. All `make` commands, `python3`, and `pytest` run
> from inside this directory require the venv to be active.

**Troubleshoot:**
- `externally-managed-environment` error → you skipped the venv step. Run `python3 -m venv venv && source venv/bin/activate` first.
- `python3 -m venv` fails → install: `apt install python3-venv` (Debian/Ubuntu) or `brew install python@3.11` (macOS)
- Permission denied → do not use `sudo`; venv installs into the local directory

---

## STEP 3 — Bootstrap the demo environment

**Command:**
```bash
make up
```

**What this does (cluster-agnostic):**
- If `kubectl get nodes` already works → uses your existing cluster
- If `kind` is installed and no cluster exists → creates a kind cluster
- Deploys 6 microservices, installs kube-prometheus-stack via Helm, applies RBAC

**Expected output (existing cluster path):**
```
╔══════════════════════════════════════════════╗
║    MCP Demo Environment Bootstrap            ║
╚══════════════════════════════════════════════╝
[bootstrap] Using existing cluster: context=<your-context>
[ok] Namespaces and RBAC ready
[bootstrap] Building service images...
[ok] All images built
[ok] Image loading complete
[ok] Services deployed
[ok] Observability stack installed
[ok] Alert rules applied
[ok] Dashboards loaded

╔══════════════════════════════════════════════════╗
║  Demo environment ready!                         ║
╚══════════════════════════════════════════════════╝
```

**Expected time:**
- Existing cluster: 5–8 minutes (Helm install dominates)
- New kind cluster: 8–12 minutes

**Verify:**
```bash
make smoke
```
**Expected:**
```
✅  All 20 checks passed. Demo environment is ready.
```

**Troubleshoot:**
- `No reachable cluster found and kind is not installed` → ensure your cluster is reachable: `kubectl get nodes`
- `helm timeout` → re-run `make up` (Helm is idempotent)
- `ImagePullBackOff` on pods → Docker not available for image build; see README for alternative
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
- `ModuleNotFoundError: kubernetes` → venv not active. Run `source venv/bin/activate` then retry.
- `asyncio` errors → venv not active, or: `pip install pytest-asyncio` inside the venv.

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
| `python3 -m venv venv && pip install` | 1 min |
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
