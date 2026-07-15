# Phase 4.7 — Guardian Layer

> Bé Tiền chuyển từ *người ghi chép* sang *người đồng hành cảnh giới*: cảnh báo lệch nhịp chi tiêu gắn với **hệ quả Twin cụ thể**, và soi "kèo đầu tư" bằng **thư viện red-flags + cách tự kiểm chứng** — KHÔNG BAO GIỜ ra phán quyết. Issue list: [`phase-4.7-issues.md`](phase-4.7-issues.md).

**Chốt lịch:** Tháng 9/2026, ~2-3 tuần. **Gate G1** (decision adoption) đo giữa tháng 9 — 4.7 build sau flag từ bây giờ nhưng **chỉ bật khi G1 pass** (Strategy V4 §180). Nếu G1 fail → dừng 4.7, re-diagnose bằng interview trước khi bật.

**Trạng thái build (cập nhật 15/07/2026):** 🛡️ IN PROGRESS.
- ✅ **E1 — Drift warning** (`drift_service.py` + empathy trigger `_check_spending_drift`) đã merged nhưng **FLAG OFF** (build dark, chỉ bật khi G1 pass).
- ✅ **E3 — Guardrail flag + kill-switch infra** đã merged, FLAG OFF.
- ⛔ **E2 — Scam check** legal-blocked, **chưa build** (chờ product-owner quyết định #994).

---

## 📋 Changelog vs Strategy V4

| Nguồn | Điều khoản | Ảnh hưởng 4.7 |
|---|---|---|
| §75-76 | Decision Moment #3 — Drift warning gắn hệ quả Twin | E1 cột sống |
| §78-80 | Decision Moment #4 — Scam check: **chỉ red-flags + tự kiểm chứng, KHÔNG verdict** | E2 red line |
| §8 | Kill criteria one-strike: 1 case verdict-sai-gây-thiệt-hại → tắt bằng kill switch trong 24h + post-mortem | E2/E3 guardrail |
| §144-146 | Guardian Layer: cả hai trụ **REUSE-not-rebuild** | Kiến trúc |
| §180 | Gate G1 decision adoption ~mid-Sept gate 4.7 | Điều kiện bật |

---

## 🧠 Design Philosophy

1. **Reuse, đừng rebuild.** Drift warning là một *empathy trigger mới* trên engine Phase 4.4, không phải hệ thống cảnh báo riêng. Scam check là một *intent mới* trên dispatcher hiện có, không phải pipeline LLM riêng.
2. **Cảnh báo phải có hệ quả cụ thể.** "Chi vượt 3tr" một mình vô nghĩa; "giữ nhịp này, mốc mua nhà 2029 lùi 14 tháng" mới đổi hành vi. Delta tính qua `plan_feasibility_service`/`goal_projection` (Phase 4.5) — không đoán.
3. **Nghiêm khắc được, sỉ nhục không.** Drift dùng tone dial gentle↔strict sẵn có (`tone_variants.yaml`). Sàn persona: KHÔNG "đừng/không nên/phải/sai/tệ/lãng phí"; KHÔNG bao giờ hạ nhục.
4. **Scam check tuyệt đối không phán quyết.** Output = danh sách red-flags khớp + hướng dẫn tự kiểm chứng. KHÔNG "đây là lừa đảo", KHÔNG "đây là an toàn". Một câu verdict lọt qua = vi phạm red line.
5. **Ship dark, kill nhanh.** Cả hai trụ sau feature flag từ ngày 1. Scam check có kill switch riêng đọc ở edge — tắt được trong <24h bằng cách đổi env + restart service (KHÔNG cần deploy code mới); nếu vận hành cần tắt *tức thì* thì nâng lên DB/config runtime toggle (đề xuất phase sau). Off → delegate về `AdvisoryHandler`, byte-identical pre-4.7.

---

## 🎬 Choreography

**Drift warning (E1)** — chạy trong job hourly `check_empathy_triggers` sẵn có:
```
job hourly → empathy_engine.check_all_triggers(include_drift=flag)
   → _check_spending_drift: spend tháng này vs baseline (median 3 tháng trước)
   → nếu vượt ngưỡng: tính Twin-consequence delta qua goal_projection
   → render qua tone dial (gentle/strict) → gửi Telegram → stamp empathy_fired
```

**Scam check (E2)** — trong luồng message hiện có:
```
user dán "kèo" → classifier → intent scam_check (flag on)
   → handler: gate SCAM_CHECK_ENABLED ở edge
   → scam_check_service.scan(text) khớp text với red-flags library (pure)
   → render: red-flags khớp + hướng dẫn tự kiểm chứng + disclaimer (KHÔNG verdict)
   → log decision_query_log(query_type=scam_check) flush-only
   (flag off → delegate AdvisoryHandler, byte-identical pre-4.7)
```

---

## 📁 Files Touched

**E1 — Drift warning (reuse Phase 4.4 empathy):**
- `backend/bot/personality/empathy_engine.py` — thêm `_check_spending_drift`, tham số `include_drift`
- `backend/services/decision/drift_service.py` *(mới)* — pure: baseline + delta chi tiêu, gọi `goal_projection` cho Twin-consequence
- `backend/intent/handlers/decision_flags.py` — `DRIFT_WARNING_ENABLED` (default false)
- `backend/jobs/check_empathy_triggers.py` — đọc flag ở edge, truyền `include_drift`
- `content/empathy_messages.yaml` + `content/tone_variants.yaml` — copy `spending_drift` (gentle/strict × xưng hô)

**E2 — Scam check (intent mới):**
- `backend/intent/intents.py` — `IntentType.SCAM_CHECK`
- `backend/intent/handlers/scam_check.py` *(mới)* — gate flag ở edge, gọi service, render, log
- `backend/services/decision/scam_check_service.py` *(mới)* — pure: khớp text ↔ red-flags library
- `backend/bot/formatters/scam_check.py` *(mới)* — render red-flags + guide + disclaimer
- `backend/intent/classifier/llm_based.py` — mô tả intent `scam_check` cho classifier
- `backend/intent/dispatcher.py` — route `SCAM_CHECK` → handler
- `content/scam_redflags.yaml` *(mới)* — thư viện red-flags + hướng dẫn tự kiểm chứng + disclaimer
- `backend/intent/handlers/decision_flags.py` — `SCAM_CHECK_ENABLED` (default false, kill switch)

**E3 — Guardrails & instrumentation:**
- `backend/models/decision_query_log.py` — `QUERY_TYPE_SCAM_CHECK` (chỉ scam_check user-initiated; drift stamp qua empathy `empathy_fired`, KHÔNG decision_query_log — tránh phồng G1/G2)
- Report-harmful-output path (kill switch runbook) + legal review checklist

---

## 🗄️ New DB Columns / Tables

Không có bảng mới. **Scam check** (user-initiated) ghi vào `decision_query_log` (Phase 4.5, append-only) qua `query_type=scam_check`. **Drift** (proactive) stamp qua empathy `empathy_fired` event stream như mọi trigger khác — KHÔNG ghi decision_query_log (nếu ghi sẽ làm phồng metric G1/G2 vì `/charts/decision-adoption` aggregate mọi row không lọc query_type). Không migration nếu cột `query_type` đủ rộng (kiểm tra trong #E3).

---

## 📦 Epics & Stories

Chi tiết sub-issue + DoD: [`phase-4.7-issues.md`](phase-4.7-issues.md).

### Epic E1 — Drift / Overspend Warnings *(cột sống — reuse empathy engine)*
Trigger `spending_drift` mới: so chi tiêu tháng hiện tại với baseline (median 3 tháng trước), vượt ngưỡng thì tính **hệ quả Twin cụ thể** (mốc goal lùi bao lâu) và cảnh báo qua tone dial. Không viết hệ thống cảnh báo riêng — cắm vào engine Phase 4.4.

### Epic E2 — Scam Check v1 *(red line — KHÔNG verdict)*
Intent `scam_check`: user dán kèo → khớp với red-flags library → trả về flags khớp + hướng dẫn tự kiểm chứng + disclaimer. Flag + kill switch từ ngày 1. **Legal review wording bắt buộc trước ship.**

### Epic E3 — Guardrails, Kill Switch & Instrumentation
Kill switch đọc ở edge (tắt scam_check <24h — env + restart service, KHÔNG cần deploy code; nâng lên DB/config toggle nếu cần tắt tức thì) + report-harmful-output path; log **scam_check** vào `decision_query_log`, **drift** vào empathy event stream; checklist legal review; §8 one-strike runbook.

---

## 🏗️ Layer Mapping

| Layer | 4.7 |
|---|---|
| `routers/`/`jobs/` | Đọc flag ở edge (`DRIFT_WARNING_ENABLED`, `SCAM_CHECK_ENABLED`), truyền quyết định vào |
| `handlers/` | `scam_check.py` gate flag, extract text, gọi service, render, log |
| `services/` | `drift_service`, `scam_check_service` — **pure/flush-only**, không env, không commit |
| `adapters/` | Gửi qua `Notifier` port (empathy job đã dùng), không import telegram_service trực tiếp |
| `content/` | Toàn bộ copy + red-flags library ở YAML — không hardcode chuỗi VN |

---

## ⚠️ Risk & Rollback

| Rủi ro | Giảm thiểu |
|---|---|
| Scam check lỡ ra verdict → §8 one-strike | Formatter chỉ render flags + guide + disclaimer; test khẳng định KHÔNG có chuỗi verdict; legal review; kill switch <24h |
| Drift warning đọc như trách móc → tổn thương persona | Tone dial gentle mặc định; sàn persona test; cooldown + quiet hours của empathy engine |
| False-positive drift (tháng có chi lớn hợp lý) | Ngưỡng theo % trên baseline median + sàn tuyệt đối; loại internal-transfer như large_transaction |
| Red-flags library lệch pháp lý | Legal review wording trước ship (gate E3) |
| Bật trước khi G1 pass | Cả hai flag default OFF; chỉ bật khi G1 mid-Sept pass |

**Rollback:** tắt `DRIFT_WARNING_ENABLED` / `SCAM_CHECK_ENABLED` → hành vi byte-identical với pre-4.7 (empathy engine bỏ qua trigger drift; scam_check delegate về `AdvisoryHandler`). Env đổi có hiệu lực sau restart service — KHÔNG cần deploy code mới.

---

## ✅ Definition of Done

- Drift trigger fire đúng cohort, tính đúng Twin-consequence delta; flag off → empathy engine byte-identical.
- Scam check trả flags + guide + disclaimer; **test khẳng định output KHÔNG chứa verdict**; flag off → fallback không lỗi.
- Kill switch tắt scam check <24h không deploy; report-harmful-output path có runbook.
- Cả hai log vào `decision_query_log` append-only.
- prompt-tester + vi-localization-checker pass; 0 chuỗi "Decision Engine/CFO/GPS"; sàn persona (không sỉ nhục) giữ.
- ruff + layer-contract-checker sạch; toàn suite xanh.
- **Legal review wording scam check ký trước khi flip flag on.**

---

## 🚫 Out of Scope (để phase sau)

- Verdict / chấm điểm rủi ro kèo (vĩnh viễn out — red line §80).
- Behavioral engine đầy đủ (Phase 5.5 — nudge fold dần vào drift).
- Per-category budget config (drift dùng baseline median, không cần budget ceiling).
- Scam check đọc link/ảnh (v1 chỉ text dán vào).

---

## 🔀 Execution Order (đề xuất)

```
E3 (kill switch + flag + log scaffolding) ──> E2 (scam check trên scaffolding)
E1 (drift warning — song song, độc lập engine empathy)
E1 + E2 ──> Legal review + persona QA ──> flip flag (gated G1)
```

E3 trước vì kill switch + flag infra là điều kiện an toàn cho E2. E1 độc lập, chạy song song.

---

## 🔓 Product Decisions Cần Owner Ký (blocking flip flag, KHÔNG blocking code sau flag)

1. **Nội dung red-flags library** — danh sách red-flags + wording hướng dẫn tự kiểm chứng (nhạy pháp lý). *Đề xuất khởi tạo trong #2.1, owner + legal duyệt.*
2. **Legal wording + disclaimer** — câu disclaimer "đây không phải lời khuyên pháp lý/đầu tư, chỉ là dấu hiệu để tự kiểm chứng". *Bắt buộc legal ký trước flip.*
3. **Kill-switch cơ chế** — env flag đọc ở edge là mặc định NHƯNG env chỉ đổi khi restart service, nên "tắt <24h không deploy" = đổi env + restart (không build/PR code mới). Có cần DB/config runtime toggle (tắt *tức thì*, không restart) trên admin dashboard không? *Đề xuất v1: env flag + runbook restart; nâng lên admin/DB toggle ở phase sau nếu §8 one-strike đòi tắt tức thì.*
4. **Ngưỡng drift** — % trên baseline + sàn tuyệt đối (VND) để fire. *Đề xuất: >20% trên median 3 tháng VÀ ≥ sàn tuyệt đối; chốt trong #1.1.*
5. **G1 gate** — xác nhận 4.7 được bật sau khi G1 mid-Sept pass. *Đến lúc đó build sau flag, không flip.*
