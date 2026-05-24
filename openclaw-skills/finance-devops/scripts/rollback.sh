#!/usr/bin/env bash
# Rollback prod 1 commit (git reset --hard HEAD~1) + rebuild stack.
#
# ⚠️ DESTRUCTIVE — DB migration KHÔNG auto-revert.
# Nếu deploy gần nhất chạy migration đổi schema, rollback code mà giữ schema
# có thể break app. Cần restore .backups/pre-deploy-*.sql.gz thủ công.
#
# Usage:
#   bash rollback.sh                  # rollback 1 commit
#   ROLLBACK_TO=abc1234 bash rollback.sh   # rollback về SHA cụ thể
#
# Env:
#   ROLLBACK_CONFIRMED=1   bắt buộc — tránh accidental invoke.

set -euo pipefail
source "$(dirname "$0")/_lib.sh"

require_admin
require_ssh_config

if [[ "${ROLLBACK_CONFIRMED:-0}" != "1" ]]; then
    err "Rollback là destructive. Cần ROLLBACK_CONFIRMED=1 để xác nhận."
    err "Skill caller phải xác nhận lại với admin trước khi set env này."
    exit 1
fi

TARGET="${ROLLBACK_TO:-HEAD~1}"

# Validate TARGET: hoặc HEAD~N, hoặc 7-40 char hex (git SHA).
if ! [[ "$TARGET" =~ ^HEAD~[0-9]+$|^[a-f0-9]{7,40}$ ]]; then
    err "ROLLBACK_TO không hợp lệ: $TARGET (cho phép HEAD~N hoặc git SHA hex)"
    exit 1
fi

log "Rollback prod về: $TARGET"
log "Triggered by user_id=$OPENCLAW_USER_ID @ $(date -u +%Y-%m-%dT%H:%M:%SZ)"
log "----------------------------------------------------------------"

ssh_prod -tt bash -s <<EOF
set -euo pipefail
cd "$PROD_PROJECT_DIR"

CURRENT_SHA=\$(git rev-parse HEAD)
echo "[rollback] Current SHA: \${CURRENT_SHA:0:7}"

# Resolve target SHA và verify nó thuộc lịch sử branch (không cho rollback
# về commit lạ).
TARGET_SHA=\$(git rev-parse --verify "$TARGET^{commit}" 2>/dev/null || true)
if [[ -z "\$TARGET_SHA" ]]; then
    echo "[rollback] ❌ Target không resolve được: $TARGET" >&2
    exit 1
fi
if ! git merge-base --is-ancestor "\$TARGET_SHA" "\$CURRENT_SHA"; then
    echo "[rollback] ❌ \${TARGET_SHA:0:7} không phải ancestor của HEAD — refuse." >&2
    exit 1
fi

echo "[rollback] Reset code về \${TARGET_SHA:0:7}..."
git reset --hard "\$TARGET_SHA"

echo "[rollback] Rebuild stack..."
docker compose --env-file "$PROD_PROJECT_DIR/.env" \\
    -p financeassistant \\
    -f "$PROD_PROJECT_DIR/deploy/production/docker-compose.yml" \\
    up -d --build --wait

echo "[rollback] Done. SHA hiện tại: \$(git log -1 --format='%h %s')"
echo "[rollback] ⚠️  DB migration KHÔNG revert. Check .backups/ nếu schema bị break."
EOF
