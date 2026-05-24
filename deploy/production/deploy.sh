#!/usr/bin/env bash
# =============================================================================
# FinanceAssistant — Production deploy script (Docker)
# =============================================================================
# Chạy trên prod server:
#   bash deploy/production/deploy.sh
#
# Override mặc định:
#   DEPLOY_BRANCH=claude/some-branch bash deploy/production/deploy.sh
#   SKIP_PULL=1 bash deploy/production/deploy.sh        # bỏ qua git pull
#   HEALTH_TIMEOUT=120 bash deploy/production/deploy.sh # tăng timeout
# =============================================================================

set -euo pipefail

# --- Config ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"
PROJECT_NAME="${COMPOSE_PROJECT_NAME:-financeassistant}"
BRANCH="${DEPLOY_BRANCH:-prod}"
BACKEND_HEALTH_URL="${BACKEND_HEALTH_URL:-http://localhost:8002/health}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-60}"
SKIP_PULL="${SKIP_PULL:-0}"

# --- Helpers ---
log()  { echo "[$(date +%H:%M:%S)] $*"; }
fail() { echo "[FAIL] $*" >&2; exit 1; }

dc() {
  # --env-file: compose mặc định tìm `.env` cạnh compose file (= deploy/production/.env, không tồn tại).
  # Phải explicit trỏ về repo-root `.env` để interpolation `${POSTGRES_PASSWORD}` v.v. trong compose work.
  docker compose --env-file "$REPO_ROOT/.env" -p "$PROJECT_NAME" -f "$COMPOSE_FILE" "$@"
}

cd "$REPO_ROOT"

# --- Banner ---
log "================================================================"
log " FinanceAssistant — Docker production deploy"
log "================================================================"
log " Repo root : $REPO_ROOT"
log " Compose   : $COMPOSE_FILE"
log " Project   : $PROJECT_NAME"
log " Branch    : $BRANCH"
log " Health URL: $BACKEND_HEALTH_URL"
log "----------------------------------------------------------------"

# --- 1. Pre-flight: dependencies ---
command -v docker >/dev/null || fail "docker chưa cài đặt"
docker compose version >/dev/null 2>&1 || fail "docker compose plugin chưa cài đặt"
command -v curl >/dev/null || fail "curl chưa cài đặt"
[[ -f "$REPO_ROOT/.env" ]] || fail ".env không tồn tại ở repo root: $REPO_ROOT/.env"

# --- 2. Pre-flight: working tree clean ---
if [[ -n "$(git status --porcelain)" ]]; then
  log "Working tree dirty — các file sau chưa commit:"
  git status --short
  fail "Commit hoặc stash các thay đổi trước khi deploy"
fi

# --- 3. Pull latest ---
if [[ "$SKIP_PULL" == "1" ]]; then
  log "Bỏ qua git pull (SKIP_PULL=1). Đang ở: $(git log -1 --oneline)"
else
  log "Fetch origin/$BRANCH..."
  git fetch origin "$BRANCH"
  git checkout "$BRANCH"

  # Refuse nếu local có commit chưa push — tránh deploy code chưa qua review.
  # `git pull --ff-only` không catch case này (no-op nếu local ahead).
  ahead=$(git rev-list --count "origin/$BRANCH..HEAD")
  behind=$(git rev-list --count "HEAD..origin/$BRANCH")
  if (( ahead > 0 )); then
    log "Local branch ahead origin/$BRANCH bởi $ahead commit(s):"
    git log --oneline "origin/$BRANCH..HEAD"
    fail "Push hoặc revert local commits trước khi deploy (origin = single source of truth)"
  fi
  if (( behind > 0 )); then
    log "Local behind $behind commit(s) — fast-forward merge..."
    git merge --ff-only "origin/$BRANCH"
  fi
  log "Sync với origin/$BRANCH: $(git log -1 --oneline)"
fi

# --- 4. Build images ---
log "Build images backend + scheduler (cache layer được tái sử dụng nếu requirements.txt không đổi)..."
dc build backend scheduler

# --- 5. Up -d ---
# - postgres / redis: nếu config không đổi, container giữ nguyên (không restart).
# - backend / scheduler: image mới → container được recreate (~5-15s downtime).
# - Migration chạy bên trong backend container startup (alembic upgrade head).
log "Khởi động services (up -d)..."
dc up -d

# --- 6. Health check ---
log "Chờ backend health check (tối đa ${HEALTH_TIMEOUT}s)..."
start_ts=$(date +%s)
while true; do
  if curl -sf "$BACKEND_HEALTH_URL" >/dev/null 2>&1; then
    log "Backend OK: $BACKEND_HEALTH_URL"
    break
  fi
  elapsed=$(($(date +%s) - start_ts))
  if (( elapsed > HEALTH_TIMEOUT )); then
    log "Backend health check TIMEOUT sau ${HEALTH_TIMEOUT}s."
    log "==== Last 50 lines: backend ===="
    dc logs --tail=50 backend || true
    log "==== Last 50 lines: scheduler ===="
    dc logs --tail=50 scheduler || true
    fail "Health check failed. Xem log + chạy rollback nếu cần (xem README §Rollback)."
  fi
  sleep 2
done

# --- 6b. Deep smoke test (DB + Redis từ trong container) ---
# `/health` chỉ trả static OK (backend/main.py) → không phát hiện được runtime dep failure.
# Hai check dưới: alembic current chạm DB qua app config; redis-cli ping verify cache.
log "Smoke test: backend → DB (alembic current)..."
if ! dc exec -T backend alembic current >/dev/null 2>&1; then
  log "==== Smoke test FAIL — backend không connect được DB ===="
  dc exec -T backend alembic current 2>&1 || true
  dc logs --tail=30 backend || true
  fail "DB connectivity broken. Check DATABASE_URL override (compose environment block)."
fi
log "Smoke test: redis container ping..."
if ! dc exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; then
  fail "Redis không respond — check redis container status."
fi
log "Smoke tests PASS"

# --- 7. Status report ---
log "----------------------------------------------------------------"
log "Service status:"
dc ps
log "----------------------------------------------------------------"
log "Backend (10 dòng cuối):"
dc logs --tail=10 backend
log "----------------------------------------------------------------"
log "Scheduler (10 dòng cuối):"
dc logs --tail=10 scheduler
log "================================================================"
log " Deploy SUCCESS"
log "================================================================"
