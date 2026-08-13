"""Phase 5.1 #4.4 — the parity suite that closes Epic E4.

The rule Phase 5.1 is built on is "không có 'phiên bản Zalo' của bất kỳ
service nào": one set of services, one dispatcher, one set of numbers, and
a difference in *presentation only* at the very edge. Every issue in the
phase asserts its own slice of that. This file asserts the claim itself,
end to end, in the shape the DoD asks for — the same input driven down
both channels, then compared.

What "parity" means here, precisely, because the naive reading is wrong:

* **The conclusion is the same.** Every case names the figures and the
  verdict words that must survive the trip on *both* channels. This is the
  part a user would notice: Telegram says spending fell 8% and Zalo must
  not say 9%, or omit the direction, or lose the total.
* **Zalo never invents a number.** The set of numbers in the Zalo bubble
  is compared against the Telegram one. For anything that comes out of a
  shared handler the two sets are *equal* — the channel edge adds no
  arithmetic. For the renderer pairs the Zalo set is a *subset*: the Twin
  caption on Telegram legitimately carries figures Zalo drops on purpose
  (the scenario cards, the age line, the present anchor), and demanding
  equality there would mean demanding Zalo grow a 1024-character caption.
* **Presentation differs.** The Zalo body carries no markdown and no HTML,
  and fits the bubble. If the two strings ever came out byte-identical the
  Zalo renderer would have stopped doing its job.

Two of the six domains are compared as *formatter/renderer pairs* rather
than through the dispatcher — capture and milestone and the Twin view —
because that is where they actually diverge in production: the same
snapshot goes into two renderers. The other three ride the real
dispatcher, so what is being compared is the whole stack from classifier
to bubble.

The suite also self-verifies. The DoD asks that it "thất bại khi cố tình
đổi một con số ở một kênh", so two tests deliberately break parity — once
at the comparator and once inside the Zalo path — and assert the failure
is caught. A parity suite that cannot fail is a checklist.

The DoD's third clause ("no channel branching in services", as a test and
not a manual step) is already held by
``test_zalo_dispatcher_parity.test_no_service_branches_on_the_zalo_channel``.
It is referenced from here rather than copied, so there is one
implementation of that walk and not two that can drift.
"""

from __future__ import annotations

import re
from decimal import Decimal
from uuid import uuid4

import pytest

from backend.adapters.telegram_content_renderer import TelegramContentRenderer
from backend.adapters.zalo_content_renderer import ZaloContentRenderer
from backend.bot.formatters.money import format_money_full, format_money_short
from backend.bot.formatters.templates import (
    format_transaction_batch_confirmation,
    format_transaction_confirmation,
)
from backend.bot.formatters.zalo_transaction import (
    format_zalo_transaction,
    format_zalo_transaction_batch,
)
from backend.bot.handlers import zalo_inbound
from backend.intent.dispatcher import IntentDispatcher
from backend.intent.intents import CLASSIFIER_RULE, IntentResult, IntentType
from backend.ports.content_renderer import MilestoneSnapshot, TwinViewSnapshot
from backend.utils.zalo_events import ZaloEvent
from backend.utils.zalo_limits import ZALO_MESSAGE_MAX_CHARS

SENDER_ID = "zalo-sender-parity-suite"
TELEGRAM_CHAT_ID = 777

# The personality wrap rolls a greeting and a suggestion off the *global*
# ``random``, so two runs of the same input differ by noise. Pinning the
# seed keeps the real wrapper in the path — it is part of what Telegram
# says, so removing it would compare a message neither user receives.
PERSONALITY_SEED = 20260803


# ---------------------------------------------------------------------------
# The comparator
# ---------------------------------------------------------------------------

# A money figure as either channel writes it: "45,000đ", "12,5tr",
# "1tỷ250", "8%", "2035". The trailing punctuation of a sentence is not
# part of the number, so it is trimmed after the match.
_NUMBER_RE = re.compile(r"\d[\d.,]*")

# Markup that must not reach a Zalo bubble. Zalo renders plain text
# verbatim, so a stray asterisk is a visible asterisk and an HTML tag is
# visible angle brackets.
_MARKUP_RE = re.compile(r"[*`\[\]]|</?[a-zA-Z]")


def numbers(text: str) -> set[str]:
    """Every numeric token in ``text``, punctuation-trimmed."""
    return {match.rstrip(".,") for match in _NUMBER_RE.findall(text)}


