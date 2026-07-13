# Phase 4.7 — Issues Breakdown

> Guardian Layer: drift/overspend warnings gắn hệ quả Twin + scam check v1 (red-flags + tự kiểm chứng, KHÔNG verdict). GitHub-ready issue list. Detail: [`phase-4.7-detailed.md`](phase-4.7-detailed.md).

## 📊 Tổng Quan

| Epic | Tên | Issues | Ưu tiên | Ước lượng |
|---|---|---|---|---|
| E1 | Drift / Overspend Warnings ⭐ | 4 | P0 (Decision Moment #3) | ~4-5 ngày |
| E2 | Scam Check v1 (KHÔNG verdict) | 4 | P0 (Decision Moment #4, red line) | ~4-5 ngày |
| E3 | Guardrails, Kill Switch & Instrumentation | 3 | P0 (điều kiện an toàn E2) | ~2-3 ngày |

**Tổng:** 3 Epics / 11 issues. Thứ tự build: E3 (scaffolding) → E2; E1 song song. Flip flag gated G1 mid-Sept + legal review.

## 🏷️ Label Conventions
- `phase-4.7`, `epic-1`/`epic-2`/`epic-3`
- `drift-warning` / `scam-check` / `guardrail`
- `persona-critical` (mọi issue chạm copy Bé Tiền — bắt buộc prompt-tester / vi-localization-checker)
- `red-line` (mọi issue chạm scam-check verdict — bắt buộc test khẳng định KHÔNG verdict + legal review)

---

## 🅰️ Epic #E1 — Drift / Overspend Warnings ⭐

### Description
Decision Moment #3: cảnh báo lệch nhịp chi tiêu, nhưng gắn với **hệ quả Twin cụ thể** ("giữ nhịp này, mốc mua nhà 2029 lùi 14 tháng"). Reuse empathy engine (Phase 4.4) + `goal_projection`/`plan_feasibility` (Phase 4.5) — KHÔNG viết hệ thống cảnh báo riêng.

### Success criteria (Epic-level)
- Trigger `spending_drift` fire khi chi tháng hiện tại vượt baseline (median 3 tháng) quá ngưỡng, có ≥1 goal để tính hệ quả.
- Cảnh báo kèm delta Twin cụ thể (mốc goal lùi bao lâu), render qua tone dial gentle/strict.
- Flag `DRIFT_WARNING_ENABLED` off → empathy engine byte-identical với pre-4.7.

### Child issues

#### Issue #1.1 — `drift_service` (pure baseline + Twin-consequence delta)
- `backend/services/decision/drift_service.py`: pure. Tính baseline = median chi tiêu non-transfer 3 tháng trước; drift = chi tháng hiện tại vs baseline. Nếu vượt ngưỡng (>20% VÀ ≥ sàn tuyệt đối — chốt hằng số trong issue), tính **hệ quả Twin** qua `goal_projection`: mốc goal lùi bao nhiêu tháng nếu giữ nhịp drift. Dùng `Decimal`, loại `_INTERNAL_CATEGORIES` như `large_transaction`.
- **DoD:** service pure (no env/commit); unit test baseline median, ngưỡng %+sàn, delta tháng lùi; edge case 0 goal → không có consequence; <3 tháng data → không fire.

#### Issue #1.2 — Trigger `_check_spending_drift` trong empathy engine
- `backend/bot/personality/empathy_engine.py`: thêm `_check_spending_drift`, tham số `include_drift` (mặc định False) như `include_activation_nudge`. Priority giữa acute (large_tx) và ambient (silent); cooldown hợp lý (đề xuất 14 ngày). Gọi `drift_service`. Engine KHÔNG đọc env.
- **DoD:** unit test trigger fire/không-fire theo ngưỡng + cooldown; `include_drift=False` → skip, các trigger khác nguyên; priority test.

#### Issue #1.3 — Flag + job wiring
- `backend/intent/handlers/decision_flags.py`: `DRIFT_WARNING_ENABLED` (default False). `backend/jobs/check_empathy_triggers.py`: đọc flag ở edge, truyền `include_drift`. Layer contract: env đọc ở job edge.
- **DoD:** test flag on/off; job truyền đúng; cooldown + quiet hours + daily cap giữ nguyên.

#### Issue #1.4 — Copy + persona QA `persona-critical`
- `content/empathy_messages.yaml` + `content/tone_variants.yaml`: copy `spending_drift` gentle/strict × 3 xưng hô, có placeholder delta Twin. Honest-not-harsh; sàn persona: KHÔNG "đừng/không nên/phải/sai/tệ/lãng phí", KHÔNG sỉ nhục.
- **DoD:** prompt-tester gentle+strict × 3 xưng hô; 0 "Decision Engine/CFO/GPS"; vi-localization-checker pass; render với/không delta đều tự nhiên.

---

## 🅱️ Epic #E2 — Scam Check v1 `red-line`

### Description
Decision Moment #4: user dán "kèo đầu tư" → Bé Tiền so với **red-flags library** + đưa **hướng dẫn tự kiểm chứng**. **RED LINE (§80): chỉ red-flags + cách tự kiểm tra, KHÔNG BAO GIỜ verdict "đây là lừa đảo / đây là an toàn".** Flag + kill switch từ ngày 1.

### Success criteria (Epic-level)
- User dán kèo → trả về red-flags khớp + hướng dẫn tự kiểm chứng + disclaimer.
- Output KHÔNG chứa verdict — test tự động khẳng định.
- Flag `SCAM_CHECK_ENABLED` off → fallback out_of_scope/advisory không lỗi.

### Child issues

#### Issue #2.1 — Red-flags library `content/scam_redflags.yaml` `persona-critical` `red-line`
- Thư viện red-flags (lãi cam kết phi thực tế, mô hình đa cấp/giới thiệu, không pháp nhân/giấy phép, giục quyết định gấp, cam kết "không rủi ro", rút tiền khó…) + hướng dẫn tự kiểm chứng mỗi flag + disclaimer chung. Mỗi flag: keyword/pattern để khớp + copy giải thích + cách tự kiểm. **Nội dung khởi tạo, owner + legal duyệt.**
- **DoD:** library có ≥6 red-flags phổ biến VN; mỗi flag có cách tự kiểm chứng; disclaimer "không phải lời khuyên pháp lý/đầu tư"; vi-localization-checker pass; **không có câu verdict nào trong YAML.**

#### Issue #2.2 — `scam_check_service` (pure matching)
- `backend/services/decision/scam_check_service.py`: pure. Khớp text dán ↔ red-flags library, trả `matched_flags` (list). KHÔNG chấm điểm, KHÔNG kết luận. Không env, không commit.
- **DoD:** unit test khớp đúng flag theo keyword/pattern; text sạch → list rỗng; service pure; **API không có field verdict/score.**

#### Issue #2.3 — Intent + handler + formatter `red-line`
- `backend/intent/intents.py`: `IntentType.SCAM_CHECK`. `backend/intent/classifier/llm_based.py`: mô tả intent (user dán kèo/hỏi "kèo này có nên không"). `backend/intent/dispatcher.py`: route. `backend/intent/handlers/scam_check.py`: gate `SCAM_CHECK_ENABLED` ở edge (off → fallback out_of_scope), gọi service, render, log. `backend/bot/formatters/scam_check.py`: render flags khớp + guide + disclaimer.
- **DoD:** integration test intent → handler → output; **test khẳng định output KHÔNG chứa chuỗi verdict** ("lừa đảo", "an toàn", "nên đầu tư"…); flag off → fallback; env đọc ở handler edge.

#### Issue #2.4 — Persona QA + legal review `persona-critical` `red-line`
- Copy scam check: cảnh giác-không-hoảng-loạn, KHÔNG verdict, có disclaimer. prompt-tester + vi-localization-checker. **Legal review wording ký trước khi flip flag on.**
- **DoD:** prompt-tester 3 xưng hô; 0 jargon; disclaimer hiện mọi output; **legal sign-off ghi lại (checkbox trong #E3 checklist).**

---

## 🅲 Epic #E3 — Guardrails, Kill Switch & Instrumentation

### Description
Điều kiện an toàn để bật E2: kill switch tắt <24h không deploy, report-harmful-output path, log cả hai trụ vào `decision_query_log`, checklist legal + §8 one-strike runbook.

### Child issues

#### Issue #3.1 — Kill switch + flag infra `red-line`
- `backend/intent/handlers/decision_flags.py`: `SCAM_CHECK_ENABLED` (default False) đọc ở edge; tắt = fallback tức thì không deploy. Runbook §8: 1 case verdict-sai-gây-thiệt-hại report → tắt trong 24h + post-mortem trước khi bật lại.
- **DoD:** test flag off → scam_check fallback; runbook viết trong doc; kill switch không cần restart để có hiệu lực (đọc env mỗi request ở edge).

#### Issue #3.2 — Log drift + scam check vào `decision_query_log`
- `backend/models/decision_query_log.py`: `QUERY_TYPE_DRIFT`, `QUERY_TYPE_SCAM_CHECK`. Ghi qua service flush-only. Migration chỉ nếu cột `query_type` không đủ rộng (kiểm tra + chốt trong issue).
- **DoD:** log ghi đúng query_type; append-only giữ nguyên; migration sạch nếu có; PII: KHÔNG log full text kèo (chỉ metadata + flags khớp).

#### Issue #3.3 — Legal review checklist + phase-status sync
- Checklist legal review (red-flags wording + disclaimer) là gate trước flip. Cập nhật `docs/current/phase-status.yaml` (4.7 status/detail_doc/issues_doc) + chạy `scripts/sync_phase_status.py`.
- **DoD:** checklist trong doc; phase-status.yaml trỏ đúng doc; sync render sạch vào CLAUDE.md/README.

---

## 🔗 Dependency Graph

```
E3 #3.1 (kill switch + flag) ──> E2 (scam check trên scaffolding an toàn)
E3 #3.2 (log query_type) ──> E1 #1.2 + E2 #2.3 (cả hai ghi log)
E1 (drift — song song, độc lập)
E1 + E2 ──> #2.4 legal + persona QA ──> flip flag (gated G1 mid-Sept)
```

E3 #3.1 trước vì không có kill switch thì E2 không được phép ship (red line). E1 độc lập engine empathy, chạy song song. Flip flag chờ G1 pass + legal sign-off.
