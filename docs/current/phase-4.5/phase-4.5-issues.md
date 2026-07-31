# Phase 4.5 — Issues Breakdown

> Decision Engine Foundation. GitHub-ready issue list. Detail: [`phase-4.5-detailed.md`](phase-4.5-detailed.md).

## 📊 Tổng Quan

| Epic | Tên | Issues | Ưu tiên | Ước lượng |
|---|---|---|---|---|
| E3 | Độ Nét Meter v1 | 4 | P0 (chặn E1/E2 answers) | ~3-4 ngày |
| E2 | Plan-to-Goal Feasibility Q&A | 3 | P0 | ~3 ngày |
| E1 | Shock Simulation + Liquidation Advice ⭐ | 5 | P0 (cột sống) | ~1 tuần |
| E4 | Quick Wins (Excel Export + Tone Dial) | 3 | P1 | ~3 ngày |
| E5 | Decision Query Log + Re-engagement | 2 | P1 (5.2 chạy CUỐI) | ~2 ngày |

**Tổng:** 5 Epics / 17 issues. Thứ tự build: E3 → E2 → E1 → E4 → E5 (broadcast cuối cùng).

## 🏷️ Label Conventions
- `phase-4.5`, `epic-1`/`epic-2`/`epic-3`/`epic-4`/`epic-5`
- `decision-shock` / `decision-feasibility` / `clarity-meter` / `quick-win` / `re-engagement`
- `persona-critical` (mọi issue chạm copy Bé Tiền — bắt buộc prompt-tester / vi-localization-checker)
- `legal-guardrail` (issue chạm liquidation advice — review ranh giới "không recommend sản phẩm ngoài")

---

## 🅲 Epic #E3 — Độ Nét Meter v1

### Description
Chưa có data completeness score (audit 07/2026: chỉ có `data_quality_warning_type` per-asset). Xây `clarity_service` deterministic + surface trên mọi Twin/decision view. **Build trước** vì mọi decision answer của E1/E2 bắt buộc kèm độ nét.

### Success criteria (Epic-level)
- Độ nét 0-100 hiện trên Twin Mini App + Twin Telegram view + mọi decision answer.
- Nhập thêm data → độ nét tăng ngay lập tức, nhìn thấy được.
- Dưới ngưỡng tối thiểu → humble mode: trả lời khiêm tốn + nói rõ cần nhập gì.

### Child issues

#### Issue #3.1 — clarity_service.compute_clarity()
- `backend/services/decision/clarity_service.py` — score 0-100 + component breakdown (asset coverage/freshness, income streams, expense history ≥1 tháng, goals). Deterministic, không LLM, <100ms, flush-only.
- **DoD:** unit test 4 profile (user trống / chỉ asset / asset+income / đầy đủ); score đơn điệu tăng khi thêm data.

#### Issue #3.2 — Surface độ nét trên Twin payload + Telegram view
- `twin_api_service.build_twin_payload()` thêm field `clarity`; Twin Telegram view render "ảnh tương lai đang nét ~X%".
- **DoD:** payload test; render test; user cũ không lỗi (score tính được với mọi state).

#### Issue #3.3 — Humble mode + prompt "làm nét thêm"
- Ngưỡng tối thiểu (30) config-driven; dưới ngưỡng → khiêm tốn + nêu missing component cụ thể; trên ngưỡng → kèm 1 gợi ý làm nét trọng số cao nhất. Copy ở `content/decision_copy.yaml`.
- **DoD:** test dưới/trên ngưỡng; vi-localization-checker pass.

#### Issue #3.4 — Flag `CLARITY_METER_ENABLED`
- Default `false`, đọc ở handler/API router (KHÔNG service). Tắt → mọi surface như trước 4.5.
- **DoD:** test flag on/off.

---

## 🅱️ Epic #E2 — Plan-to-Goal Feasibility Q&A

### Description
"100tr → 5 tỷ trong 10 năm?" trả lời thành thật bằng engine. Tái dùng `project_goal_with_savings()` + `FeasibilityBand` (Phase 3.8) — KHÔNG viết lại logic feasibility.

