#!/usr/bin/env bash
# Quick Cloudflare Tunnel — no account needed.
# Gives a free *.trycloudflare.com HTTPS URL that proxies localhost:8000.
# URL is printed to stdout and saved to /tmp/cf-tunnel-url.txt
# URL changes every time this script restarts.
#
# Use this for: initial testing, local development, demo sessions.
# For a stable URL, use tunnel-named-start.sh after running tunnel-named-setup.sh.

set -euo pipefail

BACKEND_PORT="${FINANCE_BACKEND_PORT:-8000}"
LOG_FILE="${HOME}/Library/Logs/finance-assistant/tunnel-quick.log"
URL_FILE="/tmp/cf-tunnel-url.txt"

mkdir -p "$(dirname "$LOG_FILE")"

echo "Starting Cloudflare quick tunnel → http://localhost:${BACKEND_PORT}"
echo "Logs: $LOG_FILE"
echo "URL will appear below (also saved to $URL_FILE):"
echo "---"

# Run tunnel, tee to log, and extract the URL from output
cloudflared tunnel --url "http://localhost:${BACKEND_PORT}" 2>&1 | tee "$LOG_FILE" | while IFS= read -r line; do
    echo "$line"
    # cloudflared prints: "Your quick Tunnel has been created! Visit it at (it may take some time to be reachable):"
    # followed by: "https://<random>.trycloudflare.com"
    if echo "$line" | grep -qE 'https://[a-zA-Z0-9-]+\.trycloudflare\.com'; then
        url=$(echo "$line" | grep -oE 'https://[a-zA-Z0-9-]+\.trycloudflare\.com')
        echo "$url" > "$URL_FILE"
        echo ""
        echo "============================================"
        echo "  TUNNEL URL: $url"
        echo "  Saved to:   $URL_FILE"
        echo ""
        echo "  Mini App Dashboard: ${url}/miniapp/dashboard"
        echo "  API:                ${url}/miniapp/api/"
        echo "============================================"
        echo ""
        echo "  Next: copy the tunnel URL and set it in BotFather:"
        echo "  /setmenubutton → paste URL/miniapp/dashboard"
        echo ""
    fi
done
