#!/usr/bin/env bash
# =============================================================================
# rebuild-finance-prod.sh — Production deploy (Docker-based)
# =============================================================================
# Pipeline:
#   pre-flight → git pull → DB backup → admin-build check → docker compose down
#   → build (admin SPA build TRONG image) + up --wait → smoke test → cleanup → notify
#
# Khác với deploy/production/deploy.sh (minimal): script này bổ sung
# safety guards: DB snapshot trước migrate, rollback handler, Telegram notify,
# image prune. Admin SPA được build trong Docker multi-stage (host không cần
# npm). Đây là entry point mặc định cho prod deploy.
#
# Usage:
#   bash scripts/rebuild-finance-prod.sh
# Env overrides:
#   PROJECT_DIR       (default: /home/evg-user/FinanceAssistant)
#   BRANCH            (default: prod)
#   COMPOSE_FILE      (default: $PROJECT_DIR/deploy/production/docker-compose.yml)
#   PROJECT_NAME      (default: financeassistant)
#   BACKEND_PORT      (default: 8002, mapped on host)
#   HEALTH_TIMEOUT    (default: 120s)
#   SKIP_BACKUP       (1 = bỏ qua DB snapshot — KHÔNG khuyến nghị)
#   SKIP_PRUNE        (1 = bỏ qua docker image prune)
# =============================================================================

set -Eeuo pipefail

# ── config ─────────────────────────────────────────────────────
PROJECT_DIR="${PROJECT_DIR:-/home/evg-user/FinanceAssistant}"
BRANCH="${BRANCH:-prod}"
COMPOSE_FILE="${COMPOSE_FILE:-$PROJECT_DIR/deploy/production/docker-compose.yml}"
PROJECT_NAME="${COMPOSE_PROJECT_NAME:-financeassistant}"
BACKEND_PORT="${BACKEND_PORT:-8002}"
HEALTH_URL="http://localhost:${BACKEND_PORT}/health"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-120}"
ENV_FILE="$PROJECT_DIR/.env"
BACKUP_DIR="$PROJECT_DIR/.backups"
LOCK_FILE="/tmp/rebuild-finance-prod.lock"
TS="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="/tmp/rebuild-finance-${TS}.log"

REQUIRED_ENV_KEYS=(
    POSTGRES_PASSWORD
    DEEPSEEK_API_KEY
    ANTHROPIC_API_KEY
    TELEGRAM_BOT_TOKEN
    ADMIN_JWT_SECRET
)

# ── helpers ────────────────────────────────────────────────────
log()  { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*" | tee -a "$LOG_FILE"; }
err()  { printf '[%s] ❌ %s\n' "$(date +%H:%M:%S)" "$*" | tee -a "$LOG_FILE" >&2; }
step() { log ""; log "=== $* ==="; }

dc() {
    # --env-file explicit: compose mặc định tìm `.env` cạnh compose file (=
    # deploy/production/.env, không tồn tại). Phải trỏ về repo-root `.env`.
    docker compose --env-file "$ENV_FILE" -p "$PROJECT_NAME" -f "$COMPOSE_FILE" "$@"
}

notify() {
    # Best-effort Telegram notification to ADMIN_CHAT_ID (silent if not configured).
    local msg="$1"
    [[ -f "$ENV_FILE" ]] || return 0
    local token chat
    token=$(grep -E '^TELEGRAM_BOT_TOKEN=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' || true)
    chat=$(grep -E '^ADMIN_CHAT_ID=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' || true)
    [[ -n "${token:-}" && -n "${chat:-}" ]] || return 0
    curl -s --max-time 5 -X POST \
        "https://api.telegram.org/bot${token}/sendMessage" \
        -d "chat_id=${chat}" \
        -d "text=${msg}" >/dev/null 2>&1 || true
}

CURRENT_SHA=""
NEW_SHA=""
BACKUP_FILE=""
DEPLOY_PHASE="init"
DEPLOY_START=$(date +%s)

cleanup_lock() { rm -f "$LOCK_FILE"; }

do_rollback() {
    # Best-effort: reset code về SHA cũ và rebuild stack.
    # DB migration KHÔNG auto-revert — restore từ BACKUP_FILE thủ công nếu cần.
    err "Rolling back code to ${CURRENT_SHA:0:7}"
    git -C "$PROJECT_DIR" reset --hard "$CURRENT_SHA" 2>&1 | tee -a "$LOG_FILE" || true
    log "Rebuilding stack với code cũ..."
    dc build backend scheduler 2>&1 | tee -a "$LOG_FILE" || true
    dc up -d 2>&1 | tee -a "$LOG_FILE" || true
    err "Rollback xong. DB NOT reverted — restore từ ${BACKUP_FILE:-'(no backup taken)'} thủ công nếu schema bị break."
}

on_error() {
    local exit_code=$?
    trap - ERR
    err "Deploy FAILED at phase: $DEPLOY_PHASE (exit=$exit_code)"
    case "$DEPLOY_PHASE" in
        compose-up|smoke-test|health-check)
            # Past point of no return — stack đã được tear down/recreate. Try restore.
            do_rollback
            notify "❌ Prod deploy FAILED at [$DEPLOY_PHASE]. Rolled back to ${CURRENT_SHA:0:7}. Check $LOG_FILE."
            ;;
        *)
            notify "❌ Prod deploy FAILED at [$DEPLOY_PHASE]. Check $LOG_FILE."
            ;;
    esac
    cleanup_lock
    exit "$exit_code"
}
trap on_error ERR
trap cleanup_lock EXIT

