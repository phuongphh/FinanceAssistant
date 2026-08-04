"""Phase 5.1 #4.5 — one catch-up line for a user who only has Zalo.

Three claims, and they are separate:

1. **The rule** — ``build_catchup_line`` says something only when there
   is something to say. Every ``None`` in this file has a named reason
   (has Telegram / never spoke before / spoke yesterday / nothing moved),
   because "returns None" is the common case and a test that only proved
   the happy path would pass against a function that always returned
   ``None``. So each negative case is paired with a positive one that
   differs in exactly the field under test.

2. **The reconstruction** — the line is built from rows that already
   exist (``zalo_updates``, ``asset_snapshots``, ``user_milestones``),
   which is the whole reason no ``zalo_missed_notice`` table was added.
   :class:`_CatchupSession` therefore recognises exactly the four
   statements the service issues and raises on anything else, the same
   contract ``conftest.FakeMediaSession`` keeps: the fake must never
   quietly satisfy a query the real database would have rejected.

3. **The voice** — the copy is the point of a ``persona-critical``
   issue. A user coming back after five days is the worst possible
   audience for a scolding, so the blame check below is an assertion,
   not a review note.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from backend.models.user_milestone import MilestoneType
from backend.services import zalo_catchup_service as catchup
from backend.utils.zalo_copy import load_copy
from backend.utils.zalo_limits import ZALO_MAX_EMOJI, ZALO_MESSAGE_MAX_CHARS

# The flat-string rules already live next door and are enforced there on
# every governed section. They are imported rather than restated because
# the nested ``catchup.milestones`` map is invisible to that module —
# ``_strings()`` only collects ``isinstance(value, str)`` leaves — and a
# second hand-written copy of the rules would drift from the first.
from tests.test_phase_5_1.test_zalo_copy import (  # noqa: E402
    _EMOJI_RE,
    _FORBIDDEN_CHARS,
    _PLACEHOLDER_RE,
)

NOW = datetime(2026, 8, 3, 9, 0, tzinfo=timezone.utc)
CURRENT_MSG = "msg-being-handled"


# ---------------------------------------------------------------------------
# Row stand-ins
# ---------------------------------------------------------------------------


class _FakeUser:
    def __init__(self, *, telegram_id: int | None = None, salutation: str = "anh"):
        self.id = uuid4()
        self.telegram_id = telegram_id
        self.salutation = salutation


class _FakeAsset:
    def __init__(self, current_value):
        self.id = uuid4()
        self.current_value = Decimal(str(current_value))


class _Snapshot:
    """Two columns, because the service selects two columns.

    ``select(AssetSnapshot.asset_id, AssetSnapshot.value)`` yields Row
    objects read by attribute, so the stand-in is attribute-shaped too.
    """

    def __init__(self, asset, value, when):
        self.asset_id = asset.id
        self.value = Decimal(str(value))
        self.snapshot_date = when.date() if isinstance(when, datetime) else when


class _Milestone:
    def __init__(self, milestone_type, *, achieved_at, celebrated_at=None):
        self.id = uuid4()
        self.milestone_type = milestone_type
        self.achieved_at = achieved_at
        self.celebrated_at = celebrated_at


# ---------------------------------------------------------------------------
# The fake session
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, *, rows=(), scalar=None):
        self._rows = list(rows)
        self._scalar = scalar

    def all(self):
        return list(self._rows)

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None


class _CatchupSession:
    """Answers the four reads ``build_catchup_line`` makes, and no others.

    Each branch applies the filters off the *compiled* statement rather
    than unconditionally. That distinction is the point: a fake that
    filtered by ``celebrated_at IS NULL`` on its own would go on passing
    if the production query lost the clause, and the "already celebrated
    milestones are not repeated" test below would be proving the fake.
    """

    def __init__(
        self,
        *,
        updates=(),
        assets=(),
        snapshots=(),
        milestones=(),
    ):
        # ``updates`` is ``[(msg_id, received_at), ...]`` — the raw rows,
        # so the fake computes the max itself and ``exclude_msg_id`` has
        # something real to exclude.
        self.updates = list(updates)
        self.assets = list(assets)
        self.snapshots = list(snapshots)
        self.milestones = list(milestones)
        self.commits = 0
        self.flushes = 0
        self.seen: list[str] = []

    async def commit(self):  # pragma: no cover — asserted, not exercised
        self.commits += 1
        raise AssertionError("service must not commit — the worker owns the boundary")

    async def flush(self):  # pragma: no cover
        self.flushes += 1
        raise AssertionError("catch-up reads only; nothing here writes")

    async def execute(self, stmt):
        compiled = stmt.compile()
        text = str(compiled)
        params = compiled.params

        if "FROM asset_snapshots" in text:
            self.seen.append("snapshots")
            return self._snapshots(text, params)
        if "FROM zalo_updates" in text:
            self.seen.append("updates")
            return self._updates(text, params)
        if "FROM user_milestones" in text:
            self.seen.append("milestones")
            return self._milestones(text)
        if "FROM assets" in text:
            self.seen.append("assets")
            return _Result(rows=self.assets)

        raise AssertionError(f"_CatchupSession got an unexpected statement:\n{text}")

    # -- per-statement handling -------------------------------------------

    def _updates(self, text, params):
        assert "max(zalo_updates.received_at)" in text, (
            "the silence anchor must be the newest inbound row, not an "
            "arbitrary one — an ORDER BY without max() would drift"
        )
        excluded = params.get("msg_id_1")
        stamps = [when for msg_id, when in self.updates if msg_id != excluded]
        return _Result(scalar=max(stamps) if stamps else None)

    def _snapshots(self, text, params):
        assert "snapshot_date >=" in text and "snapshot_date <=" in text, (
            "the baseline must come from inside the lookback window; "
            "an unbounded read would compare against ancient history"
        )
        bounds = sorted(v for k, v in params.items() if k.startswith("snapshot_date"))
        low, high = bounds[0], bounds[-1]
        rows = [s for s in self.snapshots if low <= s.snapshot_date <= high]
        # The service takes the *first* row per asset as the baseline and
        # relies on the query's ORDER BY for that, so the fake has to
        # honour the ordering too.
        assert "ORDER BY asset_snapshots.snapshot_date ASC" in text
        rows.sort(key=lambda s: s.snapshot_date)
        return _Result(rows=rows)

    def _milestones(self, text):
        assert "celebrated_at IS NULL" in text, (
            "catch-up is a queue of untold news; without this clause it "
            "would re-read milestones Telegram already celebrated"
        )
        rows = [m for m in self.milestones if m.celebrated_at is None]
        rows.sort(key=lambda m: m.achieved_at, reverse=True)
        return _Result(rows=rows)


class _NoDbSession:
    """For the paths that must not touch the database at all."""

    async def execute(self, _stmt):  # pragma: no cover
        raise AssertionError("this path must return before any query")

    async def commit(self):  # pragma: no cover
        raise AssertionError("service must not commit")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _silent_since(days: int):
    """The user's previous message, ``days`` ago."""
    return [(f"msg-{days}d", NOW - timedelta(days=days))]


