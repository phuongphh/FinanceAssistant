from __future__ import annotations

def build(data: dict) -> dict:
    outcome = data.get("life_outcome") or "Nếu muốn, bạn có thể mở phần kỹ thuật để xem biểu đồ xác suất."
    return {
        "id": "detail",
        "title": "Muốn xem kỹ hơn?",
        "body": outcome,
        "hint": "Biểu đồ nằm sau câu chuyện để không bị ngợp.",
        "emoji": "📊",
        "primary_action": "Xem chi tiết kỹ thuật",
    }
