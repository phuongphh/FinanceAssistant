#!/usr/bin/env bash
# Start the named Cloudflare Tunnel using .cloudflared/config.yml
# Run tunnel-named-setup.sh first if you haven't already.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG_FILE="${PROJECT_ROOT}/.cloudflared/config.yml"
LOG_FILE="${HOME}/Library/Logs/finance-assistant/tunnel-named.log"

if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "Error: ${CONFIG_FILE} not found."
    echo "Run ./scripts/tunnel-named-setup.sh first."
    exit 1
fi

mkdir -p "$(dirname "$LOG_FILE")"

HOSTNAME_FILE="${PROJECT_ROOT}/.cloudflared/.tunnel-hostname"
if [[ -f "$HOSTNAME_FILE" ]]; then
    TUNNEL_HOSTNAME=$(cat "$HOSTNAME_FILE")
    echo "Starting tunnel → https://${TUNNEL_HOSTNAME}"
    echo "  Dashboard: https://${TUNNEL_HOSTNAME}/miniapp/dashboard"
else
    echo "Starting named Cloudflare tunnel..."
fi

echo "Logs: $LOG_FILE"
echo "Press Ctrl-C to stop."
echo ""

cloudflared tunnel --config "${CONFIG_FILE}" run 2>&1 | tee -a "$LOG_FILE"
