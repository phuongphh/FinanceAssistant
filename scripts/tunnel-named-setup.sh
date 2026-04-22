#!/usr/bin/env bash
# Named Cloudflare Tunnel Setup — run ONCE to create the tunnel.
# Requires: Cloudflare account + a domain managed in Cloudflare DNS.
#
# After this script succeeds:
# 1. A tunnel named "finance-assistant" is created under your CF account.
# 2. A DNS CNAME is added: <TUNNEL_HOSTNAME> → <tunnel-id>.cfargotunnel.com
# 3. Config written to .cloudflared/config.yml
# 4. Then run: ./scripts/tunnel-named-start.sh   (or install LaunchAgent)
#
# NOTE on DuckDNS: DuckDNS only supports A/AAAA records, not CNAME.
# Cloudflare Tunnel needs a CNAME + Cloudflare proxy (orange cloud).
# DuckDNS domains cannot be added to Cloudflare — use a domain you own
# (even a free Freenom/.tk domain, or buy a cheap .xyz for ~$1/year),
# OR use a workers.dev subdomain (see below).

set -euo pipefail

TUNNEL_NAME="finance-assistant"
BACKEND_PORT="${FINANCE_BACKEND_PORT:-8000}"
CONFIG_DIR="$(cd "$(dirname "$0")/.." && pwd)/.cloudflared"
CONFIG_FILE="${CONFIG_DIR}/config.yml"
CREDENTIALS_DIR="${HOME}/.cloudflared"

# ── Prompt for hostname ────────────────────────────────────────────────────────
echo ""
echo "=== Named Cloudflare Tunnel Setup ==="
echo ""
echo "This requires:"
echo "  1. A Cloudflare account (free at cloudflare.com)"
echo "  2. A domain added to Cloudflare DNS (NOT DuckDNS — see note above)"
echo ""
echo "Options for a free stable URL:"
echo "  A) Use a free domain (e.g. https://dash.cloudflare.com → Workers & Pages"
echo "     → your-subdomain.workers.dev — set up via Worker route)"
echo "  B) Buy a cheap .xyz domain (~$1/year) and add it to Cloudflare"
echo "  C) Use quick tunnel (URL changes on restart) — run tunnel-quick.sh instead"
echo ""
read -r -p "Enter your tunnel hostname (e.g. miniapp.yourdomain.com): " TUNNEL_HOSTNAME

if [[ -z "$TUNNEL_HOSTNAME" ]]; then
    echo "Error: hostname required. Exiting."
    exit 1
fi

# ── Step 1: Login ──────────────────────────────────────────────────────────────
echo ""
echo "Step 1: Login to Cloudflare (browser will open)..."
cloudflared login

# ── Step 2: Create tunnel ──────────────────────────────────────────────────────
echo ""
echo "Step 2: Creating tunnel '${TUNNEL_NAME}'..."
cloudflared tunnel create "${TUNNEL_NAME}"

TUNNEL_ID=$(cloudflared tunnel list --output json 2>/dev/null \
    | python3 -c "import sys,json; data=json.load(sys.stdin); \
      tunnels=[t for t in data if t['name']=='${TUNNEL_NAME}']; \
      print(tunnels[0]['id'] if tunnels else '')" 2>/dev/null || echo "")

if [[ -z "$TUNNEL_ID" ]]; then
    echo "Could not determine tunnel ID. Check: cloudflared tunnel list"
    exit 1
fi

echo "  Tunnel ID: ${TUNNEL_ID}"

# ── Step 3: Write config.yml ───────────────────────────────────────────────────
echo ""
echo "Step 3: Writing ${CONFIG_FILE}..."
mkdir -p "${CONFIG_DIR}"

cat > "${CONFIG_FILE}" <<EOF
tunnel: ${TUNNEL_ID}
credentials-file: ${CREDENTIALS_DIR}/${TUNNEL_ID}.json

ingress:
  - hostname: ${TUNNEL_HOSTNAME}
    service: http://localhost:${BACKEND_PORT}
    originRequest:
      connectTimeout: 30s
      noTLSVerify: false
  - service: http_status:404
EOF

echo "  Written: ${CONFIG_FILE}"

# ── Step 4: Create DNS CNAME ───────────────────────────────────────────────────
echo ""
echo "Step 4: Creating DNS CNAME ${TUNNEL_HOSTNAME} → ${TUNNEL_ID}.cfargotunnel.com ..."
cloudflared tunnel route dns "${TUNNEL_NAME}" "${TUNNEL_HOSTNAME}"

# ── Summary ────────────────────────────────────────────────────────────────────
echo ""
echo "============================================"
echo "  Setup complete!"
echo ""
echo "  Tunnel:    ${TUNNEL_NAME} (${TUNNEL_ID})"
echo "  URL:       https://${TUNNEL_HOSTNAME}"
echo "  Dashboard: https://${TUNNEL_HOSTNAME}/miniapp/dashboard"
echo ""
echo "  To start the tunnel:"
echo "    ./scripts/tunnel-named-start.sh"
echo ""
echo "  To install as LaunchAgent (auto-start on login):"
echo "    ./scripts/launchagent-install.sh"
echo "============================================"

# Save hostname for other scripts
echo "${TUNNEL_HOSTNAME}" > "${CONFIG_DIR}/.tunnel-hostname"
