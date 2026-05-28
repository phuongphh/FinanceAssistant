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
async def test_handle_photo_happy_path_shows_category_grid_and_confirm():

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
    # Nothing is persisted until the user taps Đồng ý.
    create.assert_not_awaited()
    # Confirmation rendered with dd/mm/yyyy date and an inline keyboard.
    edit.assert_awaited()
    final_text = edit.await_args.kwargs["text"]
    assert "Co.op Mart" in final_text
    assert "13/05/2026" in final_text
    assert "2026-05-13" not in final_text
    keyboard = edit.await_args.kwargs["reply_markup"]
    assert keyboard and keyboard["inline_keyboard"]
    flat_buttons = [b for row in keyboard["inline_keyboard"] for b in row]
    button_texts = [b["text"] for b in flat_buttons]
    # The picker now prepends a category grid before the confirm/cancel row.
    assert "✅ Đồng ý" in button_texts
    assert "❌ Huỷ" in button_texts
    assert len(button_texts) > 2
    # A confident OCR category (food_drink → food/Ăn uống) is pre-ticked.
    assert any(t.startswith("✓ ") for t in button_texts)
    # The confirm/cancel pair is the final row, kept together.
    assert [b["text"] for b in keyboard["inline_keyboard"][-1]] == [
        "✅ Đồng ý",
        "❌ Huỷ",
    ]


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
async def test_confirm_pending_receipt_success_creates_expense():
    user = _user()
    token = "tok_ok"
    photo_receipt._pending_receipt_confirms[token] = {
        "created_at": 100.0,
        "user_id": str(user.id),
        "amount": 4600000.0,
        "currency": "VND",
        "merchant": "Techcombank",
        "category": "needs_review",
        "expense_date": "2026-04-22",
        "note": "Link power",
        "confidence": "high",
        "items": [{"name": "Link power", "price": 4600000}],
        "category_suggestion": "needs_review",
    }
    create = AsyncMock()
    with patch.object(photo_receipt, "time") as t, \
         patch.object(photo_receipt, "apply_default_source",
                       AsyncMock(side_effect=lambda _db, _u, d: d)), \
         patch.object(photo_receipt.expense_service, "create_expense", create):
        t.monotonic.return_value = 101.0
        ok = await photo_receipt.confirm_pending_receipt(
            db=MagicMock(), user=user, token=token
        )
    assert ok is True
    create.assert_awaited_once()


@pytest.mark.asyncio
async def test_confirm_pending_receipt_applies_default_source():
    """OCR confirm path must honour the user's default_expense_source."""
    user = _user()
    token = "tok_default_src"
    photo_receipt._pending_receipt_confirms[token] = {
        "created_at": 100.0,
        "user_id": str(user.id),
        "amount": 50000.0,
        "currency": "VND",
        "merchant": "Phở",
        "category": "food",
        "expense_date": "2026-05-28",
    }

    async def _stamp(_db, _uid, data):
        data.source = "cash"
        return data

    create = AsyncMock()
    with patch.object(photo_receipt, "time") as t, \
         patch.object(photo_receipt, "apply_default_source",
                       AsyncMock(side_effect=_stamp)) as apply_src, \
         patch.object(photo_receipt.expense_service, "create_expense", create):
        t.monotonic.return_value = 101.0
        ok = await photo_receipt.confirm_pending_receipt(
            db=MagicMock(), user=user, token=token
        )
    assert ok is True
    apply_src.assert_awaited_once()
    create.assert_awaited_once()
    passed = create.await_args.args[2]
    assert passed.source == "cash"


