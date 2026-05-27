"""Tests for backend.services.ocr_service structuring/salvage path.

The two-stage OCR pipeline was rejecting valid receipts in production:
the external OCR provider extracted the text fine, but DeepSeek V4-Flash
truncated its JSON answer at the token cap (cut right after ``"date"``),
so ``json.loads`` raised and the bot showed "đọc chưa được". These tests
cover the salvage that recovers the fields we *did* receive, plus the
end-to-end ``parse_receipt_image`` behaviour with a truncated response.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.services.ocr_service import (
    _loads_receipt_json,
    _repair_truncated_json,
    parse_receipt_image,
)

# The exact production failure: response cut off mid-object after "date".
TRUNCATED_RESPONSE = (
    '{\n'
    ' "total_amount": 4600000,\n'
    ' "currency": "VND",\n'
    ' "merchant_name": "NGUYEN THI THUY",\n'
    ' "date": "2026-04-22",\n'
)


def test_repair_closes_object_truncated_after_field():
    repaired = _repair_truncated_json(TRUNCATED_RESPONSE)
    parsed = json.loads(repaired)
    assert parsed["total_amount"] == 4600000
    assert parsed["merchant_name"] == "NGUYEN THI THUY"
    assert parsed["date"] == "2026-04-22"
    # The trailing partial field is dropped, not invented.
    assert "items" not in parsed


def test_repair_truncated_inside_items_array():
    truncated = (
        '{"total_amount": 50000, "items": ['
        '{"name": "Cà phê", "price": 30000}, '
        '{"name": "Bánh"'
    )
    parsed = json.loads(_repair_truncated_json(truncated))
    assert parsed["total_amount"] == 50000
    # Completed element survives; the half-written one is dropped.
    assert parsed["items"] == [{"name": "Cà phê", "price": 30000}]


def test_repair_handles_comma_inside_string():
    # A comma inside a quoted value must not be treated as a field boundary.
    truncated = '{"note": "Chuyen tien, ho tro", "total_amount": 800000,'
    parsed = json.loads(_repair_truncated_json(truncated))
    assert parsed["note"] == "Chuyen tien, ho tro"
    assert parsed["total_amount"] == 800000


def test_loads_receipt_json_prefers_strict_parse():
    valid = '{"total_amount": 100, "currency": "VND"}'
    assert _loads_receipt_json(valid) == {"total_amount": 100, "currency": "VND"}


def test_loads_receipt_json_returns_none_for_garbage():
    assert _loads_receipt_json("not json at all") is None


@pytest.mark.asyncio
async def test_parse_receipt_recovers_from_truncated_llm_response():
    """A truncated structuring response must still yield a usable receipt."""
    with patch(
        "backend.services.ocr_service._call_external_ocr",
        new=AsyncMock(return_value="Chuyen thanh cong\nVND 4,600,000\nNGUYEN THI THUY"),
    ), patch(
        "backend.services.ocr_service.call_llm",
        new=AsyncMock(return_value=TRUNCATED_RESPONSE),
    ):
        result = await parse_receipt_image(b"\xff\xd8fakejpeg", "image/jpeg")

    assert result["total_amount"] == 4600000
    assert result["merchant_name"] == "NGUYEN THI THUY"
    assert result.get("error") != "not_a_receipt"