def _grew(amount, *, days_ago=2):
    """One asset worth ``amount`` more now than at its window baseline.

    ``days_ago`` must sit inside :data:`catchup.LOOKBACK_DAYS`, which is
    the point of the default: a snapshot older than the window is not a
    baseline, and the case where none is in range gets its own test
    rather than leaking into every other one.
    """
    asset = _FakeAsset(Decimal("10000000") + Decimal(str(amount)))
    snapshot = _Snapshot(asset, Decimal("10000000"), NOW - timedelta(days=days_ago))
    return [asset], [snapshot]


async def _line(session, user, *, exclude=CURRENT_MSG):
    return await catchup.build_catchup_line(
        session, user=user, exclude_msg_id=exclude, now=NOW
    )


# ---------------------------------------------------------------------------
# DoD — the returning Zalo-only user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_zalo_only_user_silent_five_days_gets_one_catch_up_line():
    assets, snapshots = _grew("2350000", days_ago=2)
    session = _CatchupSession(
        updates=_silent_since(5), assets=assets, snapshots=snapshots
    )

    line = await _line(session, _FakeUser())

    assert line is not None
    # One line, not a replay: the DoD's "tối đa 1 dòng".
    assert "\n" not in line
    assert len(line) <= ZALO_MESSAGE_MAX_CHARS
    assert "2tr350" in line


