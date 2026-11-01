#!/usr/bin/env bash
# Chạy dispatcher ngay.
#
# Usage: bash run.sh [--dry-run] [--force]
#   --dry-run  chỉ xem dispatcher SẼ chọn issue nào (kết quả trong log Actions)
#   --force    bỏ qua active_hours (vd chạy lúc nửa đêm)

set -euo pipefail
source "$(dirname "$0")/_lib.sh"

require_admin
require_gh

dry_run=false
force=false
for arg in "$@"; do
    case "$arg" in
        --dry-run) dry_run=true ;;
        --force)   force=true ;;
        *) err "Tham số không hợp lệ: $arg (allowed: --dry-run, --force)"; exit 1 ;;
    esac
done

gh workflow run agent-dispatch.yml --repo "$LOOP_REPO" -f "dry_run=$dry_run" -f "force=$force"
log "Đã chạy dispatcher (dry_run=$dry_run, force=$force)."
log "Theo dõi: https://github.com/$LOOP_REPO/actions/workflows/agent-dispatch.yml"
