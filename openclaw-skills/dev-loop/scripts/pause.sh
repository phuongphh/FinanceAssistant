#!/usr/bin/env bash
# Tắt loop (kill switch). Worker đang chạy vẫn chạy nốt; không nhặt việc mới,
# không phản ứng /agent hay CI fail nữa.
#
# Usage: bash pause.sh

set -euo pipefail
source "$(dirname "$0")/_lib.sh"

require_admin
require_gh

gh variable set AGENT_LOOP_ENABLED --repo "$LOOP_REPO" --body false
log "⏸️  Đã tắt loop ($LOOP_REPO) — by user_id=$OPENCLAW_USER_ID"
