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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import (
    BinaryExpression,
    BindParameter,
    BooleanClauseList,
    Null,
)

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.adapters.zalo_content_renderer import ZaloContentRenderer  # noqa: E402
from backend.bot.handlers import (  # noqa: E402
    zalo_adoption,
    zalo_inbound,
    zalo_onboarding,
)
from backend.models.onboarding_session import (  # noqa: E402
    STEP_COMPLETED,
    STEP_FIRST_ASSET,
    STEP_GOAL_QUESTION,
    STEP_TRUST_PRIVACY,
    OnboardingSession,
)
from backend.models.user import User  # noqa: E402
from backend.models.zalo_link_token import ZaloLinkToken  # noqa: E402
from backend.services import dashboard_service, zalo_linking_service  # noqa: E402
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


_OPS = {
    operators.eq: lambda a, b: a == b,
    operators.ne: lambda a, b: a != b,
    operators.gt: lambda a, b: a > b,
    operators.lt: lambda a, b: a < b,
    operators.ge: lambda a, b: a >= b,
    operators.le: lambda a, b: a <= b,
    operators.is_: lambda a, b: a is b,
    operators.is_not: lambda a, b: a is not b,
}


def _literal(node):
    """Right-hand side of a comparison, as a plain Python value."""
    if isinstance(node, Null):
        return None
    if isinstance(node, BindParameter):
        return node.value
    raise AssertionError(f"unsupported literal in WHERE: {node!r}")


def _predicate(clause):
    """Compile a SQLAlchemy WHERE clause into a callable over ORM objects.

    Evaluating the real clause — rather than sniffing bind parameters —
    is what keeps this fake honest. Rename a column or add a predicate to
    a query and the fake follows automatically; use an operator it does
    not model and it says so instead of quietly answering the wrong rows.
    """
    if clause is None:
        return lambda _obj: True
    if isinstance(clause, BooleanClauseList):
        parts = [_predicate(c) for c in clause.clauses]
        if clause.operator is operators.or_:
            return lambda obj: any(p(obj) for p in parts)
        return lambda obj: all(p(obj) for p in parts)
    if isinstance(clause, BinaryExpression):
        op = _OPS.get(clause.operator)
        if op is None:  # pragma: no cover — teach the fake when it fires
            raise AssertionError(f"unsupported operator in WHERE: {clause.operator!r}")
        key = clause.left.key
        wanted = _literal(clause.right)
        return lambda obj: op(getattr(obj, key), wanted)
    raise AssertionError(f"unsupported WHERE clause: {clause!r}")  # pragma: no cover


class _Savepoint:
    """``db.begin_nested()`` — undoes only the inserts made inside it."""

    def __init__(self, session: "_FakeSession") -> None:
        self._session = session

    async def __aenter__(self) -> "_Savepoint":
        self._session._savepoints.append([])
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        undo = self._session._savepoints.pop()
        if exc_type is not None:
            for store, key in undo:
                store.pop(key, None)
        return False


