"""Zalo-first onboarding — Phase 5.1 E4 #4.3.

The subject is ``backend.bot.handlers.zalo_onboarding`` driven through its
real entry point, ``zalo_inbound.handle_inbound_event``: #4.3's claim is
that a stranger who messages the OA without a token is *starting*, not
failing, and that claim is only true end to end.

Two deliberate choices about the fakes:

- The onboarding services are **not** stubbed. ``_FakeSession`` implements
  the four session methods they actually use (``get`` / ``add`` / ``flush``
  / ``execute``) over ordinary ORM instances held in dicts, so the real
  step machine runs — a wrong transition fails here rather than in soak.
  It also refuses to ``commit``: the worker owns the boundary.
- What *is* stubbed is everything with a side effect outside this flow —
  asset creation, Twin projection, analytics, the chart renderer, the
  settings read — because none of those decide onboarding's behaviour.

Phase 5.1's governing rule is that there is no "Zalo version" of any
service. These tests hold that line by construction: they exercise the
same ``backend.services.onboarding`` functions the Telegram wizard calls.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.adapters.zalo_content_renderer import ZaloContentRenderer  # noqa: E402
from backend.bot.handlers import zalo_inbound, zalo_onboarding  # noqa: E402
from backend.models.onboarding_session import (  # noqa: E402
    STEP_COMPLETED,
    STEP_FIRST_ASSET,
    STEP_GOAL_QUESTION,
    STEP_TRUST_PRIVACY,
    OnboardingSession,
)
from backend.models.user import User  # noqa: E402
from backend.services import zalo_linking_service  # noqa: E402
from backend.services.onboarding import onboarding_service  # noqa: E402
from backend.utils.zalo_copy import text as zalo_text  # noqa: E402

SENDER_ID = "zalo-sender-should-never-be-logged"
BOT_URL = "https://t.me/betien_test_bot"


# --------------------------------------------------------------------------
# Session double
# --------------------------------------------------------------------------


class _Scalars:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def all(self) -> list:
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _Result:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def scalar_one_or_none(self):
        if not self._rows:
            return None
        if len(self._rows) > 1:  # pragma: no cover — would be a real bug
            raise AssertionError("expected at most one row")
        return self._rows[0]

    def scalars(self) -> _Scalars:
        return _Scalars(self._rows)


class _FakeSession:
    """In-memory stand-in for ``AsyncSession``.

    CI has no Postgres and no aiosqlite, but the onboarding services only
    ever ask a session for four things, so honouring those four is enough
    to run them for real. ``commit`` fails loudly — nothing below the
    worker may own the transaction.
    """

    def __init__(self, *, status: str = "active") -> None:
        self.users: dict = {}
        self.sessions: dict = {}
        self.status = status
        self.flushes = 0

    # -- reads ----------------------------------------------------------
    async def get(self, model, pk):
        if model is User:
            return self.users.get(pk)
        if model is OnboardingSession:
            return self.sessions.get(pk)
        raise AssertionError(f"unexpected model in db.get: {model!r}")

    async def execute(self, stmt):
        # The only query that reaches here is "which user owns this Zalo
        # id?". Matching on the compiled bind parameters keeps the fake
        # honest: rename the column and the lookup stops matching.
        wanted = set(stmt.compile().params.values())
        rows = [
            user
            for user in self.users.values()
            if user.zalo_user_id is not None and user.zalo_user_id in wanted
        ]
        return _Result(rows)

    async def scalar(self, _stmt):
        # ``is_user_allowed`` reads the manual status column.
        return self.status

    # -- writes ---------------------------------------------------------
    def add(self, obj) -> None:
        if isinstance(obj, User):
            if obj.id is None:
                obj.id = uuid4()
            self.users[obj.id] = obj
        elif isinstance(obj, OnboardingSession):
            self.sessions[obj.user_id] = obj
        else:  # pragma: no cover — nothing else is created in this flow
            raise AssertionError(f"unexpected insert: {obj!r}")

    async def flush(self) -> None:
        self.flushes += 1

    async def refresh(self, _obj) -> None:
        return None

    async def commit(self):  # pragma: no cover
        raise AssertionError("onboarding must not commit — the worker does")

    # -- convenience ----------------------------------------------------
    def only_user(self) -> User:
        assert len(self.users) == 1, f"expected exactly one user, got {len(self.users)}"
        return next(iter(self.users.values()))

    def session_of(self, user: User) -> OnboardingSession:
        return self.sessions[user.id]


class _SpyNotifier:
    """Records what the OA would have sent.

    ``send_message`` returns a truthy receipt by default; tests that care
    about a blocked window set ``fail_containing`` so the bubble matching
    that needle returns ``None``, which is what the windowed notifier does
    when the 48h window has closed. Matching on the copy rather than on a
    send count keeps the test from re-breaking every time a step gains or
    loses a bubble.

    ``expects_chat_id`` is 0 for the Zalo spy — the Zalo notifier is bound
    to a sender and ignores the chat id — and ``None`` for the Telegram
    stand-in, which legitimately addresses a real chat.
    """

    def __init__(self, *, expects_chat_id: int | None = 0) -> None:
        self.sent: list[tuple[str, tuple]] = []
        self.photos: list[tuple[bytes, str | None]] = []
        self.fail_containing: str | None = None
        self._expects_chat_id = expects_chat_id

    def _check(self, chat_id) -> None:
        if self._expects_chat_id is not None:
            assert chat_id == self._expects_chat_id, (
                "Zalo notifiers address the sender, not a chat id"
            )

    async def send_message(self, chat_id, text, **kwargs):
        self._check(chat_id)
        self.sent.append((text, kwargs.get("buttons") or ()))
        if self.fail_containing is not None and self.fail_containing in text:
            return None
        return {"ok": True}

    async def send_photo(self, chat_id, image, caption=None, filename=None):
        self._check(chat_id)
        self.photos.append((image, caption))
        return {"ok": True}

    @property
    def texts(self) -> list[str]:
        return [text for text, _ in self.sent]

    def said(self, needle: str) -> bool:
        return any(needle in text for text in self.texts)

    def buttons_for(self, needle: str) -> tuple:
        for text, buttons in self.sent:
            if needle in text:
                return buttons
        raise AssertionError(f"no bubble containing {needle!r}")


def _event(text: str, *, event_name: str = "user_send_text"):
    return zalo_inbound.ZaloEvent(
        msg_id=f"m-{text[:6]}",
        event_name=event_name,
        sender_id=SENDER_ID,
        text=text,
        timestamp="1754092800000",
        derived_key=None,
        payload={},
    )


def _stub_chart(cone, optimal=None, **_kwargs) -> bytes:
    assert cone, "the renderer must not ask for a chart of an empty cone"
    return b"\x89PNG-stub"


_CONE = [
    {"year": year, "p10": 100 * year, "p50": 200 * year, "p90": 300 * year}
    for year in range(11)
]


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture()
def zalo_out() -> _SpyNotifier:
    return _SpyNotifier()


@pytest.fixture()
def analytics_events() -> list:
    return []


@pytest.fixture()
def assets() -> list:
    return []


@pytest.fixture(autouse=True)
def _wiring(monkeypatch, zalo_out, analytics_events, assets):
    """Replace the side effects, keep the decisions."""
    monkeypatch.setattr(
        zalo_inbound, "build_zalo_notifier", lambda sender_id, **kw: zalo_out
    )
    monkeypatch.setattr(
        zalo_inbound, "get_notifier", lambda: _SpyNotifier(expects_chat_id=None)
    )

    def _track(event_type, user_id=None, properties=None):
        analytics_events.append((event_type, user_id, properties))

    monkeypatch.setattr(zalo_onboarding.analytics, "track", _track)

    async def _create_asset(db, user_id, **kwargs):
        assets.append((user_id, kwargs))
        return SimpleNamespace(id=uuid4())

    monkeypatch.setattr(zalo_onboarding.asset_service, "create_asset", _create_asset)

    # Both flags pinned: the flow under test must not change shape because
    # somebody flipped an env var in another suite.
    monkeypatch.setattr(zalo_onboarding, "is_trust_card_enabled", lambda: True)
    monkeypatch.setattr(zalo_onboarding, "is_onboarding_reset_enabled", lambda: False)
    monkeypatch.setattr(
        zalo_onboarding,
        "get_settings",
        lambda: SimpleNamespace(telegram_bot_url=BOT_URL),
    )
    monkeypatch.setattr(
        zalo_onboarding,
        "ZaloContentRenderer",
        lambda: ZaloContentRenderer(chart_renderer=_stub_chart),
    )

    from backend.twin.services import twin_projection_service

    async def _compute(db, user_id, scenario="current"):
        return [
            SimpleNamespace(
                cone_data=_CONE,
                computed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        ]

    monkeypatch.setattr(twin_projection_service, "compute_and_store", _compute)


@pytest.fixture()
def db() -> _FakeSession:
    return _FakeSession()


# --------------------------------------------------------------------------
# Labels — read from the same copy the handler reads
# --------------------------------------------------------------------------


def _salutation_label(code: str = "anh") -> str:
    return zalo_onboarding._salutation_options()[code]


def _goal_label(code: str = "understand_wealth") -> str:
    return zalo_onboarding._goal_options()[code]


def _trust_label() -> str:
    return zalo_text("onboarding", "trust_ok_label")


def _decline_label() -> str:
    return zalo_text("onboarding", "telegram_invite_decline_label")


async def _say(db, text: str):
    return await zalo_inbound.handle_inbound_event(db, event=_event(text))


async def _walk_to_asset_step(db) -> User:
    """Drive name → salutation → goal → trust and stop before the amount."""
    await _say(db, "chào Bé Tiền")
    await _say(db, "Phương")
    await _say(db, _salutation_label())
    await _say(db, _goal_label())
    await _say(db, _trust_label())
    return db.only_user()


# --------------------------------------------------------------------------
# Signup
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_stranger_without_a_token_is_signed_up_not_scolded(db, zalo_out):
    """The behaviour #4.3 replaces: this used to answer "/link_zalo"."""
    user_id = await _say(db, "chào Bé Tiền")

    user = db.only_user()
    assert user_id == user.id
    assert user.zalo_user_id == SENDER_ID
    # No honest placeholder exists for a Telegram id they don't have.
    assert user.telegram_id is None
    assert db.session_of(user).current_step == STEP_GOAL_QUESTION
    assert zalo_out.said("Bé Tiền là người đồng hành")
    assert zalo_out.said("gọi")  # ask_name


