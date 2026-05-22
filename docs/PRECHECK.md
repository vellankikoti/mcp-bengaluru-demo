# PRECHECK.md
# Pre-show safety checks — run 30 minutes before stage

All outputs below are from actual execution on 2026-05-23.

---

## Run this command first

```bash
bash demo/preflight.sh
```

If it exits 0 and prints `CLEARED TO PRESENT` — you are done. Go to RUNBOOK.md.

If it exits 1 — read the CRITICAL failures and apply the recovery command printed beside each one.

---

## What preflight.sh checks (44 checks with kind+docker present, 42 without)

### Section 1: Required Tools
| Check | Success output | Failure output | Recovery |
|---|---|---|---|
| kubectl | `✓ kubectl found (...)` | `✗ CRITICAL kubectl not found` | `brew install kubectl` or via k8s docs |
| helm | `✓ helm found (...)` | `✗ CRITICAL helm not found` | `brew install helm` |
| python3 | `✓ python3 found (...)` | `✗ CRITICAL python3 not found` | `brew install python3` |
| curl | `✓ curl found (...)` | `✗ CRITICAL curl not found` | macOS built-in; reinstall Xcode tools |
| lsof | `✓ lsof found (...)` | `✗ CRITICAL lsof not found` | macOS built-in; reinstall Xcode tools |
| docker *(optional)* | `✓ docker found (...) — optional` | `⚠ WARN docker not found — only needed for new cluster` | Skip if using existing cluster |
| kind *(optional)* | `✓ kind found (...) — optional` | `⚠ WARN kind not found — only needed for new cluster` | Skip if using existing cluster |

### Section 2: Kubernetes Cluster
| Check | Success output | Failure output | Recovery |
|---|---|---|---|
| Context found | `✓ kubectl context: <your-context>` | `✗ CRITICAL No kubectl context found` | Set KUBECONFIG or KUBE_CONTEXT env var |
| Cluster reachable | `✓ cluster reachable` | `✗ CRITICAL cluster not reachable` | Check kubeconfig and cluster status |
| Node Ready | `✓ N node(s) Ready` | `✗ CRITICAL no Ready nodes found` | `kubectl get nodes` to diagnose |

### Section 4: Production Pods
| Check | Success output | Failure output | Recovery |
|---|---|---|---|
| payment-service | `✓ payment-service: 2 replica(s) available` | `✗ CRITICAL payment-service not available` | `make recover` then wait 60s |
| order-service | `✓ order-service: 2 replica(s) available` | `✗ CRITICAL order-service not available` | `make recover` |
| auth-service | `✓ auth-service: 2 replica(s) available` | `✗ CRITICAL auth-service not available` | `make recover` |
| notification-service | `✓ notification-service: 1 replica(s) available` | `✗ CRITICAL` | `make recover` |
| email-gateway | `✓ email-gateway: 1 replica(s) available` | `✗ CRITICAL` | `make recover` |
| traffic-gen | `✓ traffic-gen: 1 replica(s) available` | `✗ CRITICAL` | `make recover` |
| No crashing pods | `✓ no crashing pods (clean baseline)` | `⚠ WARN N pod(s) crashing` | `make recover` if unintentional |

> If you already ran `make inject-oom`, payment-service will show as crashing. That is expected
> and will show as a WARN, not a CRITICAL. Only recover if you didn't mean to inject.

### Section 5: Observability Stack
| Check | Success output | Failure output | Recovery |
|---|---|---|---|
| Prometheus pod | `✓ Prometheus pod Running` | `✗ CRITICAL Prometheus not running` | `make up` (reinstalls stack) |
| Grafana pod | `✓ Grafana pod Running` | `✗ CRITICAL Grafana not running` | `make up` |
| Prometheus port-forward :9092 | `✓ Prometheus(9092) port-forward alive` | `⚠ WARN not responding` | `make agent` |
| Alertmanager port-forward :9093 | `✓ Alertmanager(9093) port-forward alive` | `⚠ WARN not responding` | `make agent` |
| Grafana port-forward :3002 | `✓ Grafana(3002) port-forward alive` | `⚠ WARN not responding` | `make agent` |

