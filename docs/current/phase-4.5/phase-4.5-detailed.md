# Phase 4.5 — Decision Engine Foundation

> Twin đổi nghề: từ "tương lai bạn trông thế nào?" (ngắm) → "bạn nên làm gì?" (quyết định). Ship 2 decision moments đầu tiên trên engine có sẵn + độ nét v1 + 2 quick wins từ feedback + 1 đợt re-engagement duy nhất.

**Status:** 📝 Planning
**Duration:** ~3 tuần (target ship: late July 2026)
**Branch:** `claude/finance-assistant-strategy-wz76aj`
**Strategy:** [`docs/current/strategy.md`](../strategy.md) — Strategy V4 §Differentiator + §Roadmap Phase 4.5
**Issues:** [`phase-4.5-issues.md`](phase-4.5-issues.md)

---

## 📋 Changelog vs Strategy V4

| Strategy V4 nói | Phase doc này cụ thể hoá | Ghi chú |
|---|---|---|
| Conversational shock sim + liquidation advice (~70% engine có sẵn từ 4B) | Epic E1: hypothetical MC run (KHÔNG persist life event) + so sánh phương án rút + vẽ lại danh mục | Tái dùng `LifeEventInjection` + `apply_life_events()` nguyên trạng |
| Plan-to-goal feasibility Q&A | Epic E2: intent mới + tái dùng `project_goal_with_savings()` (Phase 3.8) + tìm mốc "trong tầm tay" | FeasibilityBand enum đã có đủ 6 band |
| Độ nét meter v1 trên mọi Twin/decision surface | Epic E3: `clarity_service` mới (chưa tồn tại — audit 07/2026 xác nhận) | Chỉ có `data_quality_warning_type` per-asset, chưa có score tổng |
| Xuất Excel/Google Sheets | Epic E4a: **.xlsx qua Telegram sendDocument** (openpyxl). Google Sheets API sync KHÔNG làm — file .xlsx import vào Sheets 1 chạm | Thu hẹp có chủ đích: OAuth Sheets là 1 epic riêng, không đáng cho v1 |
| Tone dial (dịu dàng ↔ nghiêm khắc) | Epic E4b: cột `users.tone_preference` + tone blocks trong content YAML | Persona floor giữ nguyên — nghiêm khắc ≠ sỉ nhục |
| 1 đợt re-engagement duy nhất tới cohort dormant | Epic E5: script chạy tay 1 lần + cột dedup `reengagement_broadcast_at` | KHÔNG xây admin broadcast API (chưa cần — 1 lần duy nhất) |
| Instrumentation decision interactions + độ nét avg | E5: chỉ **ghi log** (`decision_query_log`). Chart lên admin dashboard là Phase 4.6 per strategy | 4.5 ghi data từ ngày đầu để 4.6 có gì mà vẽ và gate G1 có số |

---

## 🧠 Design Philosophy

1. **Layer mỏng trên engine có sẵn, không xây engine mới.** Monte Carlo (`twin/engine/monte_carlo.py`), Life Event injection (`twin/engine/life_events.py`), FeasibilityBand (`schemas/goal.py`) giữ nguyên. Phase 4.5 chỉ thêm: (a) đường vào hội thoại, (b) chạy hypothetical không persist, (c) lớp trình bày quyết định.
2. **Độ nét đi trước decision answers.** Mọi câu trả lời quyết định BẮT BUỘC kèm độ nét — vì vậy E3 build trước E1/E2. Không bao giờ tự tin trên data mỏng: dưới ngưỡng nét tối thiểu → trả lời khiêm tốn + nói rõ cần nhập gì.
3. **Hypothetical không bao giờ chạm data thật.** Shock sim chạy trên bản sao in-memory của danh mục + event giả định; KHÔNG tạo `LifeEvent` row, KHÔNG ghi projection mới đè lên Twin hiện tại của user.
4. **Ranh giới pháp lý encode vào code, không chỉ vào prompt.** Liquidation advice chỉ xếp hạng tài sản **user đang sở hữu**; danh sách phương án sinh từ portfolio query, LLM chỉ format lời — không có đường nào để "recommend mua X" lọt ra.
5. **Honesty là feature.** Plan-to-goal dám trả lời "gần như bất khả thi" — kèm mốc gần nhất trong tầm tay (tính bằng engine, không phải LLM đoán). Không phán xét, không an ủi sáo rỗng.
6. **User-facing không bao giờ nói "Decision Engine".** Copy dùng *người đồng hành* / *quản lý tài sản*; "độ nét" là tên user-facing của confidence meter.

