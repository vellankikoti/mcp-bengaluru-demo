#!/usr/bin/env bash
# preflight.sh — Conference pre-show safety check
# Run this 30 minutes before going on stage.
# Exits non-zero if any critical check fails.
# Usage: bash demo/preflight.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
AGENT_DIR="$ROOT/agent"
CTX="${KUBE_CONTEXT:-$(kubectl config current-context 2>/dev/null || echo "")}"
AGENT_PORT="${PORT:-8082}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

PASS=0; FAIL=0; WARN=0
CRITICAL_FAIL=0

pass()  { echo -e "  ${GREEN}✓${RESET} $*"; ((PASS++)) || true; }
fail()  { echo -e "  ${RED}✗ CRITICAL${RESET} $*"; ((FAIL++)) || true; ((CRITICAL_FAIL++)) || true; }
warn()  { echo -e "  ${YELLOW}⚠ WARN${RESET} $*"; ((WARN++)) || true; }
info()  { echo -e "  ${CYAN}ℹ${RESET} $*"; }

section() {
  echo ""
  echo -e "${BOLD}── $* ──${RESET}"
}

echo -e "${BOLD}"
echo "╔══════════════════════════════════════════════╗"
echo "║  PREFLIGHT CHECK — Conference Demo Safety    ║"
echo "╚══════════════════════════════════════════════╝"
echo -e "${RESET}"
echo "  Context: ${CTX:-<none>}"
echo "  Time:    $(date)"

# ── 1. REQUIRED TOOLS ────────────────────────────────────────────────────────
section "Required Tools"
for cmd in kubectl helm python3 curl lsof; do
  if command -v "$cmd" &>/dev/null; then
    pass "$cmd found ($(command -v $cmd))"
  else
    fail "$cmd not found — install it before presenting"
  fi
done
# Optional tools — warn only
for cmd in docker kind; do
  if command -v "$cmd" &>/dev/null; then
    pass "$cmd found ($(command -v $cmd)) — optional"
  else
    warn "$cmd not found — only needed to create a new cluster. Skip if using existing cluster."
  fi
done

# ── 2. KUBERNETES CLUSTER ────────────────────────────────────────────────────
section "Kubernetes Cluster"
if [[ -z "$CTX" ]]; then
  fail "No kubectl context found — set KUBECONFIG or KUBE_CONTEXT"
else
  pass "kubectl context: $CTX"
fi

K="kubectl --context=${CTX}"

if $K cluster-info &>/dev/null 2>&1; then
  pass "cluster reachable"
else
  fail "cluster not reachable — check KUBECONFIG and cluster status"
fi

if $K get nodes --no-headers 2>/dev/null | grep -q "Ready"; then
  NODE_COUNT=$($K get nodes --no-headers 2>/dev/null | grep -c "Ready" || true)
  pass "$NODE_COUNT node(s) Ready"
else
  fail "no Ready nodes found"
fi

# ── 4. PRODUCTION PODS ───────────────────────────────────────────────────────
section "Production Pods"
EXPECTED_SERVICES="payment-service order-service auth-service notification-service email-gateway traffic-gen"
for svc in $EXPECTED_SERVICES; do
  AVAIL=$($K -n production get deployment "$svc" \
    -o jsonpath='{.status.availableReplicas}' 2>/dev/null || echo "0")
  if [[ "$AVAIL" =~ ^[1-9] ]]; then
    pass "$svc: $AVAIL replica(s) available"
  else
    fail "$svc not available (availableReplicas=$AVAIL) — run: make recover"
  fi
done

# Check for any crashing pods
CRASHING=$($K -n production get pods --no-headers 2>/dev/null | grep -c "CrashLoop\|OOMKilled\|Error" || true)
if [[ "$CRASHING" -gt 0 ]]; then
  warn "$CRASHING pod(s) crashing — this is OK only if you just ran make inject-oom. Run 'make recover' if unintentional."
else
  pass "no crashing pods (clean baseline)"
fi

# ── 5. OBSERVABILITY ────────────────────────────────────────────────────────
section "Observability Stack"
if $K -n observability get pods -l app.kubernetes.io/name=prometheus --no-headers 2>/dev/null | grep -q "Running"; then
  pass "Prometheus pod Running"
else
  fail "Prometheus not running"
fi

if $K -n observability get pods -l app.kubernetes.io/name=grafana --no-headers 2>/dev/null | grep -q "Running"; then
  pass "Grafana pod Running"
else
  fail "Grafana not running"
fi

