# Issue #17

[Feature] Daily Morning Report — 7AM Asset Portfolio Summary with Pie Chart

## Overview

Mỗi sáng lúc **7:00 AM**, Bé Tiền tự động gửi tin nhắn chào buổi sáng kèm báo cáo tổng quan tài sản dạng **pie/donut chart** và các gợi ý hành động tiếp theo.

---

## Requirements

### 1. Scheduler
- Chạy mỗi ngày lúc **07:00 AM (GMT+7)**
- Gửi cho tất cả user đang active

---

### 2. Morning Greeting Message

```
🌅 Chào buổi sáng! Đây là báo cáo tài sản của bạn hôm nay.
📅 [Thứ X, ngày DD/MM/YYYY]
```

---

### 3. Asset Portfolio Pie Chart

Tạo ảnh **donut chart** từ dữ liệu portfolio trong DB, hiển thị phân bổ tài sản theo loại:

| Asset Type | Hiển thị |
|------------|----------|
| Bất động sản | Real Estate |
| Chứng khoán | Stocks |
| Chứng chỉ quỹ | Mutual Fund |
| Tiền số | Crypto |
| Bảo hiểm nhân thọ | Insurance |
| Vàng | Gold |
| Tiền mặt | Cash |

**Chart specs:**
- Dạng **donut chart** (tương tự ảnh đính kèm)
- Hiển thị **% phân bổ** từng loại tài sản trên chart
- Ở giữa donut: **Tổng tài sản** (VND) + **% tăng/giảm** so với tháng trước
- Legend bên phải: từng loại tài sản + giá trị (VND)
- Cuối chart: **Tài sản ròng** = Tổng tài sản - Nợ
- Timestamp cập nhật

**Technical:** Dùng `matplotlib` hoặc `plotly` để render chart → export PNG → gửi qua Telegram

---

### 4. Text Summary (kèm theo chart)

```
💰 Tổng tài sản: 524.3 triệu ↑ 9.6%
📊 Tài sản ròng: 524.3 triệu

🏠 Bất động sản:  XXX triệu (XX%)
📈 Chứng khoán:   XXX triệu (XX%)
🏦 Chứng chỉ quỹ: XXX triệu (XX%)
₿  Tiền số:       XXX triệu (XX%)
🛡️ Bảo hiểm:      XXX triệu (XX%)
🥇 Vàng:          XXX triệu (XX%)
```

---

### 5. Action Suggestions (Inline Buttons)

Sau báo cáo, hiển thị các nút gợi ý:

```
Bạn muốn làm gì tiếp theo?

[➕ Thêm tài sản]        [📊 Báo cáo chi tiêu tháng này]
[🔍 Xem cơ hội thị trường]  [🎯 Cập nhật mục tiêu tài chính]
```

---

### 6. Data Source
- Lấy dữ liệu từ bảng `portfolio_assets` (Issue #14)
- Tính % thay đổi so với snapshot tháng trước (nếu có)
- Nếu user chưa có tài sản nào → gửi tin nhắn khuyến khích thêm tài sản thay vì chart trống

---

## Acceptance Criteria

- [ ] Scheduler chạy đúng 7:00 AM GMT+7 mỗi ngày
- [ ] Donut chart được render đúng với màu sắc phân biệt từng loại tài sản
- [ ] Tổng tài sản và % thay đổi hiển thị đúng ở giữa chart
- [ ] Text summary khớp với dữ liệu trong chart
- [ ] Inline buttons hoạt động đúng với từng action
- [ ] User chưa có tài sản → nhận tin nhắn gợi ý thêm tài sản (không gửi chart trống)
- [ ] Chart được gửi dưới dạng ảnh PNG qua Telegram
- [ ] Không gửi nếu user đã tắt notification

## Implementation Notes
- Depends on: #14 (Investment Portfolio Management)
- Dùng `matplotlib` hoặc `plotly` để vẽ donut chart
- Lưu PNG tạm vào `/tmp` rồi gửi qua Telegram Bot API
- Xóa file PNG sau khi gửi xong
