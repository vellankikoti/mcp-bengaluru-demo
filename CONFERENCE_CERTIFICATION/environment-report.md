# Environment Report
# MCP Dev Summit Bengaluru 2026 — Certification Run
# Generated: 2026-05-23 00:01 IST

All values below are from actual command execution on the presenter's machine.

---

## System

| Item | Detected | Required | Pass/Fail |
|---|---|---|---|
| OS | macOS 26.4.1 (Darwin 25.4.0) | macOS 13+ or Linux | PASS |
| CPU | Apple M4 | Any modern CPU | PASS |
| Cores | 10 logical | 4+ | PASS |
| RAM | 16 GB | 8 GB minimum, 16 GB recommended | PASS |
| Disk free | 21 GB | 10 GB minimum | PASS |

---

## Required Tools

| Tool | Detected version | Required | Path | Pass/Fail |
|---|---|---|---|---|
| Docker | Client 29.4.1 / Server 29.4.1 | ≥ 24.0 | /usr/local/bin/docker | PASS |
| kind | v0.29.0 go1.24.3 darwin/arm64 | ≥ 0.20 | /opt/homebrew/bin/kind | PASS |
| kubectl | v1.34.1 (Kustomize v5.7.1) | ≥ 1.28 | /usr/local/bin/kubectl | PASS |
| helm | v3.19.1+g4f953c2 | ≥ 3.12 | /opt/homebrew/bin/helm | PASS |
| python3 | 3.9.6 | ≥ 3.9 | /Library/Developer/CommandLineTools/usr/bin/python3 | PASS |
| curl | 8.7.1 | Any | /usr/bin/curl | PASS |
| lsof | system (macOS built-in) | macOS built-in | /usr/sbin/lsof | PASS |

---

## Python Packages

| Package | Detected | Required | Pass/Fail |
|---|---|---|---|
| anthropic | 0.100.0 | ≥ 0.40.0 | PASS |
| fastapi | 0.128.8 | ≥ 0.115.0 | PASS |
| uvicorn | 0.39.0 | ≥ 0.30.0 | PASS |
| httpx | 0.28.1 | ≥ 0.27.0 | PASS |
| kubernetes | 33.1.0 | ≥ 29.0.0 | PASS |
| pydantic | 2.13.4 | ≥ 2.0 | PASS |
| pytest | 8.4.1 | ≥ 8.0 | PASS |
| pytest-asyncio | 1.0.0 | ≥ 0.23 | PASS |

---

## Cluster State

| Item | Detected | Required | Pass/Fail |
|---|---|---|---|
| Kind cluster name | mcp-demo | mcp-demo | PASS |
| Cluster node status | Ready | Ready | PASS |
| Kubernetes version | v1.33.1 | ≥ 1.28 | PASS |
| Kubeconfig path | ~/.kube/mcp-demo.yaml | ~/.kube/mcp-demo.yaml | PASS |
| Context name | kind-mcp-demo | kind-mcp-demo | PASS |

### Namespaces (all required)

| Namespace | Status |
|---|---|
| production | Active |
| observability | Active |
| mcp-system | Active |
| staging | Active |

### Production Pods (clean baseline)

| Pod | Status | Restarts |
|---|---|---|
| payment-service (×2) | Running | 0 |
| order-service (×2) | Running | 3 |
| auth-service (×2) | Running | 1–2 |
| notification-service | Running | 0 |
| email-gateway | Running | 2 |
| traffic-gen | Running | 0 |

> Note: Restarts on long-lived pods (order-service, auth-service) are expected — they reflect
> 15 days of uptime on a kind cluster. Zero restarts after a fresh `make up`.

---

## Observability Stack

| Component | Pod Status | Port-forward | URL | Pass/Fail |
|---|---|---|---|---|
| Prometheus | Running (2/2) | :9092 | http://localhost:9092 | PASS |
| Alertmanager | Running (2/2) | :9093 | http://localhost:9093 | PASS |
| Grafana | Running (3/3) | :3002 | http://localhost:3002 | PASS |
| kube-state-metrics | Running (1/1) | — | — | PASS |
| node-exporter | Running (1/1) | — | — | PASS |
| prometheus-operator | Running (1/1) | — | — | PASS |

---

## Demo-Specific State

| Item | Detected | Required | Pass/Fail |
|---|---|---|---|
| Policy gates default | ON (security_on=true) | ON | PASS |
| cascade.jsonl | 42 events, 16897 bytes | ≥ 40 events | PASS |
| dangerous-agent.jsonl | 10 events, 3900 bytes | ≥ 8 events | PASS |
| No secret values in recording | Confirmed | Confirmed | PASS |
| RBAC ServiceAccount | mcp-incident-agent present | Present | PASS |
| ClusterRoleBinding | mcp-incident-agent present | Present | PASS |

---

## Ports

| Port | Purpose | Status at certification |
|---|---|---|
| 8082 | Agent server (FastAPI) | FREE (start with `make agent`) |
| 9092 | Prometheus port-forward | IN USE by kubectl |
| 9093 | Alertmanager port-forward | IN USE by kubectl |
| 3002 | Grafana port-forward | IN USE by kubectl |

---

## API Key

| Item | Status |
|---|---|
| ANTHROPIC_API_KEY in env | NOT SET |
| ANTHROPIC_API_KEY in agent/.env | NOT SET |

> The key must be entered in the browser UI before the demo (Sidebar → AI Engine → paste key).
> Alternatively: `echo 'ANTHROPIC_API_KEY=sk-ant-...' > agent/.env` before `make agent`.

---

## Known Non-Issues

- **LibreSSL warning**: `urllib3 v2 only supports OpenSSL 1.1.1+` — macOS system Python uses
  LibreSSL. This is a warning only; all network calls work correctly.
- **Two kind clusters**: `desktop` and `mcp-demo` both exist. The demo uses `kind-mcp-demo` exclusively.
- **Docker image count**: 199 images in Docker. Not a problem; demo images are already loaded.

---

## Overall: PASS

All required tools present. Cluster healthy. Observability wired. Policy gates correct.
