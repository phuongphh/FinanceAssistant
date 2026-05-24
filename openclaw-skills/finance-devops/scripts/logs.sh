#!/usr/bin/env bash
# Tail logs từ 1 service trên prod.
#
# Usage: bash logs.sh [service] [lines]
#   service: backend (default) | scheduler | postgres | redis
#   lines:   số dòng tail (default 100)

set -euo pipefail
source "$(dirname "$0")/_lib.sh"

require_admin
require_ssh_config

SERVICE="${1:-backend}"
LINES="${2:-100}"

# Whitelist services — tránh user inject shell args qua argv.
case "$SERVICE" in
    backend|scheduler|postgres|redis) ;;
    *)
        err "Service không hợp lệ: $SERVICE (allowed: backend|scheduler|postgres|redis)"
        exit 1
        ;;
esac

# Whitelist lines — phải là integer dương.
if ! [[ "$LINES" =~ ^[0-9]+$ ]]; then
    err "Lines phải là số nguyên dương: $LINES"
    exit 1
fi
if (( LINES > 2000 )); then
    log "Lines clipped 2000 → 2000 (max)"
    LINES=2000
fi

log "Tailing $LINES lines của $SERVICE trên prod..."
log "----------------------------------------------------------------"

ssh_prod bash -s <<EOF
set -euo pipefail
cd "$PROD_PROJECT_DIR"
docker compose --env-file "$PROD_PROJECT_DIR/.env" \\
    -p financeassistant \\
    -f "$PROD_PROJECT_DIR/deploy/production/docker-compose.yml" \\
    logs --tail=$LINES --no-color $SERVICE
EOF