# ── pre-flight ─────────────────────────────────────────────────
DEPLOY_PHASE="pre-flight"
log "================================================================"
log " Bé Tiền — PRODUCTION rebuild @ $TS"
log "================================================================"
log " Project   : $PROJECT_DIR"
log " Branch    : $BRANCH"
log " Compose   : $COMPOSE_FILE"
log " Health    : $HEALTH_URL"
log " Log       : $LOG_FILE"
log "----------------------------------------------------------------"

# Concurrency lock — nếu lock file tồn tại nhưng PID dead (deploy crash / kill -9 /
# host reboot), take over thay vì stall mãi mãi.
if ! ( set -o noclobber; echo "$$" > "$LOCK_FILE" ) 2>/dev/null; then
    lock_pid=$(cat "$LOCK_FILE" 2>/dev/null || echo "")
    if [[ -n "$lock_pid" ]] && kill -0 "$lock_pid" 2>/dev/null; then
        err "Another deploy đang chạy (lock: $LOCK_FILE held by PID $lock_pid)"
        trap - EXIT
        exit 1
    fi
    log "⚠️  Stale lock found (PID ${lock_pid:-unknown} not alive) — taking over"
    rm -f "$LOCK_FILE"
    echo "$$" > "$LOCK_FILE"
fi

# Dependency checks
command -v docker >/dev/null || { err "docker chưa cài đặt"; exit 1; }
docker compose version >/dev/null 2>&1 || { err "docker compose plugin chưa cài đặt"; exit 1; }
command -v curl >/dev/null || { err "curl chưa cài đặt"; exit 1; }
command -v git >/dev/null || { err "git chưa cài đặt"; exit 1; }

# Path checks
[[ -d "$PROJECT_DIR" ]]  || { err "PROJECT_DIR không tồn tại: $PROJECT_DIR"; exit 1; }
[[ -f "$ENV_FILE" ]]     || { err ".env không tồn tại: $ENV_FILE"; exit 1; }
[[ -f "$COMPOSE_FILE" ]] || { err "compose file không tồn tại: $COMPOSE_FILE"; exit 1; }

# Required env keys
for key in "${REQUIRED_ENV_KEYS[@]}"; do
    grep -qE "^${key}=." "$ENV_FILE" || { err "Missing required key in .env: $key"; exit 1; }
done

cd "$PROJECT_DIR"

# Dirty tree refuse
if [[ -n "$(git status --porcelain)" ]]; then
    err "Working tree dirty — commit/stash trước khi deploy:"
    git status --short | tee -a "$LOG_FILE"
    exit 1
fi

# Right branch
ACTUAL_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$ACTUAL_BRANCH" != "$BRANCH" ]]; then
    err "Không phải branch $BRANCH (đang ở: $ACTUAL_BRANCH). Refuse deploy."
    exit 1
fi

CURRENT_SHA="$(git rev-parse HEAD)"
log "Current SHA: ${CURRENT_SHA:0:7}"

# ── [1/7] git pull ─────────────────────────────────────────────
DEPLOY_PHASE="git-pull"
step "[1/7] Pull origin/$BRANCH"
git fetch origin "$BRANCH" 2>&1 | tee -a "$LOG_FILE"