---

## 🎬 Choreography — 2 flow chính

### Flow 1: Shock simulation (ask của chị Nhung, end-to-end)

| Bước | Surface | Nội dung |
|---|---|---|
| 1 | User chat | "Nếu em phải chi 100tr viện phí thì rút từ đâu ít hại nhất?" |
| 2 | Intent classifier | → intent `decision_shock` (amount=100tr, loại=one-time shock) |
| 3 | Bé Tiền (ngay) | Placeholder "để em tính thử trên danh mục của mình…" |
| 4 | Engine | Clarity check → MC hypothetical run với shock injected → per-option liquidation impact |
| 5 | Bé Tiền | So sánh 2-4 phương án rút (trên chính danh mục user), khuyến nghị thứ tự + vì sao, tác động lên quỹ đạo bằng weather metaphor, **độ nét ~X%** + 1 gợi ý làm nét thêm |
| 6 | Bé Tiền (nối) | Vẽ lại danh mục sau cú sốc (breakdown text; Mini App redraw nếu user mở) |

### Flow 2: Plan-to-goal feasibility

| Bước | Surface | Nội dung |
|---|---|---|
| 1 | User chat | "Em có 100tr, muốn 5 tỷ trong 10 năm thì làm sao?" |
| 2 | Intent classifier | → intent `decision_feasibility` (start=100tr, target=5tỷ, horizon=10 năm) |
| 3 | Engine | `project_goal_with_savings()` + MC → band + required monthly + mốc gần nhất khả thi |
| 4 | Bé Tiền | Trả lời thành thật: "…gần như bất khả thi với nhịp hiện tại. Nhưng **1.8 tỷ thì trong tầm tay** nếu để dành đều Xtr/tháng…" + độ nét + prompt làm nét |

---

## 📁 Files Touched

| File | Loại | Ghi chú |
|---|---|---|
| `backend/services/decision/__init__.py` | ✨ Mới | Package cho decision services |
| `backend/services/decision/shock_simulation_service.py` | ✨ Mới | Hypothetical MC run — copy portfolio, inject shock, KHÔNG persist |
| `backend/services/decision/liquidation_advisor.py` | ✨ Mới | Xếp hạng phương án rút trên tài sản user sở hữu |
| `backend/services/decision/plan_feasibility_service.py` | ✨ Mới | Parse X→Y→Z năm; tái dùng `project_goal_with_savings()`; tìm mốc khả thi gần nhất |
| `backend/services/decision/clarity_service.py` | ✨ Mới | Độ nét 0-100 từ asset coverage/freshness + income + expense history + goals |
| `backend/intent/handlers/decision_shock.py` | ✨ Mới | Handler intent shock sim |
| `backend/intent/handlers/decision_feasibility.py` | ✨ Mới | Handler intent feasibility |
| `backend/twin/engine/monte_carlo.py` | ♻️ Tái dùng | `simulate_portfolio()` nguyên trạng; ext nhỏ nếu cần seed từ portfolio snapshot |
| `backend/twin/engine/life_events.py` | ♻️ Tái dùng | `LifeEventInjection` + `apply_life_events()` cho shock giả định |
| `backend/services/goal_projection.py` | ♻️ Tái dùng | `project_goal_with_savings()` (pure, không DB) + `get_avg_monthly_savings()` |
| `backend/twin/services/twin_api_service.py` | ✏️ Sửa | `build_twin_payload()` thêm field `clarity` |
| `backend/services/export/export_service.py` | ✨ Mới | .xlsx (openpyxl): sheets Tài sản / Thu chi / Mục tiêu |
| `backend/models/user.py` | ✏️ Sửa | +`tone_preference`, +`reengagement_broadcast_at` |
| `backend/models/decision_query_log.py` | ✨ Mới | Log decision queries (feeds gate G1/G2; chart là việc 4.6) |
| `backend/config/__init__.py` | ✏️ Sửa | 5 feature flags mới (xem bảng Risk & Rollback) |
| `backend/requirements.txt` | ✏️ Sửa | +`openpyxl` |
| `content/decision_copy.yaml` | ✨ Mới | Copy shock sim + feasibility + độ nét + humble mode |
| `content/tone_variants.yaml` | ✨ Mới | Tone blocks dịu dàng/nghiêm khắc cho copy chạm tone dial |
| `scripts/send_reengagement_broadcast.py` | ✨ Mới | One-off, chạy tay, dedup qua `reengagement_broadcast_at` |
| `alembic/versions/*` | ✨ Mới | 2 migration: user columns + bảng `decision_query_log` |
| `tests/test_phase_4_5/*` | ✨ Mới | Unit + integration + persona gate |