@pytest.mark.asyncio
async def test_a_user_who_also_has_telegram_gets_nothing():
    # The counter-case to the test above: same silence, same growth, and
    # the only difference is the channel that already told them.
    assets, snapshots = _grew("2350000", days_ago=2)
    session = _CatchupSession(
        updates=_silent_since(5), assets=assets, snapshots=snapshots
    )

    assert await _line(session, _FakeUser(telegram_id=555)) is None
    # And it bailed before spending a query on someone it can't help.
    assert session.seen == []


@pytest.mark.asyncio
async def test_nothing_missed_means_no_extra_line():
    # Five days away, but the numbers stood still and no milestone
    # landed. Silence is the correct output — a "nothing happened"
    # bubble is a notification about nothing.
    session = _CatchupSession(updates=_silent_since(5), assets=[_FakeAsset("10000000")])

    assert await _line(session, _FakeUser()) is None


@pytest.mark.asyncio
async def test_a_user_who_spoke_yesterday_is_not_caught_up():
    assets, snapshots = _grew("2350000", days_ago=1)
    session = _CatchupSession(
        updates=[("msg-yesterday", NOW - timedelta(hours=20))],
        assets=assets,
        snapshots=snapshots,
    )

    assert await _line(session, _FakeUser()) is None


@pytest.mark.asyncio
async def test_a_brand_new_sender_is_not_caught_up():
    # No previous inbound row at all. Nothing was missed because there
    # was no "away" — this is their first message.
    assets, snapshots = _grew("2350000")
    session = _CatchupSession(updates=[], assets=assets, snapshots=snapshots)

    assert await _line(session, _FakeUser()) is None


@pytest.mark.asyncio
async def test_the_message_being_handled_does_not_count_as_the_previous_one():
    # The worker stamps ``user_id`` on the update row only after handling,
    # but the orphan-recovery path replays a row that is already stamped.
    # If ``exclude_msg_id`` were ignored there, "previous inbound" would
    # resolve to *now* and catch-up would silently never fire again.
    assets, snapshots = _grew("2350000")
    session = _CatchupSession(
        updates=[(CURRENT_MSG, NOW)] + _silent_since(5),
        assets=assets,
        snapshots=snapshots,
    )

    assert await _line(session, _FakeUser()) is not None
    # Same rows, no exclusion: the current message becomes the anchor and
    # the gap collapses to zero.
    assert await _line(session, _FakeUser(), exclude=None) is None


# ---------------------------------------------------------------------------
# What counts as news
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_move_smaller_than_the_floor_stays_quiet():
    assets, snapshots = _grew(catchup.MIN_DELTA - Decimal("1"))
    session = _CatchupSession(
        updates=_silent_since(5), assets=assets, snapshots=snapshots
    )

    assert await _line(session, _FakeUser()) is None


@pytest.mark.asyncio
async def test_a_drop_is_reported_plainly_and_without_alarm():
    assets, snapshots = _grew(-Decimal("2350000"))
    session = _CatchupSession(
        updates=_silent_since(5), assets=assets, snapshots=snapshots
    )

    line = await _line(session, _FakeUser())

    assert line is not None and "2tr350" in line
    lowered = line.lower()
    for word in ("mất", "lỗ", "cảnh báo", "nguy", "tụt"):
        assert word not in lowered, f"'{word}' dramatises a three-day dip"


@pytest.mark.asyncio
async def test_an_asset_with_no_snapshot_in_the_window_contributes_nothing():
    # We do not know that it moved, so claiming it did would be a
    # fabricated number. The honest reading is zero.
    session = _CatchupSession(
        updates=_silent_since(5),
        assets=[_FakeAsset("500000000")],
        snapshots=[],
    )

    assert await _line(session, _FakeUser()) is None


