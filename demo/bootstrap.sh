#!/usr/bin/env bash
# bootstrap.sh — Cluster-agnostic demo environment setup
# Works with: kind (auto-created), or any existing K8s cluster (kubeadm, KillerCoda, GKE, EKS, etc.)
#
# Required:  kubectl, helm, python3
# Optional:  kind (to create a new cluster), docker (to build images)
#
# Env overrides:
#   KUBE_CONTEXT  — kubectl context to use (default: current context)
#   CLUSTER_NAME  — kind cluster name if creating one (default: mcp-demo)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
CLUSTER_NAME="${CLUSTER_NAME:-mcp-demo}"

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

# ── Prerequisites ─────────────────────────────────────────────────────────────
log "Checking prerequisites..."
for cmd in kubectl helm python3; do
  command -v "$cmd" &>/dev/null || die "$cmd not found. Install it first."
done
ok "Core prerequisites satisfied (kubectl, helm, python3)"

mkdir -p /tmp/mcp-demo-audit

# ── Cluster detection ─────────────────────────────────────────────────────────
# 1. If KUBE_CONTEXT is set explicitly, use it
# 2. If current context works, use it
# 3. If kind is available, create/use a kind cluster
# 4. Fail with clear message

if [[ -n "${KUBE_CONTEXT:-}" ]]; then
  CTX="$KUBE_CONTEXT"
  log "Using explicit KUBE_CONTEXT=$CTX"
elif kubectl cluster-info &>/dev/null 2>&1; then
  CTX="$(kubectl config current-context)"
  log "Using existing cluster: context=$CTX"
elif command -v kind &>/dev/null; then
  CTX="kind-${CLUSTER_NAME}"
  log "No reachable cluster found — creating kind cluster '${CLUSTER_NAME}'..."
  if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
    warn "kind cluster '${CLUSTER_NAME}' already exists. Skipping creation."
    warn "Run 'make down && make up' to rebuild from scratch."
    kind export kubeconfig --name "$CLUSTER_NAME" --kubeconfig "${HOME}/.kube/mcp-demo.yaml"
    export KUBECONFIG="${HOME}/.kube/mcp-demo.yaml"
  else
    kind create cluster \
      --name "$CLUSTER_NAME" \
      --config "$ROOT/cluster/kind-config.yaml" \
      --wait 120s
    kind export kubeconfig --name "$CLUSTER_NAME" --kubeconfig "${HOME}/.kube/mcp-demo.yaml"
    export KUBECONFIG="${HOME}/.kube/mcp-demo.yaml"
    ok "Kind cluster created"
  fi
else
  die "No reachable Kubernetes cluster found and 'kind' is not installed.
  Options:
    (a) Install kind: https://kind.sigs.k8s.io/docs/user/quick-start/#installation
    (b) Set KUBECONFIG to point to an existing cluster and re-run
    (c) Set KUBE_CONTEXT=<your-context> and re-run"
fi

K="kubectl --context=${CTX}"
log "Cluster context: $CTX"
$K get nodes --no-headers | awk '{print "  node: " $1 "  status: " $2}'

# ── Namespaces + RBAC ─────────────────────────────────────────────────────────
log "Applying namespaces and RBAC..."
$K apply -f "$ROOT/cluster/namespaces.yaml"
$K apply -f "$ROOT/cluster/rbac/"
ok "Namespaces and RBAC ready"

# ── Image loading strategy ────────────────────────────────────────────────────
SERVICES=(payment-service auth-service notification-service order-service email-gateway traffic-gen)

_is_kind_cluster() {
  command -v kind &>/dev/null && kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"
}

_docker_available() {
  command -v docker &>/dev/null && docker info &>/dev/null 2>&1
}

_ctr_available() {
  command -v ctr &>/dev/null
}

_load_image_kind() {
  local img="$1"
  kind load docker-image "$img" --name "$CLUSTER_NAME"
}