def assert_parity(
    *,
    telegram: str,
    zalo: str,
    required: tuple[str, ...],
    exact_numbers: bool = True,
) -> None:
    """The whole claim of this file, in one place.

    ``required`` is the case's answer reduced to the tokens a user would
    quote back — the figures and the verdict words. Both channels must
    carry all of them. ``exact_numbers`` is False only where Telegram is
    *allowed* to say more; the direction is never reversed, so Zalo can
    never be the channel with the extra figure.
    """
    for token in required:
        assert token in telegram, f"Telegram lost {token!r}"
        assert token in zalo, f"Zalo lost {token!r}"

    telegram_numbers, zalo_numbers = numbers(telegram), numbers(zalo)
    if exact_numbers:
        assert zalo_numbers == telegram_numbers, (
            f"số liệu lệch giữa hai kênh: chỉ Telegram "
            f"{telegram_numbers - zalo_numbers}, chỉ Zalo "
            f"{zalo_numbers - telegram_numbers}"
        )
    else:
        assert zalo_numbers <= telegram_numbers, (
            f"Zalo tự sinh ra con số không có trên Telegram: "
            f"{zalo_numbers - telegram_numbers}"
        )

    assert not _MARKUP_RE.search(zalo), f"markup rò rỉ sang Zalo: {zalo!r}"
    assert len(zalo) <= ZALO_MESSAGE_MAX_CHARS
    assert telegram != zalo, "hai kênh phải khác trình bày, không chỉ khác tên"


# ---------------------------------------------------------------------------
# Driving the two channels
# ---------------------------------------------------------------------------


class _SpyNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text))
        return {"ok": True}


class _SpySession:
    """Answers the one read the Zalo handler makes; refuses everything else.

    Both channels are driven with this, so a handler body that quietly
    reached for a database would fail here rather than pass against a
    permissive mock. CI has no database — that is the point.
    """

    async def scalar(self, _stmt):
        return "active"

    async def commit(self):  # pragma: no cover - asserted, not exercised
        raise AssertionError("handler must not commit — the worker does")

    async def flush(self):  # pragma: no cover
        raise AssertionError("handler must not flush")

    async def execute(self, _stmt):  # pragma: no cover
        raise AssertionError("no test here should reach the database")


class _FakeUser:
    """The same user object on both channels — that is half the point.

    ``wizard_state`` is None so ``pending_action.clear_if_expired`` returns
    before it would flush; ``telegram_id`` is None because a Zalo-only
    signup is now a real shape (#4.2).
    """

    def __init__(self) -> None:
        self.id = uuid4()
        self.telegram_id = None
        self.display_name = "An"
        self.wizard_state = None


class _StubHandler:
    """One handler body, shared by both channels.

    Returning a fixed string is what makes the comparison meaningful: the
    numbers enter the stack once, so any difference downstream was
    introduced by a channel.
    """

    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    async def handle(self, intent, user, db) -> str:
        self.calls += 1
        return self.text


def _event(text: str) -> ZaloEvent:
    return ZaloEvent(
        msg_id="m-parity-suite",
        event_name="user_send_text",
        sender_id=SENDER_ID,
        text=text,
        timestamp="1754092800000",
        derived_key=None,
        payload={},
    )


def _result(intent: IntentType, confidence: float = 0.95) -> IntentResult:
    return IntentResult(
        intent=intent,
        confidence=confidence,
        raw_text="",
        classifier_used=CLASSIFIER_RULE,
    )


@pytest.fixture()
def user() -> _FakeUser:
    return _FakeUser()


@pytest.fixture()
def zalo_out(monkeypatch, user):
    """Zalo transport replaced, sender resolved to the shared user."""
    notifier = _SpyNotifier()
    monkeypatch.setattr(
        zalo_inbound, "build_zalo_notifier", lambda zalo_user_id, **kwargs: notifier
    )
    monkeypatch.setattr(zalo_inbound, "get_notifier", lambda: _SpyNotifier())

    async def _get_linked_user(db, zalo_user_id):
        return user

    monkeypatch.setattr(
        zalo_inbound.zalo_linking_service, "get_linked_user", _get_linked_user
    )
    return notifier