### Success criteria (Epic-level)
- Câu hỏi tự nhiên → band + required monthly + (nếu bất khả thi) mốc gần nhất trong tầm tay.
- Honest-not-harsh: dám nói "gần như bất khả thi" mà 0 câu phán xét.

### Child issues

#### Issue #2.1 — plan_feasibility_service.assess()
- `backend/services/decision/plan_feasibility_service.py` — hypothetical goal → `project_goal_with_savings()`; band NEEDS_REVISION → search target tìm mốc đạt FEASIBLE/STRETCH. Mọi số tiền `Decimal`.
- **DoD:** unit test đủ 6 band; test mốc gần nhất hội tụ; pure logic không chạm DB ngoài savings query.

#### Issue #2.2 — Intent decision_feasibility + handler
- Classifier route (pattern + LLM) + `backend/intent/handlers/decision_feasibility.py`; extract (start, target, horizon); thiếu tham số → hỏi lại đúng 1 câu. Flag `PLAN_FEASIBILITY_QA_ENABLED` default `false` đọc ở worker/router; tắt → route advisory cũ.
- **DoD:** integration test câu hỏi → answer; test thiếu tham số; test flag on/off.

#### Issue #2.3 — Copy feasibility + persona QA `persona-critical`
- `decision_copy.yaml`: 3 tone block (khả thi / cần cố / bất khả thi + phương án); kèm độ nét.
- **DoD:** prompt-tester 3 xưng hô × 3 band; 0 phán xét; 0 "Decision Engine/CFO/GPS" user-facing.

---

## 🅰️ Epic #E1 — Shock Simulation + Liquidation Advice ⭐

### Description
Ask trực tiếp của chị Nhung, end-to-end. Layer hội thoại trên Life Event Simulator (Phase 4B): hypothetical MC run + so sánh phương án rút + vẽ lại danh mục. ~70% engine đã có.

### Success criteria (Epic-level)
- "Nếu phải chi 100tr thì rút từ đâu?" → so sánh phương án trên chính danh mục user → khuyến nghị thứ tự → redraw.
- 0 persist hypothetical (không LifeEvent row, không đè projection).
- 0 khuyến nghị sản phẩm bên ngoài (ranh giới pháp lý encode trong code).

### Child issues

#### Issue #1.1 — shock_simulation_service.simulate_shock()
- `backend/services/decision/shock_simulation_service.py` — copy portfolio in-memory, inject `LifeEventInjection` giả định vào `simulate_portfolio()` paths, trả delta P10/P50/P90. KHÔNG persist.
- **DoD:** unit test delta hợp lý với shock các cỡ; test DB không có row mới sau khi chạy; test shock > net worth → floor 0 không crash.

#### Issue #1.2 — liquidation_advisor.rank_options() `legal-guardrail`
- `backend/services/decision/liquidation_advisor.py` — per asset type user sở hữu: tác động rút lên quỹ đạo + thanh khoản → xếp hạng ít-hại-nhất. Options sinh từ portfolio query — không có code path recommend sản phẩm ngoài.
- **DoD:** unit test ranking với 3 portfolio shape; test user chỉ có 1 loại tài sản; test amount > tổng thanh khoản → nói thật "không đủ".

#### Issue #1.3 — Intent decision_shock + handler + flag
- Classifier route + `backend/intent/handlers/decision_shock.py`; extract amount/timing; placeholder khi chờ; amount >50% net worth → confirm trước khi tính. Flag `SHOCK_SIMULATION_ENABLED` default `false` đọc ở worker/router.
- **DoD:** integration test end-to-end; test confirm gate; test flag on/off.

#### Issue #1.4 — Portfolio redraw sau shock
- Breakdown trước/sau bằng text (tái dùng format asset report); Mini App cone redraw nếu mở.
- **DoD:** render test trước/sau khớp số; số tiền format `Decimal` + `format_money_short`.

#### Issue #1.5 — Copy shock sim + persona QA `persona-critical` `legal-guardrail`
- `decision_copy.yaml`: weather metaphor cho tác động (không số percentile), khuyến nghị ấm + rõ.
- **DoD:** prompt-tester 3 xưng hô × 3 portfolio; 0 recommend mua/bán sản phẩm ngoài; vi-localization-checker pass.