@pytest.mark.asyncio
async def test_confirm_pending_receipt_rejects_expired_token():
    user = _user()
    token = "tok_expired"
    photo_receipt._pending_receipt_confirms[token] = {
        "created_at": 10.0,
        "user_id": str(user.id),
        "amount": 1000.0,
        "currency": "VND",
        "category": "needs_review",
        "expense_date": "2026-04-22",
    }
    create = AsyncMock()
    with patch.object(photo_receipt, "time") as t, \
         patch.object(photo_receipt.expense_service, "create_expense", create):
        t.monotonic.return_value = 999.0
        ok = await photo_receipt.confirm_pending_receipt(
            db=MagicMock(), user=user, token=token
        )
    assert ok is False
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_confirm_pending_receipt_rejects_wrong_user():
    user = _user()
    other = _user()
    token = "tok_wrong_user"
    photo_receipt._pending_receipt_confirms[token] = {
        "created_at": 100.0,
        "user_id": str(other.id),
        "amount": 1000.0,
        "currency": "VND",
        "category": "needs_review",
        "expense_date": "2026-04-22",
    }
    create = AsyncMock()
    with patch.object(photo_receipt, "time") as t, \
         patch.object(photo_receipt.expense_service, "create_expense", create):
        t.monotonic.return_value = 101.0
        ok = await photo_receipt.confirm_pending_receipt(
            db=MagicMock(), user=user, token=token
        )
    assert ok is False
    create.assert_not_awaited()


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


# ---------------------------------------------------------------------------
# Task 1 — transaction note ("Lời nhắn" / "Nội dung chuyển khoản") extraction
# ---------------------------------------------------------------------------


def test_clean_note_collapses_whitespace():
    assert photo_receipt._clean_note("  Link  power\nchuyển   tiền ") == (
        "Link power chuyển tiền"
    )


def test_clean_note_returns_none_for_empty_or_non_string():
    assert photo_receipt._clean_note("") is None
    assert photo_receipt._clean_note("   \n\t ") is None
    assert photo_receipt._clean_note(None) is None
    assert photo_receipt._clean_note(12345) is None


def test_clean_note_bounds_length():
    long = "x" * (photo_receipt._MAX_NOTE_LEN + 50)
    out = photo_receipt._clean_note(long)
    assert out is not None
    assert out.endswith("…")
    # The ellipsis replaces the overflow, so the body stays within the cap.
    assert len(out) <= photo_receipt._MAX_NOTE_LEN + 1


def test_item_name_preview_joins_first_three_with_overflow():
    items = [
        {"name": "Cà phê"},
        {"name": "Bánh mì"},
        {"name": "Trà"},
        {"name": "Nước"},
        {"name": "Kẹo"},
    ]
    assert photo_receipt._item_name_preview(items) == "Cà phê, Bánh mì, Trà +2"


def test_item_name_preview_none_when_no_named_items():
    assert photo_receipt._item_name_preview([]) is None
    assert photo_receipt._item_name_preview([{"price": 1000}]) is None
    assert photo_receipt._item_name_preview([{"name": "   "}]) is None


@pytest.mark.asyncio
async def test_autosave_prefers_ocr_note_over_item_preview():
    """A transfer memo must survive into the pending payload and the message."""
    user = _user()
    msg = _photo_message(photos=[{"file_id": "good", "width": 1280, "height": 960}])
    parsed = {
        "total_amount": 2700000,
        "currency": "VND",
        "merchant_name": "NGUYEN THI THUY",
        "date": "2026-04-22",
        "items": [{"name": "Chuyển khoản", "price": 2700000}],
        "category_suggestion": None,
        "note": "Link power chuyển tiền so do thua dat 841",
        "confidence": "high",
        "error": None,
    }
    photo_receipt._pending_receipt_confirms.clear()
    with patch.object(photo_receipt, "send_message",
                       AsyncMock(return_value={"result": {"message_id": 5}})), \
         patch.object(photo_receipt, "edit_message_text", AsyncMock()) as edit, \
         patch.object(photo_receipt, "send_chat_action", AsyncMock()), \
         patch.object(photo_receipt, "download_file", AsyncMock(return_value=b"img")), \
         patch.object(photo_receipt.expense_service, "create_expense", AsyncMock()), \
         patch.object(photo_receipt, "parse_receipt_image",
                       AsyncMock(return_value=parsed)):
        ok = await photo_receipt.handle_photo_message(MagicMock(), msg, user)

    assert ok is True
    # The OCR memo (not the item name) is echoed back to the user...
    final_text = edit.await_args.kwargs["text"]
    assert "Link power chuyển tiền so do thua dat 841" in final_text
    # ...and stored verbatim on the pending payload for the eventual save.
    (payload,) = photo_receipt._pending_receipt_confirms.values()
    assert payload["note"] == "Link power chuyển tiền so do thua dat 841"
    photo_receipt._pending_receipt_confirms.clear()