# Refuse nếu local ahead — origin = single source of truth.
ahead=$(git rev-list --count "origin/$BRANCH..HEAD")
if (( ahead > 0 )); then
    err "Local ahead origin/$BRANCH bởi $ahead commit(s):"
    git log --oneline "origin/$BRANCH..HEAD" | tee -a "$LOG_FILE"
    err "Push hoặc revert local commits trước khi deploy."
    exit 1
fi

git pull --ff-only origin "$BRANCH" 2>&1 | tee -a "$LOG_FILE"
NEW_SHA="$(git rev-parse HEAD)"
if [[ "$CURRENT_SHA" == "$NEW_SHA" ]]; then
    log "ℹ️  No new commits — rebuild sẽ vẫn refresh image (deps có thể đổi)."
else
    log "Updated: ${CURRENT_SHA:0:7} → ${NEW_SHA:0:7}"
    log "Changed files:"
    git diff --name-only "$CURRENT_SHA..$NEW_SHA" | tee -a "$LOG_FILE"
fi

# ── [2/7] DB backup ────────────────────────────────────────────
DEPLOY_PHASE="db-backup"
step "[2/7] Backup database trước khi migrate"
if [[ "${SKIP_BACKUP:-0}" == "1" ]]; then
    log "⏭  SKIP_BACKUP=1 — bỏ qua backup (KHÔNG khuyến nghị)"
else
    mkdir -p "$BACKUP_DIR"
    BACKUP_FILE="$BACKUP_DIR/pre-deploy-${TS}.sql.gz"

    # pg_dump chạy TRONG postgres container — host không cần postgres-client.
    # Container postgres user/db lấy từ .env (defaults match compose file).
    PG_USER=$(grep -E '^POSTGRES_USER=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' || echo "finance")
    PG_DB=$(grep -E '^POSTGRES_DB=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' || echo "finance_db")
    PG_USER="${PG_USER:-finance}"
    PG_DB="${PG_DB:-finance_db}"

    # Verify postgres container running — nếu down (lần deploy đầu) thì skip backup.
    if dc ps postgres 2>/dev/null | grep -q "Up\|running"; then
        log "→ pg_dump $PG_DB từ container finance-postgres..."
        dc exec -T postgres pg_dump -U "$PG_USER" "$PG_DB" 2>>"$LOG_FILE" | gzip > "$BACKUP_FILE"
        log "Snapshot: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"
        # Keep last 10
        ls -1t "$BACKUP_DIR"/pre-deploy-*.sql.gz 2>/dev/null | tail -n +11 | xargs -r rm -f
    else
        log "⚠️  postgres container chưa chạy — bỏ qua backup (first-time deploy?)"
        BACKUP_FILE=""
    fi
fi

# ── [3/7] admin SPA — build TRONG Docker (host không cần npm) ──
# SPA build bằng multi-stage trong backend/Dockerfile (stage `admin-build`) rồi
# COPY vào image ở bước [5]. Host CHỈ cần docker — KHÔNG cần node/npm (deploy
# chạy trong namespace không có npm → cách build-trên-host cũ fail "npm: command
# not found"). VITE_API_BASE truyền vào build qua compose build.args, nội suy từ
# .env (dc dùng `--env-file`). Migration + seed vẫn chạy trong container
# (alembic ở startup; seed_admin ở bước [6]).
DEPLOY_PHASE="admin-build-check"
step "[3/7] Admin SPA build trong Docker (host không cần npm)"
ADMIN_SRC_DIR="$PROJECT_DIR/betien-admin"
if [[ -f "$ADMIN_SRC_DIR/package.json" ]]; then
    VITE_API_BASE_ENV="$(grep -E '^VITE_API_BASE=' "$ENV_FILE" | head -n1 | cut -d= -f2- | tr -d '\r')"
    log "  betien-admin/ sẽ được build trong image ở bước [5]"
    log "  VITE_API_BASE=${VITE_API_BASE_ENV:-https://admin.betien.vn/api/admin} (truyền qua compose build.args)"
else
    log "ℹ️  $ADMIN_SRC_DIR/package.json không tồn tại — image sẽ không có admin SPA"
fi

# ── [4/7] compose down ─────────────────────────────────────────
DEPLOY_PHASE="compose-down"
step "[4/7] Compose down (graceful)"
dc down --remove-orphans 2>&1 | tee -a "$LOG_FILE"

