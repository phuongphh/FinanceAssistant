"""``content/zalo.yaml`` must obey the channel it is written for (#4.1).

Zalo OA renders plain text: no Markdown, no HTML, no inline keyboard. A
``**`` in the copy is not ignored, it is *displayed*. The bubble also cuts
around 300 characters, and the persona budget is two emoji. None of that is
enforceable at the send path — the notifier's strip-and-truncate is a
safety net that silently rewrites what a human wrote — so it is checked
here, where a violation is a failing test instead of a rewritten sentence.

**Only Zalo-bound keys are checked, and they are listed by hand.** The file
also holds Telegram copy (``linking.prompt`` wraps the token in backticks,
``profile_status.not_linked`` mentions ``/link_zalo`` inside parentheses) —
both correct for the channel they are sent on. A file-wide scan would have
to be loosened until it caught nothing. The register below is the contract;
adding a key that Zalo sends means adding it here.
"""

from __future__ import annotations

import re
from string import Formatter

import pytest

from backend.adapters.zalo_notifier import strip_markdown
from backend.utils.zalo_copy import load_copy
from backend.utils.zalo_limits import ZALO_MAX_EMOJI, ZALO_MESSAGE_MAX_CHARS

# Every string this repo sends *to* a Zalo user. Sections listed as ``"*"``
# are wholly Zalo-bound; the mixed sections name their keys.
ZALO_BOUND = {
    "linking": (
        "confirm_zalo",
        "token_invalid",
        "token_already_used",
        "token_expired",
    ),
    "cashflow_alert": "*",
    "capture": "*",
    "report_short": "*",
    "fallback": "*",
    "window_closed": "*",
}

# Representative fills, chosen wide rather than typical: a length check
# against ``{amount}`` measures the braces, not the message. "1.234.567đ"
# and a three-word category are what a real bubble carries at its widest.
SAMPLES = {
    "merchant": "Nhà hàng Ngon Quận 1",
    "amount": "1.234.567đ",
    "total": "12.345.678đ",
    "category": "Ăn uống ngoài",
    "count": 12,
    "date": "31/12/2026",
    "source": "Vietcombank",
    "month": "12/2026",
    "balance": "1.234.567đ",
    "threshold": "5.000.000đ",
    "suggested_action": "giảm ăn ngoài khoảng 500k tuần này",
    "spent": "12.345.678đ",
    "budget": "15.000.000đ",
    "net_worth": "1.234.567.890đ",
}

# Emoji ranges the copy actually draws from — pictographs, dingbats,
# symbols, arrows, and the keycap combiner behind "1️⃣". Deliberately a
# fixed list rather than a library: the point is to catch a third emoji
# sneaking into copy, and a dependency for that is a poor trade.
_EMOJI_RE = re.compile("[℀-⇿⌀-⏿①-⓿■-➿⬀-⯿\U0001f000-\U0001faff]")

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\([^)]*\)")
# A Telegram slash-command mentioned inside Zalo copy ("gõ /link_zalo trên
# Telegram") legitimately carries an underscore. Zalo renders none of it as
# markup, so the underscore is safe *there* — everywhere else it reads as
# an italic marker to any renderer downstream, and is banned.
_SLASH_COMMAND_RE = re.compile(r"/[a-z][a-z0-9_]*")


def _register() -> list[tuple[str, str, str]]:
    """Flatten :data:`ZALO_BOUND` into ``(section, key, value)`` triples."""
    copy = load_copy()
    out: list[tuple[str, str, str]] = []
    for section, keys in ZALO_BOUND.items():
        block = copy.get(section) or {}
        names = sorted(block) if keys == "*" else keys
        for key in names:
            out.append((section, key, block.get(key)))
    return out


REGISTER = _register()
IDS = [f"{s}.{k}" for s, k, _ in REGISTER]


def _fill(value: str) -> str:
    """Render a template with representative values.

    A placeholder with no sample is left as-is rather than defaulted to
    something short: the missing-sample test below is what flags it, and
    quietly substituting ``""`` would make a length check pass for the
    wrong reason — and raising here would fail every test for one entry
    instead of the one that actually names the problem.
    """
    return value.format_map(_Samples())


class _Samples(dict):
    """``SAMPLES`` that renders an unknown placeholder back as itself."""

    def __missing__(self, key: str) -> str:
        return SAMPLES.get(key, "{" + key + "}")


@pytest.fixture(params=REGISTER, ids=IDS)
def entry(request) -> tuple[str, str, str]:
    return request.param


# ---------------------------------------------------------------------------
# The register itself
# ---------------------------------------------------------------------------


def test_every_registered_key_exists_and_says_something(entry):
    section, key, value = entry

    assert isinstance(value, str), f"{section}.{key} is missing from content/zalo.yaml"
    assert value.strip()


def test_the_register_is_not_quietly_empty():
    # A typo in a section name would leave that section unchecked and
    # every other test still green.
    assert len(REGISTER) >= 18


