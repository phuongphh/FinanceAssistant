# Loop Engineering — coding agent tự nhặt việc → PR → người merge

> Mục tiêu: PM agent viết Epic/US lên GitHub Project #4 → coding agent (Claude Code
> chạy trong GitHub Actions) **tự** nhặt US đã sẵn sàng, code + test, mở PR, báo
> qua Telegram (OpenClaw). Người chỉ còn **review + test tay + merge**. Merge xong
> loop tự nhặt việc kế tiếp. US khác vùng code chạy song song.

---

## 1. Bức tranh tổng thể

```
PM agent ──► Issue (US) + label agent:ready (+ area:*, Priority trên Project)
                │
                ▼
┌──────────────────────── agent-dispatch.yml ────────────────────────┐
│ Trigger: cron 30' (7h–23h VN) · label agent:ready · issue closed ·  │
│          PR closed · push main · chạy tay (force / dry_run)          │
│ 1. on-event : PR merged/closed → dọn label + báo Telegram           │
│               PR agent behind main → update-branch / tự sửa conflict │
│               agent:wip mồ côi → gỡ, gắn blocked                     │
│ 2. select   : chọn issue theo WIP / area / priority / blocker        │
│               → gắn agent:wip, Project Status = In Progress          │
│               → dispatch agent-worker.yml (mode=implement)           │
└────────────────────────────────────────────────────────────────────┘
                │
                ▼
┌──────────────────────── agent-worker.yml ──────────────────────────┐
│ job agent   (KHÔNG có token ghi)                                    │
│   prepare task.md → claude -p (skill implement-issue) → gates       │
│   → gate fail: Claude sửa 1 lần → gates lần 2 → patch.diff artifact │
│ job publish (có PAT, KHÔNG chạy code agent)                         │
│   apply patch → guard → commit → push agent/issue-N-slug            │
│   → PR "[agent] #N …" (draft nếu gate fail) → Telegram              │
└────────────────────────────────────────────────────────────────────┘
                │
                ▼
Người: đọc "🧪 Cách test tay" trên Telegram → test → merge (hoặc /agent fix …)
                │
                └──► PR merged → dispatcher chạy lại → nhặt US tiếp theo

agent-events.yml: comment "/agent fix …" trên PR · "/agent retry" trên issue
                  · CI fail trên branch agent/* → worker mode=fix
```

Thành phần:

| File | Vai trò |
|---|---|
| `.github/agent-loop.yml` | Toàn bộ cấu hình (project, giới hạn, area, gates, guard). Mọi key optional |
| `.github/workflows/agent-dispatch.yml` | Dispatcher: dọn trạng thái + chọn việc |
| `.github/workflows/agent-worker.yml` | Worker: code 1 issue / sửa 1 PR |
| `.github/workflows/agent-events.yml` | Lệnh `/agent …` + phản ứng CI fail |
| `.github/workflows/ci.yml` | CI pytest trên mọi PR (tên `CI` — được loop theo dõi) |
| `scripts/agent_loop/` | Logic Python (selection, guard, notify, GitHub API) — có unit test |
| `.claude/skills/implement-issue/SKILL.md` | "Hợp đồng" cho Claude khi chạy không giám sát |
| `openclaw-skills/dev-loop/` | Điều khiển loop từ Telegram (status/pause/retry/fix…) |
| `tests/test_agent_loop/` | Test cho `scripts/agent_loop/` |

CLI dùng chung: `PYTHONPATH=scripts python -m agent_loop.cli [--repo R] [--config path] <cmd>`
với `<cmd>` ∈ `select`, `on-event`, `prepare`, `run-gates`, `guard`, `publish`,
`on-comment`, `on-ci-fail`, `notify`, `config-get`.

---

## 2. Trạng thái issue — label là "state machine"

