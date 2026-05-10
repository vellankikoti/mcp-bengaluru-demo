#!/usr/bin/env bash
set -euo pipefail
CTX="kind-mcp-demo"
export KUBECONFIG="${HOME}/.kube/mcp-demo.yaml"
CHECKPOINT="/tmp/mcp-demo-checkpoint"
mkdir -p "$CHECKPOINT"

echo "[checkpoint] Saving cluster state..."
kubectl --context="$CTX" get deployments -n production -o yaml > "$CHECKPOINT/deployments-production.yaml"
kubectl --context="$CTX" get deployments -n staging -o yaml > "$CHECKPOINT/deployments-staging.yaml" 2>/dev/null || true
kubectl --context="$CTX" -n kube-system get configmap coredns -o yaml > "$CHECKPOINT/coredns.yaml"
kubectl --context="$CTX" get nodes -o yaml > "$CHECKPOINT/nodes.yaml"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$CHECKPOINT/timestamp"
echo "[checkpoint] Saved to $CHECKPOINT"
