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
async def test_handle_photo_happy_path_edits_ack_with_result():
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
    with patch.object(photo_receipt, "send_message", send), \
         patch.object(photo_receipt, "edit_message_text", edit), \
         patch.object(photo_receipt, "send_chat_action", AsyncMock()), \
         patch.object(photo_receipt, "download_file", AsyncMock(return_value=b"img")), \
         patch.object(photo_receipt, "parse_receipt_image",
                       AsyncMock(return_value=parsed)) as ocr:
        ok = await photo_receipt.handle_photo_message(MagicMock(), msg, user)

    assert ok is True
    # OCR called with the *medium* photo, not the smallest.
    ocr.assert_awaited_once()
    edit.assert_awaited()
    final_text = edit.await_args.kwargs["text"]
    assert "Co.op Mart" in final_text
    assert "250k" in final_text


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