| Label | Ý nghĩa | Ai gắn |
|---|---|---|
| `agent:ready` | US đủ rõ, agent được phép làm | PM agent / người |
| `agent:wip` | Agent đang code **hoặc** PR đang chờ review | dispatcher |
| `agent:blocked` | Agent có câu hỏi / worker chết / guard chặn | worker / reconcile |
| `agent:needs-fix` | PR mở nhưng gates fail hoặc hết lượt tự sửa | worker / sweep |
| `agent:conflict` | PR agent conflict với main | sweep |
| `agent:rejected` | PR bị đóng không merge | dispatcher |
| `agent` | Gắn lên **PR** do agent tạo | worker |
| `area:*` | Vùng code (`area:general`, `db`, `bot`, `zalo`, `wealth`, `docs`) | PM agent |

```
          (PM gắn)
 ready ───────────► wip ──── PR mở ────► (chờ review, vẫn wip)
   ▲                 │                         │
   │                 │ blocked / chết          ├── merged  → gỡ wip + ready, issue đóng
   │                 ▼                         └── closed  → gỡ wip, gắn rejected
   └── /agent retry ─ blocked / rejected
```

Lưu ý: PR đang chờ review **vẫn tính WIP**. Nghĩa là `wip_limit: 2` ⇒ tối đa 2
việc "đang dở" (code hoặc chờ bạn). Đây là cố ý — để agent không đẻ ra 10 PR
trong lúc bạn chưa kịp review.

---

## 3. Dispatcher chọn việc thế nào

Mỗi lần chạy `select` (trừ `--force`, chỉ chạy trong `active_hours` 7h–23h giờ VN):

1. **Lấy ứng viên**: issue open có `agent:ready`, chưa có `wip/blocked/rejected`.
   Nếu là **Epic** (có sub-issue) → mở rộng BFS ra các sub-issue; sub-issue
   **thừa hưởng Priority** của Epic nếu chính nó không có. Bản thân Epic không
   được code.
2. **Bỏ qua** issue đã có PR agent đang mở, hoặc đang bị **blocker**:
   - Dependencies native của GitHub (`issues/{n}/dependencies/blocked_by`), hoặc
   - Body có dòng `Blocked by #N` / `Depends on #N` / `Phụ thuộc #N` /
     `Phụ thuộc vào #N` mà #N còn open.
3. **Sắp xếp**: Priority trên Project (`P0` > `P1` > `P2` > `P3`, fallback đọc
   label `P0`… nếu issue không nằm trên Project), rồi số issue nhỏ trước.
4. **Giới hạn**:
   - `wip_limit` (2) — số slot = 2 − số issue đang `agent:wip`.
   - `daily_run_cap` (12) — tổng số lần chạy worker trong ngày (implement + fix),
     đếm theo `run-name` của worker.
   - **Area**: mỗi `area:*` chỉ 1 việc cùng lúc (issue không có area → `area:general`).
     Khác area → chạy **song song**.
   - **Exclusive** `area:db`: đang có việc `area:db` thì không nhặt gì thêm; muốn
     nhặt `area:db` thì phải chờ các việc khác xong (tránh 2 migration song song
     cùng `down_revision`).
5. Với mỗi issue được chọn: gắn `agent:wip` (gỡ `ready`), set Project Status =
   *In Progress*, dispatch `agent-worker.yml` (`mode=implement`).

`dry_run` in ra lựa chọn + lý do skip mà **không đổi gì** — chạy được cả khi
loop đang tắt.

### Dặn PM agent khi tạo US

- Gắn **1** label `area:*` đúng vùng code chính.
- Set **Priority** trên Project.
- Phụ thuộc → viết `Blocked by #N` trong body (hoặc dùng "Mark as blocked by").
- Acceptance Criteria rõ ràng, có kết quả mong đợi đo được.
- Chỉ gắn `agent:ready` khi US đã chốt — đó là "nút bấm" cho agent.

---

## 4. Worker — vì sao tách 2 job

Nội dung issue/comment/log là **dữ liệu không tin cậy** (prompt-injection). Vì
vậy:

| | job `agent` | job `publish` |
|---|---|---|
| Chạy code của agent / test | ✅ | ❌ |
| Có token GitHub ghi được | ❌ (`persist-credentials: false`, permissions read-only) | ✅ `PAT_TOKEN` |
| Có token Claude | ✅ | ❌ |
| Tooling loop lấy từ | snapshot `$RUNNER_TEMP/_loop` chụp **trước** khi Claude chạy | checkout base branch (`_loop/`) |