@pytest.fixture(autouse=True)
def _onboarding_declines(monkeypatch):
    """Onboarding gets first refusal on every inbound text (#4.3).

    It always declines here; the step machine is exercised for real in
    ``test_zalo_onboarding.py``.
    """

    async def _handle_text(db, *, notifier, user, text):
        return False

    monkeypatch.setattr(zalo_inbound.zalo_onboarding, "handle_text", _handle_text)


@pytest.fixture(autouse=True)
def _no_catchup(monkeypatch):
    """Catch-up stays out of the way (#4.5) — it is a database read."""

    async def _none(db, **kwargs):
        return None

    monkeypatch.setattr(zalo_inbound.zalo_catchup_service, "build_catchup_line", _none)


@pytest.fixture(autouse=True)
def _deterministic_personality(monkeypatch):
    """Pin the personality wrap's dice without removing the wrap.

    ``_execute`` imports ``add_personality`` lazily, so patching the module
    attribute is enough to reach it. The real function still runs — the
    greeting and the suggestion are genuinely in the compared text — it
    just rolls the same way on both channels.
    """
    from backend.bot.personality import query_voice

    real = query_voice.add_personality

    def _pinned(response, user, intent_type, *, rng_seed=None):
        return real(response, user, intent_type, rng_seed=PERSONALITY_SEED)

    monkeypatch.setattr(query_voice, "add_personality", _pinned)


@pytest.fixture()
def telegram_stack():
    """The Telegram intent stack, restored afterwards.

    ``classify_and_dispatch``'s legacy path reads the module *globals*
    ``_pipeline`` and ``_dispatcher`` directly, while the Zalo handler
    calls ``get_pipeline()`` / ``get_dispatcher()``. The two seams are not
    the same object, which is exactly why a parity test has to install
    both — and why installing only one would silently compare a stubbed
    channel against a real one.
    """
    from backend.bot.handlers import free_form_text

    saved = (
        free_form_text.get_pipeline(),
        free_form_text.get_dispatcher(),
        free_form_text._use_agent_orchestrator,
    )
    yield free_form_text
    free_form_text.set_pipeline(saved[0])
    free_form_text.set_dispatcher(saved[1])
    free_form_text.set_use_agent_orchestrator(saved[2])


@pytest.fixture()
def dispatcher() -> IntentDispatcher:
    return IntentDispatcher()


def _seed(dispatcher: IntentDispatcher, intent: IntentType, text: str) -> _StubHandler:
    """Give ``intent`` a body that answers with ``text`` and touches no DB.

    Written straight into the private registry: ``_get_handler`` reads the
    cache first, so a seeded entry short-circuits the lazy import of a
    module that would want a database.
    """
    handler = _StubHandler(text)
    dispatcher._handlers[intent] = handler
    return handler


def _install(monkeypatch, telegram_stack, dispatcher, result: IntentResult) -> None:
    """Point *both* channels at the same classifier and the same dispatcher."""

    class _Pipeline:
        # ``_track_classification`` reads this to price the LLM leg; ``None``
        # means "no LLM ran", which is the truth for a rule-classified stub.
        llm_classifier = None

        async def classify(self, _text: str) -> IntentResult:
            return result

    pipeline = _Pipeline()
    # The Zalo handler resolves the stack through the accessors.
    monkeypatch.setattr(telegram_stack, "get_pipeline", lambda: pipeline)
    monkeypatch.setattr(telegram_stack, "get_dispatcher", lambda: dispatcher)
    # The legacy Telegram path reads the globals, and the orchestrator has
    # to be off for the two paths to be comparable at all: Tier 2/3 would
    # re-answer the question with an LLM that CI cannot call.
    telegram_stack.set_pipeline(pipeline)
    telegram_stack.set_dispatcher(dispatcher)
    telegram_stack.set_use_agent_orchestrator(False)


async def _say_on_telegram(monkeypatch, telegram_stack, user, message: str) -> str:
    sent: list[str] = []

    async def _send_message(chat_id, text, **kwargs):
        sent.append(text)
        return {"ok": True}

    monkeypatch.setattr(telegram_stack, "send_message", _send_message)
    await telegram_stack.classify_and_dispatch(
        _SpySession(), chat_id=TELEGRAM_CHAT_ID, user=user, text=message
    )
    assert len(sent) == 1, f"Telegram gửi {len(sent)} tin, mong đợi 1"
    return sent[0]