**Số tiền:** mọi amount hiển thị/lưu DB dùng `Decimal` + `format_money_short/full`. Riêng MC paths nội bộ là numpy float (nguyên trạng từ Phase 4A — simulation, không phải bookkeeping); chỉ convert sang `Decimal` ở biên trình bày.

---

## 🗄️ New DB Columns / Tables

| Đối tượng | Cột | Kiểu | Ghi chú |
|---|---|---|---|
| `users` | `tone_preference` | `VARCHAR(10) NULL` | `gentle` / `strict`; NULL = mặc định hiện tại (dịu dàng) |
| `users` | `reengagement_broadcast_at` | `TIMESTAMPTZ NULL` | Dedup cho broadcast một-lần |
| `decision_query_log` (bảng mới) | `id, user_id (UUID NOT NULL, indexed), query_type, clarity_score NUMERIC(5,2), success BOOLEAN, created_at` | — | `query_type`: `shock_simulation` \| `plan_feasibility`; soft-delete không áp dụng (log append-only) |

---

## 📦 Epics & Stories

### Epic E3 — Độ Nét Meter v1 *(build TRƯỚC — E1/E2 phụ thuộc)*

- **3.1** `clarity_service.compute_clarity(db, user_id) -> ClarityScore` — score 0-100 + component breakdown (tài sản có giá hiện tại/stale, có income stream, có ≥1 tháng expense history, có goal). Deterministic, không LLM, <100ms.
- **3.2** Surface độ nét: `build_twin_payload()` (Mini App), Telegram Twin view, và mọi câu trả lời decision ("ảnh tương lai của anh/chị đang nét ~40%").
- **3.3** Humble mode + prompt "làm nét thêm": dưới ngưỡng tối thiểu (đề xuất: 30) → trả lời khiêm tốn, nói rõ cần nhập gì; trên ngưỡng → vẫn kèm 1 gợi ý làm nét cụ thể nhất (missing component có trọng số cao nhất).
- **3.4** Nhập thêm data → độ nét tăng **ngay lập tức** (không cache qua ngày; recompute mỗi lần render).

### Epic E1 — Shock Simulation Hội Thoại + Liquidation Advice ⭐ *(cột sống của phase)*

- **1.1** `shock_simulation_service.simulate_shock(db, user_id, amount, timing) -> ShockResult` — copy portfolio in-memory, inject `LifeEventInjection` giả định vào MC paths, trả delta quỹ đạo P10/P50/P90. KHÔNG persist life event, KHÔNG ghi đè projection.
- **1.2** `liquidation_advisor.rank_options(portfolio, amount) -> list[LiquidationOption]` — với mỗi loại tài sản user sở hữu (cash/gold/stock/crypto), tính tác động rút lên quỹ đạo dài hạn + tính thanh khoản; xếp hạng ít-hại-nhất trước. **Guardrail trong code:** options sinh từ portfolio query — không tồn tại đường sinh ra khuyến nghị sản phẩm ngoài.
- **1.3** Intent `decision_shock`: pattern + LLM classifier route, handler mới, extract amount/timing; placeholder khi chờ tính.
- **1.4** Portfolio redraw sau shock: breakdown trước/sau bằng text (tái dùng format asset report); Mini App cone redraw nếu đã mở.
- **1.5** Copy `decision_copy.yaml` (weather metaphor cho tác động, không số percentile) + persona QA gate (prompt-tester + vi-localization-checker).

