# Issue #897

feat(expense-confirm): restore footer buttons + Vietnam TZ + source/amount edit wizards

## Context

Sau khi PR #892 ẩn các footer buttons trên confirmation message của expense, user thấy thiếu khả năng sửa nhanh ngay tại tin nhắn. Cần đem lại footer buttons với UX rõ ràng hơn và sửa luôn vài bug nhỏ.

## Requirements

1. **Vietnam timezone**: thời gian (`%H:%M`) trên confirmation message phải hiển thị theo `Asia/Ho_Chi_Minh` (hiện tại đang là UTC → sai 7 tiếng).

2. **Đổi text edit hint**:
   - Cũ: "💡 Cần sửa/xoá? Vào mục Quản lý chi tiêu trong menu Chi tiêu nhé."
   - Mới: "💡 chi tiêu đã được ghi lại, nếu đúng bạn không cần làm gì thêm!"
   - Vẫn giữ italic + emoji.

3. **4 footer buttons (icon-only)** trên một row:
   - 🏷 → wizard đổi **danh mục** (như cũ).
   - 💳 → wizard đổi **nguồn tiền** (mới, design mirror category picker, scope = chỉ transaction này, KHÔNG đổi `default_expense_source` của user).
   - 💵 → cho user **nhập lại số tiền** (force_reply prompt; parse `45k`, `1.5tr`).
   - 🗑 → **xoá** transaction (flow confirm_delete như cũ).

4. **Nút thứ 5 "✅ Đồng ý"**: chỉ xuất hiện sau khi user click vào 1 trong 4 button trên (mode "đang sửa"). Click "Đồng ý" → ẩn toàn bộ keyboard, giữ message text.

## Acceptance

- [ ] Time hiển thị đúng giờ VN.
- [ ] Hint mới hiện trên confirmation message.
- [ ] 4 icon buttons hoạt động độc lập, mỗi flow re-render confirmation với "✅ Đồng ý" thêm vào.
- [ ] Click "Đồng ý" ẩn keyboard.
- [ ] Đổi source chỉ áp dụng cho transaction này.
- [ ] Đầy đủ unit tests cho từng path mới.
- [ ] Không vi phạm layer contract (service không commit).
- [ ] Vietnamese strings ở `content/*.yaml`, không hardcode.
