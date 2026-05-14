#!/usr/bin/env bash
set -euo pipefail

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