_load_image_ctr() {
  local img="$1"
  local tmpfile
  tmpfile="$(mktemp /tmp/mcp-img-XXXXXX.tar)"
  docker save "$img" -o "$tmpfile"
  # Load on all nodes
  for node in $(kubectl --context="$CTX" get nodes -o jsonpath='{.items[*].metadata.name}'); do
    if [[ "$node" == "$(hostname -s 2>/dev/null || hostname)" ]]; then
      ctr --namespace k8s.io images import "$tmpfile" &>/dev/null
      ok "  $img loaded on local node ($node)"
    elif ssh -o StrictHostKeyChecking=no -o BatchMode=yes "$node" true 2>/dev/null; then
      ssh -o StrictHostKeyChecking=no "$node" \
        "ctr --namespace k8s.io images import -" < "$tmpfile" &>/dev/null
      ok "  $img loaded on $node (via SSH)"
    else
      warn "  Cannot reach $node via SSH — $img may ImagePullBackOff on that node"
      warn "  Fix: ssh $node 'ctr --namespace k8s.io images import -' < $tmpfile"
    fi
  done
  rm -f "$tmpfile"
}

if _docker_available; then
  log "Docker available — building service images..."
  for svc in "${SERVICES[@]}"; do
    SVC_DIR="$ROOT/services/$svc"
    [[ -d "$SVC_DIR" ]] || { warn "Service dir missing: $SVC_DIR"; continue; }
    log "  Building mcp-demo/$svc:latest ..."
    docker build -t "mcp-demo/${svc}:latest" "$SVC_DIR" --quiet
  done
  ok "All images built"

  log "Loading images into cluster..."
  for svc in "${SERVICES[@]}"; do
    IMG="mcp-demo/${svc}:latest"
    if _is_kind_cluster; then
      _load_image_kind "$IMG"
      ok "  $svc → kind load"
    elif _ctr_available; then
      _load_image_ctr "$IMG"
    else
      warn "  Cannot load $IMG — no kind, no ctr. Pods will ImagePullBackOff."
      warn "  Fix: push image to a registry and set imagePullPolicy: IfNotPresent"
    fi
  done
  ok "Image loading complete"
else
  warn "Docker not available — skipping image build."
  warn "Ensure images exist in a registry accessible from the cluster."
  warn "If images are already loaded (e.g. from a previous run), deployment will proceed."
fi

# ── Deploy services ───────────────────────────────────────────────────────────
log "Deploying microservices..."
for svc in "${SERVICES[@]}"; do
  K8S_DIR="$ROOT/services/$svc/k8s"
  [[ -d "$K8S_DIR" ]] || continue
  $K apply -f "$K8S_DIR/" 2>/dev/null || true
done
ok "Services deployed"

# ── Observability stack ───────────────────────────────────────────────────────
log "Installing observability stack (this takes ~3 minutes)..."
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts --force-update 2>/dev/null
helm repo update 2>/dev/null

$K create namespace observability --dry-run=client -o yaml | $K apply -f -

helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --kube-context "$CTX" \
  --namespace observability \
  --values "$ROOT/observability/prometheus/values.yaml" \
  --wait \
  --timeout 10m \
  --set grafana.adminPassword=admin \
  2>&1 | tail -5

ok "Observability stack installed"

# ── PrometheusRules ───────────────────────────────────────────────────────────
log "Applying SLO alert rules..."
$K apply -f "$ROOT/observability/prometheus/rules/"
ok "Alert rules applied"

# ── Grafana dashboards ────────────────────────────────────────────────────────
log "Loading Grafana dashboards..."
KUBE_CONTEXT="$CTX" bash "$ROOT/observability/load-dashboards.sh"
ok "Dashboards loaded"

# ── Wait for services ─────────────────────────────────────────────────────────
log "Waiting for production deployments to be ready (up to 2 minutes)..."
$K -n production wait \
  --for=condition=available deployment \
  --all --timeout=120s 2>/dev/null || \
  warn "Some deployments not ready yet — check: kubectl get pods -n production"

# ── Save checkpoint ───────────────────────────────────────────────────────────
KUBE_CONTEXT="$CTX" "$SCRIPT_DIR/recovery/save-checkpoint.sh" 2>/dev/null || true

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}"
echo "╔══════════════════════════════════════════════════╗"
echo "║  Demo environment ready!                         ║"
echo "╟──────────────────────────────────────────────────╢"
echo "║  Context:    $CTX"
echo "╟──────────────────────────────────────────────────╢"
echo "║  make inject-oom        → payment-service OOM    ║"
echo "║  make recover           → reset all faults       ║"
echo "║  make agent             → start AI agent         ║"
echo "╚══════════════════════════════════════════════════╝"
echo -e "${RESET}"
echo "  Next: make agent"
