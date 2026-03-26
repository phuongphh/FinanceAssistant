---
name: finance-ocr
description: >
  Nhận diện hóa đơn/receipt từ ảnh qua AI Vision.
  Trích xuất số tiền, merchant, ngày, danh mục tự động.
metadata:
  openclaw:
    requires:
      bins: ["python3"]
---

# Finance OCR Skill

## Khi nào dùng skill này
- User gửi ảnh bất kỳ (hóa đơn, receipt, bill)
- User nói "scan hóa đơn", "nhận diện bill"

## Cách thực thi

### OCR ảnh hóa đơn
1. Nhận file ảnh từ user
2. Chạy: `python3 scripts/ocr_cli.py <image_path>`
3. Hiển thị kết quả parse cho user confirm
4. Nếu user confirm → chạy: `python3 scripts/ocr_cli.py --save <image_path>`

## Output format
```
Nhận diện hóa đơn:
  Merchant: Phở Thìn
  Số tiền: 150,000₫
  Ngày: 26/03/2026
  Danh mục: food_drink
  Độ tin cậy: high

Có đúng không? Reply "ok" để lưu.
```