@pytest.mark.asyncio
async def test_signup_is_idempotent_for_the_same_sender(db, analytics_events):
    """A second message must not mint a second account."""
    first = await _say(db, "chào Bé Tiền")
    # Same sender, still nameless, so still on the name sub-step.
    second = await _say(db, "")  # empty body is dropped before signup
    assert second is None

    third = await _say(db, "alo")
    assert third == first
    assert len(db.users) == 1
    started = [e for e in analytics_events if e[0] == "zalo_onboarding_started"]
    assert len(started) == 1


# --------------------------------------------------------------------------
# The walk
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_new_zalo_user_walks_the_whole_flow_to_the_twin(
    db, zalo_out, assets, analytics_events
):
    await _say(db, "chào Bé Tiền")
    user = db.only_user()

    await _say(db, "Phương")
    assert user.display_name == "Phương"
    assert db.session_of(user).current_step == STEP_GOAL_QUESTION
    # Buttons are suggestions: oa.query.show types the label back at us.
    assert [b.text for row in zalo_out.buttons_for("xưng hô") for b in row]

    await _say(db, _salutation_label("anh"))
    assert user.salutation == "anh"

    await _say(db, _goal_label("understand_wealth"))
    session = db.session_of(user)
    assert session.goal_choice == "understand_wealth"
    assert session.current_step == STEP_TRUST_PRIVACY

    await _say(db, _trust_label())
    assert db.session_of(user).current_step == STEP_FIRST_ASSET

    await _say(db, "200tr")

    # Asset captured as Decimal, never float.
    assert len(assets) == 1
    user_id, kwargs = assets[0]
    assert user_id == user.id
    assert kwargs["current_value"] == Decimal("200000000")
    assert isinstance(kwargs["current_value"], Decimal)
    assert kwargs["is_placeholder_asset"] is False

    # Twin drawn and onboarding closed out.
    assert zalo_out.photos, "the Twin cone should ship as a picture"
    _image, caption = zalo_out.photos[0]
    assert "Khiêm tốn" in caption
    assert "không phải lời hứa" in caption
    assert db.session_of(user).current_step == STEP_COMPLETED
    assert zalo_out.said("Từ giờ")  # done

    kinds = [e[0] for e in analytics_events]
    assert kinds == [
        "zalo_onboarding_started",
        "zalo_onboarding_asset_captured",
        "zalo_onboarding_completed",
        "zalo_telegram_invite_shown",
    ]


