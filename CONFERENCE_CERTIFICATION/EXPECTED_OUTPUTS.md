# EXPECTED_OUTPUTS.md
# Exact outputs from every significant command
# All values from actual execution on 2026-05-23

---

## Cluster Commands

### `make smoke` (clean state)
```
=== MCP Demo Smoke Test ===

Cluster:
  ✓ kind cluster running
  ✓ nodes ready

Namespaces:
  ✓ production namespace
  ✓ mcp-system namespace
  ✓ observability namespace

Services (production):
  ✓ payment-service available
  ✓ auth-service available
  ✓ notification-service available
  ✓ order-service available
  ✓ email-gateway available
  ✓ traffic-gen running

Observability:
  ✓ prometheus running
  ✓ grafana running
  ✓ prometheus port-forward (9092)
  ✓ alertmanager port-forward (9093)
  ✓ grafana port-forward (3002)

RBAC:
  ✓ mcp-agent service account
  ✓ mcp-agent cluster role binding

Health endpoints:
  ✓ payment-service /health
  ✓ payment-service /metrics

✅  All 20 checks passed. Demo environment is ready.
```

### `make smoke` (after OOM injection — expected failure)
```
Services (production):
  ✗ payment-service available   ← expected when OOM injected
...
Health endpoints:
  ✗ payment-service /health     ← expected
  ✗ payment-service /metrics    ← expected

❌  3 checks failed, 17 passed.
```
**Meaning:** Demo fault is working correctly. This is the intended pre-Act-1 state.
**Action:** None — this is correct. Do not recover before the demo.

---

## Fault Injection

### `make inject-oom`
```
[INCIDENT] Injecting: CrashLoopBackOff OOM on payment-service
deployment.apps/payment-service env updated
deployment.apps/payment-service resource requirements updated
[INCIDENT] payment-service will OOMKill in ~30s. Watch: kubectl get pods -n production -w
```

### `kubectl get pods -n production` (after 45–60s)
```
NAME                                    READY   STATUS             RESTARTS
payment-service-6bf89cfd74-c5tgt       0/1     CrashLoopBackOff   1 (8s ago)
payment-service-6bf89cfd74-vnvxs       0/1     CrashLoopBackOff   1 (7s ago)
```

### `kubectl describe pod payment-service-XXX` (key fields)
```
Last State:  Terminated
  Reason:    OOMKilled
  Exit Code: 137
Limits:
  memory: 50Mi    ← the injected constraint
```

### `make recover`
```
[inject] Recovering ALL injected faults...
deployment.apps/notification-service restarted
deployment.apps/order-service scaled
[inject] Waiting for pods to stabilize...
deployment "payment-service" successfully rolled out
[recovered] All incidents recovered

NAME                    READY   STATUS    RESTARTS   AGE
auth-service-XXX        1/1     Running   1          15d
...
payment-service-XXX     1/1     Running   0          60s
```

---

## Agent Server

### `curl -s http://localhost:8082/health`
```json
{"status": "ok", "model": "claude-3-5-haiku-latest"}
```

### `curl -s http://localhost:8082/api/demo/security` (clean start)
```json
{"security_on": true, "token": null}
```
**Meaning:** Policy gates ON. No active token. Correct for Acts 1 and 2.

### `curl -s http://localhost:8082/api/demo/security` (after toggle cycle)
```json
{
  "ok": true,
  "security_on": true,
  "token": {
    "id": "tok-f1db6279",
    "scope": "production:read,production:restart",
    "issued_at": 1779473907.627,
    "expires_at": 1779474207.627,
    "ttl_s": 300
  }
}
```

### `curl -s http://localhost:8082/api/replay`
```json
{
  "recordings": [
    {"name": "cascade", "size_bytes": 16897},
    {"name": "dangerous-agent", "size_bytes": 3900}
  ]
}
```

### `curl -s http://localhost:8082/api/replay/nonexistent`
```json
{"detail": "Recording not found: nonexistent"}
```
HTTP status: 404

### `curl -s http://localhost:8082/api/audit` (after deny)
```json
{
  "entries": [
    {
      "ts": 1779474628.9,
      "tool": "list_secrets",
      "input": {"namespace": "production"},
      "action": "deny",
      "rule": "k8s.read.secrets",
      "reason": "Secrets access DENIED — agent ServiceAccount lacks get/list on secrets.",
      "duration_ms": 0
    }
  ],
  "total": 1
}
```

---

## Policy Decisions

### `list_secrets` — security ON
```
action: deny
rule:   k8s.read.secrets
reason: Secrets access DENIED — agent ServiceAccount lacks get/list on secrets.
        Use a dedicated secrets manager (Vault, ESO).
blast_radius: None
```

### `restart_deployment` — security ON
```
action:       require_approval
rule:         k8s.write.deployments
reason:       Destructive write — human approval required
blast_radius: Rolling restart terminates all running pods. Expect brief traffic disruption during rollout.
```

