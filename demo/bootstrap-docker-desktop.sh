#!/usr/bin/env bash
# Deploy the full MCP demo stack to the Docker Desktop Kubernetes cluster.
# Observability runs on localhost:9091 (prometheus) and localhost:3001 (grafana).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
CTX="docker-desktop"
KUBECONFIG_DEFAULT="${HOME}/.kube/config"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
log()  { echo -e "${CYAN}[docker-desktop]${RESET} $*"; }
ok()   { echo -e "${GREEN}[ok]${RESET} $*"; }
warn() { echo -e "${YELLOW}[warn]${RESET} $*"; }
die()  { echo -e "${RED}[error]${RESET} $*" >&2; exit 1; }

echo -e "${BOLD}"
echo "╔══════════════════════════════════════════════════╗"
echo "║   MCP Demo — Docker Desktop Cluster Bootstrap   ║"
echo "╚══════════════════════════════════════════════════╝"
echo -e "${RESET}"

# ── Preflight ─────────────────────────────────────────
log "Checking Docker Desktop context..."
kubectl --context="$CTX" cluster-info &>/dev/null || die "Docker Desktop Kubernetes is not running. Enable it in Docker Desktop → Settings → Kubernetes."
ok "Docker Desktop cluster reachable"

for cmd in helm python3; do
  command -v "$cmd" &>/dev/null || die "$cmd not found"
done

# ── Namespaces + RBAC ─────────────────────────────────
log "Applying namespaces and RBAC..."
kubectl --context="$CTX" apply -f "$ROOT/cluster/namespaces.yaml"
kubectl --context="$CTX" apply -f "$ROOT/cluster/rbac/"
ok "Namespaces and RBAC ready"

# ── Build images ──────────────────────────────────────
log "Building service images (Docker Desktop shares the local Docker daemon)..."
SERVICES=(payment-service auth-service notification-service order-service email-gateway traffic-gen)
for svc in "${SERVICES[@]}"; do
  SVC_DIR="$ROOT/services/$svc"
  [[ -d "$SVC_DIR" ]] || { warn "Skipping missing service dir: $SVC_DIR"; continue; }
  log "  Building mcp-demo/$svc:latest..."
  docker build -t "mcp-demo/${svc}:latest" "$SVC_DIR" --quiet
  ok "  $svc built"
done

# ── Deploy microservices ──────────────────────────────
log "Deploying microservices to production namespace..."
for svc in "${SERVICES[@]}"; do
  K8S_DIR="$ROOT/services/$svc/k8s"
  [[ -d "$K8S_DIR" ]] || continue
  kubectl --context="$CTX" apply -f "$K8S_DIR/" 2>/dev/null || true
done

# Docker Desktop uses containerd image store — patch imagePullPolicy to IfNotPresent
# so Kubernetes finds the locally-built images without trying to pull from Docker Hub.
log "Patching imagePullPolicy to IfNotPresent for Docker Desktop..."
declare -A _CNAMES=([payment-service]=payment [auth-service]=auth [order-service]=order
                    [notification-service]=notification [email-gateway]=email-gateway [traffic-gen]=traffic-gen)
sleep 5
for svc in "${SERVICES[@]}"; do
  cname="${_CNAMES[$svc]:-$svc}"
  kubectl --context="$CTX" patch deployment/"$svc" -n production --type=json \
    -p "[{\"op\":\"replace\",\"path\":\"/spec/template/spec/containers/0/imagePullPolicy\",\"value\":\"IfNotPresent\"}]" \
    2>/dev/null || true
done
ok "Services deployed"

# ── Observability ─────────────────────────────────────
log "Installing observability stack on Docker Desktop (this takes ~3 minutes)..."
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts --force-update 2>/dev/null
helm repo update 2>/dev/null

kubectl --context="$CTX" create namespace observability --dry-run=client -o yaml | \
  kubectl --context="$CTX" apply -f -

helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --kube-context "$CTX" \
  --namespace observability \
  --values "$ROOT/observability/prometheus/values.yaml" \
  --values "$ROOT/observability/prometheus/values-docker-desktop.yaml" \
  --wait \
  --timeout 10m \
  --set grafana.adminPassword=admin \
  2>&1 | tail -5

ok "Observability stack installed"

# ── PrometheusRules ───────────────────────────────────
log "Applying SLO alert rules..."
kubectl --context="$CTX" apply -f "$ROOT/observability/prometheus/rules/"
ok "Alert rules applied"

# ── Grafana dashboards ────────────────────────────────
log "Loading Grafana dashboards..."
KUBECONFIG="$KUBECONFIG_DEFAULT" KUBE_CONTEXT="$CTX" GRAFANA_URL="http://localhost:3001" \
  bash "$ROOT/observability/load-dashboards.sh"
ok "Dashboards loaded"

# ── Wait for services ─────────────────────────────────
log "Waiting for production deployments to be ready (up to 120s)..."
kubectl --context="$CTX" -n production wait \
  --for=condition=available deployment \
  --all --timeout=120s 2>/dev/null || \
  warn "Some deployments not yet ready — check: kubectl --context=docker-desktop get pods -n production"

# ── Port-forward reminder ─────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}"
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Docker Desktop cluster bootstrapped!                   ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║  Start port-forwards:                                   ║"
echo "║    bash demo/port-forward-docker-desktop.sh             ║"
echo "║                                                          ║"
echo "║  Prometheus  →  http://localhost:9091                   ║"
echo "║  Alertmanager→  http://localhost:9094                   ║"
echo "║  Grafana     →  http://localhost:3001                   ║"
echo "║                                                          ║"
echo "║  Switch cluster in the MCP Agent UI to docker-desktop  ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo -e "${RESET}"
