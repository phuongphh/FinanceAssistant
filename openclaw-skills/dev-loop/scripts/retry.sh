#!/usr/bin/env bash
# Cho agent làm lại 1 issue (vd sau khi đã trả lời câu hỏi lúc agent báo blocked).
# Comment "/agent retry" → agent-events.yml gỡ label lỗi, gắn lại agent:ready.
#
# Usage: bash retry.sh <issue_number>

set -euo pipefail
source "$(dirname "$0")/_lib.sh"

require_admin
require_gh

ISSUE="${1:-}"
require_number "issue" "$ISSUE"

gh issue comment "$ISSUE" --repo "$LOOP_REPO" --body "/agent retry"
log "Đã yêu cầu làm lại issue #$ISSUE."
