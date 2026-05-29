"""Phase 4.4 Epic 2 — Screenshot Onboarding (default off).

Covers the ``SCREENSHOT_ONBOARDING_ENABLED`` feature flag on/off
behaviour, the ``parse_balance_screenshot`` two-stage pipeline (external
OCR → DeepSeek structuring, empty-OCR short-circuit, JSON salvage), and
the ``handle_first_asset_screenshot`` routing/consume contract: it
falls through (returns ``False``) when the user isn't on the first-asset
step, and consumes (returns ``True``) any photo while on it — saving a
read balance, nudging on a non-balance, nudging on OCR failure.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.models.onboarding_session import STEP_FIRST_ASSET


# ----- SCREENSHOT_ONBOARDING_ENABLED feature flag -----------------------


def test_screenshot_flag_default_off(monkeypatch):
    from backend.bot.handlers import onboarding_v2

    monkeypatch.delenv("SCREENSHOT_ONBOARDING_ENABLED", raising=False)
    assert onboarding_v2.is_screenshot_onboarding_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "yes", "on", "TRUE", "On"])
def test_screenshot_flag_on(monkeypatch, val):
    from backend.bot.handlers import onboarding_v2

    monkeypatch.setenv("SCREENSHOT_ONBOARDING_ENABLED", val)
    assert onboarding_v2.is_screenshot_onboarding_enabled() is True


@pytest.mark.parametrize("val", ["0", "false", "no", "off", "anything", ""])
def test_screenshot_flag_off(monkeypatch, val):
    from backend.bot.handlers import onboarding_v2

    monkeypatch.setenv("SCREENSHOT_ONBOARDING_ENABLED", val)
    assert onboarding_v2.is_screenshot_onboarding_enabled() is False


# ----- parse_balance_screenshot (two-stage pipeline) --------------------


@pytest.mark.asyncio
async def test_parse_balance_empty_ocr_short_circuits(monkeypatch):
    from backend.services import ocr_service

    async def _empty_ocr(_bytes, _mime):
        return "   \n  "

    called = {"llm": False}

    async def _llm(*_a, **_k):
        called["llm"] = True
        return "{}"

    monkeypatch.setattr(ocr_service, "_call_external_ocr", _empty_ocr)
    monkeypatch.setattr(ocr_service, "call_llm", _llm)

    result = await ocr_service.parse_balance_screenshot(b"img", "image/jpeg")
    assert result["error"] == "not_a_balance"
    assert result["total_balance"] is None
    # No point paying for the LLM when OCR found nothing.
    assert called["llm"] is False


@pytest.mark.asyncio
async def test_parse_balance_structures_ocr_text(monkeypatch):
    from backend.services import ocr_service

    async def _ocr(_bytes, _mime):
        return "Tổng số dư khả dụng 200.000.000 VND"

    captured = {}

    async def _llm(prompt, *, task_type, db, user_id, use_cache):
        captured["task_type"] = task_type
        captured["use_cache"] = use_cache
        return (
            '{"total_balance": 200000000, "currency": "VND",'
            ' "account_label": "Vietcombank", "confidence": "high",'
            ' "error": null}'
        )

    monkeypatch.setattr(ocr_service, "_call_external_ocr", _ocr)
    monkeypatch.setattr(ocr_service, "call_llm", _llm)

    result = await ocr_service.parse_balance_screenshot(b"img", "image/jpeg")
    assert result["total_balance"] == 200000000
    assert result["account_label"] == "Vietcombank"
    assert captured["task_type"] == "parse_balance"
    # No db/user_id passed → cache disabled.
    assert captured["use_cache"] is False


@pytest.mark.asyncio
async def test_parse_balance_enables_cache_with_user(monkeypatch):
    from backend.services import ocr_service

    async def _ocr(_bytes, _mime):
        return "Số dư 50.000.000"

    captured = {}

    async def _llm(prompt, *, task_type, db, user_id, use_cache):
        captured["use_cache"] = use_cache
        return '{"total_balance": 50000000, "error": null}'

    monkeypatch.setattr(ocr_service, "_call_external_ocr", _ocr)
    monkeypatch.setattr(ocr_service, "call_llm", _llm)

    await ocr_service.parse_balance_screenshot(
        b"img", "image/jpeg", db=object(), user_id=uuid.uuid4()
    )
    assert captured["use_cache"] is True


@pytest.mark.asyncio
async def test_parse_balance_invalid_json_raises(monkeypatch):
    from backend.services import ocr_service

    async def _ocr(_bytes, _mime):
        return "Số dư 50.000.000"

    async def _llm(*_a, **_k):
        return "not json at all"

    monkeypatch.setattr(ocr_service, "_call_external_ocr", _ocr)
    monkeypatch.setattr(ocr_service, "call_llm", _llm)

    with pytest.raises(ValueError):
        await ocr_service.parse_balance_screenshot(b"img", "image/jpeg")


# ----- handle_first_asset_screenshot (routing / consume contract) -------


def _user():
    return SimpleNamespace(
        id=uuid.uuid4(),
        wizard_state=None,
        get_greeting_name=lambda: "Minh",
    )


def _photo_message():
    return {
        "chat": {"id": 999},
        "photo": [
            {"file_id": "small", "width": 90, "height": 90},
            {"file_id": "big", "width": 1280, "height": 1280},
        ],
    }


def _stub_common(monkeypatch):
    """Stub Telegram + photo helpers so no network is touched."""
    from backend.bot.handlers import onboarding_v2

    sent = []

    async def _send(chat_id, text, **_k):
        sent.append(text)
        return {"result": {"message_id": 7}}

    async def _edit(*, chat_id, message_id, text, **_k):
        sent.append(text)
        return {"ok": True}

    monkeypatch.setattr(onboarding_v2, "send_message", _send)
    monkeypatch.setattr(onboarding_v2, "edit_message_text", _edit)
    return sent


@pytest.mark.asyncio
async def test_falls_through_when_not_on_first_asset_step(monkeypatch):
    from backend.bot.handlers import onboarding_v2
    from backend.services.onboarding import onboarding_service

    # No active session at the first-asset step → return False so the
    # caller routes the photo to receipt OCR instead.
    async def _no_session(_db, _uid):
        return None

    monkeypatch.setattr(onboarding_service, "get_session", _no_session)

    consumed = await onboarding_v2.handle_first_asset_screenshot(
        object(), _photo_message(), _user()
    )
    assert consumed is False


@pytest.mark.asyncio
async def test_falls_through_on_other_step(monkeypatch):
    from backend.bot.handlers import onboarding_v2
    from backend.services.onboarding import onboarding_service

    async def _session(_db, _uid):
        return SimpleNamespace(current_step="name", inferred_wealth_segment=None)

    monkeypatch.setattr(onboarding_service, "get_session", _session)

    consumed = await onboarding_v2.handle_first_asset_screenshot(
        object(), _photo_message(), _user()
    )
    assert consumed is False


@pytest.mark.asyncio
async def test_not_a_balance_nudges_and_consumes(monkeypatch):
    from backend.bot.handlers import onboarding_v2
    from backend.services import ocr_service
    from backend.services import telegram_service
    from backend.services.onboarding import onboarding_service

    async def _session(_db, _uid):
        return SimpleNamespace(
            current_step=STEP_FIRST_ASSET, inferred_wealth_segment="mass"
        )

    monkeypatch.setattr(onboarding_service, "get_session", _session)
    sent = _stub_common(monkeypatch)

    async def _download(_file_id):
        return b"\xff\xd8imagebytes"

    monkeypatch.setattr(telegram_service, "download_file", _download)

    async def _parse(*_a, **_k):
        return {"total_balance": None, "error": "not_a_balance", "confidence": "low"}

    monkeypatch.setattr(ocr_service, "parse_balance_screenshot", _parse)

    saved = {"called": False}

    async def _save(*_a, **_k):
        saved["called"] = True

    monkeypatch.setattr(onboarding_v2, "_save_onboarding_first_asset", _save)

    consumed = await onboarding_v2.handle_first_asset_screenshot(
        object(), _photo_message(), _user()
    )
    assert consumed is True
    assert saved["called"] is False
    # The not-a-balance nudge copy was shown.
    assert any("tổng tài sản" in t.lower() for t in sent)


@pytest.mark.asyncio
async def test_balance_read_saves_asset(monkeypatch):
    from backend.bot.handlers import onboarding_v2
    from backend.services import ocr_service
    from backend.services import telegram_service
    from backend.services.onboarding import (
        data_quality_service,
        onboarding_service,
    )

    async def _session(_db, _uid):
        return SimpleNamespace(
            current_step=STEP_FIRST_ASSET, inferred_wealth_segment="mass"
        )

    monkeypatch.setattr(onboarding_service, "get_session", _session)
    _stub_common(monkeypatch)

    async def _download(_file_id):
        return b"\xff\xd8imagebytes"

    monkeypatch.setattr(telegram_service, "download_file", _download)

    async def _parse(*_a, **_k):
        return {
            "total_balance": 200000000,
            "currency": "VND",
            "account_label": "Vietcombank",
            "confidence": "high",
            "error": None,
        }

    monkeypatch.setattr(ocr_service, "parse_balance_screenshot", _parse)

    # No data-quality warning → straight to save.
    async def _no_warning(*_a, **_k):
        return None

    monkeypatch.setattr(data_quality_service, "first_warning", _no_warning)

    saved = {}

    async def _save(_db, _chat, _user, value, *, raw_text, warning_type, demo):
        saved["value"] = value
        saved["raw_text"] = raw_text
        saved["demo"] = demo

    monkeypatch.setattr(onboarding_v2, "_save_onboarding_first_asset", _save)

    consumed = await onboarding_v2.handle_first_asset_screenshot(
        object(), _photo_message(), _user()
    )
    assert consumed is True
    assert saved["value"] == Decimal("200000000")
    assert saved["demo"] is False
    assert "screenshot" in saved["raw_text"]


@pytest.mark.asyncio
async def test_ocr_failure_nudges_to_type(monkeypatch):
    from backend.bot.handlers import onboarding_v2
    from backend.services import ocr_service
    from backend.services import telegram_service
    from backend.services.onboarding import onboarding_service

    async def _session(_db, _uid):
        return SimpleNamespace(
            current_step=STEP_FIRST_ASSET, inferred_wealth_segment="mass"
        )

    monkeypatch.setattr(onboarding_service, "get_session", _session)
    sent = _stub_common(monkeypatch)

    async def _download(_file_id):
        return b"\xff\xd8imagebytes"

    monkeypatch.setattr(telegram_service, "download_file", _download)

    async def _parse(*_a, **_k):
        raise ValueError("Balance parser unavailable")

    monkeypatch.setattr(ocr_service, "parse_balance_screenshot", _parse)

    consumed = await onboarding_v2.handle_first_asset_screenshot(
        object(), _photo_message(), _user()
    )
    # Consumed (not routed to receipt OCR) but no save; user nudged to type.
    assert consumed is True
    assert any("gõ" in t.lower() for t in sent)
