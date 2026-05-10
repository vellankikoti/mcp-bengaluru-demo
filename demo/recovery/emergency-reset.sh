#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
CTX="kind-mcp-demo"
export KUBECONFIG="${HOME}/.kube/mcp-demo.yaml"
K="kubectl --context=${CTX}"

echo "⚡ EMERGENCY RESET — 30 second rebuild"
START=$(date +%s)

# Kill any stuck port-forwards
pkill -f "kubectl.*port-forward" 2>/dev/null || true

# Reset all fault injections immediately
$K -n production set env deployment/payment-service FAULT_MODE=healthy FAULT_PROBABILITY=0.0 SERVICE_VERSION=v1 2>/dev/null || true
$K -n production set env deployment/notification-service FAULT_MODE=healthy 2>/dev/null || true
$K -n production set env deployment/auth-service FAULT_MODE=healthy 2>/dev/null || true

# Restore memory limit
$K -n production set resources deployment/payment-service \
  --limits=memory=256Mi -c payment 2>/dev/null || true

# Remove taints
for node in $($K get nodes -o name 2>/dev/null); do
  $K taint node "$node" demo.mcp.io/unavailable:NoSchedule- 2>/dev/null || true
done

# Restore CoreDNS if backup exists
CHECKPOINT="/tmp/mcp-demo-checkpoint"
if [[ -f "$CHECKPOINT/coredns.yaml" ]]; then
  $K apply -f "$CHECKPOINT/coredns.yaml" 2>/dev/null || true
  $K -n kube-system rollout restart deployment/coredns 2>/dev/null || true
fi

# Scale to normal
$K -n production scale deployment order-service --replicas=2 2>/dev/null || true

# Restart all production deployments
$K -n production rollout restart deployment --all 2>/dev/null || true

# Wait
$K -n production wait --for=condition=available deployment --all --timeout=60s 2>/dev/null || true

END=$(date +%s)
echo "✅ Emergency reset complete in $((END - START))s"
$K -n production get pods --no-headers