@pytest.mark.asyncio
async def test_a_milestone_reached_during_the_silence_is_told():
    session = _CatchupSession(
        updates=_silent_since(5),
        milestones=[
            _Milestone(MilestoneType.STREAK_7, achieved_at=NOW - timedelta(days=1))
        ],
    )

    line = await _line(session, _FakeUser())

    assert line is not None
    assert load_copy()["catchup"]["milestones"]["streak_7"] in line


@pytest.mark.asyncio
async def test_an_already_celebrated_milestone_is_not_repeated():
    session = _CatchupSession(
        updates=_silent_since(5),
        milestones=[
            _Milestone(
                MilestoneType.STREAK_7,
                achieved_at=NOW - timedelta(days=1),
                celebrated_at=NOW - timedelta(days=1),
            )
        ],
    )

    assert await _line(session, _FakeUser()) is None


@pytest.mark.asyncio
async def test_a_milestone_older_than_the_lookback_is_not_dredged_up():
    # Uncelebrated but ancient — a user returning after two months wants
    # to know where they stand now, not to read the backlog.
    session = _CatchupSession(
        updates=[("msg-old", NOW - timedelta(days=60))],
        milestones=[
            _Milestone(MilestoneType.DAYS_7, achieved_at=NOW - timedelta(days=45))
        ],
    )

    assert await _line(session, _FakeUser()) is None


@pytest.mark.asyncio
async def test_at_most_two_milestones_reach_the_bubble():
    titles = load_copy()["catchup"]["milestones"]
    session = _CatchupSession(
        updates=_silent_since(5),
        milestones=[
            _Milestone(MilestoneType.STREAK_7, achieved_at=NOW - timedelta(days=1)),
            _Milestone(MilestoneType.SAVINGS_1M, achieved_at=NOW - timedelta(days=1)),
            _Milestone(MilestoneType.DAYS_30, achieved_at=NOW - timedelta(days=1)),
        ],
    )

    line = await _line(session, _FakeUser())

    assert line is not None
    mentioned = [code for code, title in titles.items() if title in line]
    assert len(mentioned) == catchup.MAX_MILESTONES


@pytest.mark.asyncio
async def test_a_level_downgrade_never_appears_in_catch_up():
    # Bé Tiền does not open a conversation with "welcome back, you
    # dropped a tier". Telegram celebrates the ups; the downs are simply
    # not catch-up material.
    session = _CatchupSession(
        updates=_silent_since(5),
        milestones=[
            _Milestone(
                MilestoneType.WEALTH_LEVEL_DOWN_HNW,
                achieved_at=NOW - timedelta(days=1),
            )
        ],
    )

    assert await _line(session, _FakeUser()) is None


@pytest.mark.asyncio
async def test_an_unnamed_milestone_falls_back_to_the_generic_line():
    # Adding a MilestoneType must never take the channel down, and must
    # never leak a literal ``{title}`` into a bubble.
    session = _CatchupSession(
        updates=_silent_since(5),
        milestones=[
            _Milestone("some_future_milestone", achieved_at=NOW - timedelta(days=1))
        ],
    )

    line = await _line(session, _FakeUser())

    assert line is not None
    assert "{" not in line and "}" not in line


# ---------------------------------------------------------------------------
# Shape of the bubble
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_line_always_fits_one_zalo_bubble():
    assets, snapshots = _grew("1234567890")
    session = _CatchupSession(
        updates=_silent_since(5),
        assets=assets,
        snapshots=snapshots,
        milestones=[
            _Milestone(
                MilestoneType.FIRST_CATEGORY_CHANGE, achieved_at=NOW - timedelta(days=1)
            ),
            _Milestone(
                MilestoneType.FIRST_VOICE_INPUT, achieved_at=NOW - timedelta(days=1)
            ),
        ],
    )

    line = await _line(session, _FakeUser())

    assert line is not None and len(line) <= ZALO_MESSAGE_MAX_CHARS