### Epic E2 — Plan-to-Goal Feasibility Q&A

- **2.1** `plan_feasibility_service.assess(db, user_id, start, target, horizon_years) -> FeasibilityAnswer` — hypothetical goal → `project_goal_with_savings()` → band + required monthly; nếu band = NEEDS_REVISION → tìm mốc gần nhất đạt FEASIBLE/STRETCH (search trên target) để trả "…nhưng X thì trong tầm tay nếu…".
- **2.2** Intent `decision_feasibility`: classifier route + handler; extract (start, target, horizon) từ câu tự nhiên; thiếu tham số → hỏi lại 1 câu duy nhất.
- **2.3** Copy + persona QA: honest-not-harsh; 3 band tone (khả thi / cần cố / gần như bất khả thi + phương án).

### Epic E4 — Quick Wins: Excel Export + Tone Dial

- **4.1** `export_service.build_xlsx(db, user_id) -> bytes` — 3 sheets (Tài sản, Thu chi, Mục tiêu), openpyxl, số tiền `Decimal`, gửi qua Telegram `sendDocument`. Free tier (tracking free forever — strategy V4).
- **4.2** Entry points: command `/export` + intent `action_export` + nút trong menu báo cáo.
- **4.3** Tone dial: migration `tone_preference` + ô chỉnh trong `/profile` + `tone_variants.yaml`; v1 áp dụng cho empathy messages + decision answers. Persona floor test: tone `strict` vẫn 0 câu sỉ nhục.

### Epic E5 — Decision Query Log + Re-engagement Một Lần

- **5.1** `decision_query_log` model + migration; handlers E1/E2 ghi log (query_type, clarity_score, success) qua service flush-only. Chart lên admin dashboard = Phase 4.6 (out of scope ở đây).
- **5.2** `scripts/send_reengagement_broadcast.py` — chạy tay MỘT LẦN sau khi E1-E3 live: chọn cohort dormant (tái dùng logic `_classify_status` — extract ra service dùng chung), gửi qua Notifier port, copy "Bé Tiền giờ trả lời được câu này…", set `reengagement_broadcast_at`. Idempotent: chạy lại không gửi trùng. Dry-run mode bắt buộc có.

---

## 🏗️ Layer Mapping

| Layer | Thành phần Phase 4.5 |
|---|---|
| `routers/` / `workers/` | Đọc feature flags; không đổi gì khác |
| `bot/handlers/` (`intent/handlers/`) | `decision_shock.py`, `decision_feasibility.py`, export entry — route + format, KHÔNG business logic, KHÔNG `db.commit()` |
| `services/` | `decision/*` (4 service mới), `export/export_service.py` — flush-only, trả domain objects |
| `twin/engine/` | Tái dùng nguyên trạng (pure computation, không I/O) |
| `adapters/` | Telegram `sendDocument` cho export; Notifier port cho broadcast |
| `content/` | `decision_copy.yaml`, `tone_variants.yaml` — 0 chuỗi tiếng Việt hardcode trong code |

---

## ⚠️ Risk & Rollback

| Flag (env → `config/__init__.py`) | Default | Đọc ở | Tắt thì |
|---|---|---|---|
| `SHOCK_SIMULATION_ENABLED` | `false` | worker/handler router | Intent `decision_shock` → route về advisory cũ |
| `PLAN_FEASIBILITY_QA_ENABLED` | `false` | worker/handler router | Intent `decision_feasibility` → advisory cũ |
| `CLARITY_METER_ENABLED` | `false` | handler/API router | Twin payload + câu trả lời không kèm độ nét (như hiện tại) |
| `EXPORT_EXCEL_ENABLED` | `true` | handler | `/export` trả "tính năng đang bảo trì" |
| `TONE_DIAL_ENABLED` | `false` | handler | Mọi copy dùng tone mặc định; ô /profile ẩn |