class _FakeSession:
    """In-memory stand-in for ``AsyncSession``.

    CI has no Postgres and no aiosqlite, but the services under test only
    ever ask a session for a handful of things, so honouring those is
    enough to run them for real. ``commit`` fails loudly — nothing below
    the worker may own the transaction.

    Three behaviours matter beyond plain storage, because production bugs
    hid in exactly those gaps: savepoints roll back only their own
    inserts, ``flush`` enforces the unique index on ``users.zalo_user_id``
    (see :meth:`stage_concurrent_zalo_signup`), and ``execute`` evaluates
    the real WHERE clause instead of guessing from bind parameters.
    """

    def __init__(self, *, status: str = "active") -> None:
        self.users: dict = {}
        self.sessions: dict = {}
        self.tokens: dict = {}
        self.status = status
        self.flushes = 0
        self.info: dict = {}
        self._savepoints: list[list] = []
        self._racing_zalo_user_id: str | None = None

    # -- reads ----------------------------------------------------------
    def _store_for(self, entity):
        if entity is User:
            return self.users
        if entity is OnboardingSession:
            return self.sessions
        if entity is ZaloLinkToken:
            return self.tokens
        raise AssertionError(f"unexpected entity in query: {entity!r}")

    async def get(self, model, pk):
        if model is User:
            return self.users.get(pk)
        if model is OnboardingSession:
            return self.sessions.get(pk)
        raise AssertionError(f"unexpected model in db.get: {model!r}")

    async def execute(self, stmt):
        desc = stmt.column_descriptions[0]
        entity = desc["entity"]
        matches = _predicate(stmt.whereclause)
        rows = [obj for obj in self._store_for(entity).values() if matches(obj)]

        for clause in reversed(stmt._order_by_clauses):
            descending = getattr(clause, "modifier", None) is operators.desc_op
            column = getattr(clause, "element", clause)
            rows.sort(key=lambda obj: getattr(obj, column.key), reverse=descending)

        expr = desc["expr"]
        if expr is not entity:  # select(User.id) & friends — a column, not a row
            rows = [getattr(obj, expr.key) for obj in rows]
        return _Result(rows)

    async def scalar(self, _stmt):
        # ``is_user_allowed`` reads the manual status column.
        return self.status

    # -- writes ---------------------------------------------------------
    def _remember(self, store, key) -> None:
        if self._savepoints:
            self._savepoints[-1].append((store, key))

    def add(self, obj) -> None:
        if isinstance(obj, User):
            if obj.id is None:
                obj.id = uuid4()
            self.users[obj.id] = obj
            self._remember(self.users, obj.id)
        elif isinstance(obj, OnboardingSession):
            self.sessions[obj.user_id] = obj
            self._remember(self.sessions, obj.user_id)
        elif isinstance(obj, ZaloLinkToken):
            self.tokens[obj.token] = obj
            self._remember(self.tokens, obj.token)
        else:  # pragma: no cover — nothing else is created in this flow
            raise AssertionError(f"unexpected insert: {obj!r}")

    async def delete(self, obj) -> None:
        if isinstance(obj, ZaloLinkToken):
            self.tokens.pop(obj.token, None)
        elif isinstance(obj, User):  # pragma: no cover — never in this flow
            self.users.pop(obj.id, None)
        else:  # pragma: no cover
            raise AssertionError(f"unexpected delete: {obj!r}")

    def begin_nested(self) -> _Savepoint:
        return _Savepoint(self)

    def stage_concurrent_zalo_signup(self, zalo_user_id: str) -> None:
        """Model another worker committing this signup mid-flight.

        The row appears between our SELECT and our INSERT, so the flush
        that follows hits ``idx_users_zalo_user_id`` — exactly the race
        #1029 describes. The winner is written outside the savepoint, so
        it survives the loser's rollback the way a committed row would.
        """
        self._racing_zalo_user_id = zalo_user_id

    def _enforce_unique_zalo_user_id(self) -> None:
        racing = self._racing_zalo_user_id
        if racing is None:
            return
        if not any(user.zalo_user_id == racing for user in self.users.values()):
            return
        self._racing_zalo_user_id = None
        winner = User(zalo_user_id=racing)
        winner.id = uuid4()
        self.users[winner.id] = winner
        raise IntegrityError("INSERT INTO users", {}, Exception("duplicate key"))

    async def flush(self) -> None:
        self.flushes += 1
        self._enforce_unique_zalo_user_id()

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


async def _noop_send(chat_id, text, **kwargs):
    """Stand-in for the Telegram greeting when its content isn't the point."""
    return {"ok": True}


def _invite_token(zalo_out) -> str:
    """Pull the adoption token back out of the accept button's deep link.

    The link is what carries identity across the channel boundary (#1028),
    so the tests read it the way Telegram will: parse the ``start=``
    payload with the same helper the ``/start`` handler uses.
    """
    buttons = zalo_out.buttons_for("Bé Tiền hỏi một lần thôi")
    urls = [b.web_app_url for row in buttons for b in row if b.web_app_url]
    assert len(urls) == 1, f"expected exactly one deep link, got {urls}"
    prefix = f"{BOT_URL}?start="
    assert urls[0].startswith(prefix), urls[0]
    token = zalo_adoption.adoption_token(urls[0][len(prefix) :])
    assert token, f"the invite carries no adoption token: {urls[0]}"
    return token


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
    token = _invite_token(zalo_out)
    assert db.tokens[token].purpose == zalo_linking_service.PURPOSE_TELEGRAM_ADOPT
    assert db.tokens[token].used_at is None, "the token is spent on tap, not on send"
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
async def test_accepting_the_invite_lands_on_one_account_not_two(
    db, zalo_out, monkeypatch, analytics_events
):
    """#1028 end to end: Zalo-first → invite → ``/start`` → one ``User``.

    The bug this pins down is silent: the tap arrived at Telegram with no
    identity on it, ``get_or_create_user`` saw a telegram_id it had never
    met, and one person walked away with two accounts holding half a
    financial history each.
    """
    greetings: list[tuple[int, str]] = []

    async def _greet(chat_id, text, **kwargs):
        greetings.append((chat_id, text))
        return {"ok": True}

    monkeypatch.setattr(zalo_adoption, "send_message", _greet)

    user = await _walk_to_asset_step(db)
    await _say(db, "200tr")
    token = _invite_token(zalo_out)

    # What Telegram does before ``/start``: the suspension check looks the
    # tapper up and caches the miss. Adoption has to survive that.
    assert await dashboard_service.get_user_by_telegram_id(db, 4242) is None

    adopted = await zalo_adoption.try_adopt(
        db,
        4242,
        payload=zalo_adoption.build_payload(token),
        telegram_id=4242,
        from_user={"username": "phuong", "first_name": "Phương"},
    )

    assert adopted is user, "the tap must land on the Zalo row, not a new one"
    assert await dashboard_service.get_or_create_user(db, 4242) == (user, False)
    assert len(db.users) == 1, "one person, one account"
    assert user.zalo_user_id == SENDER_ID
    assert user.telegram_id == 4242
    assert user.telegram_handle == "phuong"
    assert db.tokens[token].used_at is not None, "the invite is single use"

    assert greetings and greetings[0][0] == 4242
    assert "{" not in greetings[0][1], "a missing format key leaks the template"
    assert "zalo_telegram_adopted" in [e[0] for e in analytics_events]


