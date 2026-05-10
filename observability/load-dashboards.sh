#!/usr/bin/env bash
# Applies all Grafana dashboard JSONs as labelled ConfigMaps.
# Idempotent — safe to re-run. The Grafana sidecar picks them up within ~5s.
# Env overrides:
#   KUBE_CONTEXT   (default: kind-mcp-demo)
#   KUBECONFIG     (default: ~/.kube/mcp-demo.yaml)
#   GRAFANA_URL    (default: http://localhost:3000)
set -euo pipefail

CTX="${KUBE_CONTEXT:-kind-mcp-demo}"
export KUBECONFIG="${KUBECONFIG:-${HOME}/.kube/mcp-demo.yaml}"
GRAFANA_URL="${GRAFANA_URL:-http://localhost:3000}"
K="kubectl --context=${CTX}"

DASHBOARD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/grafana/dashboards" && pwd)"
GREEN='\033[0;32m'; CYAN='\033[0;36m'; RESET='\033[0m'

log()  { echo -e "${CYAN}[dashboards]${RESET} $*"; }
ok()   { echo -e "${GREEN}[dashboards]${RESET} $*"; }

apply_dashboard() {
  local json_file="$1"
  local name
  name="mcp-dash-$(basename "$json_file" .json)"

  log "Applying $name from $(basename "$json_file")..."

  python3 - <<PYEOF
import json, tempfile, os, subprocess, sys

with open("$json_file") as f:
    dashboard = json.load(f)

dashboard.pop("__inputs", None)
dashboard.pop("__requires", None)

dashboard_str = json.dumps(dashboard, ensure_ascii=False)

lines = ["apiVersion: v1",
         "kind: ConfigMap",
         "metadata:",
         "  name: $name",
         "  namespace: observability",
         "  labels:",
         "    grafana_dashboard: \"1\"",
         "data:",
         "  " + os.path.basename("$json_file") + ": |"]
for line in dashboard_str.splitlines():
    lines.append("    " + line)

yaml_content = "\n".join(lines) + "\n"

with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
    f.write(yaml_content)
    fname = f.name

env = {**os.environ}
result = subprocess.run(
    ["kubectl", "--context=${CTX}", "apply", "-f", fname],
    capture_output=True, text=True, env=env
)
os.unlink(fname)
if result.returncode != 0:
    print(f"  FAIL: {result.stderr.strip()}", file=sys.stderr)
    sys.exit(1)
print(f"  {result.stdout.strip()}")
PYEOF
}

log "Loading dashboards from $DASHBOARD_DIR"
echo ""

for json_file in "$DASHBOARD_DIR"/*.json; do
  apply_dashboard "$json_file"
done

echo ""
log "Waiting 8s for Grafana sidecar to pick up ConfigMaps..."
sleep 8

GRAFANA_API="${GRAFANA_URL%/}"
TOTAL=$(curl -sf "http://admin:admin@${GRAFANA_API#http://}/api/search?type=dash-db" 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d))" 2>/dev/null || echo "?")
ok "Done. Grafana now has $TOTAL dashboard(s) at ${GRAFANA_URL}"
echo ""
curl -sf "http://admin:admin@${GRAFANA_API#http://}/api/search?type=dash-db" 2>/dev/null | python3 -c "
import json, sys
for d in json.load(sys.stdin):
    print(f'  [{d[\"uid\"]:30}] {d[\"title\"]}')
" 2>/dev/null || true
