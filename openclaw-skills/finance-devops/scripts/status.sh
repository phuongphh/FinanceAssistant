#!/usr/bin/env bash
# Check prod status: current SHA, container health, last deploy log.
#
# Usage: bash status.sh

set -euo pipefail
source "$(dirname "$0")/_lib.sh"

require_admin
require_ssh_config

# Compose 1 remote script chạy hết các check, return về local — tránh nhiều
# SSH round-trip. Heredoc 'EOF' (quoted) → không expand vars local-side.
ssh_prod bash -s <<EOF
set -euo pipefail
cd "$PROD_PROJECT_DIR"

echo "=== Current SHA ==="
git log -1 --format='%h %cr — %s' HEAD
echo ""

echo "=== Branch ==="
git rev-parse --abbrev-ref HEAD
echo ""

echo "=== Container status ==="
docker compose --env-file "$PROD_PROJECT_DIR/.env" \\
    -p financeassistant \\
    -f "$PROD_PROJECT_DIR/deploy/production/docker-compose.yml" \\
    ps 2>/dev/null || echo "(docker compose ps failed)"
echo ""

echo "=== Latest deploy log ==="
ls -1t /tmp/rebuild-finance-*.log 2>/dev/null | head -1 || echo "(no deploy logs)"
echo ""

echo "=== Disk usage ==="
df -h "$PROD_PROJECT_DIR" | tail -1
echo ""

echo "=== Backups ==="
ls -1t "$PROD_PROJECT_DIR/.backups"/pre-deploy-*.sql.gz 2>/dev/null | head -3 || echo "(no backups)"
EOF
