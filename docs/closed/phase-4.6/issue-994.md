# Issue #994

[4.6/E4][follow-up] Định nghĩa lại "product-active" làm denominator cho retention/DAU

## Bối cảnh

Trong lúc implement D28-by-cohort (issue D28 retention), Codex review nêu một P2: các metric retention/active hiện dùng **bất kỳ `Event` nào** làm tín hiệu "active". Điều này gồm cả các event thụ động (ví dụ system-driven, briefing được đẩy tự động) chứ không phải hành vi chủ động của user với sản phẩm. Kết quả là mẫu số "active" có thể bị thổi phồng, khiến D28 / DAU trông đẹp hơn thực tế.

## Vấn đề

Cần một định nghĩa **"product-active"** rõ ràng — tập event nào thực sự tính là user chủ động dùng sản phẩm (ví dụ: gửi tin nhắn, hỏi decision query, mở briefing chủ động…) so với event thụ động cần loại trừ.

## Tại sao HELD (chưa implement)

Đây là một **quyết định sản phẩm**, không phải kỹ thuật thuần túy: chưa có định nghĩa "product-active" nào được chốt. Implement bằng cách tự đoán tập event sẽ làm sai lệch mọi metric downstream. Cần product owner chốt danh sách event types (hoặc tiêu chí) trước.

## DoD (khi được unblock)

- [ ] Chốt danh sách event types / tiêu chí tính là "product-active".
- [ ] Áp dụng nhất quán cho `decision-retention`, `cohort-retention`, DAU/WAU/MAU, activation.
- [ ] Cập nhật test + doc để phản ánh denominator mới.

_Ghi chú: file như một follow-up để không mất context; không block D28-by-cohort._
