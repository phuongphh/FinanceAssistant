"""Tests for photo → receipt OCR handler (Issue #603)."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.bot.handlers import photo_receipt


def _user():
    u = MagicMock()
    u.id = uuid.uuid4()
    return u


def _photo_message(photos=None, document=None):
    msg: dict = {"chat": {"id": 999}, "from": {"id": 42}}
    if photos is not None:
        msg["photo"] = photos
    if document is not None:
        msg["document"] = document
    return msg


def test_select_photo_prefers_largest_under_budget():
    photos = [
        {"file_id": "a", "width": 90, "height": 90},
        {"file_id": "b", "width": 800, "height": 600},
        {"file_id": "c", "width": 1280, "height": 960},
        {"file_id": "d", "width": 2400, "height": 1800},
    ]
    chosen = photo_receipt._select_photo(photos)
    # 1280 is the largest size with longest-edge <= 1600 px.
    assert chosen["file_id"] == "c"


def test_select_photo_falls_back_to_smallest_if_all_oversize():
    photos = [
        {"file_id": "big1", "width": 2000, "height": 1500},
        {"file_id": "big2", "width": 3000, "height": 2200},
    ]
    chosen = photo_receipt._select_photo(photos)
    assert chosen["file_id"] == "big1"


def test_select_photo_returns_none_for_empty():
    assert photo_receipt._select_photo([]) is None


def test_format_receipt_renders_total_and_items():
    out = photo_receipt._format_receipt({
        "total_amount": 150000,
        "currency": "VND",
        "merchant_name": "Highlands Coffee",
        "date": "2026-05-13",
        "items": [{"name": "Cà phê sữa", "price": 45000}],
        "confidence": "high",
    })
    assert "Highlands Coffee" in out
    assert "150k" in out
    assert "Cà phê sữa" in out
    assert "⚠️" not in out  # high confidence => no warning


def test_format_receipt_renders_date_in_dd_mm_yyyy():
    out = photo_receipt._format_receipt({
        "total_amount": 100000,
        "currency": "VND",
        "merchant_name": "Shop",
        "date": "2026-04-22",
        "items": [],
        "confidence": "high",
    })
    assert "22/04/2026" in out
    # Raw ISO date must NOT leak through to the user.
    assert "2026-04-22" not in out


def test_parse_iso_date_rejects_garbage_and_future():
    from datetime import date, timedelta

    assert photo_receipt._parse_iso_date(None) is None
    assert photo_receipt._parse_iso_date("not a date") is None
    assert photo_receipt._parse_iso_date("2026-13-40") is None
    future = (date.today() + timedelta(days=30)).isoformat()
    assert photo_receipt._parse_iso_date(future) is None
    assert photo_receipt._parse_iso_date("2026-04-22").isoformat() == "2026-04-22"


def test_resolve_ocr_category_falls_back_to_needs_review():
    assert photo_receipt._resolve_ocr_category("food_drink") == "food_drink"
    assert photo_receipt._resolve_ocr_category("unknown_xyz") == "needs_review"
    assert photo_receipt._resolve_ocr_category(None) == "needs_review"


def test_format_receipt_low_confidence_adds_warning():
    out = photo_receipt._format_receipt({
        "total_amount": 1000,
        "currency": "VND",
        "merchant_name": None,
        "items": [],
        "confidence": "low",
    })
    assert "⚠️" in out


@pytest.mark.asyncio
async def test_handle_photo_returns_false_when_no_image():
    msg = {"chat": {"id": 1}, "from": {"id": 2}, "text": "hello"}
    assert await photo_receipt.handle_photo_message(MagicMock(), msg, _user()) is False


@pytest.mark.asyncio
async def test_handle_photo_happy_path_shows_two_button_confirm():

    user = _user()
    msg = _photo_message(photos=[
        {"file_id": "small", "width": 90, "height": 90},
        {"file_id": "good", "width": 1280, "height": 960},
    ])
    parsed = {
        "total_amount": 250000,
        "currency": "VND",
        "merchant_name": "Co.op Mart",
        "date": "2026-05-13",
        "items": [{"name": "Sữa", "price": 50000}],
        "category_suggestion": "food_drink",
        "confidence": "high",
        "error": None,
    }
    send = AsyncMock(return_value={"result": {"message_id": 77}})
    edit = AsyncMock()
    create = AsyncMock()
    with patch.object(photo_receipt, "send_message", send), \
         patch.object(photo_receipt, "edit_message_text", edit), \
         patch.object(photo_receipt, "send_chat_action", AsyncMock()), \
         patch.object(photo_receipt, "download_file", AsyncMock(return_value=b"img")), \
         patch.object(photo_receipt.expense_service, "create_expense", create), \
         patch.object(photo_receipt, "parse_receipt_image",
                       AsyncMock(return_value=parsed)) as ocr:
        ok = await photo_receipt.handle_photo_message(MagicMock(), msg, user)

    assert ok is True
    ocr.assert_awaited_once()
    create.assert_not_awaited()
    # Confirmation rendered with dd/mm/yyyy date and an inline keyboard.
    edit.assert_awaited()
    final_text = edit.await_args.kwargs["text"]
    assert "Co.op Mart" in final_text
    assert "13/05/2026" in final_text
    assert "2026-05-13" not in final_text
    keyboard = edit.await_args.kwargs["reply_markup"]
    assert keyboard and keyboard["inline_keyboard"]
    # OCR flow now has only two actions: Đồng ý / Huỷ.
    flat_buttons = [b for row in keyboard["inline_keyboard"] for b in row]
    assert [b["text"] for b in flat_buttons] == ["✅ Đồng ý", "❌ Huỷ"]


@pytest.mark.asyncio
async def test_handle_photo_zero_total_skips_autosave():
    user = _user()
    msg = _photo_message(photos=[{"file_id": "good", "width": 1280, "height": 960}])
    parsed = {
        "total_amount": 0,
        "currency": "VND",
        "merchant_name": "Shop",
        "date": "2026-04-22",
        "items": [],
        "confidence": "low",
        "error": None,
    }
    create = AsyncMock()
    with patch.object(photo_receipt, "send_message",
                       AsyncMock(return_value={"result": {"message_id": 1}})), \
         patch.object(photo_receipt, "edit_message_text", AsyncMock()) as edit, \
         patch.object(photo_receipt, "send_chat_action", AsyncMock()), \
         patch.object(photo_receipt, "download_file", AsyncMock(return_value=b"img")), \
         patch.object(photo_receipt.expense_service, "create_expense", create), \
         patch.object(photo_receipt, "parse_receipt_image",
                       AsyncMock(return_value=parsed)):
        ok = await photo_receipt.handle_photo_message(MagicMock(), msg, user)

    assert ok is True
    create.assert_not_awaited()
    # User is nudged to type the amount manually instead of a silent failure.
    final_text = edit.await_args.kwargs["text"]
    assert "gõ tay" in final_text or "150k" in final_text
    # Date is still rendered in dd/mm/yyyy in the fallback view.
    assert "22/04/2026" in final_text


@pytest.mark.asyncio
async def test_handle_photo_not_a_receipt_friendly_message():
    user = _user()
    msg = _photo_message(photos=[{"file_id": "x", "width": 1280, "height": 960}])
    with patch.object(photo_receipt, "send_message",
                       AsyncMock(return_value={"result": {"message_id": 1}})), \
         patch.object(photo_receipt, "edit_message_text", AsyncMock()) as edit, \
         patch.object(photo_receipt, "send_chat_action", AsyncMock()), \
         patch.object(photo_receipt, "download_file", AsyncMock(return_value=b"img")), \
         patch.object(photo_receipt, "parse_receipt_image",
                       AsyncMock(return_value={"error": "not_a_receipt"})):
        ok = await photo_receipt.handle_photo_message(MagicMock(), msg, user)

    assert ok is True
    assert "không thấy đây là hoá đơn" in edit.await_args.kwargs["text"]


@pytest.mark.asyncio
async def test_handle_photo_ocr_error_replies_friendly():
    user = _user()
    msg = _photo_message(photos=[{"file_id": "x", "width": 1280, "height": 960}])
    with patch.object(photo_receipt, "send_message",
                       AsyncMock(return_value={"result": {"message_id": 1}})), \
         patch.object(photo_receipt, "edit_message_text", AsyncMock()) as edit, \
         patch.object(photo_receipt, "send_chat_action", AsyncMock()), \
         patch.object(photo_receipt, "download_file", AsyncMock(return_value=b"img")), \
         patch.object(photo_receipt, "parse_receipt_image",
                       AsyncMock(side_effect=ValueError("upstream 500"))):
        ok = await photo_receipt.handle_photo_message(MagicMock(), msg, user)

    assert ok is True
    assert "đọc chưa được" in edit.await_args.kwargs["text"]


@pytest.mark.asyncio
async def test_handle_photo_download_failure():
    user = _user()
    msg = _photo_message(photos=[{"file_id": "x", "width": 1280, "height": 960}])
    with patch.object(photo_receipt, "send_message",
                       AsyncMock(return_value={"result": {"message_id": 1}})), \
         patch.object(photo_receipt, "edit_message_text", AsyncMock()) as edit, \
         patch.object(photo_receipt, "send_chat_action", AsyncMock()), \
         patch.object(photo_receipt, "download_file", AsyncMock(return_value=None)), \
         patch.object(photo_receipt, "parse_receipt_image", AsyncMock()) as ocr:
        ok = await photo_receipt.handle_photo_message(MagicMock(), msg, user)

    assert ok is True
    ocr.assert_not_awaited()
    assert "không tải được ảnh" in edit.await_args.kwargs["text"]


@pytest.mark.asyncio
async def test_handle_photo_accepts_image_document():
    user = _user()
    msg = _photo_message(document={
        "file_id": "doc1",
        "mime_type": "image/png",
        "file_size": 12345,
    })
    parsed = {
        "total_amount": 50000,
        "currency": "VND",
        "merchant_name": "Shop",
        "items": [],
        "confidence": "medium",
        "error": None,
    }
    with patch.object(photo_receipt, "send_message",
                       AsyncMock(return_value={"result": {"message_id": 1}})), \
         patch.object(photo_receipt, "edit_message_text", AsyncMock()), \
         patch.object(photo_receipt, "send_chat_action", AsyncMock()), \
         patch.object(photo_receipt, "download_file", AsyncMock(return_value=b"img")), \
         patch.object(photo_receipt, "parse_receipt_image",
                       AsyncMock(return_value=parsed)) as ocr:
        ok = await photo_receipt.handle_photo_message(MagicMock(), msg, user)

    assert ok is True
    # Document path forwards the declared mime_type to the OCR service.
    call_kwargs = ocr.await_args
    assert call_kwargs.args[1] == "image/png"