Các bước job `agent`:

1. Snapshot `scripts/agent_loop` + `agent-loop.yml` ra ngoài working tree →
   Claude có sửa file cũng không đổi được gates.
2. Cài deps backend (fallback bỏ `vnstock` nếu cài lỗi) + Claude Code CLI.
3. `prepare` → tạo `.agent-out/task.md` (issue, Epic cha, comment của
   OWNER/MEMBER/COLLABORATOR, review, log CI…) + `meta.json` (`base_sha`).
   Mode fix: checkout branch PR, merge main vào (nếu conflict thì để marker cho
   Claude xử lý).
4. `claude -p` với `--max-turns 80`, `--allowedTools` hẹp (Read/Edit/Write/
   Glob/Grep + Bash cho pytest/ruff/git status|diff|log/ls/mkdir — **không** có
   network, không `git commit/push`).
5. **Gates** → fail thì Claude sửa **1 lần** (bỏ qua nếu agent đã báo
   `blocked`) → gates lần 2.
6. Xuất `patch.diff` (so với `base_sha`) + upload artifact `agent-out` (giữ 7 ngày,
   xem lại log Claude ở đây khi cần debug).

Job `publish`:

1. `git apply` patch → **guard** → commit (tác giả `be-tien-agent`) → push
   `agent/issue-N-slug`.
2. Mở PR `[agent] #N <title>` với `Closes #N`, body = `summary.md` + kết quả
   gates + câu hỏi. Gates fail → PR **draft** + label `agent:needs-fix`.
3. Telegram: link PR + mục **🧪 Cách test tay** + câu hỏi của agent.
4. Agent báo `blocked` hoặc guard chặn → **không** mở PR, gắn `agent:blocked`,
   comment câu hỏi lên issue, báo Telegram.

### Gates (trong `agent-loop.yml`)

```yaml
gates:
  pytest: python -m pytest -q -p no:cacheprovider -x --maxfail=20
  ruff:   <file .py thay đổi> | xargs -r ruff check --select E9,F63,F7,F82
```

Ruff chỉ check lỗi nghiêm trọng trên file thay đổi vì repo đang có sẵn rất
nhiều lỗi ruff cũ. Muốn chặt hơn thì sửa dòng này.

### Guard (chạy trên patch, trong job có PAT)

- `forbidden`: `.env`, `.env.*`, `.github/**`, `scripts/agent_loop/**`,
  `.claude/skills/implement-issue/**` — agent không tự sửa được luật của chính nó.
- `allowed`: `.env.example`.
- `immutable_existing`: `alembic/versions/**` — sửa/xoá migration **đã có** →
  chặn; thêm migration **mới** → chỉ cảnh báo trong PR.
- Còn conflict marker (`<<<<<<<` …) → chặn.

---

## 5. Tự sửa và tự dọn

| Tình huống | Loop làm gì |
|---|---|
| PR agent **behind** main | `sweep_prs` gọi update-branch (nếu `auto_update_branch`) |
| PR agent **conflict** | Gắn `agent:conflict`, dispatch worker `mode=fix` (Claude resolve) — tối đa `max_auto_fix` (2) lần, sau đó báo "cần người" |
| **CI fail** trên `agent/*` | `agent-events.yml` → `on-ci-fail`: chỉ khi head SHA khớp, chưa quá `max_auto_fix`, không có worker đang chạy → worker `mode=fix` với log CI |
| Worker chết / bị cancel | `reconcile_wip`: issue `agent:wip` không có PR mở và không có run đang chạy quá **15 phút** → gỡ wip; PR đã merged → gỡ ready; PR closed → `rejected`; không có PR → `blocked` + comment hướng dẫn `/agent retry` + Telegram |
| PR **merged** | Gỡ label, Telegram "✅ Đã merge…"; nếu mọi sub-issue của Epic đã đóng → "🎉 Epic xong" |
| PR **đóng không merge** | Gắn `agent:rejected` + Telegram |

