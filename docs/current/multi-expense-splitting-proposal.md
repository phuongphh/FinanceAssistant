# Đề xuất: tách nhiều chi phí trong một tin nhắn

## Vấn đề

Ví dụ user nhắn: `tiền xăng 50k, ăn trưa 50k`.

Hiện tại luồng quick transaction chỉ trả về một cặp `amount + merchant`, nên hệ thống cộng thành một giao dịch `100,000đ` và chỉ gán được một category. Kết quả đúng nên là hai giao dịch:

1. `tiền xăng` — `50,000đ` — `transport`
2. `ăn trưa` — `50,000đ` — `food`

## Nguyên nhân chính

- Parser hiện tại được thiết kế cho một chi phí duy nhất.
- Handler chỉ tạo một `ExpenseCreate` cho mỗi tin nhắn.
- Auto-categorize chỉ chạy trên từng expense, nên khi nhiều món bị gộp lại thì chỉ còn một category tổng.

## Hướng giải quyết đề xuất

Thêm bước `multi-expense parser` trước khi tạo expense.

Parser nên trả JSON dạng danh sách:

```json
{
  "is_expense": true,
  "items": [
    {"merchant": "tiền xăng", "amount": 50000, "category_hint": "transport"},
    {"merchant": "ăn trưa", "amount": 50000, "category_hint": "food"}
  ]
}
```

Sau đó handler:

1. Nếu `items.length == 1`: giữ flow cũ.
2. Nếu `items.length > 1`: tạo nhiều `ExpenseCreate`, mỗi item là một expense riêng.
3. Gửi confirmation dạng nhóm, ví dụ:

```text
✅ Ghi xong 2 khoản!
🚗 tiền xăng — 50,000đ
🍜 ăn trưa — 50,000đ
Tổng: 100,000đ
```

## Quy tắc tách đơn giản

Ưu tiên tách khi câu có nhiều cụm `mô tả + số tiền`, ngăn bởi:

- dấu phẩy: `xăng 50k, ăn trưa 50k`
- chữ `và`: `xăng 50k và ăn trưa 50k`
- dấu cộng: `xăng 50k + ăn trưa 50k`
- xuống dòng: mỗi dòng một khoản

Không tách nếu chỉ có một số tiền tổng, ví dụ: `ăn tối và trà sữa 400k`. Case này nên giữ một expense vì không biết chia bao nhiêu cho từng món.

## Nên làm theo 2 lớp

### Lớp 1: heuristic nhanh

Dùng regex để phát hiện nhiều amount trong câu. Nếu có từ 2 amount trở lên thì gọi multi-parser.

Ví dụ pattern amount: `\d+[.,]?\d*\s*(k|ngàn|nghìn|tr|triệu)?`.

### Lớp 2: LLM parser có schema chặt

LLM chỉ được trả JSON theo schema `items[]`. Mỗi item bắt buộc có:

- `merchant`
- `amount`
- `category_hint` nếu đoán được

Nếu tổng các item không rõ hoặc parser thiếu dữ liệu, fallback về flow cũ hoặc hỏi lại user.

## Acceptance criteria

- `tiền xăng 50k, ăn trưa 50k` tạo 2 expenses khác category.
- `xăng 50k và cafe 30k` tạo 2 expenses.
- `ăn tối và trà sữa 400k` vẫn tạo 1 expense.
- Confirmation hiển thị từng dòng và tổng tiền.
- Undo nên xóa cả batch nếu user bấm hủy ngay sau khi ghi nhóm.

## Gợi ý triển khai

- Đổi `_extract()` trong `ActionQuickTransactionHandler` từ trả một tuple sang trả danh sách item, hoặc thêm hàm mới `_extract_items()` để tránh phá flow cũ.
- Thêm helper `create_expenses_batch()` trong `expense_service` để tạo nhiều expense chung một transaction.
- Thêm formatter confirmation nhóm, không dùng card đơn hiện tại cho batch nhiều item.
- Lưu `batch_id` vào `raw_data` để hỗ trợ undo cả nhóm.