- Mỗi flag có issue định nghĩa tên + nơi đọc + test on/off (convention từ 4.4). Flags đọc ở router/worker/handler, KHÔNG trong service.
- **Rollback shock sim:** hypothetical run không persist gì → tắt flag là sạch, không cần dọn data.
- **Rollback broadcast:** không có rollback (tin đã gửi) → vì thế bắt buộc dry-run + user cap + operator xác nhận số lượng trước khi chạy thật.
- **Risk pháp lý (liquidation advice):** encode ranh giới trong code (chỉ tài sản user sở hữu); persona QA gate thêm check "0 khuyến nghị mua/bán sản phẩm bên ngoài".
- **Risk LLM extract sai số tiền:** amount extract phải qua confirm nếu >50% net worth ("em hiểu là anh cần rút 100tr, đúng không?").

---

## ✅ Definition of Done

- [ ] Shock sim end-to-end: câu hỏi tự nhiên → so sánh phương án rút → khuyến nghị thứ tự → redraw danh mục; 0 persist hypothetical.
- [ ] Feasibility Q&A trả lời thành thật cả 6 FeasibilityBand; case NEEDS_REVISION luôn kèm mốc trong tầm tay.
- [ ] Độ nét hiện trên: Twin Mini App, Twin Telegram view, mọi decision answer; nhập data → tăng ngay lập tức; dưới ngưỡng → humble mode.
- [ ] `/export` trả file .xlsx mở được trong Excel + import Google Sheets; số tiền đúng format.
- [ ] Tone dial đổi được trong /profile, persist, ảnh hưởng empathy + decision copy; tone strict pass persona floor test.
- [ ] `decision_query_log` ghi đủ mọi decision query với clarity_score.
- [ ] Broadcast script dry-run cho số đếm đúng cohort dormant; chạy thật idempotent.
- [ ] 5 flags có test on/off; tắt hết flags → behavior y hệt trước 4.5.
- [ ] 0 chuỗi "Decision Engine"/"GPS tài chính"/"CFO" trong user-facing copy (vi-localization-checker).
- [ ] Persona gates pass: prompt-tester cho shock/feasibility answers × 3 xưng hô × 2 tone.
- [ ] Toàn bộ test xanh; ruff + layer-contract-checker sạch.

---

## 🚫 Out of Scope (đã có nhà)

- **Scam check + drift warnings** → Phase 4.7 Guardian Layer (kill-switch design riêng).
- **Admin dashboard charts** cho decision interactions + độ nét avg → Phase 4.6 (4.5 chỉ ghi log).
- **Quota enforcement / paywall N queries** → Phase 5.7 Monetization (4.5 không giới hạn — cần data hành vi thật trước).
- **Google Sheets API sync (OAuth)** → chưa có phase; v1 = .xlsx importable.
- **Decision moment trong onboarding** → Phase 4.6 Onboarding Reset.
- **Zalo surface cho decision queries** → Phase 5.1.

---

## 🔀 Execution Order (đề xuất)

```
E3 (độ nét — nền cho mọi answer)
 └─> E2 (feasibility — nhỏ, reuse nhiều nhất, ship sớm để test tone honest)
      └─> E1 (shock sim — lớn nhất, cột sống)
           └─> E4 (quick wins — song song được với E1 nếu có slack)
                └─> E5 (log từ khi E1/E2 merge; broadcast CHẠY CUỐI CÙNG khi mọi thứ live)
```

E5.2 (broadcast) là bước ship cuối có chủ đích: chỉ gửi khi sản phẩm đã trả lời được "câu này" thật — gửi sớm là đốt one-shot duy nhất với cohort dormant.

---

*Tạo 09/07/2026 — kickoff Phase 4.5 theo Strategy V4 (amendment Zalo 08/07/2026 đã merge).*