async def _say_on_zalo(zalo_out: _SpyNotifier, message: str) -> str:
    await zalo_inbound.handle_inbound_event(_SpySession(), event=_event(message))
    assert len(zalo_out.sent) == 1, f"Zalo gửi {len(zalo_out.sent)} tin, mong đợi 1"
    return zalo_out.sent[0][1]


# ---------------------------------------------------------------------------
# 1. The dispatcher-borne domains — report, twin, decision, advisory
# ---------------------------------------------------------------------------

# (case id, intent, what the user types, what the shared handler answers,
#  the tokens both channels must carry).
#
# Every answer carries markdown on purpose: flattening it is part of what
# "arrived as a Zalo bubble" means, and it keeps the two strings from
# coming out identical for the wrong reason.
DISPATCH_CASES = [
    (
        "report",
        IntentType.QUERY_EXPENSES,
        "tháng này tôi tiêu bao nhiêu",
        "Tháng này bạn tiêu *12,5tr*.\n"
        "Nhiều nhất là ăn uống *4,2tr*.\n"
        "So với tháng trước: giảm 8%.",
        ("12,5tr", "4,2tr", "8%", "giảm"),
    ),
    (
        "twin_view",
        IntentType.QUERY_TWIN,
        "twin của tôi thế nào",
        "Đến *2035* Twin thấy vùng khả năng từ *820tr* đến *1tỷ900*.\n"
        "Bạn đang đi đúng hướng.",
        ("2035", "820tr", "1tỷ900", "đúng hướng"),
    ),
    (
        "decision_query",
        IntentType.DECISION_FEASIBILITY,
        "tôi mua xe 600tr được không",
        "Mua xe *600tr* lúc này là *khả thi nhưng hơi căng*.\n"
        "Quỹ khẩn cấp còn *45tr*, tức 2 tháng chi tiêu.",
        ("600tr", "khả thi nhưng hơi căng", "45tr"),
    ),
    (
        "advisory",
        IntentType.ADVISORY,
        "tôi nên để tiền vào đâu",
        "Với *120tr* đang để không, Bé Tiền nghiêng về chia đôi.\n"
        "Một nửa vào quỹ khẩn cấp, một nửa vào quỹ mở.\n"
        "Đây là thông tin tham khảo, không phải khuyến nghị đầu tư.",
        ("120tr", "chia đôi", "không phải khuyến nghị đầu tư"),
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("intent", "message", "answer", "required"),
    [case[1:] for case in DISPATCH_CASES],
    ids=[case[0] for case in DISPATCH_CASES],
)
async def test_the_same_question_gets_the_same_answer_on_both_channels(
    monkeypatch,
    telegram_stack,
    dispatcher,
    zalo_out,
    user,
    intent,
    message,
    answer,
    required,
):
    """One input, one handler, two channels — same numbers, same verdict.

    Nothing between the classifier and the bubble is stubbed: the
    confidence policy, the personality wrap, the follow-up picker and the
    markdown flattening are all the production code. What is replaced is
    the transport at each end and the handler *body*, because a handler
    that reads a database cannot run in CI.
    """
    handler = _seed(dispatcher, intent, answer)
    _install(monkeypatch, telegram_stack, dispatcher, _result(intent))

    telegram = await _say_on_telegram(monkeypatch, telegram_stack, user, message)
    zalo = await _say_on_zalo(zalo_out, message)

    assert handler.calls == 2, "cả hai kênh phải chạy qua đúng một handler"
    assert_parity(telegram=telegram, zalo=zalo, required=required)


# ---------------------------------------------------------------------------
# 2. Capture — the formatter pair
# ---------------------------------------------------------------------------

CAPTURE_MERCHANT = "Phở Bát Đàn"
CAPTURE_AMOUNT = Decimal("45000")
CAPTURE_CATEGORY = "food"


def test_a_captured_transaction_reads_the_same_on_both_channels():
    """The receipt for something the user just said, on two channels.

    Capture is the case where a "Zalo version" would have been easiest to
    justify — the Telegram card is HTML with a progress bar and four
    buttons, none of which survive. It is still parity, because the number
    that matters is rendered by the same ``format_money_full`` on both
    sides: what the user is checking is that we stored 45,000đ, and both
    bubbles say 45,000đ.
    """
    telegram = format_transaction_confirmation(
        CAPTURE_MERCHANT,
        CAPTURE_AMOUNT,
        CAPTURE_CATEGORY,
    )
    zalo = format_zalo_transaction(
        merchant=CAPTURE_MERCHANT,
        amount=CAPTURE_AMOUNT,
        category_code=CAPTURE_CATEGORY,
    )

    assert_parity(
        telegram=telegram,
        zalo=zalo,
        required=(CAPTURE_MERCHANT, format_money_full(CAPTURE_AMOUNT)),
    )


BATCH_ITEMS: list[tuple[str, Decimal, str]] = [
    ("Phở Bát Đàn", Decimal("45000"), "food"),
    ("Grab về nhà", Decimal("62000"), "transport"),
    ("Áo khoác", Decimal("390000"), "shopping"),
]


def test_a_batch_agrees_on_the_total_even_though_the_rows_are_rounded():
    """The one place the two channels deliberately write a number differently.

    Zalo shortens the per-item amounts (``45k``) and writes the total in
    full; Telegram writes every row in full. That is a real divergence and
    it is intentional — inside a 300-character bubble the rows exist to
    confirm nothing was invented, and the total is the number being
    checked. So parity here is asserted where it is actually claimed: the
    total is byte-identical, the count agrees, every merchant survives on
    both, and each rounded row is the short form *of the same amount* —
    not of some other one.
    """
    total = sum((amount for _, amount, _ in BATCH_ITEMS), start=Decimal(0))
    telegram = format_transaction_batch_confirmation(BATCH_ITEMS)
    zalo = format_zalo_transaction_batch(items=list(BATCH_ITEMS))

    assert format_money_full(total) in telegram
    assert format_money_full(total) in zalo
    assert str(len(BATCH_ITEMS)) in zalo

    for merchant, amount, _category in BATCH_ITEMS:
        assert merchant in telegram
        assert merchant in zalo
        assert format_money_full(amount) in telegram
        assert format_money_short(amount) in zalo

    assert not _MARKUP_RE.search(zalo)
    assert len(zalo) <= ZALO_MESSAGE_MAX_CHARS


# ---------------------------------------------------------------------------
# 3. Twin view — the renderer pair
# ---------------------------------------------------------------------------

TWIN_P10 = Decimal("820000000")
TWIN_P50 = Decimal("1250000000")
TWIN_P90 = Decimal("1900000000")


def _twin_snapshot() -> TwinViewSnapshot:
    """The shape a real Twin read model has, cards included.

    The scenario cards matter to this test: they are where the Telegram
    caption states the p50 figure, which its headline sentence ("từ p10
    đến p90") leaves out. Without them the comparison would report Zalo as
    inventing p50, when in fact Telegram says it one paragraph lower.
    """
    return TwinViewSnapshot(
        user_name="An",
        target_year=2035,
        p10=TWIN_P10,
        p50=TWIN_P50,
        p90=TWIN_P90,
        age_text="12 năm tới, từ tuổi 30",
        cone=[{"year": 2026, "p50": float(TWIN_P50)}],
        scenario_cards=[
            {"p_code": "p10", "label": "🌧️ Khiêm tốn", "amount": TWIN_P10},
            {"p_code": "p50", "label": "⛅ Bình thường", "amount": TWIN_P50},
            {"p_code": "p90", "label": "☀️ Lạc quan", "amount": TWIN_P90},
        ],
        salutation="bạn",
    )


def _chart(cone, optimal=None) -> bytes:
    return b"PNG-BYTES"


def test_the_twin_cone_lands_on_the_same_three_figures():
    """One snapshot, two renderers, three figures that must not move.

    Exact number equality is the wrong assertion here and asserting it
    would push the wrong fix. Telegram has a 1024-character caption and
    spends it on the cards, the age line and the narrative; Zalo has ~300
    characters and spends them on the range and the disclaimer. What must
    hold is the direction: everything Zalo says, Telegram also says.
    """
    snapshot = _twin_snapshot()
    telegram = TelegramContentRenderer(chart_renderer=_chart).render_twin_view(snapshot)
    zalo = ZaloContentRenderer(chart_renderer=_chart).render_twin_view(snapshot)

    assert_parity(
        telegram=telegram.text,
        zalo=zalo.text,
        required=(
            "2035",
            format_money_short(TWIN_P10),
            format_money_short(TWIN_P50),
            format_money_short(TWIN_P90),
        ),
        exact_numbers=False,
    )
    # The chart is the same picture on both channels — only the way it
    # travels differs (bytes here, a signed URL once the notifier has it).
    assert telegram.images == zalo.images == (b"PNG-BYTES",)


# ---------------------------------------------------------------------------
# 4. Milestone — the renderer pair
# ---------------------------------------------------------------------------

MILESTONE_TITLE = "Quỹ khẩn cấp chạm 30tr"
MILESTONE_EFFECT = "Twin nhích lên 1tỷ250 vào 2035"
MILESTONE_TEXT = (
    "🎉 Chúc mừng! Quỹ khẩn cấp chạm 30tr rồi.\n\n"
    "Twin nhích lên 1tỷ250 vào 2035 nhờ mốc này.\n\n"
    "Bé Tiền ghi lại rồi nhé."
)


def test_a_milestone_celebrates_the_same_numbers_on_both_channels():
    """Telegram passes the composed text through; Zalo rebuilds from parts.

    That asymmetry is the interesting bit. ``render_milestone`` on
    Telegram is a pass-through of ``text``; on Zalo it composes
    ``title`` + ``effect`` into three short lines. Two different strings
    from two different fields of one snapshot — and the figures in them
    have to agree, or a caller has filled the fields from two different
    reads.
    """
    snapshot = MilestoneSnapshot(
        text=MILESTONE_TEXT,
        title=MILESTONE_TITLE,
        effect=MILESTONE_EFFECT,
        salutation="bạn",
    )
    telegram = TelegramContentRenderer(chart_renderer=_chart).render_milestone(snapshot)
    zalo = ZaloContentRenderer(chart_renderer=_chart).render_milestone(snapshot)

    assert_parity(
        telegram=telegram.text,
        zalo=zalo.text,
        required=("30tr", "1tỷ250", "2035"),
    )


# ---------------------------------------------------------------------------
# 5. The suite verifies itself
# ---------------------------------------------------------------------------


def test_the_comparator_catches_a_number_changed_on_one_channel():
    """Change one digit on one channel and the comparator must object.

    Without this the whole file could be passing vacuously — a comparator
    that only ever sees matching inputs proves nothing about what it does
    when they stop matching.
    """
    telegram = "Tháng này bạn tiêu *12,5tr*, giảm 8%."
    honest = "Tháng này bạn tiêu 12,5tr, giảm 8%."
    tampered = "Tháng này bạn tiêu 12,9tr, giảm 8%."

    assert_parity(telegram=telegram, zalo=honest, required=("12,5tr", "8%"))

    with pytest.raises(AssertionError):
        assert_parity(telegram=telegram, zalo=tampered, required=("12,5tr", "8%"))


@pytest.mark.asyncio
async def test_a_number_rewritten_inside_the_zalo_path_breaks_the_suite(
    monkeypatch, telegram_stack, dispatcher, zalo_out, user
):
    """The same proof, one level deeper — through the real Zalo path.

    The comparator test above proves the assertion works on two strings.
    This one proves the *wiring* works: a defect introduced where Zalo
    actually formats its bubble reaches the comparison and is caught. If
    the two channels were ever accidentally driven from the same captured
    output, this test would go green for the wrong reason and then this
    test would be the one that fails.
    """
    _, intent, message, answer, required = DISPATCH_CASES[0]
    _seed(dispatcher, intent, answer)
    _install(monkeypatch, telegram_stack, dispatcher, _result(intent))

    real_plain_body = zalo_inbound._plain_body
    monkeypatch.setattr(
        zalo_inbound,
        "_plain_body",
        lambda text: real_plain_body(text).replace("12,5tr", "12,9tr"),
    )

    telegram = await _say_on_telegram(monkeypatch, telegram_stack, user, message)
    zalo = await _say_on_zalo(zalo_out, message)

    assert "12,9tr" in zalo, "bản vá thử nghiệm phải thật sự đổi được con số"
    with pytest.raises(AssertionError):
        assert_parity(telegram=telegram, zalo=zalo, required=required)


def test_the_no_channel_branching_guard_runs_as_a_test():
    """The DoD's third clause, referenced rather than reimplemented.

    "0 file trong ``backend/services/`` chứa nhánh theo kênh" is already
    enforced as a real test in ``test_zalo_dispatcher_parity``. Calling it
    from here keeps it visible as part of the parity suite without giving
    the repository two copies of the same directory walk to keep in sync.
    """
    from tests.test_phase_5_1 import test_zalo_dispatcher_parity as guard

    guard.test_no_service_branches_on_the_zalo_channel()
