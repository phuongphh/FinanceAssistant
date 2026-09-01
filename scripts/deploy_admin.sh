#!/usr/bin/env bash
# ⚠️ DEPRECATED — KHÔNG dùng cho prod nữa (retired 2026-09).
#
# Script này thuộc kiến trúc cũ: backend chạy bằng systemd unit `betien-api`
# trên host, admin SPA build bằng npm trên host rồi copy vào backend/static/admin,
# Caddy reload thủ công.
#
# Prod hiện tại chạy Docker: admin SPA được build TRONG multi-stage image
# (backend/Dockerfile), stack lên bằng deploy/production/docker-compose.yml.
# Chạy script này trên prod sẽ vô ích (không có systemd unit `betien-api`) và
# có hại (dòng `rm -rf "${ADMIN_STATIC_DIR:?}"/*` xoá static của bản build hiện tại).
#
# Entry point deploy prod duy nhất:  bash scripts/rebuild-finance-prod.sh
# Quy trình release:                 docs/conventions/production-deployment.md
#
# Giữ lại vì còn được tham chiếu trong docs/admin/* và trong comment của
# alembic/versions/20260529_phase44_salutation.py (ngữ cảnh lịch sử).
# Đặt DEPLOY_ADMIN_LEGACY_OK=1 nếu thật sự cần chạy trên môi trường legacy.
set -euo pipefail

if [[ "${DEPLOY_ADMIN_LEGACY_OK:-0}" != "1" ]]; then
    echo "ERROR: scripts/deploy_admin.sh đã deprecated (kiến trúc systemctl+caddy cũ)." >&2
    echo "       Deploy prod bằng: bash scripts/rebuild-finance-prod.sh" >&2
    echo "       Nếu thật sự cần chạy trên môi trường legacy: DEPLOY_ADMIN_LEGACY_OK=1 bash scripts/deploy_admin.sh" >&2
    exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ADMIN_STATIC_DIR="${ADMIN_STATIC_DIR:-${REPO_ROOT}/backend/static/admin}"
API_SERVICE="${API_SERVICE:-betien-api}"
CADDY_CONFIG="${CADDY_CONFIG:-/etc/caddy/Caddyfile}"

cd "${REPO_ROOT}"
echo "=== Bé Tiền Admin Console Deploy ==="

echo "→ Verify required env"
: "${ADMIN_JWT_SECRET:?ADMIN_JWT_SECRET must be set before deploy}"
: "${DATABASE_URL:?DATABASE_URL must be set before deploy}"

echo "→ Apply migrations"
alembic upgrade head

echo "→ Seed initial admin (idempotent)"
python -m scripts.seed_admin

echo "→ Install frontend dependencies"
npm --prefix betien-admin install

echo "→ Build frontend"
VITE_API_BASE="${VITE_API_BASE:-https://admin.betien.vn/api/admin}" npm --prefix betien-admin run build

echo "→ Copy static files to ${ADMIN_STATIC_DIR}"
rm -rf "${ADMIN_STATIC_DIR:?}"/*
mkdir -p "${ADMIN_STATIC_DIR}"
cp -R betien-admin/dist/. "${ADMIN_STATIC_DIR}/"

echo "→ Restart FastAPI service (${API_SERVICE})"
systemctl restart "${API_SERVICE}"

echo "→ Reload Caddy"
caddy reload --config "${CADDY_CONFIG}"

echo "✓ Deploy complete. Run docs/admin/DEPLOY.md smoke test next."