# Port-forward checks
check_pf() {
  local name="$1" url="$2"
  if curl -sf --connect-timeout 2 "$url" &>/dev/null; then
    pass "$name port-forward alive"
  else
    warn "$name port-forward not responding — run: make agent to start all"
  fi
}
check_pf "Prometheus(9092)" "http://localhost:9092/-/ready"
check_pf "Alertmanager(9093)" "http://localhost:9093/-/ready"
check_pf "Grafana(3002)" "http://localhost:3002/api/health"

# ── 6. RBAC ──────────────────────────────────────────────────────────────────
section "RBAC"
if $K -n mcp-system get serviceaccount mcp-incident-agent &>/dev/null; then
  pass "mcp-incident-agent ServiceAccount present"
else
  fail "mcp-incident-agent ServiceAccount missing — run: make up"
fi

if $K get clusterrolebinding mcp-incident-agent &>/dev/null; then
  pass "mcp-incident-agent ClusterRoleBinding present"
else
  fail "mcp-incident-agent ClusterRoleBinding missing"
fi

# ── 7. AGENT SERVER ──────────────────────────────────────────────────────────
section "Agent Server"
if curl -sf --connect-timeout 2 "http://localhost:${AGENT_PORT}/health" &>/dev/null; then
  SECURITY_STATE=$(curl -sf "http://localhost:${AGENT_PORT}/api/demo/security" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('security_on', 'unknown'))" 2>/dev/null || echo "unknown")
  pass "Agent server running on port ${AGENT_PORT}"

  if [[ "$SECURITY_STATE" == "True" ]] || [[ "$SECURITY_STATE" == "true" ]]; then
    pass "Policy Gates: ON ✓ (correct for Acts 1 and 2)"
  elif [[ "$SECURITY_STATE" == "False" ]] || [[ "$SECURITY_STATE" == "false" ]]; then
    warn "Policy Gates: OFF — toggle ON before Act 1 (F4 in browser, or Demo Controls in sidebar)"
  else
    warn "Could not determine policy gate state: $SECURITY_STATE"
  fi

  # Check recordings are served
  RECORDINGS=$(curl -sf "http://localhost:${AGENT_PORT}/api/replay" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('recordings', [])))" 2>/dev/null || echo "0")
  if [[ "$RECORDINGS" -ge 2 ]]; then
    pass "Recordings available: $RECORDINGS (cascade + dangerous-agent)"
  else
    warn "Expected 2 recordings, found $RECORDINGS"
  fi
else
  warn "Agent server not running — run: make agent  (start 30s before talk)"
fi