# ── [5/7] build + up --wait ────────────────────────────────────
DEPLOY_PHASE="compose-up"
step "[5/7] Build + up -d (chờ healthcheck với --wait)"
DOWN_START=$(date +%s)
dc build backend scheduler 2>&1 | tee -a "$LOG_FILE"
# --wait: docker compose tự block đến khi tất cả services có healthcheck = healthy
# (postgres + redis + backend). Timeout mặc định 600s — đủ thoải mái.
dc up -d --wait 2>&1 | tee -a "$LOG_FILE"

# ── [6/7] smoke test ───────────────────────────────────────────
DEPLOY_PHASE="smoke-test"
step "[6/7] Smoke test (health endpoint + DB + Redis)"

# 5a. /health endpoint
HEALTH_OK=0
start_ts=$(date +%s)
while true; do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$HEALTH_URL" || true)
    if [[ "$code" == "200" ]]; then
        HEALTH_OK=1
        log "  /health → HTTP 200"
        break
    fi
    elapsed=$(($(date +%s) - start_ts))
    if (( elapsed > HEALTH_TIMEOUT )); then
        err "Health check TIMEOUT sau ${HEALTH_TIMEOUT}s (last code: $code)"
        log "==== Last 50 lines: backend ===="
        dc logs --tail=50 backend 2>&1 | tee -a "$LOG_FILE" || true
        log "==== Last 50 lines: scheduler ===="
        dc logs --tail=50 scheduler 2>&1 | tee -a "$LOG_FILE" || true
        exit 1  # trap → do_rollback
    fi
    sleep 2
done

DOWN_END=$(date +%s)
DOWNTIME=$((DOWN_END - DOWN_START))

# 5b. DB connectivity (alembic current chạm DB qua app config)
log "→ DB connectivity (alembic current)..."
if ! dc exec -T backend alembic current >/dev/null 2>&1; then
    err "Backend không connect được DB"
    dc exec -T backend alembic current 2>&1 | tee -a "$LOG_FILE" || true
    exit 1
fi
log "  alembic current: $(dc exec -T backend alembic current 2>/dev/null | tail -1)"

# 5c. Redis ping
log "→ Redis ping..."
if ! dc exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; then
    err "Redis không respond"
    exit 1
fi
log "  redis-cli ping → PONG"

# 6d. Seed initial admin (idempotent — no-op nếu admin đã tồn tại). Chạy TRONG
# container (host có thể không có venv/deps). Non-fatal: lỗi seed không nên
# rollback một deploy đã healthy — chỉ cảnh báo để operator kiểm tra.
log "→ Seed admin (idempotent, trong container)..."
if dc exec -T backend python -m scripts.seed_admin 2>&1 | tee -a "$LOG_FILE"; then
    log "  seed_admin OK"
else
    log "⚠️  seed_admin lỗi (non-fatal) — kiểm tra ADMIN_JWT_SECRET / DB. Deploy vẫn tiếp tục."
fi

# ── [7/7] cleanup ──────────────────────────────────────────────
DEPLOY_PHASE="cleanup"
step "[7/7] Cleanup"
if [[ "${SKIP_PRUNE:-0}" != "1" ]]; then
    log "→ docker image prune (dangling)..."
    docker image prune -f 2>&1 | tee -a "$LOG_FILE" || true
fi
# Keep last 20 deploy logs
ls -1t /tmp/rebuild-finance-*.log 2>/dev/null | tail -n +21 | xargs -r rm -f

# ── done ───────────────────────────────────────────────────────
DEPLOY_PHASE="done"
trap - ERR
DEPLOY_END=$(date +%s)
TOTAL=$((DEPLOY_END - DEPLOY_START))

log ""
log "================================================================"
log " ✅ REBUILD HOÀN TẤT"
log "    Total:    ${TOTAL}s   (downtime backend: ${DOWNTIME}s)"
log "    SHA:      ${NEW_SHA:0:7}"
log "    Mini App: https://finance.nuitruc.ai/miniapp/wealth"
log "    Admin:    https://finance.nuitruc.ai/admin/"
log "    Docs:     https://finance.nuitruc.ai/docs"
log "    Log:      $LOG_FILE"
log "================================================================"

# Final service report
dc ps 2>&1 | tee -a "$LOG_FILE" || true

notify "✅ Prod deploy OK — ${NEW_SHA:0:7} (downtime ${DOWNTIME}s, total ${TOTAL}s)"
