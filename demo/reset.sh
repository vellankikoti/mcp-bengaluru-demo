#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Resetting demo environment to clean state..."
bash "$SCRIPT_DIR/inject-incident.sh" recover
bash "$SCRIPT_DIR/recovery/save-checkpoint.sh"
echo "Reset complete."
