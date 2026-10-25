# Issue #450

[Feature] Goals UI/UX Improvements — 5 enhancements

## Summary
Cải thiện UX cho Goals (Mục tiêu) — remove duplicate, auto-recalculate, loading indicator, navigation fix, và optimize LLM performance.

---

## 1. Remove button "Cập nhật tiến độ" (duplicate)

**Vấn đề:** Button "Cập nhật tiến độ" trong submenu Mục tiêu có nội dung trùng với chức năng đã có khi click vào từng goal trong list view.

**Yêu cầu:** Bỏ button này khỏi submenu.

**Acceptance Criteria:**
- [ ] Remove button khỏi `content/menu_copy.yaml` (key `action_goals_update`)
- [ ] Update callback routing trong `menu_handler.py`
- [ ] User vẫn có thể update progress bằng cách click vào từng goal trong list → detail view → update
- [ ] No broken references

---

## 2. Auto-recalculate monthly savings when target date changes

**Vấn đề:** Khi user sửa hạn của mục tiêu (ví dụ từ 2 năm thành 3 năm), số tiền cần tiết kiệm mỗi tháng không được tự động tính lại.

**Yêu cầu:** Khi user thay đổi target_date → hệ thống tự tính lại `required_monthly_savings = (target_amount - current_amount) / months_remaining`.

**Acceptance Criteria:**
- [ ] Detect khi target_date thay đổi trong edit flow
- [ ] Compute: `required_monthly_savings = (target_amount - current_amount) / months_between(today, target_date)`
- [ ] Display lại projection summary sau khi tính: "Cần tiết kiệm Xđ/tháng để đạt mục tiêu vào [date]"
- [ ] Edge cases:
  - target_date < today → reject với message "Ngày hoàn thành phải sau hôm nay"
  - target_amount <= current_amount → mục tiêu đã đạt, không cần tính
  - months_remaining = 0 → display "Cần hoàn thành ngay"
- [ ] Reuse `GoalProjectionService` từ Phase 3.8 (S14)

---

## 3. Loading indicator for "Gợi ý lộ trình" (LLM)

**Vấn đề:** Click "Gợi ý lộ trình" → gọi LLM → user thấy màn hình đứng yên 5-10s → tưởng bot bị lỗi.

**Yêu cầu:** Thêm loading indicator ngay khi click, trước khi LLM trả response.

**Acceptance Criteria:**
- [ ] Khi user click "🎯 Gợi ý lộ trình" → ngay lập tức gửi message: "⏳ Bé Tiền đang phân tích mục tiêu của bạn..."
- [ ] Gửi typing indicator qua `bot.send_chat_action(chat_id, "typing")`
- [ ] Reuse `TelegramStreamer` pattern từ Phase 3.7 (S7) nếu LLM trả streaming
- [ ] Sau khi LLM response → edit message gốc, thay "⏳ Đang phân tích..." thành nội dung gợi ý
- [ ] Nếu LLM fail sau 15s → edit message: "⏳ Bé Tiền cần thêm thời gian — bạn thử lại sau nhé 💚"
- [ ] Test: click → indicator xuất hiện trong < 2s

---

## 4. Replace "Hủy" with "Quay về" in Add Goal wizard

**Vấn đề:** Trong flow "Thêm mục tiêu", button "❌ Hủy" mang tính destructive — user có thể ngại click vì sợ mất dữ liệu.

**Yêu cầu:** Đổi label thành "◀️ Quay về" — navigation-friendly.

**Acceptance Criteria:**
- [ ] Tất cả các step trong add-goal wizard: button "❌ Hủy" → "◀️ Quay về"
- [ ] Callback behavior không thay đổi (vẫn clear state và return về submenu)
- [ ] Cập nhật trong `content/menu_copy.yaml` hoặc goal wizard templates
- [ ] Consistent với pattern "◀️ Quay về" ở các menu khác (Phase 3.6)

---

## 5. Optimize "lộ trình mua nhà" — LLM timeout & cold start

**Vấn đề:** Khi user gõ "lộ trình mua nhà", hệ thống gọi LLM nhưng mất rất lâu (có thể do cold start hoặc LLM timeout). Sau đó trả về "mình cần thêm thời gian — bạn cho mình thử lại sau nhé" — UX rất tệ.

**Yêu cầu:** Optimize luồng này để response nhanh hơn và có fallback tốt hơn.

**Root cause investigate:**
- [ ] Check: LLM call có bị timeout ở provider không? (DeepSeek / Claude)
- [ ] Check: LLM call có đang dùng model chậm không? (cần dùng model nhanh nhất cho gợi ý)
- [ ] Check: Context có quá lớn không? (giảm context xuống chỉ essential fields)
- [ ] Check: Co-hosted services có competing resources không?

**Optimization:**
- [ ] **Cache layer:** Cache kết quả gợi ý lộ trình theo `goal_type + wealth_level` với TTL 24h — user khác cùng goal type có thể dùng cached kết quả (với disclaimer cá nhân hóa)
- [ ] **Timeout handling:** LLM call với timeout 10s. Nếu timeout → fallback to rule-based template (không phải "thử lại sau")
- [ ] **Fallback template:** Prepare rule-based lộ trình templates cho 7 goal types từ Phase 3.8. Nếu LLM fail/timeout → gửi template + note "Gợi ý này dựa trên mẫu phổ biến. Bé Tiền có thể phân tích chi tiết hơn nếu bạn thử lại sau."
- [ ] **Optimize prompt:** Rút gọn prompt, chỉ gửi essential fields (goal_name, target_amount, current_amount, target_date, wealth_level)
- [ ] **Warm-up:** Nếu detect cold start (lần gọi LLM đầu tiên trong session) → call model nhỏ hơn trước để warm

**Acceptance Criteria:**
- [ ] Gợi ý lộ trình response trong < 8s (P95)
- [ ] Cache hit rate > 40% cho các goals common type
- [ ] Fallback template không dùng từ "thử lại sau" — luôn có gợi ý
- [ ] Unit test: LLM timeout → fallback template sent
- [ ] Manual test: gõ "lộ trình mua nhà" → response < 8s

---

## Files Likely Touched
- `content/menu_copy.yaml` — buttons
- `backend/bot/handlers/menu_handler.py` — routing
- `backend/goals/services/goal_service.py` — recalculate
- `backend/goals/services/projection_service.py` — recalculate
- `backend/intent/handlers/advisory.py` — LLM prompt optimization
- `content/goal_templates.yaml` — fallback templates
- `app/agent/streaming/telegram_streamer.py` — loading indicator

## Estimate
~1-1.5 days

## Priority
🟠 High — UX improvement trước soft launch