@pytest.mark.asyncio
async def test_autosave_falls_back_to_item_preview_without_note():
    user = _user()
    msg = _photo_message(photos=[{"file_id": "good", "width": 1280, "height": 960}])
    parsed = {
        "total_amount": 95000,
        "currency": "VND",
        "merchant_name": "Highlands",
        "date": "2026-05-13",
        "items": [{"name": "Cà phê"}, {"name": "Bánh"}],
        "category_suggestion": "food_drink",
        "note": None,
        "confidence": "high",
        "error": None,
    }
    photo_receipt._pending_receipt_confirms.clear()
    with patch.object(photo_receipt, "send_message",
                       AsyncMock(return_value={"result": {"message_id": 5}})), \
         patch.object(photo_receipt, "edit_message_text", AsyncMock()), \
         patch.object(photo_receipt, "send_chat_action", AsyncMock()), \
         patch.object(photo_receipt, "download_file", AsyncMock(return_value=b"img")), \
         patch.object(photo_receipt.expense_service, "create_expense", AsyncMock()), \
         patch.object(photo_receipt, "parse_receipt_image",
                       AsyncMock(return_value=parsed)):
        await photo_receipt.handle_photo_message(MagicMock(), msg, user)

    (payload,) = photo_receipt._pending_receipt_confirms.values()
    assert payload["note"] == "Cà phê, Bánh"
    photo_receipt._pending_receipt_confirms.clear()


# ---------------------------------------------------------------------------
# Task 2 — inline category picker before confirm
# ---------------------------------------------------------------------------


def test_render_receipt_confirmation_uncertain_invites_pick():
    payload = {
        "user_id": "u1",
        "amount": 2700000.0,
        "currency": "VND",
        "merchant": "NGUYEN THI THUY",
        "category": "needs_review",
        "expense_date": "2026-04-22",
        "note": "Link power",
        "confidence": "high",
        "items": [],
    }
    text, keyboard = photo_receipt._render_receipt_confirmation(payload, "tok")
    # Invitation copy, not a concrete (possibly wrong) "Khác" label.
    assert "bạn chọn" in text
    button_texts = [
        b["text"] for row in keyboard["inline_keyboard"] for b in row
    ]
    # Nothing pre-ticked while the category is still uncertain.
    assert not any(t.startswith("✓ ") for t in button_texts)
    assert [b["text"] for b in keyboard["inline_keyboard"][-1]] == [
        "✅ Đồng ý",
        "❌ Huỷ",
    ]


def test_render_receipt_confirmation_confident_ticks_category():
    payload = {
        "user_id": "u1",
        "amount": 95000.0,
        "currency": "VND",
        "merchant": "Highlands",
        "category": "food",
        "expense_date": "2026-05-13",
        "note": None,
        "confidence": "high",
        "items": [],
    }
    text, keyboard = photo_receipt._render_receipt_confirmation(payload, "tok")
    assert "Ăn uống" in text
    button_texts = [
        b["text"] for row in keyboard["inline_keyboard"] for b in row
    ]
    ticked = [t for t in button_texts if t.startswith("✓ ")]
    assert len(ticked) == 1
    assert "Ăn uống" in ticked[0]


def test_set_pending_receipt_category_records_valid_pick():
    user = _user()
    token = "tok_pick"
    photo_receipt._pending_receipt_confirms[token] = {
        "created_at": 100.0,
        "user_id": str(user.id),
        "amount": 2700000.0,
        "currency": "VND",
        "merchant": "NGUYEN THI THUY",
        "category": "needs_review",
        "expense_date": "2026-04-22",
        "note": "Link power",
        "confidence": "high",
        "items": [],
    }
    with patch.object(photo_receipt, "time") as t:
        t.monotonic.return_value = 150.0
        rendered = photo_receipt.set_pending_receipt_category(
            token=token, user=user, category="transfer"
        )

    assert rendered is not None
    text, keyboard = rendered
    # Pick is persisted on the payload and the TTL is refreshed.
    payload = photo_receipt._pending_receipt_confirms[token]
    assert payload["category"] == "transfer"
    assert payload["created_at"] == 150.0
    # The chosen category is now ticked in the re-rendered keyboard.
    ticked = [
        b["text"]
        for row in keyboard["inline_keyboard"]
        for b in row
        if b["text"].startswith("✓ ")
    ]
    assert len(ticked) == 1
    assert "Chuyển khoản" in ticked[0]
    del photo_receipt._pending_receipt_confirms[token]