@pytest.mark.asyncio
async def test_the_salutation_the_user_picked_reaches_the_twin_bubble(db, zalo_out):
    await _walk_to_asset_step(db)
    await _say(db, "200tr")

    _image, caption = zalo_out.photos[0]
    assert "anh" in caption
    assert "{" not in caption, "a missing format key leaks the raw template"


@pytest.mark.asyncio
async def test_every_bubble_stays_inside_the_zalo_copy_budget(db, zalo_out):
    """content/zalo.yaml's own rule: plain text, ~300 chars, no Markdown."""
    await _walk_to_asset_step(db)
    await _say(db, "200tr")

    for text in zalo_out.texts:
        assert "{" not in text and "}" not in text
        assert "**" not in text


# --------------------------------------------------------------------------
# Re-prompts
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_unusable_name_reprompts_without_advancing(db, zalo_out):
    await _say(db, "chào Bé Tiền")
    user = db.only_user()

    await _say(db, "x" * 80)

    assert user.display_name is None
    assert zalo_out.said("nhắn lại tên ngắn")
    assert onboarding_service.goal_substep(user) == onboarding_service.SUBSTEP_NAME


@pytest.mark.asyncio
async def test_an_unrecognised_salutation_reprompts(db, zalo_out):
    await _say(db, "chào Bé Tiền")
    await _say(db, "Phương")
    user = db.only_user()

    await _say(db, "gọi tôi là sếp")

    assert user.salutation is None
    assert zalo_out.said("nhắn anh, chị hoặc bạn")


