from __future__ import annotations

def build(data: dict) -> dict:
    contributors = data.get("uncertainty_contributors") or []
    if contributors:
        top = ", ".join(str(c.get("asset_class", "tài sản")) for c in contributors[:2])
        body = f"Vùng 🌧️–☀️ rộng/chặt chủ yếu do {top}."
    else:
        body = "Kết quả thay đổi theo tài sản hiện tại, tiết kiệm mỗi tháng và phân bổ danh mục."
    return {
        "id": "why",
        "title": "Vì sao lại ra vùng này?",
        "body": body,
        "hint": "Đây là giải thích định hướng, không phải lời khuyên đầu tư.",
        "emoji": "🧭",
    }