def test_set_pending_receipt_category_rejects_wrong_user():
    user = _user()
    other = _user()
    token = "tok_owner"
    photo_receipt._pending_receipt_confirms[token] = {
        "created_at": 100.0,
        "user_id": str(other.id),
        "amount": 1000.0,
        "currency": "VND",
        "category": "needs_review",
        "expense_date": "2026-04-22",
    }
    with patch.object(photo_receipt, "time") as t:
        t.monotonic.return_value = 101.0
        assert photo_receipt.set_pending_receipt_category(
            token=token, user=user, category="food"
        ) is None
    del photo_receipt._pending_receipt_confirms[token]


def test_set_pending_receipt_category_rejects_expired():
    user = _user()
    token = "tok_old"
    photo_receipt._pending_receipt_confirms[token] = {
        "created_at": 10.0,
        "user_id": str(user.id),
        "amount": 1000.0,
        "currency": "VND",
        "category": "needs_review",
        "expense_date": "2026-04-22",
    }
    with patch.object(photo_receipt, "time") as t:
        t.monotonic.return_value = 10.0 + photo_receipt._PENDING_RECEIPT_TTL_S + 1
        assert photo_receipt.set_pending_receipt_category(
            token=token, user=user, category="food"
        ) is None
    del photo_receipt._pending_receipt_confirms[token]


def test_set_pending_receipt_category_rejects_invalid_code():
    """A spoofed callback carrying an unknown code must be ignored."""
    user = _user()
    token = "tok_bad_code"
    photo_receipt._pending_receipt_confirms[token] = {
        "created_at": 100.0,
        "user_id": str(user.id),
        "amount": 1000.0,
        "currency": "VND",
        "category": "needs_review",
        "expense_date": "2026-04-22",
    }
    with patch.object(photo_receipt, "time") as t:
        t.monotonic.return_value = 101.0
        assert photo_receipt.set_pending_receipt_category(
            token=token, user=user, category="not_a_real_category"
        ) is None
    # Payload is left untouched on rejection.
    assert photo_receipt._pending_receipt_confirms[token]["category"] == "needs_review"
    del photo_receipt._pending_receipt_confirms[token]


def test_set_pending_receipt_category_unknown_token_returns_none():
    user = _user()
    assert photo_receipt.set_pending_receipt_category(
        token="nope", user=user, category="food"
    ) is None


@pytest.mark.asyncio
async def test_confirm_pending_receipt_persists_picked_category():
    """A user-picked display category is the one written to the expense."""
    user = _user()
    token = "tok_picked"
    photo_receipt._pending_receipt_confirms[token] = {
        "created_at": 100.0,
        "user_id": str(user.id),
        "amount": 2700000.0,
        "currency": "VND",
        "merchant": "NGUYEN THI THUY",
        "category": "transfer",
        "expense_date": "2026-04-22",
        "note": "Link power chuyển tiền",
        "confidence": "high",
        "items": [],
        "category_suggestion": None,
    }
    create = AsyncMock()
    with patch.object(photo_receipt, "time") as t, \
         patch.object(photo_receipt, "apply_default_source",
                       AsyncMock(side_effect=lambda _db, _u, d: d)), \
         patch.object(photo_receipt.expense_service, "create_expense", create):
        t.monotonic.return_value = 101.0
        ok = await photo_receipt.confirm_pending_receipt(
            db=MagicMock(), user=user, token=token
        )

    assert ok is True
    create.assert_awaited_once()
    expense_create = create.await_args.args[2]
    assert expense_create.category == "transfer"
    assert expense_create.note == "Link power chuyển tiền"


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
