"""Phase 4B Epic 4 — Zalo Adapter Foundation tests (S21–S24).

Tests are unit-only (no DB / no httpx). DB-touching paths use the
``FakeDB`` pattern established in ``test_epic1.py``; HTTP paths use
:class:`httpx.MockTransport` so we never hit the network.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest


# ---------------------------------------------------------------------------
# S21 — ZaloOAClient retry & fail-open
# ---------------------------------------------------------------------------


class _Counter:
    """Track invocations for the mocked transport."""

    def __init__(self):
        self.count = 0


def _make_client_with_responses(responses: list[httpx.Response]):
    """Build a ZaloOAClient whose POSTs are served by ``responses``
    (FIFO). Replaces the module-level singleton getter."""
    from backend.adapters import zalo_oa

    counter = _Counter()

    def handler(request: httpx.Request) -> httpx.Response:
        idx = min(counter.count, len(responses) - 1)
        counter.count += 1
        return responses[idx]

    transport = httpx.MockTransport(handler)
    mock_client = httpx.AsyncClient(transport=transport)

    async def _fake_get_client():
        return mock_client

    return zalo_oa, mock_client, counter, _fake_get_client


@pytest.mark.asyncio
async def test_zalo_oa_send_message_returns_true_on_200(monkeypatch):
    zalo_oa, _client, counter, fake = _make_client_with_responses(
        [httpx.Response(200, json={"error": 0, "message": "Success"})]
    )
    monkeypatch.setattr(zalo_oa, "_get_client", fake)
    # Make backoff a no-op so the test runs fast.
    monkeypatch.setattr(zalo_oa.asyncio, "sleep", AsyncMock())

    client = zalo_oa.ZaloOAClient(access_token="test-token")
    ok = await client.send_message("zalo-user-1", "hello")
    assert ok is True
    assert counter.count == 1


@pytest.mark.asyncio
async def test_zalo_oa_returns_false_when_token_missing(monkeypatch):
    from backend.adapters import zalo_oa

    client = zalo_oa.ZaloOAClient(access_token="")
    ok = await client.send_message("zalo-user-1", "hello")
    assert ok is False


@pytest.mark.asyncio
async def test_zalo_oa_returns_false_when_recipient_empty(monkeypatch):
    from backend.adapters import zalo_oa

    client = zalo_oa.ZaloOAClient(access_token="t")
    assert await client.send_message("", "hi") is False
    assert await client.send_message("u", "") is False


@pytest.mark.asyncio
async def test_zalo_oa_retries_on_429_then_succeeds(monkeypatch):
    zalo_oa, _client, counter, fake = _make_client_with_responses(
        [
            httpx.Response(429, json={"error": "rate_limited"}),
            httpx.Response(429, json={"error": "rate_limited"}),
            httpx.Response(200, json={"error": 0, "message": "ok"}),
        ]
    )
    monkeypatch.setattr(zalo_oa, "_get_client", fake)
    monkeypatch.setattr(zalo_oa.asyncio, "sleep", AsyncMock())

    client = zalo_oa.ZaloOAClient(access_token="t")
    ok = await client.send_message("u", "hi")
    assert ok is True
    assert counter.count == 3


@pytest.mark.asyncio
async def test_zalo_oa_gives_up_after_3_retries(monkeypatch):
    zalo_oa, _client, counter, fake = _make_client_with_responses(
        [httpx.Response(429, json={"error": "rate"})] * 4
    )
    monkeypatch.setattr(zalo_oa, "_get_client", fake)
    monkeypatch.setattr(zalo_oa.asyncio, "sleep", AsyncMock())

    client = zalo_oa.ZaloOAClient(access_token="t")
    ok = await client.send_message("u", "hi")
    assert ok is False
    # 1 initial + 3 retries
    assert counter.count == 4


@pytest.mark.asyncio
async def test_zalo_oa_returns_false_on_500_no_retry(monkeypatch):
    zalo_oa, _client, counter, fake = _make_client_with_responses(
        [httpx.Response(500, text="boom")]
    )
    monkeypatch.setattr(zalo_oa, "_get_client", fake)
    monkeypatch.setattr(zalo_oa.asyncio, "sleep", AsyncMock())

    client = zalo_oa.ZaloOAClient(access_token="t")
    ok = await client.send_message("u", "hi")
    assert ok is False
    # No retry on 500
    assert counter.count == 1


@pytest.mark.asyncio
async def test_zalo_oa_fail_open_on_network_error(monkeypatch):
    from backend.adapters import zalo_oa

    async def boom():
        raise httpx.ConnectError("nope")

    class _BoomClient:
        async def post(self, *args, **kwargs):
            raise httpx.ConnectError("nope")

    async def fake_get_client():
        return _BoomClient()

    monkeypatch.setattr(zalo_oa, "_get_client", fake_get_client)
    monkeypatch.setattr(zalo_oa.asyncio, "sleep", AsyncMock())

    client = zalo_oa.ZaloOAClient(access_token="t")
    ok = await client.send_message("u", "hi")
    assert ok is False


@pytest.mark.asyncio
async def test_zalo_oa_treats_200_with_app_error_as_failure(monkeypatch):
    """Zalo signals some failures with HTTP 200 + error code != 0."""
    zalo_oa, _client, counter, fake = _make_client_with_responses(
        [httpx.Response(200, json={"error": 100, "message": "user not followed"})]
    )
    monkeypatch.setattr(zalo_oa, "_get_client", fake)
    monkeypatch.setattr(zalo_oa.asyncio, "sleep", AsyncMock())

    client = zalo_oa.ZaloOAClient(access_token="t")
    ok = await client.send_message("u", "hi")
    assert ok is False


# ---------------------------------------------------------------------------
# S22 — ZaloNotifier strip_markdown + truncate + Notifier port behaviour
# ---------------------------------------------------------------------------


def test_strip_markdown_drops_bold_italic_code():
    from backend.adapters.zalo_notifier import strip_markdown

    out = strip_markdown("**Bold** and *italic* and `code` and ~~strike~~")
    assert "*" not in out
    assert "_" not in out
    assert "`" not in out
    assert "~~" not in out
    assert "Bold" in out and "italic" in out and "code" in out


def test_strip_markdown_drops_html_tags():
    from backend.adapters.zalo_notifier import strip_markdown

    out = strip_markdown("<b>Cảnh báo</b> số dư <i>thấp</i>")
    assert "<" not in out
    assert ">" not in out
    assert "Cảnh báo" in out and "thấp" in out


def test_strip_markdown_keeps_markdown_link_label():
    from backend.adapters.zalo_notifier import strip_markdown

    out = strip_markdown("Xem [chi tiết](https://example.com) ngay")
    assert "chi tiết" in out
    assert "example.com" not in out
    assert "[" not in out and "]" not in out


def test_strip_markdown_empty_input():
    from backend.adapters.zalo_notifier import strip_markdown
    assert strip_markdown("") == ""
    assert strip_markdown(None) == ""  # type: ignore[arg-type]


def test_strip_markdown_idempotent():
    from backend.adapters.zalo_notifier import strip_markdown

    raw = "**hi** [link](u) `code`"
    once = strip_markdown(raw)
    twice = strip_markdown(once)
    assert once == twice


def test_truncate_for_zalo_passes_through_short():
    from backend.adapters.zalo_notifier import truncate_for_zalo
    assert truncate_for_zalo("hello") == "hello"


def test_truncate_for_zalo_caps_at_300_with_ellipsis():
    from backend.adapters.zalo_notifier import (
        truncate_for_zalo,
        ZALO_MESSAGE_MAX_CHARS,
    )

    msg = "x" * 500
    out = truncate_for_zalo(msg)
    assert len(out) == ZALO_MESSAGE_MAX_CHARS
    assert out.endswith("…")


@pytest.mark.asyncio
async def test_zalo_notifier_send_message_strips_and_calls_client():
    from backend.adapters.zalo_notifier import ZaloNotifier

    captured: dict[str, Any] = {}

    class FakeClient:
        async def send_message(self, recipient_id, text):
            captured["recipient_id"] = recipient_id
            captured["text"] = text
            return True

    notifier = ZaloNotifier(client=FakeClient(), zalo_user_id="z-1")
    result = await notifier.send_message(
        chat_id=0,
        text="<b>Cảnh báo</b> *quan trọng*",
        parse_mode="HTML",
        reply_markup={"inline_keyboard": []},
    )
    assert result == {"ok": True, "channel": "zalo"}
    assert captured["recipient_id"] == "z-1"
    assert "<" not in captured["text"] and "*" not in captured["text"]
    assert "Cảnh báo" in captured["text"]


@pytest.mark.asyncio
async def test_zalo_notifier_returns_none_when_client_fails():
    from backend.adapters.zalo_notifier import ZaloNotifier

    class FakeClient:
        async def send_message(self, *_args, **_kwargs):
            return False

    notifier = ZaloNotifier(client=FakeClient(), zalo_user_id="z-1")
    result = await notifier.send_message(chat_id=0, text="hello")
    assert result is None


@pytest.mark.asyncio
async def test_zalo_notifier_returns_none_when_text_empty_after_strip():
    from backend.adapters.zalo_notifier import ZaloNotifier

    class FakeClient:
        called = False

        async def send_message(self, *_args, **_kwargs):
            self.called = True
            return True

    client = FakeClient()
    notifier = ZaloNotifier(client=client, zalo_user_id="z-1")
    # All-markdown text → strips to empty → notifier should bail.
    assert await notifier.send_message(0, "**__**") is None
    assert client.called is False


@pytest.mark.asyncio
async def test_zalo_notifier_caps_at_300_chars():
    from backend.adapters.zalo_notifier import ZaloNotifier

    captured: dict[str, Any] = {}

    class FakeClient:
        async def send_message(self, recipient_id, text):
            captured["text"] = text
            return True

    notifier = ZaloNotifier(client=FakeClient(), zalo_user_id="z-1")
    long_text = "Số dư có thể xuống thấp. " * 50
    await notifier.send_message(chat_id=0, text=long_text)
    assert len(captured["text"]) <= 300


# ---------------------------------------------------------------------------
# S23 — Linking service: token issue + redeem
# ---------------------------------------------------------------------------


class FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return self._value if isinstance(self._value, list) else []


class FakeDB:
    """In-memory stand-in for AsyncSession. Each execute() pops from
    a configured response queue; flush/delete/add are no-ops we count."""

    def __init__(self, execute_queue: list[Any] | None = None):
        self._queue = list(execute_queue or [])
        self.added: list[Any] = []
        self.deleted: list[Any] = []
        self.flush_count = 0

    async def execute(self, _stmt):
        if not self._queue:
            return FakeScalarResult(None)
        val = self._queue.pop(0)
        return FakeScalarResult(val)

    def add(self, obj):
        self.added.append(obj)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def flush(self):
        self.flush_count += 1


def _make_user(zalo_user_id: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        telegram_id=12345,
        zalo_user_id=zalo_user_id,
    )


@pytest.mark.asyncio
async def test_issue_link_token_creates_new_when_none_active():
    from backend.services import zalo_linking_service

    user = _make_user()
    # First exec: list active tokens → empty. Second exec: PK existence
    # check → None (slot is free).
    db = FakeDB(execute_queue=[[], None])

    token = await zalo_linking_service.issue_link_token(db, user)
    assert token.startswith("BT-")
    assert len(token) == len("BT-") + 6
    assert db.flush_count == 1
    assert len(db.added) == 1
    assert db.added[0].user_id == user.id


@pytest.mark.asyncio
async def test_issue_link_token_reuses_active_token():
    from backend.services import zalo_linking_service
    from backend.models.zalo_link_token import ZaloLinkToken

    user = _make_user()
    existing = ZaloLinkToken(
        token="BT-ABC234",
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        created_at=datetime.now(timezone.utc),
    )
    db = FakeDB(execute_queue=[[existing]])

    token = await zalo_linking_service.issue_link_token(db, user)
    assert token == "BT-ABC234"
    assert db.flush_count == 0  # nothing new inserted
    assert db.added == []


def test_normalize_token_input_extracts_from_freeform():
    from backend.services.zalo_linking_service import normalize_token_input
    assert normalize_token_input("Mã của tôi là BT-A7K3P2 nhé") == "BT-A7K3P2"
    assert normalize_token_input("bt-a7k3p2") == "BT-A7K3P2"


def test_normalize_token_input_rejects_garbage():
    from backend.services.zalo_linking_service import normalize_token_input
    assert normalize_token_input("hello") is None
    assert normalize_token_input("") is None
    # I/O/L/U are excluded from the alphabet — a token with them is invalid.
    assert normalize_token_input("BT-IIIIII") is None
    # Too short
    assert normalize_token_input("BT-A") is None


@pytest.mark.asyncio
async def test_redeem_link_token_success():
    from backend.services import zalo_linking_service
    from backend.models.zalo_link_token import ZaloLinkToken

    user = _make_user()
    row = ZaloLinkToken(
        token="BT-AAAAAA",
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        used_at=None,
        created_at=datetime.now(timezone.utc),
    )
    # execute_queue: [row lookup, user lookup, conflict check (no other user)]
    db = FakeDB(execute_queue=[row, user, None])

    result = await zalo_linking_service.redeem_link_token(
        db, token="BT-AAAAAA", zalo_user_id="zuser-99"
    )
    assert result.status == "linked"
    assert result.user_id == user.id
    assert user.zalo_user_id == "zuser-99"
    assert row.used_at is not None


@pytest.mark.asyncio
async def test_redeem_link_token_expired():
    from backend.services import zalo_linking_service
    from backend.models.zalo_link_token import ZaloLinkToken

    user = _make_user()
    row = ZaloLinkToken(
        token="BT-AAAAAA",
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        used_at=None,
        created_at=datetime.now(timezone.utc),
    )
    db = FakeDB(execute_queue=[row])
    result = await zalo_linking_service.redeem_link_token(
        db, token="BT-AAAAAA", zalo_user_id="zuser"
    )
    assert result.status == "expired"
    assert user.zalo_user_id is None


@pytest.mark.asyncio
async def test_redeem_link_token_already_used():
    from backend.services import zalo_linking_service
    from backend.models.zalo_link_token import ZaloLinkToken

    user = _make_user()
    row = ZaloLinkToken(
        token="BT-AAAAAA",
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        used_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        created_at=datetime.now(timezone.utc),
    )
    db = FakeDB(execute_queue=[row])
    result = await zalo_linking_service.redeem_link_token(
        db, token="BT-AAAAAA", zalo_user_id="zuser"
    )
    assert result.status == "already_used"


@pytest.mark.asyncio
async def test_redeem_link_token_unknown():
    from backend.services import zalo_linking_service

    db = FakeDB(execute_queue=[None])
    result = await zalo_linking_service.redeem_link_token(
        db, token="BT-FAKEXY", zalo_user_id="z"
    )
    assert result.status == "invalid"


@pytest.mark.asyncio
async def test_redeem_link_token_conflict_blocks_steal():
    """A different user trying to redeem a token must NOT clobber an
    existing zalo_user_id binding on someone else."""
    from backend.services import zalo_linking_service
    from backend.models.zalo_link_token import ZaloLinkToken

    user = _make_user()
    row = ZaloLinkToken(
        token="BT-AAAAAA",
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        used_at=None,
        created_at=datetime.now(timezone.utc),
    )
    # conflict_q returns another uuid → blocked
    db = FakeDB(execute_queue=[row, user, uuid.uuid4()])
    result = await zalo_linking_service.redeem_link_token(
        db, token="BT-AAAAAA", zalo_user_id="zuser-shared"
    )
    assert result.status == "invalid"
    assert user.zalo_user_id is None


@pytest.mark.asyncio
async def test_unlink_user_clears_when_linked():
    from backend.services import zalo_linking_service

    user = _make_user(zalo_user_id="z-1")
    db = FakeDB()
    ok = await zalo_linking_service.unlink_user(db, user)
    assert ok is True
    assert user.zalo_user_id is None
    assert db.flush_count == 1


@pytest.mark.asyncio
async def test_unlink_user_noop_when_not_linked():
    from backend.services import zalo_linking_service

    user = _make_user(zalo_user_id=None)
    db = FakeDB()
    ok = await zalo_linking_service.unlink_user(db, user)
    assert ok is False
    assert db.flush_count == 0


# ---------------------------------------------------------------------------
# S24 — Notifier resolver + multi-channel alert fan-out
# ---------------------------------------------------------------------------


def test_resolve_targets_telegram_only_when_zalo_not_linked(monkeypatch):
    from backend.services import notifier_resolver

    user = _make_user(zalo_user_id=None)
    targets = notifier_resolver.resolve_targets(user)
    assert len(targets) == 1
    assert targets[0].channel == "telegram"
    assert targets[0].target_id == "12345"


def test_resolve_targets_appends_zalo_when_linked_and_configured(monkeypatch):
    from backend.services import notifier_resolver
    from backend.adapters import zalo_oa

    user = _make_user(zalo_user_id="zuser-1")

    class FakeOAClient:
        is_configured = True

    monkeypatch.setattr(zalo_oa, "get_zalo_oa_client", lambda: FakeOAClient())
    monkeypatch.setattr(
        notifier_resolver, "get_zalo_oa_client", lambda: FakeOAClient()
    )

    targets = notifier_resolver.resolve_targets(user)
    assert [t.channel for t in targets] == ["telegram", "zalo"]
    assert targets[1].target_id == "zuser-1"


def test_resolve_targets_skips_zalo_when_oa_not_configured(monkeypatch):
    from backend.services import notifier_resolver

    user = _make_user(zalo_user_id="zuser-1")

    class FakeOAClient:
        is_configured = False

    monkeypatch.setattr(
        notifier_resolver, "get_zalo_oa_client", lambda: FakeOAClient()
    )

    targets = notifier_resolver.resolve_targets(user)
    assert [t.channel for t in targets] == ["telegram"]


# ---------------------------------------------------------------------------
# Cashflow alert: multi-channel fan-out
# ---------------------------------------------------------------------------


class FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}
        self.exists_calls: list[str] = []
        self.setex_calls: list[tuple[str, int, str]] = []

    async def exists(self, key):
        self.exists_calls.append(key)
        return 1 if key in self.store else 0

    async def setex(self, key, ttl, val):
        self.setex_calls.append((key, ttl, val))
        self.store[key] = val


def _make_forecast():
    return SimpleNamespace(
        low_balance_risk=True,
        low_balance_month=datetime(2026, 11, 1).date(),
        low_balance_threshold=Decimal("15000000"),
        monthly_data=[
            {
                "month": "2026-11-01",
                "balance_eom": "12000000",
                "income": "20000000",
                "expense": "23000000",
                "net": "-3000000",
            }
        ],
    )


@pytest.mark.asyncio
async def test_check_and_send_alert_fans_out_to_both_channels(monkeypatch):
    from backend.cashflow import alert as alert_mod
    from backend.services import notifier_resolver

    user = _make_user(zalo_user_id="zuser-1")
    forecast = _make_forecast()
    redis = FakeRedis()

    async def fake_get_latest(db, uid):
        return forecast

    monkeypatch.setattr(alert_mod, "get_latest_forecast", fake_get_latest)
    monkeypatch.setattr(alert_mod, "_get_redis", lambda: redis)

    tg_notifier = SimpleNamespace(send_message=AsyncMock(return_value={"ok": True}))
    zalo_notifier = SimpleNamespace(
        send_message=AsyncMock(return_value={"ok": True, "channel": "zalo"})
    )

    def fake_resolve(_user):
        return [
            notifier_resolver.ChannelTarget(
                channel="telegram", notifier=tg_notifier, target_id="12345"
            ),
            notifier_resolver.ChannelTarget(
                channel="zalo", notifier=zalo_notifier, target_id="zuser-1"
            ),
        ]

    monkeypatch.setattr(alert_mod, "resolve_targets", fake_resolve)

    sent = await alert_mod.check_and_send_alert(db=None, user=user, confirmed_patterns=[])
    assert sent is True
    tg_notifier.send_message.assert_awaited_once()
    zalo_notifier.send_message.assert_awaited_once()
    # Per-channel dedup keys
    assert any("telegram" not in k and "2026-11-01" in k for k in redis.store)
    assert any(":zalo:" in k for k in redis.store)


@pytest.mark.asyncio
async def test_check_and_send_alert_fail_open_when_zalo_fails(monkeypatch):
    """Story #441: Zalo fail → Telegram still sends."""
    from backend.cashflow import alert as alert_mod
    from backend.services import notifier_resolver

    user = _make_user(zalo_user_id="zuser-1")
    forecast = _make_forecast()
    redis = FakeRedis()

    async def fake_get_latest(db, uid):
        return forecast

    monkeypatch.setattr(alert_mod, "get_latest_forecast", fake_get_latest)
    monkeypatch.setattr(alert_mod, "_get_redis", lambda: redis)

    tg = SimpleNamespace(send_message=AsyncMock(return_value={"ok": True}))
    zalo = SimpleNamespace(send_message=AsyncMock(return_value=None))

    monkeypatch.setattr(
        alert_mod,
        "resolve_targets",
        lambda _u: [
            notifier_resolver.ChannelTarget("telegram", tg, "12345"),
            notifier_resolver.ChannelTarget("zalo", zalo, "zuser-1"),
        ],
    )

    sent = await alert_mod.check_and_send_alert(db=None, user=user, confirmed_patterns=[])
    assert sent is True  # Telegram succeeded
    tg.send_message.assert_awaited_once()
    zalo.send_message.assert_awaited_once()
    # Zalo dedup key NOT set (send failed)
    assert all(":zalo:" not in k for k in redis.store)


