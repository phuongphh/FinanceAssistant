from __future__ import annotations

def build(data: dict) -> dict:
    return {
        "id": "scenarios",
        "title": "Năm 2030 có 3 phiên bản Bé Tiền",
        "body": "Không đoán một con số duy nhất — Bé Tiền kể bằng 3 vùng thời tiết.",
        "hint": "Vuốt để xem từng kịch bản.",
        "emoji": "🔮",
        "cards": data.get("scenario_cards") or [],
    }
