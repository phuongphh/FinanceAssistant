#!/usr/bin/env bash
# Yêu cầu agent sửa 1 PR của nó theo ghi chú (sau khi test tay thấy lỗi).
# Comment "/agent fix <ghi chú>" trên PR → worker mode=fix.
#
# Usage: bash fix.sh <pr_number> <ghi chú...>

set -euo pipefail
source "$(dirname "$0")/_lib.sh"

require_admin
require_gh

PR="${1:-}"
require_number "PR" "$PR"
shift
NOTE="$*"
if [[ -z "$NOTE" ]]; then
    err "Thiếu ghi chú — agent cần biết phải sửa gì."
    exit 1
fi
if (( ${#NOTE} > 4000 )); then
    err "Ghi chú quá dài (${#NOTE} ký tự, tối đa 4000)."
    exit 1
fi

# --body nhận nguyên chuỗi (không qua shell) → an toàn với ký tự đặc biệt.
gh pr comment "$PR" --repo "$LOOP_REPO" --body "/agent fix $NOTE"
log "Đã gửi yêu cầu sửa PR #$PR."