def test_composition_drops_whole_clauses_rather_than_clipping():
    # A truncated amount is worse than a missing one, so the tail goes
    # away intact. The first clause must survive.
    fmt = {"salutation": "anh", "Salutation": "Anh"}
    parts = ["tài sản nhích lên 2tr350"] + ["x" * 120] * 3

    line = catchup._compose(parts, fmt=fmt)

    assert line is not None
    assert len(line) <= ZALO_MESSAGE_MAX_CHARS
    assert "tài sản nhích lên 2tr350" in line
    assert line.count("x" * 120) < 3


def test_composition_gives_up_rather_than_emitting_half_a_sentence():
    fmt = {"salutation": "anh", "Salutation": "Anh"}

    assert catchup._compose(["y" * (ZALO_MESSAGE_MAX_CHARS + 1)], fmt=fmt) is None


@pytest.mark.asyncio
async def test_the_service_never_owns_the_transaction():
    assets, snapshots = _grew("2350000")
    session = _CatchupSession(
        updates=_silent_since(5), assets=assets, snapshots=snapshots
    )

    await _line(session, _FakeUser())

    assert session.commits == 0
    assert session.flushes == 0


@pytest.mark.asyncio
async def test_a_missing_salutation_still_renders():
    # Users created before the salutation column, and the fake users the
    # other Zalo suites build without one, must not produce "{salutation}".
    assets, snapshots = _grew("2350000")
    session = _CatchupSession(
        updates=_silent_since(5), assets=assets, snapshots=snapshots
    )
    user = _FakeUser()
    del user.salutation

    line = await _line(session, user)

    assert line is not None
    assert "{" not in line and "bạn" in line


# ---------------------------------------------------------------------------
# The voice — #4.5 is persona-critical
# ---------------------------------------------------------------------------

_SALUTATIONS = ("anh", "chị", "bạn")

# Every phrasing that turns "here's what happened" into "where were you".
# The issue names the first one explicitly; the rest are the same move in
# different clothes.
_BLAME = (
    "đi đâu",
    "mất tiêu",
    "biến mất",
    "sao lâu",
    "lâu rồi",
    "bỏ bê",
    "quên",
    "lười",
    "nhớ ghi",
    "nhớ vào",
    "đáng lẽ",
    "lẽ ra",
    "mãi mới",
)


@pytest.mark.parametrize("salutation", _SALUTATIONS)
@pytest.mark.asyncio
async def test_the_catch_up_line_carries_no_blame_in_any_salutation(salutation):
    assets, snapshots = _grew("2350000")
    session = _CatchupSession(
        updates=_silent_since(5), assets=assets, snapshots=snapshots
    )

    line = await _line(session, _FakeUser(salutation=salutation))

    assert line is not None
    assert salutation in line
    lowered = line.lower()
    for phrase in _BLAME:
        assert phrase not in lowered, f"'{phrase}' scolds a user who came back"


@pytest.mark.parametrize("salutation", _SALUTATIONS)
def test_every_catch_up_string_renders_for_all_three_salutations(salutation):
    for key, value in load_copy()["catchup"].items():
        if not isinstance(value, str):
            continue
        rendered = value.replace("{salutation}", salutation).replace(
            "{Salutation}", salutation.capitalize()
        )
        assert "{salutation}" not in rendered
        assert "{Salutation}" not in rendered
        assert len(rendered) <= ZALO_MESSAGE_MAX_CHARS


def test_the_whole_catch_up_section_is_free_of_blame():
    # The rendering test above only sees the clauses that happened to be
    # composed; this reads the section itself, including copy that only
    # fires for a milestone nobody has hit yet.
    section = load_copy()["catchup"]
    joined = " ".join(v for v in section.values() if isinstance(v, str)).lower()
    joined += " " + " ".join(section["milestones"].values()).lower()

    for phrase in _BLAME:
        assert phrase not in joined


# ---------------------------------------------------------------------------
# The nested milestone map — the gap test_zalo_copy.py cannot see
# ---------------------------------------------------------------------------


