#!/usr/bin/env bash
# Chạy pytest cho Claude (job agent của agent-worker.yml) trong sandbox:
#   - network namespace riêng (chỉ có loopback) → không gửi dữ liệu ra ngoài;
#   - user nobody → không đọc được /proc/<pid>/environ của process Claude;
#   - env -i → token Claude (CLAUDE_CODE_OAUTH_TOKEN/ANTHROPIC_API_KEY) không lọt vào test.
# Code test do agent viết (conftest.py, fixture…) chạy ở đây, KHÔNG cùng quyền với Claude.
# Thiếu sudo/unshare/setpriv → từ chối chạy (fail closed), không fallback chạy trần.
#
# Workflow cài file này thành /usr/local/bin/sandbox-pytest (root sở hữu, agent không sửa được).
# Dùng: sandbox-pytest -q tests/<thư mục>
set -euo pipefail

die() { echo "sandbox-pytest: $*" >&2; exit 2; }

for bin in sudo unshare setpriv; do
  command -v "$bin" >/dev/null 2>&1 || die "thiếu '$bin' — không chạy test ngoài sandbox"
done
sudo -n true 2>/dev/null || die "cần sudo không mật khẩu — không chạy test ngoài sandbox"
PY="$(command -v python3 || command -v python)" || die "không tìm thấy python"

# shellcheck disable=SC2016  # $@ được bash con mở rộng, không phải shell này
exec sudo -n unshare --net -- bash -c 'ip link set lo up 2>/dev/null || true; exec "$@"' _ \
  setpriv --reuid=65534 --regid=65534 --clear-groups \
  env -i PATH="$(dirname "$PY"):/usr/local/bin:/usr/bin:/bin" HOME=/tmp LANG=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
  "$PY" -m pytest -p no:cacheprovider "$@"
