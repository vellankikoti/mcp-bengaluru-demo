#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
CLUSTER_NAME="mcp-demo"
CONTEXT="kind-${CLUSTER_NAME}"
KUBECONFIG_PATH="${HOME}/.kube/mcp-demo.yaml"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
log()  { echo -e "${CYAN}[bootstrap]${RESET} $*"; }
ok()   { echo -e "${GREEN}[ok]${RESET} $*"; }
warn() { echo -e "${YELLOW}[warn]${RESET} $*"; }
die()  { echo -e "${RED}[error]${RESET} $*" >&2; exit 1; }

echo -e "${BOLD}"
echo "╔══════════════════════════════════════════════╗"
echo "║    MCP Demo Environment Bootstrap            ║"
echo "╚══════════════════════════════════════════════╝"
echo -e "${RESET}"

# ── Prerequisites ───────────────────────────────────
log "Checking prerequisites..."
for cmd in kind kubectl docker helm python3; do
  command -v "$cmd" &>/dev/null || die "$cmd not found. Install it first."
done

DOCKER_RUNNING=$(docker info &>/dev/null && echo yes || echo no)
[[ "$DOCKER_RUNNING" == "yes" ]] || die "Docker is not running."
ok "All prerequisites satisfied"

mkdir -p /tmp/mcp-demo-audit

# ── Kind cluster ─────────────────────────────────────
if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
  warn "Cluster '${CLUSTER_NAME}' already exists. Skipping creation."
  warn "Run 'make down && make up' to rebuild from scratch."
else
  log "Creating kind cluster '${CLUSTER_NAME}'..."
  kind create cluster \
    --name "$CLUSTER_NAME" \
    --config "$ROOT/cluster/kind-config.yaml" \
    --wait 120s
  ok "Cluster created"
fi

# Export kubeconfig
kind export kubeconfig --name "$CLUSTER_NAME" --kubeconfig "$KUBECONFIG_PATH"
export KUBECONFIG="$KUBECONFIG_PATH"
ok "KUBECONFIG exported to $KUBECONFIG_PATH"

# ── Namespaces + RBAC ────────────────────────────────
log "Applying namespaces and RBAC..."
kubectl --context="$CONTEXT" apply -f "$ROOT/cluster/namespaces.yaml"
kubectl --context="$CONTEXT" apply -f "$ROOT/cluster/rbac/"
ok "Namespaces and RBAC ready"

# ── Build service images ─────────────────────────────
log "Building service images..."
SERVICES=(payment-service auth-service notification-service order-service email-gateway traffic-gen)
for svc in "${SERVICES[@]}"; do
  SVC_DIR="$ROOT/services/$svc"
  [[ -d "$SVC_DIR" ]] || { warn "Service dir missing: $SVC_DIR"; continue; }
  log "  Building mcp-demo/$svc:latest ..."
  docker build -t "mcp-demo/${svc}:latest" "$SVC_DIR" --quiet
  kind load docker-image "mcp-demo/${svc}:latest" --name "$CLUSTER_NAME"
  ok "  $svc loaded into cluster"
done

# ── Deploy services ──────────────────────────────────
log "Deploying microservices..."
for svc in "${SERVICES[@]}"; do
  K8S_DIR="$ROOT/services/$svc/k8s"
  [[ -d "$K8S_DIR" ]] || continue
  kubectl --context="$CONTEXT" apply -f "$K8S_DIR/" 2>/dev/null || true
done
ok "Services deployed"

# ── Observability stack ──────────────────────────────
log "Installing observability stack (this takes ~3 minutes)..."
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts --force-update 2>/dev/null
helm repo update 2>/dev/null

kubectl --context="$CONTEXT" create namespace observability --dry-run=client -o yaml | \
  kubectl --context="$CONTEXT" apply -f -

helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --kube-context "$CONTEXT" \
  --namespace observability \
  --values "$ROOT/observability/prometheus/values.yaml" \
  --wait \
  --timeout 10m \
  --set grafana.adminPassword=admin \
  2>&1 | tail -5

ok "Observability stack installed"

# ── PrometheusRules ──────────────────────────────────
log "Applying SLO alert rules..."
kubectl --context="$CONTEXT" apply -f "$ROOT/observability/prometheus/rules/"
ok "Alert rules applied"

# ── Grafana dashboards ───────────────────────────────
log "Loading Grafana dashboards..."
bash "$ROOT/observability/load-dashboards.sh"
ok "Dashboards loaded"

# ── Wait for services ────────────────────────────────
log "Waiting for all production deployments to be ready..."
kubectl --context="$CONTEXT" -n production wait \
  --for=condition=available deployment \
  --all --timeout=120s 2>/dev/null || \
  warn "Some deployments not ready yet — check with: kubectl get pods -n production"

# ── Save checkpoint ──────────────────────────────────
"$SCRIPT_DIR/recovery/save-checkpoint.sh"

# ── Done ─────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}"
echo "╔══════════════════════════════════════════════════╗"
echo "║  Demo environment ready!                         ║"
echo "╟──────────────────────────────────────────────────╢"
echo "║  Grafana:    http://localhost:3000  (admin/admin) ║"
echo "║  Prometheus: http://localhost:9090               ║"
echo "║  Context:    kind-mcp-demo                       ║"
echo "╟──────────────────────────────────────────────────╢"
echo "║  make inject-oom        → payment-service OOM    ║"
echo "║  make inject-retry      → retry storm            ║"
echo "║  make inject-cascade    → multi-incident         ║"
echo "║  make recover           → reset all faults       ║"
echo "║  make setup-tmux        → demo terminal layout   ║"
echo "╚══════════════════════════════════════════════════╝"
echo -e "${RESET}"

# Hint about KUBECONFIG
echo "  export KUBECONFIG=${KUBECONFIG_PATH}"
echo "  or add to your shell profile."