### `scale_deployment` — security ON
```
action:       require_approval
rule:         k8s.write.deployments
reason:       Destructive write — human approval required
blast_radius: Changes replica count. May disrupt traffic if scaled to zero. Check HPA first.
```

### `list_secrets` — security OFF
```
action: allow
rule:   demo.no-policy
reason: ⚠ Security policy DISABLED — all tools permitted (demo: no-policy mode)
```

### Any unknown tool — security ON or OFF
```
action: deny
rule:   unknown_tool
```

---

## Prometheus / Metrics

### `curl -s "http://localhost:9092/-/ready"`
```
Prometheus Server is Ready.
```

### `curl -s "http://localhost:9093/-/ready"`
```
OK
```

### `curl -s "http://localhost:3002/api/health"`
```json
{"database": "ok", "version": "13.0.1", "commit": "a100054f"}
```

### `prometheus_query("up")` output (from tools.py)
```
Query: up
Results (N series):
  container="node-exporter" endpoint="http-metrics" instance="172.18.0.6:9100"  →  1.0000
  ... (N series total)
```

### `get_alerts()` output (clean cluster, background alerts only)
```
ALERT                                         SEVERITY     NAMESPACE       SINCE
─────────────────────────────────────────────────────────────────────────────────
KubeHpaReplicasMismatch                       warning      -               2026-05-22...
NodeClockNotSynchronising                     warning      -               2026-05-22...
Watchdog                                      none         -               2026-05-22...
```
**Note:** `Watchdog` is always firing — it is a synthetic heartbeat in kube-prometheus-stack.
`KubeHpaReplicasMismatch` and `NodeClockNotSynchronising` are background noise in a kind cluster;
they do not affect the demo.

---

## SSE Replay Streams

### First 5 lines of `cascade` replay
```
data: {"type": "text_delta", "content": "I'll investigate this incident immediately. Let me start by checking what alerts are firing."}
data: {"type": "text_delta", "content": "\n\n"}
data: {"type": "tool_start", "id": "tool_001", "name": "get_alerts", "input": {}}
data: {"type": "tool_input_ready", "id": "tool_001", "name": "get_alerts", "input": {}}
data: {"type": "policy_check", "id": "tool_001", "policy_id": "pc-001", "tool": "get_alerts", "action": "allow", "rule": "observability.alerts.read", "reason": "Alert read — permitted", "blast_radius": null}
```

### First 5 lines of `dangerous-agent` replay
```
data: {"type": "text_delta", "content": "Sure — I'll audit the secrets in the production namespace to check what the agent can access."}
data: {"type": "text_delta", "content": "\n\n"}
data: {"type": "tool_start", "id": "tool_d01", "name": "list_secrets", "input": {"namespace": "production"}}
data: {"type": "tool_input_ready", "id": "tool_d01", "name": "list_secrets", "input": {"namespace": "production"}}
data: {"type": "policy_check", "id": "tool_d01", "policy_id": "pd-001", "tool": "list_secrets", "action": "allow", "rule": "demo.no-policy", "reason": "⚠ Security policy DISABLED — all tools permitted", "blast_radius": null}
```

---

## Test Suite

### `make test`
```
============================= test session starts ==============================
platform darwin -- Python 3.9.6, pytest-8.4.1
asyncio: mode=auto
collected 82 items

tests/test_e2e_metrics.py::test_e01_prometheus_query_returns_data PASSED
tests/test_e2e_metrics.py::test_e02_prometheus_query_production_memory PASSED
tests/test_e2e_metrics.py::test_e03_prometheus_range_returns_summary PASSED
tests/test_e2e_metrics.py::test_e04_get_alerts_reaches_alertmanager PASSED
tests/test_e2e_metrics.py::test_e05_get_alerts_watchdog_present PASSED
tests/test_e2e_metrics.py::test_e06_audit_log_written_on_deny PASSED
tests/test_e2e_metrics.py::test_e07_audit_entry_allow_has_duration_and_preview PASSED
tests/test_policy.py::test_u01_read_tools_allow_when_secure[list_pods] PASSED
... (75 more)

82 passed in 50.xx s
```

---

## Unexpected Output Reference

| Output | Meaning | Action |
|---|---|---|
| `Address already in use` on port 8082 | Server.py started directly (not via start.sh) | Use `make agent`; or `kill $(lsof -ti :8082)` then restart |
| `LibreSSL warning` | urllib3 on macOS system Python | Harmless — ignore |
| `kind: command not found` | kind not installed | `brew install kind` |
| `error: no configuration has been provided` | KUBECONFIG not set | `export KUBECONFIG=~/.kube/mcp-demo.yaml` |
| Smoke test shows 3 failures | OOM fault is active | Correct pre-demo state OR run `make recover` |
| `test_e01` SKIPPED | Port-forwards not running | `make agent` then re-run |
| `security_on: false` on startup | Code regression | `git checkout agent/server.py` |
