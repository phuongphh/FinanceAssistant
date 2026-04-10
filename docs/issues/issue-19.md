# Issue #19

[Feature] Persistent Navigation — Back to Main Menu after Every Action

## Overview

Sau mỗi action/response của Bé Tiền, luôn hiển thị suggestion buttons để user có thể điều hướng tiếp, bao gồm nút **"🏠 Về Menu Chính"**. Menu chính là màn hình **donut chart phân bổ tài sản** kèm các action buttons bên dưới.

---

## Context

Hiện tại sau khi bot trả lời xong, user không biết làm gì tiếp theo. Issue này đảm bảo mọi response đều có **persistent navigation** giúp user không bị "lạc" trong conversation.

**Depends on:** #17 (Daily Morning Report — donut chart là Main Menu)

---

## Requirements

### 1. Main Menu Definition

**Main Menu = Morning Report Screen**, bao gồm:
- 🍩 Donut chart phân bổ tài sản (render mới theo data hiện tại)
- Text summary tổng tài sản
- Inline buttons phía dưới:

```
[➕ Thêm tài sản]           [📊 Báo cáo chi tiêu tháng này]
[🔍 Xem cơ hội thị trường]  [🎯 Mục tiêu tài chính]
[📧 Quét Gmail hoá đơn]     [💼 Danh mục đầu tư]
```

---

### 2. Persistent Navigation after Every Action

Sau **mọi response** của bot, luôn thêm suggestion block ở cuối:

```
━━━━━━━━━━━━━━━━━━
Bạn muốn làm gì tiếp theo?

[🏠 Về Menu Chính]  [🔙 Quay lại]
```

Hoặc kèm **context-aware suggestions** tùy theo action vừa thực hiện:

| Action vừa làm | Suggestions hiển thị |
|----------------|---------------------|
| Thêm tài sản | [➕ Thêm tài sản khác] [📊 Xem danh mục] [🏠 Menu Chính] |
| Xem báo cáo chi tiêu | [📅 Báo cáo tháng trước] [📊 Theo danh mục] [🏠 Menu Chính] |
| Quét Gmail | [📸 OCR hoá đơn] [✍️ Nhập thủ công] [🏠 Menu Chính] |
| Cập nhật mục tiêu | [🎯 Xem tất cả mục tiêu] [📊 Tiến độ] [🏠 Menu Chính] |
| Xem thị trường | [📈 Chi tiết cổ phiếu] [💰 Cập nhật giá tài sản] [🏠 Menu Chính] |
| Bất kỳ action nào khác | [🏠 Về Menu Chính] |

---

### 3. Trigger "Về Menu Chính"

Khi user bấm **"🏠 Về Menu Chính"** hoặc nhắn:
- *"menu"*
- *"về menu"*
- *"trang chủ"*
- *"home"*

Bot sẽ render lại **donut chart mới nhất** + action buttons = hiển thị Main Menu

---

### 4. /menu command

Command `/menu` cũng trigger Main Menu (đồng bộ với issue #7)

---

## Acceptance Criteria

- [ ] Sau **mọi response** đều có ít nhất nút **"🏠 Về Menu Chính"**
- [ ] Context-aware suggestions hiển thị đúng theo action vừa thực hiện
- [ ] Bấm "🏠 Về Menu Chính" → render lại donut chart với data mới nhất
- [ ] Natural language triggers ("menu", "về menu", "trang chủ") hoạt động
- [ ] `/menu` command hoạt động
- [ ] Không có action nào kết thúc mà không có navigation suggestion
- [ ] Donut chart trong Main Menu luôn là data real-time (không cache cũ)

## Implementation Notes
- Tạo helper function `build_navigation_buttons(context)` để tái sử dụng
- Main Menu render function nên tách riêng để gọi từ nhiều nơi
- Đồng bộ với `/menu` command từ issue #7
