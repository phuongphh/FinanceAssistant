# Từ ý tưởng đến PO nghiệm thu

PO tập trung vào nhu cầu và kết quả; PM phụ trách lựa chọn kỹ thuật, phối hợp triển khai và xử lý vấn đề kỹ thuật.

1. **Viết mã cục bộ:** Nhóm phát triển sửa mã trên máy làm việc. **PO:** mô tả nhu cầu, ví dụ mong muốn và tiêu chí chấp nhận; trả lời câu hỏi nghiệp vụ.

2. **Tạo PR:** Nhóm mở yêu cầu hợp nhất mã (PR), ghi rõ thay đổi và phạm vi. **PO:** đọc tóm tắt, xác nhận đúng nhu cầu và bổ sung tình huống còn thiếu.

3. **Chạy kiểm thử tự động:** GitHub Actions kiểm tra phiên bản mới nhất của PR. **PO:** chờ kết quả; nếu thất bại, để PM điều phối sửa lỗi. Kết quả xanh của phiên bản cũ chưa đủ.

4. **Rà soát kỹ thuật:** Người phụ trách kỹ thuật kiểm tra mã và yêu cầu chỉnh sửa nếu cần. **PO:** làm rõ nghiệp vụ khi được hỏi; để PM xử lý quyết định kỹ thuật.

5. **Triển khai Dev và xác minh:** Nhóm triển khai, đối chiếu Delivery Contract và xác nhận phiên bản Dev cùng bot kiểm thử tương ứng. **PO:** chờ xác nhận rõ phiên bản và bot. Không kiểm thử thủ công qua Telegram trước xác nhận này.

6. **PO nghiệm thu:** **PO:** kiểm tra trên Dev đã xác minh theo tiêu chí chấp nhận, ghi kết quả và lỗi kèm bước tái hiện; xác nhận đạt hoặc yêu cầu sửa.
