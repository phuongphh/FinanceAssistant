#!/usr/bin/env bash
# Trigger prod deploy qua SSH.
# Stream output live về stdout (OpenClaw sẽ forward về Telegram).
#
# Usage: bash deploy.sh
# Tất cả config qua env vars — xem SKILL.md.

set -euo pipefail
source "$(dirname "$0")/_lib.sh"

require_admin
require_ssh_config

log "SSH → ${PROD_SSH_USER}@${PROD_SSH_HOST} :: rebuild-finance-prod.sh"
log "Triggered by user_id=$OPENCLAW_USER_ID @ $(date -u +%Y-%m-%dT%H:%M:%SZ)"
log "----------------------------------------------------------------"

# Chạy rebuild script trên prod. `-tt` để PTY allocate → output stream real-time
# (không bị buffer). Exit code của remote command propagate về local.
ssh_prod -tt "bash '$PROD_PROJECT_DIR/scripts/rebuild-finance-prod.sh'"
exit_code=$?

log "----------------------------------------------------------------"
if [[ $exit_code -eq 0 ]]; then
    log "Deploy OK"
else
    err "Deploy exited với code $exit_code"
fi
exit $exit_code