def test_every_milestone_title_obeys_the_channel_rules():
    for code, title in load_copy()["catchup"]["milestones"].items():
        assert isinstance(title, str) and title.strip(), f"{code} has no title"
        assert len(title) <= ZALO_MESSAGE_MAX_CHARS
        assert len(_EMOJI_RE.findall(title)) <= ZALO_MAX_EMOJI
        rendered = _PLACEHOLDER_RE.sub("", title)
        found = [ch for ch in _FORBIDDEN_CHARS if ch in rendered]
        assert not found, f"catchup.milestones.{code} contains {found}"


def test_every_celebratable_milestone_type_has_a_short_title():
    # The generic fallback exists so a new code cannot crash the channel,
    # not so the map can stay incomplete. Downgrades are excluded by the
    # service, so they need no title.
    titled = set(load_copy()["catchup"]["milestones"])
    expected = {
        code
        for code in MilestoneType.all()
        if code not in catchup._SKIP_MILESTONE_TYPES
    }

    assert expected - titled == set(), "missing short titles"
    assert titled - expected == set(), "titles for codes that never reach catch-up"


def test_the_skip_list_covers_every_downgrade():
    downs = {code for code in MilestoneType.all() if "level_down" in code}

    assert downs and downs == set(catchup._SKIP_MILESTONE_TYPES)


# ---------------------------------------------------------------------------
# The wiring — what the handler does with the line
# ---------------------------------------------------------------------------
#
# Everything above proves the line is *right*. These prove it is delivered
# on the right terms: after the answer, in its own bubble, and never at
# the answer's expense. The service is stubbed here on purpose — mixing
# the two would mean a copy change could turn a wiring test red for a
# reason that has nothing to do with wiring.


class _HandlerSession:
    """Answers the one read the handler itself makes, and nothing else.

    Catch-up's own queries never arrive because the service is stubbed in
    every test below, so ``execute`` stays the loud guard it is in the
    neighbouring suites.
    """

    async def scalar(self, _stmt):
        return "active"

    async def commit(self):  # pragma: no cover
        raise AssertionError("handler must not commit — the worker does")

    async def flush(self):  # pragma: no cover
        raise AssertionError("handler must not flush")

    async def execute(self, _stmt):  # pragma: no cover
        raise AssertionError("the handler tests stub catch-up; nothing queries")


class _HandlerNotifier:
    def __init__(self, *, window_closes_after: int | None = None):
        self.sent: list[str] = []
        # ``None`` from ``send_message`` is how the windowed notifier says
        # "the 48h window shut" — not an error, just a drop.
        self.window_closes_after = window_closes_after

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append(text)
        if (
            self.window_closes_after is not None
            and len(self.sent) > self.window_closes_after
        ):
            return None
        return {"ok": True}


def _zalo_event(text="số dư của tôi"):
    from backend.utils.zalo_events import ZaloEvent

    return ZaloEvent(
        msg_id=CURRENT_MSG,
        event_name="user_send_text",
        sender_id="zalo-sender-catchup",
        text=text,
        timestamp="1754211600000",
        derived_key=None,
        payload={},
    )


@pytest.fixture()
def wiring(monkeypatch):
    """A handler with every collaborator but catch-up replaced.

    Returns the pieces the assertions need: the notifier that recorded the
    bubbles, the analytics events, and a place to set what the stubbed
    service returns.
    """
    from backend.bot.handlers import zalo_inbound

    user = _FakeUser()
    notifier = _HandlerNotifier()
    state = {"line": None, "raises": False, "dispatched": []}
    events: list[tuple[str, dict]] = []

    async def _get_linked_user(db, zalo_user_id):
        return user

    async def _onboarding_declines(db, *, notifier, user, text):
        return False

    async def _dispatch(db, *, notifier, user, text):
        state["dispatched"].append(text)
        await notifier.send_message(0, "REPLY")

    async def _build_catchup_line(db, *, user, exclude_msg_id=None, **kwargs):
        if state["raises"]:
            raise RuntimeError("snapshot table exploded")
        return state["line"]

    monkeypatch.setattr(
        zalo_inbound, "build_zalo_notifier", lambda zalo_user_id, **kw: notifier
    )
    monkeypatch.setattr(zalo_inbound, "get_notifier", lambda: _HandlerNotifier())
    monkeypatch.setattr(
        zalo_inbound.zalo_linking_service, "get_linked_user", _get_linked_user
    )
    monkeypatch.setattr(
        zalo_inbound.zalo_onboarding, "handle_text", _onboarding_declines
    )
    monkeypatch.setattr(zalo_inbound, "_dispatch_intent", _dispatch)
    monkeypatch.setattr(
        zalo_inbound.zalo_catchup_service, "build_catchup_line", _build_catchup_line
    )
    monkeypatch.setattr(
        zalo_inbound.analytics,
        "track",
        lambda name, user_id=None, properties=None: events.append(
            (name, properties or {})
        ),
    )

    state.update(module=zalo_inbound, notifier=notifier, user=user, events=events)
    return state


