# Issue #412

[Feature] Dashboard Enhancement — VN wealth level labels, inline edit/delete buttons, sortable asset list

## Summary
Enhance the Asset Dashboard với 3 cải tiến UX: (1) thay thế wealth level labels tiếng Anh bằng tiếng Việt, (2) thêm inline edit/delete buttons trên mỗi row asset, (3) sortable asset list với multiple sort options.

---

## 1. Wealth Level Labels — VN-Native

**Vấn đề:** Dashboard hiện tại hiển thị wealth level labels tiếng Anh như "High Net Worth", "Young Professional", "Starter" — không phù hợp với sản phẩm Personal CFO cho người Việt.

**Yêu cầu:** Thay thế tất cả wealth level labels bằng tiếng Việt (đã define trong Phase 3.8.5):

| Internal | Display | Icon | Range |
|---------|---------|------|-------|
| STARTER | **Khởi Đầu** | 🌱 | 0-30tr |
| YOUNG_PROFESSIONAL | **Trẻ Năng Động** | 🚀 | 30-200tr |
| MASS_AFFLUENT | **Trung Lưu Vững** | 💎 | 200tr-1tỷ |
| HIGH_NET_WORTH | **Tinh Hoa** | 🏆 | 1tỷ+ |

**Acceptance Criteria:**
- [ ] Grep toàn bộ codebase cho các string "High Net Worth", "Young Professional", "Starter", "Mass Affluent" trong user-facing output
- [ ] Thay thế bằng VN labels tương ứng
- [ ] Wealth level labels load từ `content/wealth_levels.yaml` (đã có từ Phase 3.8.5)
- [ ] Morning briefing, dashboard, profile view — tất cả đều dùng VN labels
- [ ] Backend/internal code vẫn dùng enum keys (STARTER, etc.) — chỉ display string thay đổi
- [ ] vi-localization-checker pass

---

## 2. Inline Edit/Delete Buttons trên Asset List

**Vấn đề:** Hiện tại mỗi row asset click vào → mở edit flow. User cũng cần delete (xoá) nhanh mà không cần vào menu riêng. Một nút click duy nhất cho cả edit và delete gây confusion.

**Yêu cầu:** Mỗi row asset có 2 inline buttons nhỏ: ✏️ (sửa) và 🗑️ (xoá).

**UX Design:**


**Acceptance Criteria:**
- [ ] Mỗi row asset có 2 buttons: [✏️] và [🗑️], đủ nhỏ để không chiếm nhiều không gian
- [ ] ✏️ → mở edit wizard cho asset đó (reuse existing flow từ asset_entry.py)
- [ ] 🗑️ → confirmation dialog trước khi xoá, sau đó soft delete
- [ ] Callback format: `asset:edit:<uuid>` và `asset:delete:<uuid>`
- [ ] Buttons consistent cho tất cả asset types: stocks, crypto, gold, real_estate, cash
- [ ] Button size phù hợp với mobile (Telegram inline keyboard)
- [ ] Confirmation step cho delete: [✅ Xoá] [❌ Hủy]
- [ ] Sau khi edit/delete thành công → refresh dashboard view (không send new message)

---

## 3. Sortable Asset List

**Vấn đề:** Danh sách tài sản hiện tại không có sort order cố định, gây khó tìm kiếm.

**Yêu cầu:** Default sort theo alphabet (tên asset A-Z). Cung cấp sort options.

**Default: Alphabetical (A-Z)**
- Tất cả assets trong dashboard list theo thứ tự tên alphabet
- Không phân biệt uppercase/lowercase

**Sort Options (Inline Buttons):**
- [A-Z 🔤] Alphabetical (default)
- [📊 Theo loại tài sản] — Grouped by asset type, then alphabetically within each type
- [📈 Lớn → Nhỏ] — Theo giá trị tài sản giảm dần
- [📉 Nhỏ → Lớn] — Theo giá trị tài sản tăng dần

**Acceptance Criteria:**
- [ ] Default sort: alphabet (A-Z) trên tên asset
- [ ] 4 sort options available via inline buttons trên first row của list
- [ ] Current sort indicator (highlighted button)
- [ ] Sort by value dùng `current_value` (Decimal, không float)
- [ ] Sort persists trong session (context.user_data)
- [ ] Support sorting cho cả dashboard full list và filtered-by-type view
- [ ] Consistent order giữa Telegram view và Mini App dashboard
- [ ] Edge: assets cùng tên → tie-break bằng created_at desc

---

## Files Likely Touched
- `content/wealth_levels.yaml` — verify VN labels exist
- `backend/bot/formatters/dashboard_formatter.py` — buttons, sort, labels
- `backend/services/wealth_dashboard_service.py` — sort logic, metadata
- `backend/bot/handlers/asset_entry.py` — delete callback handler
- `backend/intent/handlers/query_assets.py` — VN labels trong responses
- `backend/briefing/morning_briefing.py` — VN labels trong briefing

## Out of Scope
- ❌ Thêm asset từ dashboard (có sẵn qua menu Tài sản)
- ❌ Bulk delete (chỉ single asset delete)
- ❌ Custom sort order (chỉ 4 presets trên)

## Estimate
~1.5-2 days

## Priority
🟠 High — UX improvement trước soft launch

## Labels
`phase-3.9.5` `dashboard` `ux`
