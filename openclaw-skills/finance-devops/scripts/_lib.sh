#!/usr/bin/env bash
# Shared helpers cho finance-devops skill scripts.
# Source bằng:  source "$(dirname "$0")/_lib.sh"
#
# Trách nhiệm:
#   - Verify caller là admin (OPENCLAW_USER_ID ∈ ADMIN_USER_IDS)
#   - Build SSH command với options chuẩn
#   - Helper logging

set -euo pipefail

PROD_SSH_HOST="${PROD_SSH_HOST:-}"
PROD_SSH_USER="${PROD_SSH_USER:-evg-user}"
PROD_SSH_KEY="${PROD_SSH_KEY:-}"
PROD_PROJECT_DIR="${PROD_PROJECT_DIR:-/home/evg-user/FinanceAssistant}"
ADMIN_USER_IDS="${ADMIN_USER_IDS:-}"
OPENCLAW_USER_ID="${OPENCLAW_USER_ID:-}"

log()  { printf '[devops] %s\n' "$*"; }
err()  { printf '[devops] ❌ %s\n' "$*" >&2; }

require_admin() {
    if [[ -z "$ADMIN_USER_IDS" ]]; then
        err "ADMIN_USER_IDS chưa cấu hình trên OpenClaw host — refuse all devops commands."
        exit 1
    fi
    if [[ -z "$OPENCLAW_USER_ID" ]]; then
        err "OPENCLAW_USER_ID không có (skill được gọi sai context?)."
        exit 1
    fi
    # Match OPENCLAW_USER_ID với 1 trong ADMIN_USER_IDS (comma-separated).
    # Dùng grep -F để literal match, tránh regex injection từ user_id.
    local match
    match=$(printf '%s' "$ADMIN_USER_IDS" | tr ',' '\n' | grep -Fx "$OPENCLAW_USER_ID" || true)
    if [[ -z "$match" ]]; then
        err "User $OPENCLAW_USER_ID không phải admin — refuse."
        exit 1
    fi
}

require_ssh_config() {
    if [[ -z "$PROD_SSH_HOST" ]]; then
        err "PROD_SSH_HOST chưa cấu hình."
        exit 1
    fi
}

ssh_prod() {
    # SSH với options an toàn cho automation:
    #   -o BatchMode=yes              → không prompt password (key-only)
    #   -o ConnectTimeout=10          → fail fast nếu network drop
    #   -o ServerAliveInterval=30     → keep-alive cho deploy lâu
    #   -o StrictHostKeyChecking=accept-new → trust-on-first-use
    local ssh_args=(
        -o BatchMode=yes
        -o ConnectTimeout=10
        -o ServerAliveInterval=30
        -o StrictHostKeyChecking=accept-new
    )
    if [[ -n "$PROD_SSH_KEY" ]]; then
        ssh_args+=(-i "$PROD_SSH_KEY")
    fi
    ssh "${ssh_args[@]}" "${PROD_SSH_USER}@${PROD_SSH_HOST}" "$@"
}
