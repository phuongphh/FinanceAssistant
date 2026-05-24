#!/usr/bin/env bash
# rebuild-finance-prod.sh — Production deploy: pull, migrate, build, restart, health-check.
#
# Usage: ./rebuild-finance-prod.sh
# Env overrides:
#   PROJECT_DIR  (default: /home/evg-user/FinanceAssistant)
#   BRANCH       (default: prod)
#   PORT         (default: 8000)
#   SKIP_MINIAPP (1 = skip Mini App build)
#   SKIP_BACKUP  (1 = skip DB snapshot — not recommended)

set -Eeuo pipefail

# ── config ─────────────────────────────────────────────────────
PROJECT_DIR="${PROJECT_DIR:-/home/evg-user/FinanceAssistant}"
BRANCH="${BRANCH:-prod}"
PORT="${PORT:-8000}"
ENV_FILE="$PROJECT_DIR/.env"
VENV_DIR="$PROJECT_DIR/.venv"
BACKUP_DIR="$PROJECT_DIR/.backups"
LOCK_FILE="/tmp/rebuild-finance-prod.lock"
TS="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="/tmp/rebuild-finance-${TS}.log"

# Required env keys to validate before restart
REQUIRED_ENV_KEYS=(
    DATABASE_URL
    DEEPSEEK_API_KEY
    TELEGRAM_BOT_TOKEN
)

# ── helpers ────────────────────────────────────────────────────
log()   { printf '%s\n' "$*" | tee -a "$LOG_FILE"; }
err()   { printf '❌ %s\n' "$*" | tee -a "$LOG_FILE" >&2; }
step()  { log ""; log "=== $* ==="; }

notify() {
    # Best-effort Telegram notification to ADMIN_CHAT_ID (silent if not configured)
    local msg="$1"
    [[ -f "$ENV_FILE" ]] || return 0
    local token chat
    token=$(grep -E '^TELEGRAM_BOT_TOKEN=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"')
    chat=$(grep -E '^ADMIN_CHAT_ID=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"')
    [[ -n "$token" && -n "$chat" ]] || return 0
    curl -s --max-time 5 -X POST \
        "https://api.telegram.org/bot${token}/sendMessage" \
        -d "chat_id=${chat}" \
        -d "text=${msg}" >/dev/null || true
}

CURRENT_SHA=""
DEPLOY_PHASE="init"
cleanup_lock() { rm -f "$LOCK_FILE"; }
on_error() {
    local exit_code=$?
    err "Deploy FAILED at phase: $DEPLOY_PHASE (exit=$exit_code)"
    notify "❌ Prod deploy FAILED at [$DEPLOY_PHASE] — see $LOG_FILE"
    cleanup_lock
    exit "$exit_code"
}
trap on_error ERR
trap cleanup_lock EXIT

# ── pre-flight ─────────────────────────────────────────────────
DEPLOY_PHASE="pre-flight"
log "=== Bé Tiền — PRODUCTION rebuild @ $TS ==="
log "    Project: $PROJECT_DIR  Branch: $BRANCH  Log: $LOG_FILE"

# Concurrency lock (avoid two deploys racing)
if ! ( set -o noclobber; echo "$$" > "$LOCK_FILE" ) 2>/dev/null; then
    err "Another deploy is in progress (lock: $LOCK_FILE held by PID $(cat "$LOCK_FILE" 2>/dev/null || echo '?'))"
    trap - EXIT  # don't remove the other deploy's lock
    exit 1
fi

[[ -d "$PROJECT_DIR" ]]   || { err "PROJECT_DIR not found"; exit 1; }
[[ -f "$ENV_FILE" ]]      || { err ".env not found at $ENV_FILE"; exit 1; }
[[ -d "$VENV_DIR" ]]      || { err "venv not found at $VENV_DIR — run scripts/install-launchd.sh first"; exit 1; }
command -v uv >/dev/null  || { err "uv not installed — see https://docs.astral.sh/uv/"; exit 1; }

