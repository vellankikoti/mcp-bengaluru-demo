#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
CLUSTER_NAME="mcp-demo"
CTX="kind-${CLUSTER_NAME}"
KUBECONFIG_PATH="${HOME}/.kube/mcp-demo.yaml"
export KUBECONFIG="$KUBECONFIG_PATH"

K="kubectl --context=${CTX}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; RESET='\033[0m'
log()     { echo -e "${CYAN}[inject]${RESET} $*"; }
alert()   { echo -e "${RED}[INCIDENT]${RESET} $*"; }
ok()      { echo -e "${GREEN}[recovered]${RESET} $*"; }

INCIDENT="${1:-help}"
DRY_RUN="${2:-}"

run() {
  if [[ "$DRY_RUN" == "--dry-run" ]]; then
    echo "  [dry-run] $*"
  else
    eval "$@"
  fi
}

inject_crashloop_oom() {
  alert "Injecting: CrashLoopBackOff OOM on payment-service"
  # Step 1: enable OOM fault mode (continuous memory allocation in-process)
  run $K -n production set env deployment/payment-service FAULT_MODE=oom
  # Step 2: drop memory limit to 50Mi (request must be <= limit)
  run $K -n production set resources deployment/payment-service \
    --requests=memory=32Mi --limits=memory=50Mi -c payment
  alert "payment-service will OOMKill in ~30s. Watch: kubectl get pods -n production -w"
}

inject_error_rate() {
  alert "Injecting: High error rate on payment-service (40% errors)"
  run $K -n production set env deployment/payment-service \
    FAULT_MODE=error \
    FAULT_PROBABILITY=0.4
  alert "payment-service now returning ~40% HTTP 500"
}

inject_slow() {
  alert "Injecting: Slow payment-service (1.5-4s latency)"
  run $K -n production set env deployment/payment-service FAULT_MODE=slow
  alert "payment-service now slow — order-service p99 will spike"
}

inject_retry_storm() {
  alert "Injecting: Retry storm from notification-service → email-gateway"
  run $K -n production set env deployment/notification-service \
    FAULT_MODE=aggressive_retry \
    RETRY_TARGET="http://email-gateway.production.svc.cluster.local/send" \
    RETRY_COUNT=5000
  run $K -n production rollout restart deployment/notification-service
  alert "Retry storm active. email-gateway will rate-limit. order-service latency will spike."
  alert "Watch: kubectl get pods -n production"
}

inject_cert_expiry() {
  alert "Injecting: Certificate expiry warning on auth-service"
  run $K -n production set env deployment/auth-service FAULT_MODE=cert_expiry
  alert "auth-service now returning cert-expiry warnings in responses"
  alert "Check: kubectl logs -n production -l app=auth-service"
}

inject_bad_rollout() {
  alert "Injecting: Bad rollout on payment-service (v2 with 50% error rate)"
  # Add v2 env — same image but error mode
  run $K -n production set env deployment/payment-service \
    FAULT_MODE=error_rate \
    FAULT_PROBABILITY=0.5 \
    SERVICE_VERSION=v2
  run $K -n production annotate deployment payment-service \
    kubernetes.io/change-cause="deploy-v2-perf-improvement" --overwrite 2>/dev/null || true
  alert "payment-service v2 rolling out with 50% error rate"
}

inject_dns_failure() {
  alert "Injecting: CoreDNS upstream failure"
  # Backup first
  $K -n kube-system get configmap coredns -o yaml > /tmp/mcp-coredns-backup.yaml
  # Write broken Corefile via a temp ConfigMap YAML (avoids shell newline escaping issues)
  python3 - <<'PYEOF'
import subprocess, tempfile, os
broken = """apiVersion: v1
kind: ConfigMap
metadata:
  name: coredns
  namespace: kube-system
data:
  Corefile: |
    .:53 {
        errors
        health {
           lameduck 5s
        }
        ready
        forward . 192.0.2.254
        cache 5
        loop
        reload
        loadbalance
    }
"""
with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
    f.write(broken)
    fname = f.name
result = subprocess.run(['kubectl', '--context=kind-mcp-demo', 'apply', '-f', fname], capture_output=True, text=True)
os.unlink(fname)
if result.returncode != 0:
    print(f"FAIL: {result.stderr}")
else:
    print(result.stdout.strip())
PYEOF
  run $K -n kube-system rollout restart deployment/coredns
  alert "CoreDNS now using invalid upstream (192.0.2.254). DNS will fail in ~15s."
  alert "Recover with: make recover"
}

inject_stuck_hpa() {
  alert "Injecting: Node taint → HPA pods pending"
  # Taint all worker nodes so HPA can't schedule
  # Taint the node to block new scheduling, then force scale beyond what fits
  for node in $($K get nodes -o name); do
    run $K taint node "$node" demo.mcp.io/unavailable=true:NoSchedule --overwrite 2>/dev/null || true
  done
  # Scale up so new pods need to schedule — but node is tainted so they'll be Pending
  run $K -n production scale deployment order-service --replicas=6
  alert "Node tainted. order-service scaled to 6 replicas — new pods Pending (can't schedule)."
  alert "Classic stuck-HPA: desired > schedulable. Recover with: make recover"
}

