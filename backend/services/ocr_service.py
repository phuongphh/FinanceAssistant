"""Receipt OCR pipeline.

Two-stage design:

1. **External OCR provider** (``ocr.nuitruc.ai``) extracts raw text from
   the receipt image. Vision models are expensive; a specialised OCR
   endpoint is faster and cheaper for plain-text extraction.
2. **DeepSeek** parses the extracted text into the structured shape the
   ingestion router and downstream expense flow already expect.

Keeping the public ``parse_receipt_image(image_bytes, mime_type)`` shape
means the router/CLI contract is unchanged — only the implementation
swaps under the hood.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.services.llm_service import LLMError, call_llm

logger = logging.getLogger(__name__)
settings = get_settings()

# Singleton client — HTTP/2 + connection pool reuse keeps latency low
# across consecutive OCR requests. Lazily constructed so importing this
# module in tests/CLI doesn't open sockets.
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.ocr_api_timeout_seconds, connect=5.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
            http2=True,
        )
    return _client


_STRUCTURE_PROMPT = """Bạn là trợ lý phân tích chứng từ chi tiêu tiếng Việt.
Dưới đây là text trích xuất từ ảnh (có thể nhiễu OCR). Ảnh có thể là:
- Hoá đơn / biên lai mua hàng, HOẶC
- Ảnh chụp xác nhận giao dịch / chuyển tiền (app ngân hàng, ví điện tử).
Hãy trả về DUY NHẤT một JSON theo schema sau, không kèm giải thích:

{{
  "total_amount": <số thực, chỉ số, đơn vị mặc định VND>,
  "currency": "VND" | "USD" | ...,
  "merchant_name": <string hoặc null>,
  "date": "YYYY-MM-DD" | null,
  "items": [{{"name": <string>, "price": <số>}}],
  "note": <string hoặc null>,
  "category_suggestion": "food_drink"|"transport"|"shopping"|"health"|"entertainment"|"utilities"|"other"|null,
  "confidence": "high"|"medium"|"low",
  "error": null | "not_a_receipt"
}}

Quy tắc:
- Luồng này CHỈ ghi nhận khoản CHI (tiền ra). Đặt "error": "not_a_receipt" khi:
  - text hoàn toàn KHÔNG phải chứng từ tài chính (không tìm thấy số tiền giao dịch nào), HOẶC
  - là giao dịch TIỀN VÀO / nhận tiền (dấu "+", "Nhận tiền", "Ghi có", "Tiền vào", "Hoàn tiền") — KHÔNG ghi nhận như một khoản chi.
  Ảnh chuyển tiền ĐI (tiền ra) VẪN HỢP LỆ dù không có "merchant" kiểu cửa hàng — đừng đặt not_a_receipt chỉ vì thiếu merchant.
- Hoá đơn mua hàng: ``total_amount`` chọn dòng tổng cuối cùng (TỔNG CỘNG / TOTAL / THÀNH TIỀN), KHÔNG cộng dồn các dòng item.
- Ảnh chuyển tiền ĐI / giao dịch tiền ra: ``total_amount`` lấy từ dòng "Số tiền giao dịch" / "Số tiền"; bỏ dấu "-" và "VND" (ví dụ "-800,000 VND" → 800000). ``merchant_name`` = tên người/đơn vị nhận nếu rõ, nếu không → null. ``category_suggestion`` = null khi không rõ mục đích chi (đừng mặc định "other") để hệ thống tự phân loại.
- Bỏ dấu phân cách hàng nghìn khi parse số. Ví dụ "150.000" → 150000.
- ``note``: nội dung/diễn giải giao dịch — lấy NGUYÊN VĂN dòng "Lời nhắn", "Nội dung chuyển khoản", "Nội dung giao dịch", "Diễn giải", "Nội dung", "payment reference" hoặc "memo" nếu có. KHÔNG tóm tắt, KHÔNG thêm chữ. Nếu không có → null.
- ``confidence``: "high" nếu thấy rõ số tiền + (merchant hoặc nội dung giao dịch); "medium" nếu thiếu 1 field; "low" nếu nhiều field phải đoán.

