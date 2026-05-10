#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'; CYAN='\033[0;36m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; RESET='\033[0m'

# Check for API key
if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  if [[ -f ".env" ]] && grep -q "ANTHROPIC_API_KEY" .env; then
    export $(grep "ANTHROPIC_API_KEY" .env | xargs)
    echo -e "${GREEN}[agent]${RESET} Loaded ANTHROPIC_API_KEY from .env"
  else
    echo -e "${RED}[agent]${RESET} ANTHROPIC_API_KEY not set."
    echo ""
    echo "  Option 1 — export before running:"
    echo "    export ANTHROPIC_API_KEY=sk-ant-..."
    echo "    bash demo/start-agent.sh"
    echo ""
    echo "  Option 2 — create agent/.env file:"
    echo "    echo 'ANTHROPIC_API_KEY=sk-ant-...' > agent/.env"
    echo ""
    exit 1
  fi
fi

# Merge default kubeconfig with the kind-specific one so all contexts are visible
_DEFAULT_KC="${HOME}/.kube/config"
_KIND_KC="${HOME}/.kube/mcp-demo.yaml"
if [[ -f "$_DEFAULT_KC" && -f "$_KIND_KC" ]]; then
  export KUBECONFIG="${_DEFAULT_KC}:${_KIND_KC}"
elif [[ -f "$_KIND_KC" ]]; then
  export KUBECONFIG="$_KIND_KC"
fi

CTX="kind-mcp-demo"

# ── Ensure observability port-forwards are alive ──────────────────────────────
_pf_alive() { curl -sf --connect-timeout 1 "$1" &>/dev/null; }

if ! _pf_alive "http://localhost:9092/-/ready"; then
  echo -e "${CYAN}[agent]${RESET} Starting Prometheus port-forward → localhost:9092"
  kubectl --context=${CTX} -n observability \
    port-forward svc/kube-prometheus-stack-prometheus 9092:9090 \
    &>/tmp/pf-prometheus.log &
fi

if ! _pf_alive "http://localhost:9093/-/ready"; then
  echo -e "${CYAN}[agent]${RESET} Starting Alertmanager port-forward → localhost:9093"
  kubectl --context=${CTX} -n observability \
    port-forward svc/kube-prometheus-stack-alertmanager 9093:9093 \
    &>/tmp/pf-alertmanager.log &
fi

if ! _pf_alive "http://localhost:3002/api/health"; then
  echo -e "${CYAN}[agent]${RESET} Starting Grafana port-forward → localhost:3002"
  kubectl --context=${CTX} -n observability \
    port-forward svc/kube-prometheus-stack-grafana 3002:80 \
    &>/tmp/pf-grafana.log &
fi

# Give port-forwards a moment to bind
sleep 1

PORT="${PORT:-8082}"

echo -e "${CYAN}[agent]${RESET} Starting MCP Incident Agent on http://localhost:${PORT}"
echo -e "${CYAN}[agent]${RESET} Cluster:  ${CTX} (kubeconfig: $KUBECONFIG)"
echo -e "${CYAN}[agent]${RESET} Model:    claude-sonnet-4-6"
echo -e "${CYAN}[agent]${RESET} Prometheus  → http://localhost:9092"
echo -e "${CYAN}[agent]${RESET} Alertmanager → http://localhost:9093"
echo -e "${CYAN}[agent]${RESET} Grafana      → http://localhost:3002"
echo ""
echo -e "${GREEN}[agent]${RESET} Open http://localhost:${PORT} in your browser"
echo ""

PORT=$PORT python3 server.py
