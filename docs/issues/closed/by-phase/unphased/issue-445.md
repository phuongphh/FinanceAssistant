# Issue #445

[Feature] Dòng tiền Menu Enhancement — Consolidate Tổng quan, rename Thu vs Chi, remove duplicate

## Summary
Streamline submenu Dòng tiền với 3 cải tiến: (1) consolidate nội dung Tổng quan vào menu chính, (2) rename Thu vs Chi thành Chi tiêu, (3) remove duplicate Tỷ lệ tiết kiệm.

---

## 1. Consolidate Tổng quan vào menu Dòng tiền

**Vấn đề:** Khi user click button "Dòng tiền" → thấy submenu, cần click thêm "Tổng quan" mới thấy nội dung. Gây redundant click.

**Yêu cầu:** Đưa nội dung của "Dòng tiền -> Tổng quan" lên làm nội dung chính của menu "Dòng tiền". Sau đó bỏ button "Tổng quan" khỏi submenu.

**Implementation:**
- [ ] Nội dung hiện tại của action `(cashflow, overview)` render ngay khi user vào submenu Dòng tiền
- [ ] Button "📊 Tổng quan" được remove khỏi submenu
- [ ] Vẫn giữ nguyên phần "mẹo" (hint) hiện tại ở cuối view
- [ ] Các button còn lại trong submenu giữ nguyên vị trí

**Expected UX:**


---

## 2. Rename "Thu vs Chi" → "Chi tiêu"

**Vấn đề:** Button "Thu vs Chi" không intuitive — user không biết click vào sẽ thấy gì. Should trigger existing expense flow.

**Yêu cầu:** 
- Đổi label button từ "📊 Thu vs Chi" thành "💸 Chi tiêu"
- Khi click → trigger luồng Chi tiêu đã có (reuse existing handler, không tạo mới)

**Implementation:**
- [ ] Update YAML: `content/menu_copy.yaml` → rename button label
- [ ] Update callback routing: action `(cashflow, expense_vs_income)` → reroute tới existing expense handler (thay vì comparison view)
- [ ] Test: click button → thấy expense report, không phải comparison chart
- [ ] Không tạo handler mới — chỉ re-use

---

## 3. Remove "Tỷ lệ tiết kiệm" button

**Vấn đề:** Nội dung "Tỷ lệ tiết kiệm" đã có trong view Dòng tiền tổng quan (saving rate displayed inline). Button riêng gây duplicate.

**Yêu cầu:** Bỏ button "💰 Tỷ lệ tiết kiệm" khỏi submenu Dòng tiền.

**Implementation:**
- [ ] Remove button entry từ `content/menu_copy.yaml`
- [ ] Remove/unregister callback handler nếu không còn action nào reference
- [ ] Verify saving rate vẫn hiển thị trong view Tổng quan / Dòng tiền chính
- [ ] No broken references

---

## Files Likely Touched
- `content/menu_copy.yaml` — button labels, entries
- `backend/bot/handlers/menu_handler.py` — routing changes
- `backend/intent/handlers/query_cashflow.py` — maybe handler consolidation

## Out of Scope
- Không thay đổi nội dung của các view khác (Thu nhập, Chi tiêu, Mục tiêu)
- Không thêm tính năng mới — chỉ consolidation

## Estimate
~0.5 day

## Priority
Medium — UX simplification trước soft launch
