# Issue #985

[Phase 4.6][E3] Decision Moment trong onboarding — 1 câu hỏi gắn goal + đúng 1 con số + độ nét thành thật

## Epic E3 — Decision Moment Trong Onboarding

Phase 4.6 (Onboarding Reset cho segment mới). Detail: `docs/current/phase-4.6/phase-4.6-detailed.md` · Issues: `docs/current/phase-4.6/phase-4.6-issues.md`.

Decision moment đầu tiên xảy ra ngay trong onboarding: **ngay sau Twin reveal**, Bé Tiền hỏi 1 câu quyết định gắn goal đã chọn (E1) rồi trả lời liền với **đúng 1 con số** + **độ nét thành thật**. Tái dùng `plan_feasibility_service` + `clarity_service` (Phase 4.5) — **KHÔNG viết engine mới**. Toàn bộ nằm sau flag `ONBOARDING_DECISION_MOMENT_ENABLED` default `false`, đọc ở handler edge (KHÔNG service/formatter). Off → reveal byte-identical như trước 4.6.

### Child issues
- **#3.1** Decision moment gắn goal: sau Twin reveal hỏi 1 câu quyết định theo goal đã chọn; trả lời bằng `plan_feasibility_service` với 1 con số + goal. 3 answer shape thành thật theo lượng data engine kết luận được — `on_track` (số tháng), `building` (mức đang trên đà tới), `direction` (mốc tham chiếu, khung "điểm khởi đầu" thay vì "không") cho ca onboarding thường gặp (chưa có nhịp tiết kiệm). Fallback `default_goal` cho goal legacy/lạ để không kẹt flow.
- **#3.2** Độ nét thành thật: kèm `clarity_service` score + gợi ý làm nét đúng component thiếu nhất; dưới ngưỡng → humble copy, trên ngưỡng → nudge nhẹ. KHÔNG ép nhập thêm trường để trả lời được.
- **#3.3** Copy + persona QA: copy decision moment honest-not-harsh, goal-specific, 0 jargon, salutation-aware (anh/chị/bạn), toàn bộ ở `content/onboarding/decision_moment.yaml`.

### Success criteria
- [x] 1 câu hỏi quyết định goal-specific, trả lời ngay với data tối thiểu (integration test cho mỗi goal reset + fallback goal lạ).
- [x] Flag off (default) → onboarding kết ở Twin reveal như cũ, byte-identical.
- [x] Độ nét thấp vẫn trả lời được; humble copy đúng ngưỡng; gợi ý làm nét bám component thiếu nhất.
- [x] Best-effort: decision moment lỗi không bao giờ vỡ Twin reveal; ghi 1 dòng `decision_query_log` append-only (flush-only service, worker commit) kèm clarity score cho E4.
- [x] Flag đọc ở handler edge, KHÔNG trong service/formatter; formatter thuần (no I/O, no env).
- [x] 0 chuỗi tiếng Việt hardcode trong code; 0 term "Decision Engine/CFO/GPS tài chính" user-facing; 0 tone từ khắt khe.
- [x] Toàn bộ test xanh; ruff sạch.
