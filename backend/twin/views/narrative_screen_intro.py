from __future__ import annotations

def build(data: dict) -> dict:
    anchor = data.get("present_anchor") or {}
    return {
        "id": "present",
        "title": "Hôm nay Bé Tiền đang ở đâu?",
        "body": anchor.get("present_label") or "Bắt đầu từ tài sản hiện tại của bạn.",
        "hint": anchor.get("growth_rate_label") or "Bé Tiền theo dõi nhịp thay đổi theo thời gian.",
        "emoji": "📍",
    }