=== OCR TEXT ===
{text}
=== END ==="""


def _extract_text(payload: Any) -> str:
    """Best-effort text extraction from the provider response.

    The provider hasn't published a stable schema, so we probe a few
    common shapes rather than crashing on the first miss.
    """
    if isinstance(payload, str):
        return payload.strip()
    if isinstance(payload, list):
        return "\n".join(_extract_text(p) for p in payload).strip()
    if isinstance(payload, dict):
        for key in ("text", "result", "ocr_text", "content", "data", "output"):
            if key in payload:
                extracted = _extract_text(payload[key])
                if extracted:
                    return extracted
        # Fallback: concatenate string-valued fields
        return "\n".join(
            v.strip() for v in payload.values() if isinstance(v, str) and v.strip()
        )
    return ""


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = [l for l in text.split("\n") if not l.startswith("```")]
        text = "\n".join(lines).strip()
    return text


async def _call_external_ocr(image_bytes: bytes, mime_type: str) -> str:
    """POST image to the external OCR endpoint, return extracted text."""
    headers: dict[str, str] = {"accept": "application/json"}
    if settings.ocr_api_key:
        headers["Authorization"] = f"Bearer {settings.ocr_api_key}"

    filename = f"receipt.{(mime_type.split('/')[-1] or 'jpg')}"
    files = {"file": (filename, image_bytes, mime_type)}

    client = _get_client()
    try:
        resp = await client.post(settings.ocr_api_url, headers=headers, files=files)
    except httpx.TimeoutException as exc:
        # Don't log image bytes; record size only.
        logger.warning("OCR provider timeout (image_size=%d)", len(image_bytes))
        raise ValueError("OCR provider timeout") from exc
    except httpx.HTTPError as exc:
        logger.exception("OCR provider transport error: %s", exc)
        raise ValueError(f"OCR provider error: {exc}") from exc

    if resp.status_code >= 400:
        # Body may include sensitive details; keep first 200 chars at debug level.
        logger.error("OCR provider HTTP %d", resp.status_code)
        logger.debug("OCR provider body: %s", resp.text[:200])
        raise ValueError(f"OCR provider HTTP {resp.status_code}")

    try:
        payload = resp.json()
    except json.JSONDecodeError:
        payload = resp.text

    text = _extract_text(payload)
    if not text:
        logger.info("OCR provider returned empty text")
    return text


async def parse_receipt_image(
    image_bytes: bytes,
    mime_type: str,
    *,
    db: AsyncSession | None = None,
    user_id: uuid.UUID | None = None,
) -> dict:
    """Extract structured receipt info from an image.

    ``db`` and ``user_id`` are forwarded to ``call_llm`` for cost
    tracking + per-user caching. Callers in the request path (router)
    SHOULD pass both; CLI/tests may omit them.
    """
    ocr_text = await _call_external_ocr(image_bytes, mime_type)
    if not ocr_text.strip():
        return {
            "total_amount": 0,
            "currency": "VND",
            "merchant_name": None,
            "date": None,
            "items": [],
            "note": None,
            "category_suggestion": "other",
            "confidence": "low",
            "error": "not_a_receipt",
        }

    prompt = _STRUCTURE_PROMPT.format(text=ocr_text)
    try:
        response_text = await call_llm(
            prompt,
            task_type="parse_receipt",
            db=db,
            user_id=user_id,
            # Cache per-user: identical receipts re-uploaded shouldn't pay twice.
            use_cache=bool(db and user_id),
        )
    except LLMError as exc:
        # Missing key, upstream timeout/quota — surface as a ValueError so
        # the router's OCR_PROVIDER_ERROR path returns 502 instead of 500.
        # BudgetExceededError is intentionally NOT caught: callers convert
        # it to the user-facing "tạm dừng" message (see CLAUDE.md).
        logger.warning("Receipt structuring LLM failed: %s", exc)
        raise ValueError(f"Receipt parser unavailable: {exc}") from exc

    response_text = _strip_code_fence(response_text)
    try:
        result = json.loads(response_text)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse structuring LLM response: %s", response_text[:300])
        raise ValueError(f"Invalid JSON from receipt parser: {exc}") from exc

    logger.info(
        "OCR parsed: merchant=%s amount=%s confidence=%s error=%s",
        result.get("merchant_name"),
        result.get("total_amount"),
        result.get("confidence"),
        result.get("error"),
    )
    return result