### Section 6: RBAC
| Check | Success output | Failure output | Recovery |
|---|---|---|---|
| ServiceAccount | `✓ mcp-incident-agent ServiceAccount present` | `✗ CRITICAL` | `make up` |
| ClusterRoleBinding | `✓ mcp-incident-agent ClusterRoleBinding present` | `✗ CRITICAL` | `make up` |

### Section 7: Agent Server
| Check | Success output | Failure output | Recovery |
|---|---|---|---|
| Server running | `✓ Agent server running on port 8082` | `⚠ WARN Agent server not running` | `make agent` |
| Policy gates | `✓ Policy Gates: ON ✓` | `⚠ WARN Policy Gates: OFF` | Press F4 in browser, or toggle in Demo Controls |
| Recordings | `✓ Recordings available: 2` | `⚠ WARN Expected 2 recordings, found N` | Check agent/demo-recordings/ |

### Section 8: AI Provider
| Check | Success output | Failure output | Recovery |
|---|---|---|---|
| AI provider configured | `✓ AI provider configured: <source>` | `⚠ WARN No AI provider configured` | Enter key or URL in browser UI (Sidebar → AI Engine) |

> This is a WARN, not a CRITICAL. Supports Anthropic, OpenAI, OpenRouter, Groq, Google AI, Ollama.
> You can enter the key in the browser UI during the demo. Any provider key or `AI_BASE_URL` for Ollama satisfies this check.

### Section 9: Demo Recordings
| Check | Success output | Failure output | Recovery |
|---|---|---|---|
| cascade.jsonl | `✓ cascade.jsonl present (42 events, 16897 bytes)` | `✗ CRITICAL missing` | Check git: `git checkout agent/demo-recordings/cascade.jsonl` |
| dangerous-agent.jsonl | `✓ dangerous-agent.jsonl present (10 events, 3900 bytes)` | `✗ CRITICAL missing` | `git checkout agent/demo-recordings/dangerous-agent.jsonl` |
| No secret values | `✓ dangerous-agent.jsonl: no secret values` | `✗ CRITICAL contains forbidden secret values!` | `git checkout agent/demo-recordings/dangerous-agent.jsonl` |

### Section 10: Python Dependencies
| Check | Success output | Failure output | Recovery |
|---|---|---|---|
| Each of 6 packages | `✓ fastapi importable`, etc. | `✗ CRITICAL X not installed` | `source venv/bin/activate && pip install -r agent/requirements.txt` |

### Section 11: Ports
| Check | Success output | Failure output | Recovery |
|---|---|---|---|
| Port 8082 | `✓ Port 8082 in use by '...' (agent server expected)` | `⚠ WARN Port 8082 free — agent not started` | `make agent` |
| Port 9092 | `✓ Port 9092 in use by 'kubectl'` | `⚠ WARN port-forward not running` | `make agent` |
| Port 9093 | `✓ Port 9093 in use by 'kubectl'` | `⚠ WARN` | `make agent` |
| Port 3002 | `✓ Port 3002 in use by 'kubectl'` | `⚠ WARN` | `make agent` |

### Section 12: System Resources
| Check | Success output | Failure output | Recovery |
|---|---|---|---|
| Free disk | `✓ Free disk: 21GB (> 5GB required)` | `⚠ WARN Free disk low` | `docker system prune -f` |

### Section 13: Automated Tests
| Check | Success output | Failure output | Recovery |
|---|---|---|---|
| Unit tests | `✓ Unit tests: 56 passed in 0.03s` | `✗ CRITICAL Unit tests FAILED` | Run `make test` for detail |

> Note: preflight.sh runs only policy + recording tests (56 tests, fast).
> Full 82-test suite (including E2E metrics) runs via `make test`.

