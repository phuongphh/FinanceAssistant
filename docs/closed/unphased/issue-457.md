# Issue #457

[Feature] UI/UX Enhancements — Consolidate menus, fix labels, improve copy

## Summary
5 UI/UX enhancements: consolidate Tài sản menu, fix "Thuê BĐS" label, fix Goals back button, trim Profile text, improve main menu intro.

---

## 1. Tài sản menu — Consolidate Tổng tài sản

**Vấn đề:** Khi user click "Tài sản" → thấy submenu, cần click thêm "Tổng tài sản" mới thấy nội dung. Gây redundant click.

**Yêu cầu:** Đưa nội dung của "Tài sản → Tổng tài sản" lên làm nội dung chính khi vào menu Tài sản. Giữ nguyên phần "mẹo". Sau đó xóa button "Tổng tài sản".

**Acceptance Criteria:**
- [ ] Nội dung action `(assets, net_worth)` render ngay khi user vào submenu Tài sản
- [ ] Button "💎 Tổng tài sản" removed khỏi submenu
- [ ] Phần "mẹo" (hint) vẫn giữ nguyên ở cuối view
- [ ] Các button còn lại giữ nguyên vị trí
- [ ] File: `content/menu_copy.yaml` + `backend/bot/handlers/menu_handler.py`

---

## 2. Sửa label "Thuê BĐS" → "BĐS cho thuê"

**Vấn đề:** Label "Thuê BĐS" sai tiếng Việt — "Thuê BĐS" nghĩa là "đi thuê bất động sản", đúng phải là "BĐS cho thuê" (BĐS được đem cho thuê).

**Yêu cầu:** Tìm tất cả nơi dùng label "Thuê BĐS" trong codebase và sửa thành "BĐS cho thuê".

**Acceptance Criteria:**
- [ ] Grep toàn bộ codebase cho string "Thuê BĐS" (case-insensitive)
- [ ] Thay thế tất cả bằng "BĐS cho thuê"
- [ ] Kiểm tra: content YAML, formatter, handler responses, test snapshots
- [ ] Test: user click rental section → thấy "BĐS cho thuê" đúng
- [ ] Không ảnh hưởng đến các label khác có "thuê" (ví dụ: "thuê nhà" là correct)

**Files likely:**
- `content/menu_copy.yaml`
- `content/wealth_levels.yaml` (if referenced)
- `backend/bot/formatters/*`
- Test fixtures/snapshots

---

## 3. Goals — "Quay về" button direct về main menu Mục tiêu

**Vấn đề:** Trong flow "Thêm mục tiêu", button "Quay về" hiện tại direct về Mục tiêu hiện tại (specific goal) thay vì main menu Mục tiêu (list all goals).

**Yêu cầu:** Sửa behavior để "Quay về" trong add-goal wizard direct về đúng main menu Mục tiêu.

**Acceptance Criteria:**
- [ ] Xác định callback hiện tại của button "Quay về" trong add-goal wizard
- [ ] Sửa callback về `(goals, list)` thay vì `(goals, view_current)`
- [ ] Test: add goal → cancel giữa chừng → quay về list goals, không phải detail view
- [ ] Consistent behavior qua các step trong wizard

---

## 4. Profile — Trim "không cần điền form"

**Vấn đề:** Dòng text "Profile này được tự động tổng hợp từ dữ liệu bạn đã dùng — không cần điền form" hơi dài và phần "không cần điền form" redundant vì user đã thấy profile tự động hiện ra.

**Yêu cầu:** Bỏ đoạn "không cần điền form". Giữ lại: "Profile này được tự động tổng hợp từ dữ liệu bạn đã dùng."

**Acceptance Criteria:**
- [ ] Tìm exact string trong `content/menu_copy.yaml` (key `profile_auto_intro` hoặc tương đương)
- [ ] Remove " — không cần điền form" (bao gồm em dash)
- [ ] vi-localization-checker pass

---

## 5. Main menu intro — Improve Bé Tiền introduction

**Vấn đề:** Lời giới thiệu hiện tại "Tổng quan tài chính cá nhân của [name]" không rõ nghĩa và không ấn tượng — không cho user biết Bé Tiền là gì và làm được gì.

**Yêu cầu:** Cải thiện intro ngắn gọn nhưng ấm áp, thân thiện. Product position là Personal CFO nhưng **KHÔNG dùng từ "CFO" trong user-facing text** — từ này khô khan, nặng nề.

**Nguyên tắc:**
- ❌ Không dùng: CFO, tài chính cá nhân, quản lý tài sản
- ✅ Dùng từ gần gũi: đồng hành, cùng bạn, giúp bạn
- ✅ Bé Tiền tone: warm, "mình" - "bạn"
- ✅ ≤ 2 dòng, mention tên user

**Gợi ý (tham khảo, chọn 1 hoặc đề xuất khác):**
- Option A: "💎 [name] ơi, Bé Tiền đây — mình cùng nhau xây dựng tương lai nhé!"
- Option B: "💎 Chào [name]! Bé Tiền luôn ở đây, đồng hành cùng bạn."
- Option C: "💎 *Bé Tiền* — Người bạn đồng hành của [name]"

**Acceptance Criteria:**
- [ ] Intro ≤ 2 dòng
- [ ] KHÔNG chứa từ "CFO" trong bất kỳ user-facing string nào
- [ ] Bé Tiền tone consistent (warm, "mình"/"bạn")
- [ ] Cập nhật trong content/menu_copy.yaml (main_menu greeting)
- [ ] Wealth-level adaptive intro giữ nguyên tone mới
- [ ] vi-localization-checker pass

---

## Files Likely Touched
- `content/menu_copy.yaml` — main menu intro, submenu intros, buttons
- `backend/bot/formatters/menu_formatter.py` — profile intro formatting
- `backend/bot/handlers/goal_handler.py` — back button routing
- `backend/bot/handlers/asset_entry.py` — goal wizard back navigation
- Test snapshots

## Estimate
~0.75-1 day

## Priority
🟡 Medium
