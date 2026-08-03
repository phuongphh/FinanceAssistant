"""Phase 5.1 #2.1 — the channel rules, enforced on the file itself.

``content/zalo.yaml`` states four constraints in a comment at the top:
plain text, ≤300 characters, ≤2 emoji, and no positioning jargon. A
comment cannot fail a build, so this module walks every string in the
file and checks them.

The checks run over *every* section rather than a list of the ones 5.1
added, which is deliberate: a copy file grows by people adding sections,
and a test that only knows today's section names would pass forever
while the file drifted. The exemptions below are therefore an explicit,
asserted-closed set — adding a section to it is a visible decision, not
an omission.
"""

from __future__ import annotations

import re

import pytest

from backend.utils.zalo_copy import ZALO_CONTENT_PATH, load_copy, text
from backend.utils.zalo_limits import ZALO_MAX_EMOJI, ZALO_MESSAGE_MAX_CHARS

# Sections written before Phase 5.0 introduced the strict formatting
# block in the file header. They break the rules for reasons that were
# right at the time and are not worth churning copy over:
#
#   linking       — mostly *Telegram*-side copy that happens to live in
#                   this file. It carries a backticked token the user
#                   must copy, ``/link_zalo`` (an underscore inside a
#                   command name, not emphasis), and numbered-step emoji.
#   cashflow_alert— Phase 4B; uses parentheses for the threshold aside.
#   profile_status— Telegram ``/profile`` snippet, not a Zalo bubble.
#
# Anything else must comply. This set is asserted closed below.
_PRE_5_0_SECTIONS = frozenset({"linking", "cashflow_alert", "profile_status"})

# Positioning language that may never reach a user (CLAUDE.md). Checked
# against the whole file with no exemption.
_BANNED_TERMS = ("Decision Engine", "CFO", "GPS tài chính")

# Zalo renders the bubble verbatim, so a Markdown character is a
# character the user sees. Parentheses are on the list because the 5.0
# header block put them there — they read as leftover markup next to the
# "·" separator this file uses for asides.
_FORBIDDEN_CHARS = ("*", "_", "`", "[", "]", "(", ")", "~")

# ``{net_worth}`` is a format key, not emphasis: the user sees the
# substituted value, never the underscore. The rule is about what reaches
# the bubble, so placeholders come out before the characters are counted.
_PLACEHOLDER_RE = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")

# Rough but sufficient: the ranges that cover every emoji this file uses
# or plausibly will. Variation selectors and ZWJ are outside the ranges,
# so "⚖️" and a joined sequence each count once, which is what a reader
# perceives.
_EMOJI_RE = re.compile(
    "["
    "\U0001f300-\U0001faff"
    "\U0001f000-\U0001f2ff"
    "☀-➿"
    "⬀-⯿"
    "]"
)


def _strings() -> list[tuple[str, str, str]]:
    """Every leaf string as ``(section, key, value)``."""
    out: list[tuple[str, str, str]] = []
    for section, body in load_copy().items():
        if not isinstance(body, dict):
            raise AssertionError(
                f"content/zalo.yaml section '{section}' is not a mapping — "
                "zalo_copy.text() reads section → key, so a bare string "
                "at the top level is unreachable"
            )
        for key, value in body.items():
            if isinstance(value, str):
                out.append((section, key, value))
    return out


def _governed() -> list[tuple[str, str, str]]:
    return [item for item in _strings() if item[0] not in _PRE_5_0_SECTIONS]


def test_the_file_actually_loads_and_is_not_empty():
    # load_copy() swallows a malformed file into {} by design (it must
    # never take the bot down), which would make every check below pass
    # vacuously. This is the guard against that.
    assert len(_strings()) > 40


def test_the_exemption_list_has_not_grown():
    # New sections comply. If this fails, either the section was named
    # like a pre-5.0 one or someone added an exemption without saying so.
    assert _PRE_5_0_SECTIONS <= {section for section, _, _ in _strings()}
    assert _PRE_5_0_SECTIONS == frozenset(
        {"linking", "cashflow_alert", "profile_status"}
    )


# ---------------------------------------------------------------------------
# The four channel rules
# ---------------------------------------------------------------------------


def test_no_positioning_jargon_anywhere_in_the_file():
    raw = ZALO_CONTENT_PATH.read_text(encoding="utf-8")
    for term in _BANNED_TERMS:
        assert term not in raw, f"'{term}' must never reach a user"


def test_every_string_fits_a_zalo_bubble():
    for section, key, value in _strings():
        assert len(value) <= ZALO_MESSAGE_MAX_CHARS, (
            f"{section}.{key} is {len(value)} chars"
        )


def test_no_markdown_characters_in_the_governed_sections():
    for section, key, value in _governed():
        rendered = _PLACEHOLDER_RE.sub("", value)
        found = [ch for ch in _FORBIDDEN_CHARS if ch in rendered]
        assert not found, f"{section}.{key} contains {found} — Zalo shows it raw"


def test_at_most_two_emoji_per_string():
    for section, key, value in _governed():
        count = len(_EMOJI_RE.findall(value))
        assert count <= ZALO_MAX_EMOJI, f"{section}.{key} has {count} emoji"


# ---------------------------------------------------------------------------
# Salutation templating (#2.1's "3 xưng hô")
# ---------------------------------------------------------------------------

_SALUTATIONS = ("anh", "chị", "bạn")

# Sections #2.1 adds. Listed explicitly because the assertion below is
# about these surfaces having salutation-aware copy at all — a generic
# sweep could not tell "no placeholder needed" from "placeholder
# forgotten".
_PARITY_SECTIONS = (
    "twin",
    "twin_comparison",
    "milestone",
    "advisory",
    "decision",
    "asset_entry",
    "onboarding",
)


@pytest.mark.parametrize("section", _PARITY_SECTIONS)
def test_parity_section_exists_and_addresses_the_user(section):
    body = load_copy().get(section)

    assert isinstance(body, dict) and body, f"missing section '{section}'"
    joined = " ".join(v for v in body.values() if isinstance(v, str))
    assert "{salutation}" in joined or "{Salutation}" in joined, (
        f"'{section}' never addresses the user — every parity surface has "
        "a voice, and the voice is xưng hô"
    )


@pytest.mark.parametrize("salutation", _SALUTATIONS)
def test_every_parity_string_renders_for_all_three_salutations(salutation):
    # The reason placeholders beat three hand-written variants: this is
    # the whole proof, and it costs one loop.
    for section in _PARITY_SECTIONS:
        for key, value in load_copy()[section].items():
            if not isinstance(value, str):
                continue
            rendered = value.replace("{salutation}", salutation).replace(
                "{Salutation}", salutation.capitalize()
            )
            assert "{salutation}" not in rendered
            assert "{Salutation}" not in rendered
            assert len(rendered) <= ZALO_MESSAGE_MAX_CHARS


def test_milestone_copy_carries_no_pressure_or_blame():
    # #2.3's DoD. Bé Tiền celebrates without turning the milestone into
    # a comparison or a reminder of what came before.
    joined = " ".join(load_copy()["milestone"].values()).lower()

    for word in ("đáng lẽ", "lẽ ra", "chậm", "trễ", "so với người", "hơn ai"):
        assert word not in joined


def test_text_helper_reaches_the_new_sections():
    # zalo_copy.text() reads section → key and returns "" for a miss, so
    # a section that exists in the file but is shaped wrong would fail
    # silently at runtime. One end-to-end read proves the wiring.
    line = text("twin", "range_line", p10="10tr", p50="20tr", p90="30tr")

    assert "10tr" in line and "30tr" in line
