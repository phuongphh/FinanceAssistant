#!/usr/bin/env bash
# Shared helpers cho dev-loop skill scripts.
# Source bằng:  source "$(dirname "$0")/_lib.sh"
#
# Trách nhiệm:
#   - Verify caller là admin (OPENCLAW_USER_ID ∈ ADMIN_USER_IDS)
#   - Kiểm tra gh CLI + token
#   - Helper logging, validate tham số

set -euo pipefail

LOOP_REPO="${LOOP_REPO:-phuongphh/FinanceAssistant}"
ADMIN_USER_IDS="${ADMIN_USER_IDS:-}"
OPENCLAW_USER_ID="${OPENCLAW_USER_ID:-}"

log()  { printf '[dev-loop] %s\n' "$*"; }
err()  { printf '[dev-loop] ❌ %s\n' "$*" >&2; }

require_admin() {
    if [[ -z "$ADMIN_USER_IDS" ]]; then
        err "ADMIN_USER_IDS chưa cấu hình trên OpenClaw host — refuse all dev-loop commands."
        exit 1
    fi
    if [[ -z "$OPENCLAW_USER_ID" ]]; then
        err "OPENCLAW_USER_ID không có (skill được gọi sai context?)."
        exit 1
    fi
    # Literal match (grep -Fx), tránh regex injection từ user_id.
    local match
    match=$(printf '%s' "$ADMIN_USER_IDS" | tr ',' '\n' | grep -Fx "$OPENCLAW_USER_ID" || true)
    if [[ -z "$match" ]]; then
        err "User $OPENCLAW_USER_ID không phải admin — refuse."
        exit 1
    fi
}

require_gh() {
    if ! command -v gh >/dev/null 2>&1; then
        err "Thiếu gh CLI trên OpenClaw host."
        exit 1
    fi
    if [[ -z "${GH_TOKEN:-}${GITHUB_TOKEN:-}" ]] && ! gh auth status >/dev/null 2>&1; then
        err "gh chưa đăng nhập — set GH_TOKEN trên OpenClaw host."
        exit 1
    fi
}

# Số issue/PR phải là số nguyên dương — tránh inject tham số qua argv.
require_number() {
    local name="$1" value="${2:-}"
    if ! [[ "$value" =~ ^[0-9]+$ ]]; then
        err "$name phải là số nguyên dương: '${value}'"
        exit 1
    fi
}