@pytest.mark.asyncio
async def test_a_stale_invite_is_refused_rather_than_re_pointed(
    db, zalo_out, monkeypatch
):
    """A spent token must never move a telegram_id onto another account."""
    monkeypatch.setattr(zalo_adoption, "send_message", _noop_send)

    user = await _walk_to_asset_step(db)
    await _say(db, "200tr")
    token = _invite_token(zalo_out)
    await zalo_adoption.try_adopt(
        db, 4242, payload=zalo_adoption.build_payload(token), telegram_id=4242
    )

    # Someone else opens the same link.
    intruder = await zalo_adoption.try_adopt(
        db, 777, payload=zalo_adoption.build_payload(token), telegram_id=777
    )

    assert intruder is None, "refusing is the only safe answer"
    assert user.telegram_id == 4242


@pytest.mark.asyncio
async def test_an_ordinary_start_is_not_mistaken_for_an_adoption(db):
    """``/start`` with no payload, or another namespace, is not ours."""
    for payload in (None, "", "invite_ABC123", "src_facebook"):
        assert await zalo_adoption.try_adopt(
            db, 4242, payload=payload, telegram_id=4242
        ) is None
    assert db.users == {}


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
async def test_two_workers_on_one_first_message_make_one_account(db):
    """#1029: the loser of the signup race joins the winner, it doesn't insert.

    Zalo delivers retries, and two webhook deliveries of a stranger's first
    message used to race between the "is there a user?" SELECT and the
    INSERT. The savepoint is what makes the loser recoverable.
    """
    db.stage_concurrent_zalo_signup(SENDER_ID)

    user, created = await zalo_linking_service.get_or_create_zalo_user(
        db, SENDER_ID, display_name=None
    )

    assert created is False, "the loser must adopt the winner's row"
    assert len(db.users) == 1, "the loser's INSERT must be rolled back"
    assert user is db.only_user()
    assert user.zalo_user_id == SENDER_ID


@pytest.mark.asyncio
async def test_a_trust_card_that_never_arrived_is_sent_again(db, zalo_out):
    """#1029: a promise nobody received cannot be accepted on their behalf."""
    header = zalo_onboarding._trust_card_lines()[0]
    zalo_out.fail_containing = header

    await _say(db, "chào Bé Tiền")
    await _say(db, "Phương")
    await _say(db, _salutation_label())
    await _say(db, _goal_label())

    user = db.only_user()
    session = db.session_of(user)
    assert session.current_step == STEP_TRUST_PRIVACY
    assert session.trust_shown_at is None, "a failed send leaves no receipt"

    # Whatever they type next is about something else entirely.
    await _say(db, "alo?")

    assert session.current_step == STEP_TRUST_PRIVACY
    assert session.trust_shown_at is None
    assert len([t for t in zalo_out.texts if header in t]) == 2, "card re-sent"

    # Once the window reopens the card lands, and only then does a reply
    # count as acceptance.
    zalo_out.fail_containing = None
    await _say(db, "alo?")
    assert session.trust_shown_at is not None
    assert session.current_step == STEP_TRUST_PRIVACY

    await _say(db, _trust_label())
    assert session.current_step == STEP_FIRST_ASSET


@pytest.mark.asyncio
async def test_onboarding_never_owns_the_transaction(db):
    """``_FakeSession.commit`` raises; reaching the end proves nobody called
    it. The flush count proves the writes were real all the same."""
    await _walk_to_asset_step(db)
    await _say(db, "200tr")

    assert db.flushes > 0
