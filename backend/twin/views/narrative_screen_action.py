from __future__ import annotations

def build(data: dict) -> dict:
    needed = data.get("monthly_savings_needed")
    if needed and str(needed) != "0":
        body = "Thử kịch bản Tối ưu để thấy nếu tăng tiết kiệm đều đặn thì vùng ⛅ có thể nhích thế nào."
    else:
        body = "Việc quan trọng nhất lúc này là duy trì nhịp và cập nhật tài sản đều đặn."
    return {
        "id": "action",
        "title": "Bạn có thể làm gì ngay?",
        "body": body,
        "hint": "Một hành động nhỏ đủ để Bé Tiền tính lại ở vòng sau.",
        "emoji": "✨",
    }