Số lần tự sửa được đếm bằng comment marker `<!-- agent-loop:auto-fix -->` trên PR.

### Lệnh tay (comment trên GitHub — chỉ OWNER/MEMBER/COLLABORATOR)

- `/agent fix <ghi chú>` trên PR agent → worker `mode=fix`, đọc ghi chú (ưu tiên
  cao nhất) + review comment + CI log, push commit sửa lên **chính PR đó**.
- `/agent retry` trên issue → gỡ `blocked/rejected`, gắn lại `agent:ready`. Nếu
  agent có câu hỏi, **trả lời bằng comment trên issue trước** rồi mới retry —
  agent sẽ đọc comment đó.

`agent-events.yml` luôn checkout **base branch**, không bao giờ chạy code từ PR.

---

## 6. Điều khiển từ Telegram — skill OpenClaw `dev-loop`

`openclaw-skills/dev-loop/` (chỉ admin trong `ADMIN_USER_IDS`):

| Nói với bot | Script | Tác dụng |
|---|---|---|
| "loop đang làm gì" | `status.sh` | Bật/tắt, đang code, PR chờ review, việc cần người |
| "còn bao nhiêu việc" | `queue.sh` | Issue `agent:ready` |
| "tạm dừng agent" | `pause.sh` | `AGENT_LOOP_ENABLED=false` (worker đang chạy vẫn chạy nốt) |
| "bật lại agent" | `resume.sh` | `=true` + kick dispatcher |
| "chạy loop ngay" / "thử dry-run" | `run.sh [--dry-run\|--force]` | Chạy dispatcher ngay |
| "cho agent làm lại #123" | `retry.sh 123` | Comment `/agent retry` |
| "sửa PR #456: …" | `fix.sh 456 "…"` | Comment `/agent fix …` |

Env trên OpenClaw host: `ADMIN_USER_IDS`, `GH_TOKEN` (fine-grained PAT: Issues,
Pull requests, Actions, Variables R/W; Contents R), `LOOP_REPO`
(default `phuongphh/FinanceAssistant`). Skill **không bao giờ merge**.

Tin báo tự động (PR mới, blocked, merged, Epic xong) đi **thẳng** từ GitHub
Actions qua Telegram Bot API (`LOOP_TELEGRAM_BOT_TOKEN` + `LOOP_TELEGRAM_CHAT_ID`)
— có thể dùng chính bot OpenClaw hoặc 1 bot riêng. Thiếu secret thì bỏ qua,
không làm fail workflow.

---

## 7. Chi phí & giới hạn

- **Claude**: mỗi run ≤ `max_turns` 80 turn × tối đa 2 lần (implement + retry
  gate). `daily_run_cap` 12 run/ngày chặn chi phí trên. Dùng
  `CLAUDE_CODE_OAUTH_TOKEN` (gói Pro/Max — tính vào quota gói) hoặc
  `ANTHROPIC_API_KEY` (trả theo token).
- **GitHub Actions**: worker ~10–40 phút/run (cài deps + full pytest 2–3 lần).
  Repo private dùng phút Actions của tài khoản; cron dispatcher chỉ ~30 giây/lần.
- Giờ hoạt động 7h–23h VN: ngoài giờ không nhặt việc mới (PR/CI fix vẫn xử lý).

---

## 8. Checklist bật loop (làm 1 lần)

1. **Secrets** (Settings → Secrets and variables → Actions):
   - `PAT_TOKEN` — scopes `repo`, `project`, **`workflow`** (cần để dispatch
     workflow và push branch). Fine-grained thì: Contents, Issues, Pull requests,
     Actions, Workflows R/W + Projects R/W.
   - `CLAUDE_CODE_OAUTH_TOKEN` (chạy `claude setup-token` trên máy bạn) **hoặc**
     `ANTHROPIC_API_KEY`.
   - `LOOP_TELEGRAM_BOT_TOKEN`, `LOOP_TELEGRAM_CHAT_ID`.
2. **Labels**: `bash scripts/agent_loop/setup_labels.sh phuongphh/FinanceAssistant`.
3. **Thử khô**: Actions → *Agent Dispatch* → Run workflow, tick `dry_run` → xem
   log nó định chọn issue nào.
