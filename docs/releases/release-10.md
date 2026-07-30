# Release 10 — Deploy Notes (1.4.7.0.1)

> **Ngày deploy:** 2026-07-30
> **Branch:** `claude/phase-4-7-prod-deploy-u77gl7` → `prod` (qua PR)
> **Diff:** `origin/prod..origin/main` (117 commits — 35 substantive, còn lại `docs(issues): sync …`; 177 files, +14.413 −1.083)
> **Commit prod trước release:** `3134d02 Merge pull request #956 from phuongphh/claude/merge-prod-release-12-feedback`
> **APP_VERSION:** `1.4.4.10` → `1.4.7.0.1` (hiển thị ở `/about`, đồng thời bust cache miniapp qua `APP_VERSION_MARKER`)

## Tổng quan

Release 10 gom toàn bộ work kể từ release 9 (merge prod gần nhất #956), tập trung 4 hướng:

1. **Phase 4.5 — Decision Engine Foundation** (PR #981): hỏi một câu quyết định thật và
   nhận câu trả lời dựa trên số liệu của chính user — feasibility Q&A, shock simulation,
   thanh "độ nét", tone dial, `/export` Excel, decision query log.
2. **Phase 4.6 — Onboarding Reset** (PR #983, #986, #988, #990, #992, #995): làm lại
   onboarding cho segment 22-35, activation nudge cho cohort chưa kích hoạt, decision
   moment sau Twin reveal, đo lường adoption/retention theo cohort.
3. **Phase 4.7 — Guardian Layer, build dark** (PR #1004): spending-drift warning (E1) +
   hạ tầng guardrail flag / kill-switch (E3). **Flag OFF** — merge để build dark, chỉ bật
   khi gate G1 pass. E2 scam-check chưa build (legal-blocked).
4. **Regression fixes & robustness** (PR #1007): Twin menu không còn "nút chết", money
   formatter nhận Decimal dạng chuỗi từ projection payload, build info trong miniapp,
   khôi phục độ tin cậy của full test suite.

> ⚠️ **Tất cả feature flag của 4.5/4.6/4.7 đều default OFF trong code.** Deploy này
> **không tự thay đổi hành vi** với user hiện tại — xem section _Config / env_ để biết
> flag nào cần bật thủ công trên prod cho đúng nội dung broadcast.

---

## PRs trong release này

| PR | Mô tả | Phase |
|---|---|---|
| [#957](https://github.com/phuongphh/FinanceAssistant/pull/957) | `docs`: Strategy V4 — Decision Engine pivot sau soft launch tháng 6/2026 | — |
| [#958](https://github.com/phuongphh/FinanceAssistant/pull/958) | `docs`: Phase 4.5 kickoff — Decision Engine Foundation planning | — |
| [#981](https://github.com/phuongphh/FinanceAssistant/pull/981) | `feat(phase-4.5)`: Decision Engine Foundation — E1–E5 complete | 4.5 |
| [#983](https://github.com/phuongphh/FinanceAssistant/pull/983) | `feat(onboarding)`: Phase 4.6 E1 goal reset + E2 activation nudge (behind flags) | 4.6 |
| [#986](https://github.com/phuongphh/FinanceAssistant/pull/986) | `feat(onboarding)`: decision moment sau Twin reveal (E3) | 4.6 |
| [#988](https://github.com/phuongphh/FinanceAssistant/pull/988) | `fix(onboarding)`: decision-moment review follow-ups (E3) | 4.6 |
| [#990](https://github.com/phuongphh/FinanceAssistant/pull/990) | `feat(4.6-e4)`: cohort-tagged decision log + admin adoption chart | 4.6 |
| [#992](https://github.com/phuongphh/FinanceAssistant/pull/992) | `fix(4.6-e4)`: tenant-scope decision-adoption chart + độ nét per active user | 4.6 |
| [#995](https://github.com/phuongphh/FinanceAssistant/pull/995) | `feat(4.6-e4)`: D28 retention theo cohort (reset vs legacy) | 4.6 |
| [#996](https://github.com/phuongphh/FinanceAssistant/pull/996) | `docs(4.6)`: mark Phase 4.6 done — reconcile stale status với merged E1–E4 | — |
| [#997](https://github.com/phuongphh/FinanceAssistant/pull/997) | `docs(phase-4.7)`: Guardian Layer plan — drift warnings + scam check v1 | — |
| [#1004](https://github.com/phuongphh/FinanceAssistant/pull/1004) | Phase 4.7 E1+E3: spending-drift warnings + guardrail flag infra (**dark**) | 4.7 |
| [#1005](https://github.com/phuongphh/FinanceAssistant/pull/1005) | `docs`: sync phase status — 4.5/4.6 done, 4.7 current | — |
| [#1006](https://github.com/phuongphh/FinanceAssistant/pull/1006) | `docs(releases)`: Release 10 broadcast message (1.4.7.0.1) | — |
| [#1007](https://github.com/phuongphh/FinanceAssistant/pull/1007) | Handle JSON-decimal inputs, make Twin menu robust, inject build info in miniapp, update tests | — |

---

## Migrations

Chạy theo thứ tự (`alembic upgrade head`) — chain nối tiếp head hiện tại của prod
(`20260608ccsoftdel`):

| Thứ tự | Revision | File | Mô tả |
|---|---|---|---|
| 1 | `20260710tone45` | `20260710_phase45_tone_reengagement.py` | Tone preference (gentle/strict) + state re-engagement broadcast |
| 2 | `20260710dqlog45` | `20260710_phase45_decision_query_log.py` | Bảng append-only `decision_query_log` (E5) |
| 3 | `20260712dqcohort46` | `20260712_phase46_decision_query_log_cohort.py` | Thêm cohort tag vào `decision_query_log` (4.6 E4) |

Tất cả đều **additive** (thêm bảng / thêm cột nullable) → an toàn, không cần backfill,
code cũ ignore được nếu phải rollback code mà giữ DB.

---

## Config / env

**Không có env key mới bắt buộc** — `.env.example` không đổi trong release này.

Toàn bộ feature flag đọc ở handler/job edge (`backend/intent/handlers/decision_flags.py`,
`backend/bot/handlers/onboarding_v2.py`) và **default OFF**, nên deploy trần sẽ giữ nguyên
hành vi hiện tại. Broadcast 1.4.7.0.1 (`docs/releases/release-10-broadcast.md`) quảng bá 3
tính năng — **phải bật 3 flag dưới đây trên prod rồi restart service TRƯỚC khi gửi broadcast**:

| Env var | Đặt | Bật cái gì |
|---|---|---|
| `PLAN_FEASIBILITY_QA_ENABLED` | `true` | Hỏi một câu quyết định → feasibility Q&A |
| `CLARITY_METER_ENABLED` | `true` | Thanh "độ nét" trên mỗi câu trả lời |
| `SHOCK_SIMULATION_ENABLED` | `true` | Thử "nếu… thì sao" trên bản sao số liệu |
| `EXPORT_EXCEL_ENABLED` | *(default `true`)* | `/export` — đã ON sẵn, không cần set |

Giữ **OFF** ở release này (không nằm trong broadcast):

| Env var | Lý do |
|---|---|
| `DRIFT_WARNING_ENABLED` | Phase 4.7 E1 build dark — chỉ bật khi gate G1 pass + owner sign-off |
| `SCAM_CHECK_ENABLED` | Phase 4.7 E2 legal-blocked; đây cũng là kill switch §8 |
| `TONE_DIAL_ENABLED` | Opt-in experiment, chưa quảng bá |
| `ACTIVATION_NUDGE_ENABLED` | Opt-in experiment cho cohort never-activated |
| `ONBOARDING_RESET_ENABLED` / `ONBOARDING_DECISION_MOMENT_ENABLED` | Onboarding reset — bật riêng khi muốn chạy cho user mới |

> Flag đọc từ `os.environ`, chỉ đổi khi **restart process** —
> `scripts/rebuild-finance-prod.sh` / launchd reload. Đây là cơ chế kill-switch <24h
> không cần deploy code (xem §8 runbook trong `phase-4.7-detailed.md`).

---

## Thay đổi đáng chú ý

### Phase 4.5 — Decision Engine Foundation (#981)

- **E1 shock simulation + liquidation advice** — "nếu phải chi 100tr thì sao?" chạy trên
  bản sao, gợi ý thanh khoản nào nên rút trước; số liệu gốc không đụng tới.
- **E2 plan-to-goal feasibility Q&A** — "3 năm nữa đủ cọc nhà chưa?" trả lời đủ/chưa,
  còn cách bao xa, mốc gần nhất trong tầm tay. Khi flag OFF thì fallback về advisory
  handler chung (không rơi vào `out_of_scope`).
- **E3 thanh "Độ Nét"** — mức chắc chắn của bức tranh tiền, kèm gợi ý bổ sung dữ liệu.
- **E4 `/export` Excel + tone dial** — xuất toàn bộ số liệu ra Excel; tone gentle/strict
  với copy variants riêng cho empathy + feasibility.
- **E5 decision query log + re-engagement** — log append-only mọi câu hỏi quyết định;
  broadcast một lần cho cohort dormant.
- Kèm `fix(phase-4.5)`: giữ chi phí classifier trong budget sau khi thêm decision intents.

### Phase 4.6 — Onboarding Reset (#983 → #995)

- **E1 goal reset** cho segment 22-35 (behind flag) — hỏi đúng điều user muốn lo xong trước.
- **E2 activation nudge** cho cohort chưa bao giờ kích hoạt (behind flag).
- **E3 decision moment** ngay sau Twin reveal + follow-up fixes; giữ **một con số trung thực**
  ở nhánh already-reached và building.
- **E4 đo lường** — decision log gắn cohort tag, admin adoption chart (đã tenant-scope),
  độ nét per active user, D28 retention tách cohort reset vs legacy.

### Phase 4.7 — Guardian Layer, build dark (#997, #1004)

- **E1 spending-drift warning** — cảnh báo lệch nhịp chi tiêu gắn hệ quả Twin, chạy qua
  hourly empathy job. Flag OFF → job bỏ qua trigger `spending_drift`, mọi trigger empathy
  cũ vẫn chạy y hệt pre-4.7.
- **E3 guardrail flag / kill-switch infra** — `decision_flags.py` cho phép tắt một surface
  bằng env + restart, không cần deploy code.
- **Fix trong PR #1004** (`fix(drift)`): history gate của `_spend_windows` nay loại internal
  transfer giống baseline spend query (user chỉ có 1 dòng pre-cutoff là chuyển khoản nội bộ
  không còn lọt gate "<3 windows"); goal label do user đặt được HTML-escape trước khi vào
  render context vì hourly job gửi `parse_mode="HTML"`.
- **E2 scam-check chưa build** — legal-blocked.

### Regression fixes & robustness (#1007)

- **Twin menu không còn nút chết** — route `twin` gửi bubble mới thay vì `editMessageText`
  (Telegram không edit được mọi loại message nguồn, đặc biệt sau Twin share).
- **Money formatter nhận Decimal dạng chuỗi** — projection payload JSON-safe trả Decimal
  dưới dạng numeric string; trước đây đi qua `repr()` nên `Decimal` từ chối.
- **Build info trong miniapp** — bust cache WebView theo mỗi deploy.
- **Full test suite ổn định trở lại** (Closes #371).

---

## Pre-deploy checklist

- [ ] Prod secrets / env file đã set 3 flag broadcast ở trên (nếu định gửi broadcast)
- [ ] DB backup snapshot trong vòng 24h gần nhất
- [ ] Telegram bot token & webhook URL không đổi
- [ ] Disk space VPS còn ≥ 20%
- [ ] CI `test` trên PR này PASS

---

## Rollback

Rollback nhanh (revert về prod trước release):

```bash
git checkout prod
git pull origin prod
git revert -m 1 <merge-commit-sha>
git push origin prod
```

Commit prod trước release này: `3134d02 Merge pull request #956 from phuongphh/claude/merge-prod-release-12-feedback` (APP_VERSION `1.4.4.10`).

> ⚠️ Cả 3 migration đều additive → **không bắt buộc** downgrade DB khi rollback code
> (bảng/cột thừa vô hại). Nếu vẫn muốn revert: `alembic downgrade 20260608ccsoftdel`.

**Rollback không cần deploy:** vì mọi surface mới đều sau flag, cách nhanh nhất để tắt một
tính năng lỗi là set flag về `false` rồi restart service — không phải revert prod.

---

## Sanity checks sau deploy

- [ ] `/about` hiển thị version `1.4.7.0.1`
- [ ] `alembic upgrade head` chạy clean → có bảng `decision_query_log` + cột cohort
- [ ] Bot phản hồi `/start` bằng welcome message Bé Tiền
- [ ] Gửi 1 transaction text → ghi nhận và lưu DB
- [ ] Gửi 1 ảnh receipt → OCR trả kết quả < 15s
- [ ] Menu → **Twin** trả về bubble mới (không còn nút chết), kể cả khi mở từ message cũ / ảnh
- [ ] Miniapp dashboard load không lỗi, không phục vụ HTML cache cũ sau deploy
- [ ] Số tiền hiển thị đúng ở mọi surface đọc từ projection payload (không mất phần thập phân)
- [ ] Scheduler / hourly empathy job chạy đúng ở lần fire đầu tiên, log không ERROR
- [ ] **Với flag OFF:** "3 năm nữa đủ cọc nhà chưa?" rơi về advisory chung, KHÔNG `out_of_scope`
- [ ] **Sau khi bật 3 flag + restart:** feasibility Q&A trả lời có thanh độ nét; "nếu rút 100tr thì sao" chạy shock simulation
- [ ] `/export` trả file Excel
- [ ] `DRIFT_WARNING_ENABLED` vẫn OFF → hourly job không gửi cảnh báo drift cho ai
- [ ] `docker compose logs backend --tail 100` — không ERROR/CRITICAL