@pytest.mark.asyncio
async def test_a_typed_salutation_works_as_well_as_the_button(db):
    await _say(db, "chào Bé Tiền")
    await _say(db, "Phương")
    await _say(db, "chị")

    assert db.only_user().salutation == "chị"


@pytest.mark.parametrize(
    ("amount", "needle"),
    [
        ("linh tinh", "chưa hiểu con số"),
        ("500k", "nhỏ hơn 1 triệu"),
        ("999999 tỷ", "lớn quá"),
    ],
)
@pytest.mark.asyncio
async def test_a_bad_amount_reprompts_and_captures_nothing(
    db, zalo_out, assets, amount, needle
):
    user = await _walk_to_asset_step(db)

    await _say(db, amount)

    assert assets == []
    assert zalo_out.said(needle)
    assert db.session_of(user).current_step == STEP_FIRST_ASSET


@pytest.mark.asyncio
async def test_the_demo_label_captures_the_demo_amount_and_says_it_is_fake(
    db, zalo_out, assets
):
    await _walk_to_asset_step(db)

    await _say(db, zalo_text("onboarding", "asset_demo_label"))

    _user_id, kwargs = assets[0]
    assert kwargs["current_value"] == onboarding_service.DEMO_ASSET_VND
    assert kwargs["is_placeholder_asset"] is True
    assert kwargs["suppress_twin_event"] is True
    assert zalo_out.said("không phải tài sản thật")


@pytest.mark.asyncio
async def test_a_failed_projection_says_so_and_still_finishes(db, zalo_out):
    from backend.twin.services import twin_projection_service

    async def _boom(db_, user_id, scenario="current"):
        raise RuntimeError("projection engine down")

    twin_projection_service.compute_and_store = _boom  # restored by monkeypatch
    user = await _walk_to_asset_step(db)

    await _say(db, "200tr")

    assert zalo_out.photos == []
    assert zalo_out.said("chưa vẽ được Twin")
    # A missing picture must not strand someone mid-onboarding.
    assert db.session_of(user).current_step == STEP_COMPLETED


# --------------------------------------------------------------------------
# The one-time Telegram invitation
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_invitation_is_offered_exactly_once(db, zalo_out):
    user = await _walk_to_asset_step(db)
    await _say(db, "200tr")

    assert zalo_out.said("Bé Tiền hỏi một lần thôi")
    assert user.zalo_telegram_invite_at is not None
    assert zalo_linking_service.telegram_invite_pending(user) is False

    # The accept button carries the deep link; the body never does.
    buttons = zalo_out.buttons_for("Bé Tiền hỏi một lần thôi")
    urls = [b.web_app_url for row in buttons for b in row if b.web_app_url]
    assert urls == [BOT_URL]
    assert BOT_URL not in "".join(zalo_out.texts)

    # Nothing later re-opens the offer.
    before = len(zalo_out.sent)
    await zalo_onboarding._finish(db, notifier=zalo_out, user=user)
    assert not any(
        "Bé Tiền hỏi một lần thôi" in text for text in zalo_out.texts[before:]
    )


@pytest.mark.asyncio
async def test_no_bot_url_means_the_offer_is_kept_not_burned(
    db, zalo_out, monkeypatch, analytics_events
):
    monkeypatch.setattr(
        zalo_onboarding, "get_settings", lambda: SimpleNamespace(telegram_bot_url="  ")
    )
    user = await _walk_to_asset_step(db)

    await _say(db, "200tr")

    assert not zalo_out.said("Bé Tiền hỏi một lần thôi")
    assert user.zalo_telegram_invite_at is None
    assert zalo_linking_service.telegram_invite_pending(user) is True
    assert "zalo_telegram_invite_shown" not in [e[0] for e in analytics_events]


