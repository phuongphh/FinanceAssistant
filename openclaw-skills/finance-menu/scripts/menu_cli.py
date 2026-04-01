#!/usr/bin/env python3
"""OpenClaw Skill CLI: finance-menu
Display the main menu with all available features.
"""

MENU_TEXT = """🏦 Finance Assistant — Menu

Chọn tính năng bạn muốn sử dụng:

📧 Quét hóa đơn Gmail — "quét gmail" hoặc "scan gmail"
📸 Nhận diện hóa đơn — Gửi ảnh hóa đơn/receipt trực tiếp
✍️ Thêm chi tiêu — "thêm chi tiêu 150k ăn trưa"
📊 Báo cáo chi tiêu — "báo cáo tháng này"
📈 Thông tin thị trường — "thị trường hôm nay?"
🎯 Mục tiêu tài chính — "mục tiêu" hoặc "tiến độ"
💰 Cập nhật thu nhập — "thu nhập tháng này 20tr"
💡 Gợi ý đầu tư — "nên đầu tư gì?"

Nhập lệnh hoặc mô tả nhu cầu bằng tiếng Việt tự nhiên."""

if __name__ == "__main__":
    print(MENU_TEXT)
