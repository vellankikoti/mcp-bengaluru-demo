#!/usr/bin/env bash
# Port-forward observability services from the Docker Desktop cluster.
# Runs all three forwards in the background.  Kills them on Ctrl-C.
set -euo pipefail

CTX="docker-desktop"
NS="observability"
CYAN='\033[0;36m'; GREEN='\033[0;32m'; RED='\033[0;31m'; RESET='\033[0m'

log() { echo -e "${CYAN}[pf-docker]${RESET} $*"; }
ok()  { echo -e "${GREEN}[pf-docker]${RESET} $*"; }

cleanup() {
  echo ""
  log "Stopping port-forwards..."
  kill "${PIDS[@]}" 2>/dev/null || true
  exit 0
}
trap cleanup INT TERM

PIDS=()

log "Starting port-forwards for Docker Desktop cluster..."

# Prometheus → localhost:9091
kubectl --context="$CTX" -n "$NS" port-forward \
  svc/kube-prometheus-stack-prometheus 9091:9090 &>/dev/null &
PIDS+=($!)

# Alertmanager → localhost:9094
kubectl --context="$CTX" -n "$NS" port-forward \
  svc/kube-prometheus-stack-alertmanager 9094:9093 &>/dev/null &
PIDS+=($!)

# Grafana → localhost:3001
kubectl --context="$CTX" -n "$NS" port-forward \
  svc/kube-prometheus-stack-grafana 3001:80 &>/dev/null &
PIDS+=($!)

sleep 2
ok "Prometheus  →  http://localhost:9091"
ok "Alertmanager→  http://localhost:9094"
ok "Grafana     →  http://localhost:3001  (admin/admin)"
echo ""
echo "Press Ctrl-C to stop all port-forwards."

wait