### Section 14: Security Invariant (AST check)
| Check | Success output | Failure output | Recovery |
|---|---|---|---|
| _security_on default | `✓ _security_on defaults to True in server.py` | `✗ CRITICAL _security_on is not True` | `git checkout agent/server.py` |

---

## Full passing preflight output (representative — your paths and context name will differ)

```
╔══════════════════════════════════════════════╗
║  PREFLIGHT CHECK — Conference Demo Safety    ║
╚══════════════════════════════════════════════╝

  Context: <your-kubectl-context>
  Time:    <current date/time>

── Required Tools ──
  ✓ kubectl found (/usr/local/bin/kubectl)
  ✓ helm found (/opt/homebrew/bin/helm)
  ✓ python3 found (/usr/bin/python3)
  ✓ curl found (/usr/bin/curl)
  ✓ lsof found (/usr/sbin/lsof)
  ✓ docker found (/usr/local/bin/docker) — optional
  ✓ kind found (/opt/homebrew/bin/kind) — optional

── Kubernetes Cluster ──
  ✓ kubectl context: <your-context>
  ✓ cluster reachable
  ✓ 1 node(s) Ready

── Production Pods ──
  ✓ payment-service: 2 replica(s) available
  ✓ order-service: 2 replica(s) available
  ✓ auth-service: 2 replica(s) available
  ✓ notification-service: 1 replica(s) available
  ✓ email-gateway: 1 replica(s) available
  ✓ traffic-gen: 1 replica(s) available
  ✓ no crashing pods (clean baseline)

── Observability Stack ──
  ✓ Prometheus pod Running
  ✓ Grafana pod Running
  ✓ Prometheus(9092) port-forward alive
  ✓ Alertmanager(9093) port-forward alive
  ✓ Grafana(3002) port-forward alive

── RBAC ──
  ✓ mcp-incident-agent ServiceAccount present
  ✓ mcp-incident-agent ClusterRoleBinding present

── Agent Server ──
  ✓ Agent server running on port 8082
  ✓ Policy Gates: ON ✓ (correct for Acts 1 and 2)
  ✓ Recordings available: 2 (cascade + dangerous-agent)

── AI Provider ──
  ⚠ WARN No AI provider configured — enter key or URL in browser UI (Sidebar → AI Engine)

── Demo Recordings ──
  ✓ cascade.jsonl present (42 events, 16897 bytes)
  ✓ dangerous-agent.jsonl present (10 events, 3900 bytes)
  ✓ dangerous-agent.jsonl: no secret values (truth guarantee met)

── Python Dependencies ──
  ✓ fastapi importable
  ✓ anthropic importable
  ✓ uvicorn importable
  ✓ httpx importable
  ✓ kubernetes importable
  ✓ pydantic importable

── Port Availability ──
  ✓ Port 8082 in use by 'Python' (agent server expected)
  ✓ Port 9092 in use by 'kubectl' (port-forward expected)
  ✓ Port 9093 in use by 'kubectl' (port-forward expected)
  ✓ Port 3002 in use by 'kubectl' (port-forward expected)

── System Resources ──
  ✓ Free disk: 21GB (> 5GB required)

── Automated Tests ──
  ✓ Unit tests: 56 passed in 0.03s

── Security Invariant (AST check) ──
  ✓ _security_on defaults to True in server.py (critical invariant)

══════════════════════════════════════════════
✅  PREFLIGHT PASSED
   44 checks passed · 1 warnings · 0 critical failures

  You are CLEARED TO PRESENT.

  Pre-talk checklist:
  1. make inject-oom              (60s before Act 1)
  2. Browser at http://localhost:8082?mode=presentation
  3. Sidebar: Policy Gates ON, AI key green
  4. Demo menu → Reset demo to start
```

---

## What preflight does NOT check

These require the full `make test` to validate:
- Live Prometheus queries (`test_e01`–`test_e03`)
- Live Alertmanager responses (`test_e04`–`test_e05`)
- Audit log field completeness (`test_e06`–`test_e07`)

Run `make test` once before the day of talk to confirm E2E metrics.