inject_cascade() {
  alert "Injecting: CASCADE INCIDENT — OOM + retry storm + cert expiry"
  alert "This is the full conference demo scenario"
  echo ""
  inject_crashloop_oom &
  sleep 3
  inject_retry_storm &
  sleep 3
  inject_cert_expiry
  wait
  alert "CASCADE ACTIVE:"
  alert "  1. payment-service → OOMKilling"
  alert "  2. notification-service → retry storm → email-gateway rate limited"
  alert "  3. auth-service → cert expiry warning"
  alert ""
  alert "Watch the Grafana dashboard at http://localhost:3000"
}

recover_all() {
  log "Recovering ALL injected faults..."

  # Reset payment-service
  $K -n production set env deployment/payment-service \
    FAULT_MODE=healthy FAULT_PROBABILITY=0.0 SERVICE_VERSION=v1 2>/dev/null || true
  $K -n production set resources deployment/payment-service \
    --limits=memory=256Mi -c payment 2>/dev/null || true

  # Reset notification-service
  $K -n production set env deployment/notification-service \
    FAULT_MODE=healthy RETRY_COUNT=0 2>/dev/null || true
  $K -n production rollout restart deployment/notification-service 2>/dev/null || true

  # Reset auth-service
  $K -n production set env deployment/auth-service \
    FAULT_MODE=healthy 2>/dev/null || true

  # Reset email-gateway
  $K -n production set env deployment/email-gateway \
    FAULT_MODE=healthy 2>/dev/null || true

  # Restore CoreDNS if backup exists
  if [[ -f /tmp/mcp-coredns-backup.yaml ]]; then
    log "Restoring CoreDNS config..."
    $K apply -f /tmp/mcp-coredns-backup.yaml 2>/dev/null || true
    $K -n kube-system rollout restart deployment/coredns 2>/dev/null || true
    rm -f /tmp/mcp-coredns-backup.yaml
  fi

  # Remove node taints
  for node in $($K get nodes -o name); do
    $K taint node "$node" demo.mcp.io/unavailable:NoSchedule- 2>/dev/null || true
  done

  # Scale order-service back to normal
  $K -n production scale deployment order-service --replicas=2 2>/dev/null || true

  # Scale order-service back to normal
  $K -n production scale deployment order-service --replicas=2 2>/dev/null || true

  # Wait for stabilization
  log "Waiting for pods to stabilize..."
  sleep 5
  $K -n production rollout status deployment/payment-service --timeout=60s 2>/dev/null || true

  ok "All incidents recovered"
  echo ""
  $K -n production get pods
}

show_status() {
  echo ""
  echo -e "${CYAN}Current cluster state:${RESET}"
  $K -n production get pods -o wide
  echo ""
  echo -e "${CYAN}Deployments:${RESET}"
  $K -n production get deployments
  echo ""
  echo -e "${CYAN}Active fault modes:${RESET}"
  $K -n production get deployments -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{range .spec.template.spec.containers[*]}{range .env[*]}{.name}={.value}{" "}{end}{end}{"\n"}{end}' | grep FAULT_MODE || echo "  (none — all healthy)"
}

case "$INCIDENT" in
  crashloop-oom)   inject_crashloop_oom ;;
  error-rate)      inject_error_rate ;;
  slow)            inject_slow ;;
  retry-storm)     inject_retry_storm ;;
  cert-expiry)     inject_cert_expiry ;;
  bad-rollout)     inject_bad_rollout ;;
  dns-failure)     inject_dns_failure ;;
  stuck-hpa)       inject_stuck_hpa ;;
  cascade)         inject_cascade ;;
  recover)         recover_all ;;
  status)          show_status ;;
  *)
    echo "Usage: $0 <incident>"
    echo ""
    echo "Incidents:"
    echo "  crashloop-oom   — payment-service OOMKills (real OOM via memory limit)"
    echo "  error-rate      — payment-service 40% HTTP 500s"
    echo "  slow            — payment-service 1.5-4s latency"
    echo "  retry-storm     — notification-service hammers email-gateway"
    echo "  cert-expiry     — auth-service cert expiry warning"
    echo "  bad-rollout     — payment-service v2 with 50% error rate"
    echo "  dns-failure     — CoreDNS invalid upstream (all DNS breaks)"
    echo "  stuck-hpa       — node taint blocks HPA scaling"
    echo "  cascade         — ALL incidents at once (conference demo)"
    echo ""
    echo "  recover         — reset all faults"
    echo "  status          — show current cluster state"
    ;;
esac