# Validate required env keys are present
for key in "${REQUIRED_ENV_KEYS[@]}"; do
    grep -qE "^${key}=." "$ENV_FILE" || { err "Missing required key in .env: $key"; exit 1; }
done

cd "$PROJECT_DIR"

# Refuse to deploy from a dirty working tree
if [[ -n "$(git status --porcelain)" ]]; then
    err "Working tree is dirty. Commit/stash changes before deploy:"
    git status --short | tee -a "$LOG_FILE"
    exit 1
fi

# Make sure we're on the right branch
ACTUAL_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$ACTUAL_BRANCH" != "$BRANCH" ]]; then
    err "Not on $BRANCH branch (currently on: $ACTUAL_BRANCH). Refusing to deploy."
    exit 1
fi

CURRENT_SHA="$(git rev-parse HEAD)"
log "Current SHA: $CURRENT_SHA"

# ── [1/7] pull ─────────────────────────────────────────────────
DEPLOY_PHASE="git-pull"
step "[1/7] Pull code mới nhất từ origin/$BRANCH"
git fetch origin "$BRANCH" 2>&1 | tee -a "$LOG_FILE"
git pull --ff-only origin "$BRANCH" 2>&1 | tee -a "$LOG_FILE"
NEW_SHA="$(git rev-parse HEAD)"
if [[ "$CURRENT_SHA" == "$NEW_SHA" ]]; then
    log "ℹ️  No new commits — rebuild will refresh deps/services anyway."
else
    log "Updated: $CURRENT_SHA → $NEW_SHA"
    log "Changed files:"
    git diff --name-only "$CURRENT_SHA..$NEW_SHA" | tee -a "$LOG_FILE"
fi

# ── [2/7] dependencies ─────────────────────────────────────────
DEPLOY_PHASE="uv-sync"
step "[2/7] Cài dependencies (uv sync)"
uv sync --frozen 2>&1 | tee -a "$LOG_FILE"

# ── [3/7] DB backup ────────────────────────────────────────────
DEPLOY_PHASE="db-backup"
step "[3/7] Backup database trước khi migrate"
if [[ "${SKIP_BACKUP:-0}" == "1" ]]; then
    log "⏭  SKIP_BACKUP=1 — bỏ qua backup (KHÔNG khuyến nghị)"
else
    mkdir -p "$BACKUP_DIR"
    DB_URL=$(grep -E '^DATABASE_URL=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"')
    BACKUP_FILE="$BACKUP_DIR/pre-deploy-${TS}.sql.gz"
    pg_dump "$DB_URL" 2>>"$LOG_FILE" | gzip > "$BACKUP_FILE"
    log "Snapshot: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"
    # Keep last 10 snapshots, drop the rest
    ls -1t "$BACKUP_DIR"/pre-deploy-*.sql.gz 2>/dev/null | tail -n +11 | xargs -r rm -f
fi

# ── [4/7] migration ────────────────────────────────────────────
DEPLOY_PHASE="alembic-migrate"
step "[4/7] Chạy DB migration (alembic)"
ALEMBIC="$VENV_DIR/bin/alembic"
log "Before:  $("$ALEMBIC" current 2>&1 | tail -1)"

HEADS_COUNT=$("$ALEMBIC" heads 2>/dev/null | grep -c '(head)' || true)
if [[ "$HEADS_COUNT" -gt 1 ]]; then
    err "Multiple alembic heads detected ($HEADS_COUNT). Refusing to auto-merge on prod."
    "$ALEMBIC" heads 2>&1 | tee -a "$LOG_FILE"
    err "Resolve locally with: alembic merge heads -m '...', then redeploy."
    exit 1
fi

"$ALEMBIC" upgrade head 2>&1 | tee -a "$LOG_FILE"
log "After:   $("$ALEMBIC" current 2>&1 | tail -1)"

# ── [5/7] Mini App build ───────────────────────────────────────
DEPLOY_PHASE="miniapp-build"
step "[5/7] Build Mini App frontend"
if [[ "${SKIP_MINIAPP:-0}" == "1" ]]; then
    log "⏭  SKIP_MINIAPP=1 — bỏ qua build frontend"