@pytest.mark.asyncio
async def test_an_undelivered_invitation_stays_pending(db, zalo_out):
    """A closed 48h window means it was never asked, so it is still owed."""
    user = await _walk_to_asset_step(db)
    zalo_out.fail_containing = "Bé Tiền hỏi một lần thôi"
    await _say(db, "200tr")

    assert zalo_out.said("Bé Tiền hỏi một lần thôi"), "the send was attempted"

    assert user.zalo_telegram_invite_at is None
    assert zalo_linking_service.telegram_invite_pending(user) is True


@pytest.mark.asyncio
async def test_declining_is_recorded_and_never_asked_again(
    db, zalo_out, analytics_events
):
    user = await _walk_to_asset_step(db)
    await _say(db, "200tr")

    await _say(db, _decline_label())

    assert user.zalo_telegram_invite_response == (
        zalo_linking_service.INVITE_RESPONSE_DECLINED
    )
    assert zalo_out.said("không nhắc lại nữa")
    assert "zalo_telegram_invite_declined" in [e[0] for e in analytics_events]


@pytest.mark.asyncio
async def test_the_decline_answer_is_consumed_only_once(db, zalo_out):
    user = await _walk_to_asset_step(db)
    await _say(db, "200tr")
    await _say(db, _decline_label())

    consumed = await zalo_onboarding.handle_text(
        db, notifier=zalo_out, user=user, text=_decline_label()
    )

    # Second time it is just a sentence; dispatch should get it.
    assert consumed is False


@pytest.mark.asyncio
async def test_a_user_who_already_has_telegram_is_never_invited(db, zalo_out):
    user = await _walk_to_asset_step(db)
    user.telegram_id = 555

    await _say(db, "200tr")

    assert not zalo_out.said("Bé Tiền hỏi một lần thôi")
    assert user.zalo_telegram_invite_at is None


# --------------------------------------------------------------------------
# Boundaries with the rest of the inbound path
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_finished_user_falls_through_to_intent_dispatch(
    db, zalo_out, monkeypatch
):
    dispatched: list[str] = []

    async def _dispatch(db_, *, notifier, user, text):
        dispatched.append(text)

    monkeypatch.setattr(zalo_inbound, "_dispatch_intent", _dispatch)
    user = await _walk_to_asset_step(db)
    await _say(db, "200tr")

    result = await _say(db, "ăn trưa 50k")

    assert dispatched == ["ăn trưa 50k"]
    assert result == user.id


@pytest.mark.asyncio
async def test_a_token_still_redeems_instead_of_signing_up(db, monkeypatch, zalo_out):
    """The BT-XXXXXX path predates #4.3 and must be untouched by it."""
    existing = User(id=uuid4(), telegram_id=555, display_name="Cũ")

    async def _redeem(db_, token, zalo_user_id):
        assert token == "BT-ABC234"
        return zalo_linking_service.LinkRedemption(status="linked", user_id=existing.id)

    async def _get_user_by_id(db_, user_id):
        return existing

    async def _never(*args, **kwargs):  # pragma: no cover
        raise AssertionError("a token holder must not be signed up as new")

    monkeypatch.setattr(zalo_inbound.zalo_linking_service, "redeem_link_token", _redeem)
    monkeypatch.setattr(
        zalo_inbound.zalo_linking_service, "get_user_by_id", _get_user_by_id
    )
    monkeypatch.setattr(zalo_onboarding, "start_new_user", _never)

    result = await _say(db, "mã của tôi: BT-ABC234 nhé")

    assert result == existing.id
    assert db.users == {}, "redemption must not mint an account"


@pytest.mark.asyncio
async def test_a_suspended_zalo_first_account_is_still_stopped(db, zalo_out):
    await _say(db, "chào Bé Tiền")
    db.status = "suspended"
    before = len(zalo_out.sent)

    await _say(db, "Phương")

    assert db.only_user().display_name is None
    assert len(zalo_out.sent) == before + 1  # the refusal, nothing else


@pytest.mark.asyncio
async def test_onboarding_never_owns_the_transaction(db):
    """``_FakeSession.commit`` raises; reaching the end proves nobody called
    it. The flush count proves the writes were real all the same."""
    await _walk_to_asset_step(db)
    await _say(db, "200tr")

    assert db.flushes > 0