# ── 8. API KEY ────────────────────────────────────────────────────────────────
section "API Key"
if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
  KEY_LEN=${#ANTHROPIC_API_KEY}
  if [[ $KEY_LEN -gt 20 ]]; then
    pass "ANTHROPIC_API_KEY set (${KEY_LEN} chars)"
  else
    fail "ANTHROPIC_API_KEY looks too short ($KEY_LEN chars) — check for typos"
  fi
elif [[ -f "$AGENT_DIR/.env" ]] && grep -q "ANTHROPIC_API_KEY" "$AGENT_DIR/.env"; then
  STORED_KEY=$(grep "ANTHROPIC_API_KEY" "$AGENT_DIR/.env" | cut -d= -f2 | tr -d '"' | tr -d "'")
  KEY_LEN=${#STORED_KEY}
  if [[ $KEY_LEN -gt 20 ]]; then
    pass "ANTHROPIC_API_KEY in agent/.env ($KEY_LEN chars)"
  else
    fail "ANTHROPIC_API_KEY in .env looks invalid ($KEY_LEN chars)"
  fi
else
  warn "No ANTHROPIC_API_KEY set — you will need to enter it in the browser UI before the demo"
fi

# ── 9. RECORDINGS ────────────────────────────────────────────────────────────
section "Demo Recordings"
for rec in cascade dangerous-agent; do
  REC_PATH="$AGENT_DIR/demo-recordings/${rec}.jsonl"
  if [[ -f "$REC_PATH" ]]; then
    LINES=$(grep -c "^{" "$REC_PATH" 2>/dev/null || echo 0)
    SIZE=$(wc -c < "$REC_PATH")
    pass "${rec}.jsonl present ($LINES events, ${SIZE} bytes)"
    # Check for secret values in dangerous-agent
    if [[ "$rec" == "dangerous-agent" ]]; then
      if grep -q "DB_PASSWORD:\|sk_live_\|REAL_KEY_HERE" "$REC_PATH" 2>/dev/null; then
        fail "dangerous-agent.jsonl contains forbidden secret value patterns!"
      else
        pass "dangerous-agent.jsonl: no secret values (truth guarantee met)"
      fi
    fi
  else
    fail "${rec}.jsonl missing at $REC_PATH"
  fi
done

# ── 10. PYTHON DEPENDENCIES ───────────────────────────────────────────────────
section "Python Dependencies"
MISSING_DEPS=()
for pkg in fastapi anthropic uvicorn httpx kubernetes pydantic; do
  if python3 -c "import $pkg" 2>/dev/null; then
    pass "$pkg importable"
  else
    MISSING_DEPS+=("$pkg")
    fail "$pkg not installed — run: source venv/bin/activate && pip install -r agent/requirements.txt"
  fi
done

# ── 11. PORTS ────────────────────────────────────────────────────────────────
section "Port Availability"
for port in 8082 9092 9093 3002; do
  if lsof -ti :$port &>/dev/null; then
    PROC=$(lsof -ti :$port | head -1)
    CMD=$(ps -p "$PROC" -o comm= 2>/dev/null || echo "unknown")
    if [[ "$port" == "8082" ]]; then
      pass "Port $port in use by '$CMD' (agent server expected)"
    else
      pass "Port $port in use by '$CMD' (port-forward expected)"
    fi
  else
    if [[ "$port" == "8082" ]]; then
      warn "Port 8082 free — agent server not started yet (run: make agent)"
    else
      warn "Port $port free — port-forward not running (run: make agent)"
    fi
  fi
done

# ── 12. DISK AND MEMORY ───────────────────────────────────────────────────────
section "System Resources"
FREE_DISK_GB=$(df -g / 2>/dev/null | awk 'NR==2 {print $4}' || df -H / | awk 'NR==2 {print $4}' | tr -d 'G')
if [[ "${FREE_DISK_GB:-0}" -gt 5 ]]; then
  pass "Free disk: ${FREE_DISK_GB}GB (> 5GB required)"
else
  warn "Free disk low: ${FREE_DISK_GB}GB — Docker may fail to pull images"
fi

# ── 13. UNIT TESTS ───────────────────────────────────────────────────────────
section "Automated Tests"
if python3 -m pytest "$ROOT/tests/test_policy.py" "$ROOT/tests/test_recordings.py" \
    -q --tb=no 2>&1 | grep -q "passed"; then
  TEST_RESULT=$(python3 -m pytest "$ROOT/tests/test_policy.py" "$ROOT/tests/test_recordings.py" \
    -q --tb=no 2>&1 | tail -1)
  pass "Unit tests: $TEST_RESULT"
else
  fail "Unit tests FAILED — policy or recording regressions detected"
fi

# ── 14. SECURITY INVARIANT ───────────────────────────────────────────────────
section "Security Invariant (AST check)"
SECURITY_DEFAULT=$(python3 -c "
import ast
from pathlib import Path
source = (Path('$ROOT') / 'agent' / 'server.py').read_text()
tree = ast.parse(source)
for node in ast.walk(tree):
    if isinstance(node, ast.AnnAssign):
        if isinstance(node.target, ast.Name) and node.target.id == '_security_on':
            print('True' if (isinstance(node.value, ast.Constant) and node.value.value is True) else 'False')
            break
" 2>/dev/null || echo "error")

if [[ "$SECURITY_DEFAULT" == "True" ]]; then
  pass "_security_on defaults to True in server.py (critical invariant)"
else
  fail "CRITICAL: _security_on is not True in server.py — policy gates will be OFF at start!"
fi

# ── SUMMARY ───────────────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════"
if [[ $CRITICAL_FAIL -eq 0 ]]; then
  echo -e "${GREEN}${BOLD}✅  PREFLIGHT PASSED${RESET}"
  echo -e "   ${PASS} checks passed · ${WARN} warnings · ${FAIL} critical failures"
  echo ""
  if [[ $WARN -gt 0 ]]; then
    echo -e "${YELLOW}  Warnings do not block the demo but should be reviewed.${RESET}"
    echo -e "${YELLOW}  Most warnings clear after 'make agent' is running.${RESET}"
  fi
  echo ""
  echo "  You are CLEARED TO PRESENT."
  echo ""
  echo "  Pre-talk checklist:"
  echo "  1. make inject-oom              (60s before Act 1)"
  echo "  2. Browser at http://localhost:8082?mode=presentation"
  echo "  3. Sidebar: Policy Gates ON, AI key green"
  echo "  4. Demo menu → Reset demo to start"
  echo ""
  exit 0
else
  echo -e "${RED}${BOLD}❌  PREFLIGHT FAILED — DO NOT PRESENT YET${RESET}"
  echo -e "   ${PASS} checks passed · ${WARN} warnings · ${CRITICAL_FAIL} CRITICAL failures"
  echo ""
  echo -e "${RED}  Fix all CRITICAL failures before going on stage.${RESET}"
  echo ""
  exit 1
fi