@pytest.mark.asyncio
async def test_catch_up_arrives_as_its_own_bubble_after_the_answer(wiring):
    wiring["line"] = "Mấy hôm anh bận, Bé Tiền vẫn theo giúp: tài sản nhích lên 2tr350."

    await wiring["module"].handle_inbound_event(_HandlerSession(), event=_zalo_event())

    # Order is the claim: the thing they asked for comes first. Prepending
    # to the reply would push it off the bottom of a 300-char bubble.
    assert wiring["notifier"].sent == ["REPLY", wiring["line"]]


@pytest.mark.asyncio
async def test_no_catch_up_means_no_extra_bubble(wiring):
    wiring["line"] = None

    await wiring["module"].handle_inbound_event(_HandlerSession(), event=_zalo_event())

    assert wiring["notifier"].sent == ["REPLY"]
    assert wiring["events"] == []


@pytest.mark.asyncio
async def test_a_broken_catch_up_never_costs_the_user_their_answer(wiring, caplog):
    # The whole reason the handler swallows: catch-up is a courtesy on top
    # of the reply. Losing the reply to it would be a strictly worse trade.
    wiring["raises"] = True

    with caplog.at_level("ERROR"):
        await wiring["module"].handle_inbound_event(
            _HandlerSession(), event=_zalo_event()
        )

    assert wiring["notifier"].sent == ["REPLY"]
    assert wiring["dispatched"] == ["số dư của tôi"]
    # Swallowed, but not silent — an operator has to be able to see it.
    assert any("catchup" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_the_current_message_is_passed_through_as_the_exclusion(
    wiring, monkeypatch
):
    # If the handler forgot this, the orphan-recovery replay path would
    # measure the silence from *now* and catch-up would never fire again.
    seen = {}

    async def _capture(db, *, user, exclude_msg_id=None, **kwargs):
        seen["exclude"] = exclude_msg_id
        return None

    monkeypatch.setattr(
        wiring["module"].zalo_catchup_service, "build_catchup_line", _capture
    )

    await wiring["module"].handle_inbound_event(_HandlerSession(), event=_zalo_event())

    assert seen["exclude"] == CURRENT_MSG


@pytest.mark.asyncio
async def test_a_closed_window_is_recorded_as_undelivered_not_as_sent(wiring):
    # The reply gets the last slot and the catch-up line is dropped. It is
    # still uncelebrated, so the next time they write it is still waiting —
    # which is only true if nothing here marked it told.
    wiring["notifier"].window_closes_after = 1
    wiring["line"] = "Mấy hôm anh bận, Bé Tiền vẫn theo giúp: tài sản nhích lên 2tr350."

    await wiring["module"].handle_inbound_event(_HandlerSession(), event=_zalo_event())

    assert wiring["events"] == [
        ("zalo_catchup", {"channel": "zalo", "delivered": False})
    ]


@pytest.mark.asyncio
async def test_a_delivered_catch_up_is_recorded_as_delivered(wiring):
    wiring["line"] = "Mấy hôm anh bận, Bé Tiền vẫn theo giúp: tài sản nhích lên 2tr350."

    await wiring["module"].handle_inbound_event(_HandlerSession(), event=_zalo_event())

    assert wiring["events"] == [
        ("zalo_catchup", {"channel": "zalo", "delivered": True})
    ]
