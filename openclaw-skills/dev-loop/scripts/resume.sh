#!/usr/bin/env bash
# Bật lại loop và chạy dispatcher ngay (không đợi cron 30 phút).
#
# Usage: bash resume.sh

set -euo pipefail
source "$(dirname "$0")/_lib.sh"

require_admin
require_gh

gh variable set AGENT_LOOP_ENABLED --repo "$LOOP_REPO" --body true
gh workflow run agent-dispatch.yml --repo "$LOOP_REPO"
log "▶️  Đã bật loop ($LOOP_REPO) và chạy dispatcher — by user_id=$OPENCLAW_USER_ID"