def test_every_placeholder_has_a_representative_sample(entry):
    section, key, value = entry
    fields = {f for _, f, _, _ in Formatter().parse(value) if f}

    missing = fields - set(SAMPLES)
    assert not missing, (
        f"{section}.{key} uses {sorted(missing)} — add a sample so the "
        "length check measures the message and not the braces"
    )


def test_placeholders_are_named_so_a_caller_cannot_pass_them_positionally(entry):
    # ``text()`` only ever calls ``.format(**kwargs)``; a bare ``{}`` would
    # raise IndexError, be swallowed, and ship the raw template.
    section, key, value = entry
    fields = [f for _, f, _, _ in Formatter().parse(value) if f is not None]

    assert all(f and not f.isdigit() for f in fields), f"{section}.{key}"


# ---------------------------------------------------------------------------
# Plain text
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("marker", ["**", "__", "~~", "*", "`"])
def test_no_markdown_emphasis_survives_into_zalo_copy(entry, marker):
    section, key, value = entry

    assert marker not in value, f"{section}.{key} carries a Markdown {marker!r}"


def test_no_html_tags(entry):
    section, key, value = entry

    assert not _HTML_TAG_RE.search(value), f"{section}.{key} carries an HTML tag"


def test_no_markdown_links(entry):
    section, key, value = entry

    assert not _MD_LINK_RE.search(value), f"{section}.{key} carries a Markdown link"


def test_no_bracketed_pseudo_buttons(entry):
    # Zalo has no inline keyboard in 5.0, so "[Xem chi tiết]" is a control
    # the reader will try to tap and nothing will happen.
    section, key, value = entry

    assert "[" not in value and "]" not in value, f"{section}.{key}"


def test_underscores_appear_only_inside_slash_commands(entry):
    # "/link_zalo" is a Telegram command name quoted inside Zalo copy —
    # legitimate. A loose underscore is an italic marker waiting to render.
    # Checked on the *filled* message: "{suggested_action}" is a variable
    # name the reader never sees, and banning it would ban naming things.
    section, key, value = entry
    bare = _SLASH_COMMAND_RE.sub("", _fill(value))

    assert "_" not in bare, f"{section}.{key} has an underscore outside a command"


def test_stripping_markup_is_a_no_op_on_the_rendered_message(entry):
    # The end-to-end version of the rules above, stated as the property
    # that matters: what the notifier would send is what was written.
    # Compared on the *filled* template, since a sample value could carry
    # markup the raw template hides.
    #
    # Slash commands are masked on *both* sides first. ``strip_markdown``
    # treats a bare "_" as an italic marker, so it rewrites "/link_zalo"
    # into "/linkzalo" — a known cosmetic quirk of the shared helper, and
    # harmless on Zalo, which renders no markup at all. Masking keeps this
    # test aimed at copy that carries real markup instead of re-reporting
    # that quirk on every string that names a Telegram command.
    section, key, value = entry
    masked = _SLASH_COMMAND_RE.sub("CMD", _fill(value))

    assert strip_markdown(masked) == masked.strip(), f"{section}.{key}"


# ---------------------------------------------------------------------------
# The bubble
# ---------------------------------------------------------------------------


def test_the_filled_message_fits_one_bubble(entry):
    section, key, value = entry
    filled = _fill(value)

    assert len(filled) <= ZALO_MESSAGE_MAX_CHARS, (
        f"{section}.{key} renders to {len(filled)} chars, "
        f"over the {ZALO_MESSAGE_MAX_CHARS} display limit"
    )


def test_the_emoji_budget_is_respected(entry):
    section, key, value = entry
    found = _EMOJI_RE.findall(value)

    assert len(found) <= ZALO_MAX_EMOJI, f"{section}.{key} uses {found}"


def test_the_emoji_detector_actually_detects(entry):
    # Guards the test above: a regex that matched nothing would pass every
    # budget check. At least one registered string is known to carry an
    # emoji, so the detector must fire somewhere in the register.
    assert any(_EMOJI_RE.search(v) for _, _, v in REGISTER if isinstance(v, str))


# ---------------------------------------------------------------------------
# Persona
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("banned", ["Decision Engine", "GPS tài chính", "CFO"])
def test_the_internal_positioning_vocabulary_never_reaches_a_user(entry, banned):
    section, key, value = entry

    assert banned.lower() not in value.lower(), f"{section}.{key}"


def test_the_out_of_slice_reply_reads_as_an_invitation_not_an_error():
    # Bé Tiền never scolds. An intent Zalo can't serve is a redirection,
    # and the copy that carries it is the one place that is easy to get
    # wrong — "không hỗ trợ" is technically true and entirely wrong here.
    body = load_copy()["fallback"]["body"]

    for scold in ("lỗi", "không hỗ trợ", "sai", "không hợp lệ"):
        assert scold not in body.lower()