elif [[ -f "$PROJECT_DIR/miniapp/package.json" ]]; then
    (
        cd "$PROJECT_DIR/miniapp"
        npm ci 2>&1 | tee -a "$LOG_FILE"
        npm run build 2>&1 | tee -a "$LOG_FILE"
    )
    log "Mini App build OK"
else
    log "ℹ️  No miniapp/package.json — bỏ qua"
fi

# ── [6/7] restart services ─────────────────────────────────────
DEPLOY_PHASE="service-restart"
step "[6/7] Restart backend + scheduler (launchd)"
DOWN_START=$(date +%s)
for label in com.financeassistant.backend com.financeassistant.scheduler; do
    plist="$HOME/Library/LaunchAgents/${label}.plist"
    [[ -f "$plist" ]] || { err "Missing plist: $plist (run scripts/install-launchd.sh)"; exit 1; }
    launchctl unload "$plist" 2>&1 | tee -a "$LOG_FILE" || true
done
sleep 2
for label in com.financeassistant.backend com.financeassistant.scheduler; do
    launchctl load "$HOME/Library/LaunchAgents/${label}.plist" 2>&1 | tee -a "$LOG_FILE"
done

# Verify each service actually has a PID (load can "succeed" but process can crash)
sleep 5
for label in com.financeassistant.backend com.financeassistant.scheduler; do
    pid=$(launchctl list | awk -v l="$label" '$3==l {print $1}')
    if [[ -z "$pid" || "$pid" == "-" ]]; then
        err "Service $label loaded but has no PID — crashed on startup. Check launchd stdout/stderr logs."
        exit 1
    fi
    log "  $label → PID $pid"
done

# ── [7/7] health check + rollback on failure ───────────────────
DEPLOY_PHASE="health-check"
step "[7/7] Health check"

HEALTH_OK=0
for attempt in 1 2 3 4 5; do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://localhost:${PORT}/health" || true)
    log "  attempt $attempt: HTTP $code"
    if [[ "$code" == "200" ]]; then
        HEALTH_OK=1
        break
    fi
    sleep 3
done

DOWN_END=$(date +%s)
DOWNTIME=$((DOWN_END - DOWN_START))

if [[ "$HEALTH_OK" != "1" ]]; then
    err "Health check FAILED after 5 attempts — rolling back to $CURRENT_SHA"
    DEPLOY_PHASE="rollback"
    git reset --hard "$CURRENT_SHA" 2>&1 | tee -a "$LOG_FILE"
    uv sync --frozen 2>&1 | tee -a "$LOG_FILE" || true
    for label in com.financeassistant.backend com.financeassistant.scheduler; do
        launchctl unload "$HOME/Library/LaunchAgents/${label}.plist" 2>&1 | tee -a "$LOG_FILE" || true
        launchctl load "$HOME/Library/LaunchAgents/${label}.plist" 2>&1 | tee -a "$LOG_FILE" || true
    done
    err "Rolled back code. DB migration was NOT reverted — manually restore from $BACKUP_FILE if needed."
    notify "❌ Prod deploy FAILED health check. Code rolled back to ${CURRENT_SHA:0:7}. DB needs manual review."
    exit 1
fi

# ── cleanup old logs (keep last 20) ────────────────────────────
ls -1t /tmp/rebuild-finance-*.log 2>/dev/null | tail -n +21 | xargs -r rm -f

# ── done ───────────────────────────────────────────────────────
DEPLOY_PHASE="done"
trap - ERR
log ""
log "========================================"
log "✅ REBUILD HOÀN TẤT (downtime: ${DOWNTIME}s)"
log "   SHA:      ${NEW_SHA:0:7}"
log "   Mini App: https://finance.nuitruc.ai/miniapp/wealth"
log "   Admin:    https://finance.nuitruc.ai/admin/"
log "   Docs:     https://finance.nuitruc.ai/docs"
log "   Log:      $LOG_FILE"
log "========================================"

notify "✅ Prod deploy OK — ${NEW_SHA:0:7} (downtime ${DOWNTIME}s)"
