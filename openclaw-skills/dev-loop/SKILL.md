---
name: dev-loop
description: >
  Điều khiển Loop Engineering (coding agent tự động trên GitHub Actions) từ
  Telegram — xem loop đang làm gì, hàng đợi, tạm dừng/bật lại, chạy ngay, cho
  agent làm lại 1 issue, yêu cầu agent sửa 1 PR. CHỈ admin được phép dùng
  (kiểm soát bằng ADMIN_USER_IDS env var).
metadata:
  openclaw:
    requires:
      bins: ["bash", "gh"]
---

# Dev Loop Skill

Skill này cho phép admin điều khiển coding agent tự động (Loop Engineering)
trực tiếp từ Telegram. Mỗi script là thin wrapper gọi `gh` CLI vào repo
GitHub — không chứa business logic. Logic thật nằm trong
`scripts/agent_loop/` + `.github/workflows/agent-*.yml` của repo.

Thiết kế tổng thể: `docs/architecture/loop-engineering.md`.

## Khi nào dùng skill này

- Hỏi trạng thái: "loop đang làm gì", "agent đang code gì", "status loop",
  "có PR nào chờ review không"
- Xem hàng đợi: "còn bao nhiêu việc", "queue agent", "issue nào đang chờ"
- Tạm dừng: "tạm dừng agent", "dừng loop", "pause loop"
- Bật lại: "bật lại agent", "resume loop", "cho agent chạy tiếp"
- Chạy ngay (không chờ cron): "chạy loop ngay", "kick agent", "thử dry-run loop"
- Làm lại 1 issue bị blocked/rejected: "cho agent làm lại #123", "retry #123"
- Sửa PR agent: "sửa PR #456: đổi tên nút thành …", "PR #456 test tay bị lỗi X"

**Không phải admin** → từ chối ngay, KHÔNG chạy bất kỳ command nào.

## Security model

Script tự verify `OPENCLAW_USER_ID` (Telegram user_id do OpenClaw inject) match
1 trong các giá trị trong `ADMIN_USER_IDS` (comma-separated). Không match →
exit 1 với message "refuse" trước khi gọi `gh`.

`GH_TOKEN` chỉ tồn tại trên server chạy OpenClaw bot, không bao giờ commit vào
repo. Tham số từ user (số issue/PR, ghi chú) được validate trong script
(số nguyên dương, ghi chú ≤ 4000 ký tự) và luôn truyền dưới dạng 1 argument —
không ghép vào shell.

Comment `/agent …` được post bằng token của admin → workflow
`agent-events.yml` chấp nhận vì tác giả là OWNER/COLLABORATOR.

## ⛔ Guardrails

- **KHÔNG BAO GIỜ merge PR thay admin.** Merge là bước người review làm tay
  trên GitHub sau khi test. Skill này không có script merge — đừng tự gọi
  `gh pr merge`.
- **TUYỆT ĐỐI KHÔNG đụng `.env`** (trên OpenClaw host lẫn prod). Xem
  [AGENTS.md](../../AGENTS.md).
- Chỉ chạy các script trong skill này. KHÔNG chạy `gh` ad-hoc làm thay đổi
  repo (xoá branch, đóng issue, sửa label/variable, sửa workflow).
- `pause` có hiệu lực ngay với lần dispatch tiếp theo, nhưng worker **đang
  chạy** vẫn chạy nốt — nói rõ điều này với admin.

### Required env vars (set trên OpenClaw host)

| Var | Ví dụ | Ghi chú |
|---|---|---|
| `ADMIN_USER_IDS` | `123456789,987654321` | Telegram user_id của admin, comma-separated |
| `GH_TOKEN` | `github_pat_…` | Fine-grained PAT, chỉ repo cần điều khiển: Issues R/W, Pull requests R/W, Actions R/W, Variables R/W, Contents R |
| `LOOP_REPO` | `phuongphh/FinanceAssistant` | Repo `owner/name` (default như ví dụ). Đổi để điều khiển repo khác |

## Cách thực thi

### Trạng thái loop

```bash
bash scripts/status.sh
```

In ra: loop đang bật/tắt (`AGENT_LOOP_ENABLED`), issue đang code
(`agent:wip`), PR agent đang mở (chờ review), issue `agent:blocked` /
`agent:needs-fix` (cần admin), worker run đang chạy trên Actions.

### Hàng đợi

```bash
bash scripts/queue.sh
```

Liệt kê issue có label `agent:ready` chưa được nhặt. Thứ tự thực tế do
dispatcher quyết định (Priority trên Project, area, WIP limit).

### Tạm dừng loop

```bash
bash scripts/pause.sh
```

Set repo variable `AGENT_LOOP_ENABLED=false`. Dispatcher ngừng nhặt việc mới;
worker đang chạy vẫn chạy xong và mở PR.

### Bật lại loop

```bash
bash scripts/resume.sh
```

Set `AGENT_LOOP_ENABLED=true` và kick dispatcher chạy ngay.

### Chạy dispatcher ngay

```bash
bash scripts/run.sh                # chạy thật
bash scripts/run.sh --dry-run      # chỉ xem SẼ chọn issue nào, không đổi gì
bash scripts/run.sh --force        # bỏ qua giờ hoạt động (active_hours)
```

`--dry-run` chạy được cả khi loop đang tắt — dùng để kiểm tra trước khi bật.
Kết quả dry-run xem trong tab Actions → "Agent Dispatch".

### Cho agent làm lại 1 issue

```bash
bash scripts/retry.sh 123
```

Comment `/agent retry` lên issue #123 → gỡ `blocked`/`rejected`, gắn lại
`agent:ready`. Nếu issue bị blocked vì câu hỏi, admin nên trả lời câu hỏi
bằng comment trên issue **trước** khi retry (agent sẽ đọc comment đó).

### Yêu cầu agent sửa PR

```bash
bash scripts/fix.sh 456 "Nút Xác nhận phải nằm dưới cùng, và số tiền hiển thị dạng 1.5tr"
```

Comment `/agent fix <ghi chú>` lên PR #456 → worker chạy mode=fix, đọc ghi
chú + review comment + CI log, push commit sửa lên chính PR đó, báo lại qua
Telegram. Ghi chú càng cụ thể (bước tái hiện, kết quả mong đợi) càng tốt.

## Output format

- Trả lời admin ngắn gọn bằng tiếng Việt, giữ nguyên số issue/PR và link.
- `status`: tóm tắt dạng "Loop: BẬT · đang code 2 (#12, #15) · chờ review 1
  PR (#40) · cần anh xử lý: #18 blocked".
- Lệnh thay đổi trạng thái (`pause`, `resume`, `run`, `retry`, `fix`): xác
  nhận đã làm gì + bước tiếp theo sẽ xảy ra (VD: "agent sẽ báo qua Telegram
  khi PR sửa xong").
- Script exit ≠ 0 → báo nguyên văn dòng lỗi `[dev-loop] ❌ …`, không tự thử
  cách khác.