4. **Bật**: repo variable `AGENT_LOOP_ENABLED` = `true`.
5. **OpenClaw**: cài skill `openclaw-skills/dev-loop` + set env ở mục 6.
6. **PM agent**: cập nhật prompt để gắn `area:*`, Priority, `Blocked by #N`,
   `agent:ready` (mục 3).
7. **Smoke test**: gắn `agent:ready` cho 1 US thật nhỏ → kiểm tra: label đổi sang
   `agent:wip`, Project → In Progress, worker chạy, PR `[agent] #N` xuất hiện,
   Telegram có tin → merge → wip được gỡ, US tiếp theo được nhặt.

---

## 9. Áp dụng cho repo khác

Bước 1 (ngay bây giờ — copy):

1. Copy sang repo mới:
   - `scripts/agent_loop/` (cả `setup_labels.sh`)
   - `.github/workflows/agent-dispatch.yml`, `agent-worker.yml`,
     `agent-events.yml` (+ `ci.yml` nếu repo chưa có CI chạy test trên PR)
   - `.github/agent-loop.yml`
   - `.claude/skills/implement-issue/SKILL.md`
   - `tests/test_agent_loop/` (tuỳ chọn)
2. Sửa `.github/agent-loop.yml`:
   - `project.number` (và `owner`), tên field Status/Priority nếu khác.
   - `gates` — lệnh test/lint của repo đó (VD Node: `npm ci && npm test`).
   - `guard` — file cấm/bất biến (migrations của framework khác…).
   - `areas` — vùng code + vùng exclusive.
   - `ci_workflows` — **tên** workflow CI (khớp `workflows:` trong `agent-events.yml`).
3. Sửa phần cài deps trong `agent-worker.yml` (Python/Node/…).
4. Viết lại phần "Quy ước code" trong `SKILL.md` theo `CLAUDE.md` của repo đó.
5. Làm checklist mục 8. Skill `dev-loop` dùng chung — chỉ đổi `LOOP_REPO`
   (hoặc cài thêm 1 bản với `LOOP_REPO` khác).

Bước 2 (khi có ≥ 3 repo — tập trung hoá):

- Tách repo `phuongphh/agent-loop` chứa `scripts/agent_loop` + **reusable
  workflows** (`on: workflow_call`). Repo con chỉ còn 3 workflow mỏng
  `uses: phuongphh/agent-loop/.github/workflows/worker.yml@v1` + file
  `agent-loop.yml` + skill. Sửa loop 1 chỗ, mọi repo hưởng (pin theo tag để an toàn).

---

## 10. Rủi ro đã biết

- **PAT cần scope `workflow`** — thiếu thì dispatch/push branch fail.
- **Test trong job `agent` đọc được token Claude** (cùng job với Claude). Token
  GitHub ghi được thì không — chỉ ở job `publish`. Nếu lo, dùng API key riêng có
  hạn mức cho loop.
- **Worker bị cancel/timeout** → `publish` hoặc `reconcile_wip` gắn `blocked`;
  khôi phục bằng `/agent retry`.
- **Concurrency dispatcher chỉ giữ 1 run chờ** — event dồn dập có thể bị gộp;
  cron 30 phút là lưới an toàn.
- **`issue-lifecycle.yml` commit `docs/issues/` lên main** mỗi lần đổi label →
  dispatcher đã `paths-ignore: docs/issues/**` để không tự kích hoạt vòng lặp.
- **`pause` không dừng worker đang chạy** — muốn dừng ngay thì Cancel run trên
  Actions (issue sẽ được reconcile thành `blocked`).
- **Agent không tự đổi được gates/guard**: Claude không có quyền push, guard
  chạy trên patch trong job khác, tooling lấy từ base branch / snapshot.
- **Migration song song**: 2 US cùng tạo migration sẽ trùng `down_revision` →
  luôn gắn `area:db` (exclusive) cho US có migration.
- Agent **không bao giờ merge**. Merge luôn là quyết định của người.