---

## 🅳 Epic #E4 — Quick Wins: Excel Export + Tone Dial

### Description
2 ask từ feedback: xuất Excel (Hà Châu) + tone dial (dịu dàng ↔ nghiêm khắc). Độc lập với E1-E3, làm song song được.

### Success criteria (Epic-level)
- `/export` trả .xlsx mở được Excel + import Google Sheets; free tier.
- Tone đổi được trong /profile, ảnh hưởng copy, persona floor giữ nguyên.

### Child issues

#### Issue #4.1 — export_service + /export entry
- `backend/services/export/export_service.py` (openpyxl, 3 sheets Tài sản/Thu chi/Mục tiêu, `Decimal`); command `/export` + intent + nút menu báo cáo; gửi qua Telegram `sendDocument` (adapter). Flag `EXPORT_EXCEL_ENABLED` default `true`.
- **DoD:** file mở được (openpyxl round-trip test); số khớp DB; user trống → file có header không crash; test flag off.

#### Issue #4.2 — Migration tone_preference + /profile setting
- Alembic: `users.tone_preference VARCHAR(10) NULL` (+ `reengagement_broadcast_at TIMESTAMPTZ NULL` gộp cùng migration); ô chỉnh trong /profile; copy ở `content/profile_copy.yaml`. Flag `TONE_DIAL_ENABLED` default `false` → ô ẩn.
- **DoD:** migration sạch; đổi persist; NULL → tone mặc định.

#### Issue #4.3 — tone_variants.yaml + áp dụng `persona-critical`
- Tone blocks gentle/strict cho empathy messages + decision answers; strict = thẳng thắn hơn, KHÔNG sỉ nhục (persona floor §4 kill criterion).
- **DoD:** render test 2 tone × 3 xưng hô; prompt-tester xác nhận strict pass persona floor; vi-localization-checker pass.

---

## 🅴 Epic #E5 — Decision Query Log + Re-engagement Một Lần

### Description
Ghi log decision queries (nuôi gate G1/G2 — chart là Phase 4.6) + 1 đợt broadcast duy nhất tới cohort dormant khi ship.

### Success criteria (Epic-level)
- Mọi decision query được log với clarity_score.
- Broadcast idempotent, dry-run bắt buộc, chạy đúng MỘT lần.

### Child issues

#### Issue #5.1 — decision_query_log model + ghi log
- `backend/models/decision_query_log.py` + migration (user_id UUID NOT NULL indexed, query_type, clarity_score NUMERIC(5,2), success, created_at); handlers E1/E2 ghi qua service flush-only.
- **DoD:** migration sạch; log ghi cả case success=False; append-only.

#### Issue #5.2 — Broadcast script one-time `persona-critical`
- `scripts/send_reengagement_broadcast.py`: cohort dormant (extract `_classify_status` từ `api/admin/users.py` ra service dùng chung), Notifier port, copy "Bé Tiền giờ trả lời được câu này…" ở content YAML, set `reengagement_broadcast_at`. `--dry-run` bắt buộc có (in số đếm, không gửi); chạy thật cần `--confirm`.
- **DoD:** dry-run đếm đúng; chạy 2 lần không gửi trùng; copy pass vi-localization-checker; **CHỈ chạy thật sau khi E1-E3 live** (ghi rõ trong runbook đầu script).

---

## 🔗 Dependency Graph

```
E3 (độ nét) ──┬──> E2 (feasibility answer kèm độ nét)
              └──> E1 (shock answer kèm độ nét)
E1 + E2 ──────────> E5.1 (log cần handler tồn tại)
E1 + E2 + E3 ─────> E5.2 (broadcast CHỈ chạy khi decision moments live)
E4 (độc lập — song song với E1)
#4.2 (migration) ──> #5.2 (cần cột reengagement_broadcast_at)
```

E3 là blocker cứng cho câu trả lời hoàn chỉnh của E1/E2 (có thể dev song song, merge answer format sau khi E3 xong). E5.2 là bước ship cuối có chủ đích — one-shot duy nhất với cohort dormant.