@pytest.mark.asyncio
async def test_check_and_send_alert_fail_open_when_zalo_raises(monkeypatch):
    """Defence-in-depth: a Zalo adapter that raises must not stop Telegram."""
    from backend.cashflow import alert as alert_mod
    from backend.services import notifier_resolver

    user = _make_user(zalo_user_id="zuser-1")
    forecast = _make_forecast()
    redis = FakeRedis()

    async def fake_get_latest(db, uid):
        return forecast

    monkeypatch.setattr(alert_mod, "get_latest_forecast", fake_get_latest)
    monkeypatch.setattr(alert_mod, "_get_redis", lambda: redis)

    tg = SimpleNamespace(send_message=AsyncMock(return_value={"ok": True}))

    async def boom(*_a, **_kw):
        raise RuntimeError("zalo client exploded")

    zalo = SimpleNamespace(send_message=AsyncMock(side_effect=boom))

    monkeypatch.setattr(
        alert_mod,
        "resolve_targets",
        lambda _u: [
            notifier_resolver.ChannelTarget("telegram", tg, "12345"),
            notifier_resolver.ChannelTarget("zalo", zalo, "zuser-1"),
        ],
    )

    sent = await alert_mod.check_and_send_alert(db=None, user=user, confirmed_patterns=[])
    assert sent is True
    tg.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_and_send_alert_dedup_skips_resend(monkeypatch):
    from backend.cashflow import alert as alert_mod
    from backend.services import notifier_resolver

    user = _make_user(zalo_user_id=None)
    forecast = _make_forecast()
    redis = FakeRedis()
    # Pre-populate the telegram dedup key with the legacy format.
    redis.store[f"cashflow_alert:{user.id}:2026-11-01"] = "sent"

    async def fake_get_latest(db, uid):
        return forecast

    monkeypatch.setattr(alert_mod, "get_latest_forecast", fake_get_latest)
    monkeypatch.setattr(alert_mod, "_get_redis", lambda: redis)

    tg = SimpleNamespace(send_message=AsyncMock())
    monkeypatch.setattr(
        alert_mod,
        "resolve_targets",
        lambda _u: [notifier_resolver.ChannelTarget("telegram", tg, "12345")],
    )

    sent = await alert_mod.check_and_send_alert(db=None, user=user, confirmed_patterns=[])
    assert sent is False
    tg.send_message.assert_not_awaited()


def test_format_alert_zalo_is_plain_and_short(monkeypatch):
    from backend.cashflow import alert as alert_mod

    forecast = _make_forecast()
    msg = alert_mod._format_alert_for_channel(
        forecast, confirmed_patterns=[], channel="zalo"
    )
    assert "<" not in msg and ">" not in msg
    assert "**" not in msg
    # The naturally formatted Zalo body must stay under the cap so
    # the notifier doesn't have to truncate normal alerts.
    assert len(msg) <= 300


def test_format_alert_telegram_uses_html(monkeypatch):
    from backend.cashflow import alert as alert_mod

    forecast = _make_forecast()
    msg = alert_mod._format_alert_for_channel(
        forecast, confirmed_patterns=[], channel="telegram"
    )
    assert "<b>" in msg
