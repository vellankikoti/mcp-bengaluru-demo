#!/usr/bin/env bash
set -euo pipefail
CTX="kind-mcp-demo"
export KUBECONFIG="${HOME}/.kube/mcp-demo.yaml"
K="kubectl --context=${CTX}"

PASS=0; FAIL=0
check() {
  local desc="$1"; shift
  if eval "$@" &>/dev/null; then
    echo "  ✓ $desc"
    ((PASS++)) || true
  else
    echo "  ✗ $desc"
    ((FAIL++)) || true
  fi
}

echo "=== MCP Demo Smoke Test ==="
echo ""
echo "Cluster:"
check "kind cluster running"             "kind get clusters | grep -q mcp-demo"
check "nodes ready"                      "$K get nodes | grep -v NotReady | grep -q Ready"

echo ""
echo "Namespaces:"
check "production namespace"             "$K get namespace production"
check "mcp-system namespace"             "$K get namespace mcp-system"
check "observability namespace"          "$K get namespace observability"

echo ""
echo "Services (production):"
check "payment-service available"        "$K -n production get deployment payment-service -o jsonpath='{.status.availableReplicas}' | grep -qv '^0$'"
check "auth-service available"           "$K -n production get deployment auth-service -o jsonpath='{.status.availableReplicas}' | grep -qv '^0$'"
check "notification-service available"  "$K -n production get deployment notification-service -o jsonpath='{.status.availableReplicas}' | grep -qv '^0$'"
check "order-service available"          "$K -n production get deployment order-service -o jsonpath='{.status.availableReplicas}' | grep -qv '^0$'"
check "email-gateway available"          "$K -n production get deployment email-gateway -o jsonpath='{.status.availableReplicas}' | grep -qv '^0$'"
check "traffic-gen running"              "$K -n production get deployment traffic-gen"

echo ""
echo "Observability:"
check "prometheus running"               "$K -n observability get pods -l app.kubernetes.io/name=prometheus --no-headers | grep -q Running"
check "grafana running"                  "$K -n observability get pods -l app.kubernetes.io/name=grafana --no-headers | grep -q Running"
check "prometheus port-forward (9092)"   "curl -sf http://localhost:9092/-/ready"
check "alertmanager port-forward (9093)" "curl -sf http://localhost:9093/-/ready"
check "grafana port-forward (3002)"      "curl -sf http://localhost:3002/api/health"

echo ""
echo "RBAC:"
check "mcp-agent service account"       "$K -n mcp-system get serviceaccount mcp-incident-agent"
check "mcp-agent cluster role binding"  "$K get clusterrolebinding mcp-incident-agent"

echo ""
echo "Health endpoints:"
# Quick pod exec smoke test
POD=$($K -n production get pod -l app=payment-service -o name 2>/dev/null | head -1)
if [[ -n "$POD" ]]; then
  # Use python3 urllib (curl not available in slim image)
  check "payment-service /health" \
    "$K -n production exec $POD -- python3 -c \"import urllib.request; r=urllib.request.urlopen('http://localhost:8080/health'); exit(0 if r.status==200 else 1)\""
  check "payment-service /metrics" \
    "$K -n production exec $POD -- python3 -c \"import urllib.request; d=urllib.request.urlopen('http://localhost:8080/metrics').read().decode(); exit(0 if 'payment_requests_total' in d else 1)\""
else
  echo "  - (no payment-service pod found)"
fi

echo ""
if [[ $FAIL -eq 0 ]]; then
  echo "✅  All $PASS checks passed. Demo environment is ready."
  exit 0
else
  echo "❌  $FAIL checks failed, $PASS passed."
  echo "   Run 'make up' to rebuild, or check: kubectl get pods -A"
  exit 1
fi
