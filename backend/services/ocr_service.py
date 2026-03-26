import logging

import anthropic

from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

OCR_PROMPT = """Đây là hóa đơn/receipt. Hãy trích xuất thông tin và trả về JSON hợp lệ:
{
  "total_amount": <số thực, chỉ số không có đơn vị>,
  "currency": <"VND" hoặc currency khác>,
  "merchant_name": <tên nơi mua>,
  "date": <"YYYY-MM-DD" hoặc null nếu không rõ>,
  "items": [{"name": <tên>, "price": <giá>}],
  "category_suggestion": <một trong: food_drink|transport|shopping|health|entertainment|utilities|other>,
  "confidence": <"high"|"medium"|"low">,
  "error": <null hoặc "not_a_receipt" nếu không phải hóa đơn>
}
Chỉ trả về JSON, không có text khác."""


async def parse_receipt_image(image_bytes: bytes, mime_type: str) -> dict:
    if not settings.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY not configured")

    import base64
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    message = await client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime_type,
                            "data": image_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": OCR_PROMPT,
                    },
                ],
            }
        ],
    )

    response_text = message.content[0].text.strip()

    # Strip markdown code fences if present
    if response_text.startswith("```"):
        lines = response_text.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        response_text = "\n".join(lines)

    import json
    try:
        result = json.loads(response_text)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse OCR response: %s", response_text)
        raise ValueError(f"Invalid JSON from OCR: {e}") from e

    logger.info(
        "OCR result: merchant=%s amount=%s confidence=%s",
        result.get("merchant_name"),
        result.get("total_amount"),
        result.get("confidence"),
    )
    return result
