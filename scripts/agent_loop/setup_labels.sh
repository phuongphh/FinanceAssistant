#!/usr/bin/env bash
# Tạo (hoặc cập nhật) các label mà agent loop dùng. Chạy 1 lần cho mỗi repo:
#   bash scripts/agent_loop/setup_labels.sh phuongphh/FinanceAssistant
# Cần `gh` đã login với quyền ghi issue trên repo.
set -euo pipefail

REPO="${1:-${GITHUB_REPOSITORY:-}}"
if [[ -z "$REPO" ]]; then
  echo "Usage: $0 owner/repo" >&2
  exit 1
fi

label() {
  gh label create "$1" --force -R "$REPO" --color "$2" --description "$3"
}

# State machine của loop
label "agent:ready"     "0E8A16" "Sẵn sàng cho coding agent nhặt"
label "agent:wip"       "FBCA04" "Agent đang làm (hoặc PR đang chờ review)"
label "agent:blocked"   "B60205" "Agent dừng: thiếu thông tin / lỗi — cần người xem"
label "agent:needs-fix" "D93F0B" "PR của agent cần sửa (CI fail, guard, push lỗi)"
label "agent:rejected"  "5319E7" "PR của agent bị đóng không merge"
label "agent:conflict"  "E99695" "PR của agent bị merge conflict với base"
label "agent"           "1D76DB" "PR do coding agent tạo"

# Area — US khác area chạy song song; area:db là exclusive (1 lúc 1 issue)
label "area:general" "C5DEF5" "Area mặc định"
label "area:db"      "C5DEF5" "Đụng schema/migration — chạy tuần tự"
label "area:bot"     "C5DEF5" "Telegram bot handlers"
label "area:zalo"    "C5DEF5" "Zalo channel"
label "area:wealth"  "C5DEF5" "Wealth / net worth"
label "area:docs"    "C5DEF5" "Chỉ docs"

echo "✅ Labels đã sẵn sàng trên $REPO"
