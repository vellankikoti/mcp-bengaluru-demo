#!/usr/bin/env bash
# start.sh — Start the MCP agent server with port-forwards
# Works with any kubectl context (kind, kubeadm, GKE, EKS, etc.)
#
# Env overrides:
#   KUBE_CONTEXT — kubectl context to use (default: current context)
#   PORT         — agent HTTP port (default: 8082)
#
# .env file supports any provider (all optional — can also configure in browser UI):
#   ANTHROPIC_API_KEY=sk-ant-...          Anthropic Claude
#   OPENAI_API_KEY=sk-...                 OpenAI
#   OPENROUTER_API_KEY=sk-or-...          OpenRouter
#   AI_API_KEY=<any key>                  Generic — any provider key
#   AI_BASE_URL=http://localhost:11434/v1 Ollama or any OpenAI-compatible endpoint
#   AI_MODEL=llama3.2                     Model override
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; RESET='\033[0m'

# ── Load .env ─────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPT_DIR/.env" ]]; then
  # Export all non-comment, non-empty lines
  set -a
  # shellcheck disable=SC1090
  source <(grep -v '^\s*#' "$SCRIPT_DIR/.env" | grep -v '^\s*$')
  set +a
  echo -e "${GREEN}[agent]${RESET} Loaded .env from $SCRIPT_DIR/.env"
fi

# Detect if any AI key/URL is configured
_has_ai_config=false
for _var in ANTHROPIC_API_KEY OPENAI_API_KEY OPENROUTER_API_KEY AI_API_KEY AI_BASE_URL; do
  if [[ -n "${!_var:-}" ]]; then _has_ai_config=true; break; fi
done

if [[ "$_has_ai_config" == "false" ]]; then
  echo -e "${YELLOW}[agent]${RESET} No AI provider configured — enter your key or URL in the browser UI."
  echo -e "${YELLOW}[agent]${RESET} Sidebar → AI Engine → choose provider → Save & Test"
  echo -e "${YELLOW}[agent]${RESET} Supports: Anthropic, OpenAI, OpenRouter, Groq, Google AI, Ollama (any OpenAI-compatible)"
  echo ""
fi

# ── Cluster context ───────────────────────────────────────────────────────────
CTX="${KUBE_CONTEXT:-$(kubectl config current-context 2>/dev/null || echo "")}"
if [[ -z "$CTX" ]]; then
  echo -e "${YELLOW}[agent]${RESET} No kubectl context found. K8s tools will fail."
  echo -e "${YELLOW}[agent]${RESET} Set KUBECONFIG or KUBE_CONTEXT and restart."
else
  echo -e "${CYAN}[agent]${RESET} Cluster context: $CTX"
fi

# Export so python process inherits it
export KUBE_CONTEXT="$CTX"

# ── Port-forwards ─────────────────────────────────────────────────────────────
_pf_alive() { curl -sf --connect-timeout 1 "$1" &>/dev/null; }

if [[ -n "$CTX" ]]; then
  if ! _pf_alive "http://localhost:9092/-/ready"; then
    echo -e "${CYAN}[agent]${RESET} Starting Prometheus port-forward → localhost:9092"
    kubectl --context="$CTX" -n observability \
      port-forward svc/kube-prometheus-stack-prometheus 9092:9090 \
      &>/tmp/pf-prometheus.log &
  fi

  if ! _pf_alive "http://localhost:9093/-/ready"; then
    echo -e "${CYAN}[agent]${RESET} Starting Alertmanager port-forward → localhost:9093"
    kubectl --context="$CTX" -n observability \
      port-forward svc/kube-prometheus-stack-alertmanager 9093:9093 \
      &>/tmp/pf-alertmanager.log &
  fi

  if ! _pf_alive "http://localhost:3002/api/health"; then
    echo -e "${CYAN}[agent]${RESET} Starting Grafana port-forward → localhost:3002"
    kubectl --context="$CTX" -n observability \
      port-forward svc/kube-prometheus-stack-grafana 3002:80 \
      &>/tmp/pf-grafana.log &
  fi

  sleep 1
fi

# ── Agent port ────────────────────────────────────────────────────────────────
PORT="${PORT:-8082}"

_pid=$(lsof -ti :"$PORT" 2>/dev/null || true)
if [[ -n "$_pid" ]]; then
  echo -e "${YELLOW}[agent]${RESET} Port ${PORT} in use (pid $_pid) — releasing it"
  kill -9 $_pid 2>/dev/null || true
  sleep 0.5
fi

echo -e "${CYAN}[agent]${RESET} Starting MCP Incident Agent on http://localhost:${PORT}"
echo -e "${CYAN}[agent]${RESET} Context:     $CTX"
echo -e "${CYAN}[agent]${RESET} Prometheus   → http://localhost:9092"
echo -e "${CYAN}[agent]${RESET} Alertmanager → http://localhost:9093"
echo -e "${CYAN}[agent]${RESET} Grafana      → http://localhost:3002"
echo ""
echo -e "${GREEN}[agent]${RESET} Open http://localhost:${PORT} in your browser"
echo ""

cd "$SCRIPT_DIR"
PORT=$PORT python3 server.py
