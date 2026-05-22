#!/usr/bin/env bash
set -euo pipefail
CTX="${KUBE_CONTEXT:-$(kubectl config current-context 2>/dev/null || echo "")}"
[[ -z "$CTX" ]] && { echo "ERROR: No kubectl context. Set KUBECONFIG or KUBE_CONTEXT."; exit 1; }

SESSION="mcp-demo"
tmux kill-session -t "$SESSION" 2>/dev/null || true
tmux new-session -d -s "$SESSION" -x 220 -y 55

# Configure tmux appearance inline
tmux set-option -t "$SESSION" status-style 'bg=#1a1a2e,fg=#e0e8ff'
tmux set-option -t "$SESSION" status-left '#[fg=#00ff88,bold] ◉ MCP DEMO #[fg=#4a9eff] │ '
tmux set-option -t "$SESSION" status-right '#[fg=#ff4444,bold] LIVE #[fg=#888888]%H:%M '
tmux set-option -t "$SESSION" status-interval 1
tmux set-option -t "$SESSION" pane-border-style 'fg=#2a2a4a'
tmux set-option -t "$SESSION" pane-active-border-style 'fg=#4a9eff'

# Split into 4 panes: 2x2 grid
tmux split-window -h -t "${SESSION}:1"
tmux split-window -v -t "${SESSION}:1.1"
tmux split-window -v -t "${SESSION}:1.2"

# Pane 1 (top-left): kubectl pod watch
tmux send-keys -t "${SESSION}:1.1" \
  "watch -n2 -c 'kubectl --context=${CTX} get pods -n production -o wide 2>&1 | \
  GREP_COLOR=\"01;31\" grep --color=always -E \"CrashLoopBackOff|OOMKilled|Error|0/[0-9]+|$\" || \
  kubectl --context=${CTX} get pods -n production'" \
  Enter

# Pane 2 (top-right): kubectl events
tmux send-keys -t "${SESSION}:1.2" \
  "kubectl --context=${CTX} get events -n production --watch --field-selector=type!=Normal 2>&1 | \
   grep --line-buffered --color=always -E 'OOMKilling|BackOff|Failed|Error|Killing|Unhealthy|Warning'" \
  Enter

# Pane 3 (bottom-left): Prometheus alerts live
tmux send-keys -t "${SESSION}:1.3" \
  "watch -n3 'curl -s http://localhost:9092/api/v1/alerts 2>/dev/null | \
   python3 -c \"
import json,sys,time
try:
    d=json.load(sys.stdin)
    alerts=d.get(\\\"data\\\",{}).get(\\\"alerts\\\",[])
    if not alerts:
        print(\\\"  No firing alerts\\\")
    for a in alerts:
        st=a[\\\"state\\\"]
        color = \\\"\\\\033[91m\\\" if st==\\\"firing\\\" else \\\"\\\\033[93m\\\"
        name=a[\\\"labels\\\"].get(\\\"alertname\\\",\\\"\\\")
        svc=a[\\\"labels\\\"].get(\\\"service\\\",a[\\\"labels\\\"].get(\\\"app\\\",\\\"\\\"))
        ns=a[\\\"labels\\\"].get(\\\"namespace\\\",\\\"\\\")
        print(f\\\"{color}{st.upper():10}\\\\033[0m {name:<40} {svc:<25} {ns}\\\")
except Exception as e:
    print(f\\\"  (prometheus unreachable: {e})\\\")
\"'" \
  Enter

# Pane 4 (bottom-right): quick commands reference
tmux send-keys -t "${SESSION}:1.4" \
  "cat << 'HELP'
  INCIDENT INJECTION
  ──────────────────────────────────
  make inject-oom        OOM kill payment-service
  make inject-retry      retry storm → email-gateway
  make inject-cascade    ALL incidents (demo mode)
  make inject-cert       auth cert expiry warning
  make inject-hpa        stuck HPA on order-service
  make inject-bad-rollout bad deploy on payment-service
  make inject-dns        CoreDNS upstream failure

  RECOVERY
  ──────────────────────────────────
  make recover           reset all faults
  make emergency-reset   nuclear reset in 30s

  OBSERVE
  ──────────────────────────────────
  Grafana    → http://localhost:3002
  Prometheus → http://localhost:9092

  CLUSTER CONTEXT
  ──────────────────────────────────
  Current: $CTX

HELP" Enter

echo "tmux session '${SESSION}' ready."
echo "Attach with: tmux attach -t ${SESSION}"
tmux attach -t "$SESSION"
