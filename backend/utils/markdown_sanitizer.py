"""Sanitize LLM-generated text for Telegram's legacy Markdown parser.

Telegram's Bot API rejects messages whose markdown entities aren't
balanced and returns ``Bad Request: can't parse entities`` — fatal,
the message is silently dropped. The advisory handler hit this in
prod (#231): an LLM response with an odd number of ``*`` made the
whole reply disappear, the user saw the spinner clear with no answer.

The previous fix (#230) was a transport-layer band-aid: on parse
failure, retry without ``parse_mode``. That ships, but it's
plain-text — bullets, bolds, links all become noise. Worse, it
hides the real problem: the LLM output should be valid in the first
place, or, failing that, *fixed* before send rather than stripped of
all formatting.

This module is the root-cause fix. It pre-processes Markdown bodies
so unbalanced entities get escaped (``\\*``) and render as literal
characters instead of breaking parsing. The plain-text retry stays
as a last-resort safety net for cases the sanitizer doesn't catch
(deeply nested cross-emphasis, novel LLM failure modes), but should
be exercised <1% of the time once this lands.

Failure modes this catches
--------------------------
- Truncated mid-emphasis: ``Mua *VinHomes`` (LLM hit token cap).
- Standard-vs-Telegram syntax mix: ``**bold**`` (renders fine, was
  parsing OK already, no change here — included for coverage).
- Stray opener: ``Đây là _quan trọng cho việc tiết kiệm.``
- Broken link: ``[xem thêm](https://example.com`` (no closing ``)``).
- Bullet lists: ``* Mục 1\\n* Mục 2`` — Telegram parses the leading
  ``*`` as a bold opener, eating the next line. We escape line-leading
  ``*`` followed by a space so bullets stay literal.
- Stray code-span backtick: ``` Lệnh `git st `` ``` (no close).

Limitations
-----------
- We don't recurse into balanced spans to repair nested unbalance
  (e.g. ``*foo _bar*`` leaves the inner ``_`` alone — Telegram errors
  on this and the plain-text retry will catch it).
- We don't rewrite ``**foo**`` into ``*foo*``. Telegram parses the
  former as two empty bolds + literal ``foo``, which is ugly but
  doesn't error.
- MarkdownV2 (different escape set) is not handled — the codebase
  uses legacy ``Markdown``.

Idempotence: passing already-balanced markdown through the sanitizer
returns the input unchanged. Tests assert this.
"""
from __future__ import annotations

__all__ = ["sanitize_markdown"]


def sanitize_markdown(text: str) -> str:
    """Escape unbalanced legacy-Markdown entities for Telegram.

    Walks ``text`` once. For each entity opener (``*``, ``_``, `````,
    ``[``, ```` ``` ````), tries to find a matching closer. Matched pairs
    pass through verbatim. Unmatched openers get backslash-escaped so
    Telegram renders them literally instead of erroring on parse.

    Line-leading ``* `` is treated as a literal list bullet (escaped),
    not a bold opener — this is the single most common LLM failure
    mode for Vietnamese advisory output.
    """
    if not text:
        return text

    # Pre-pass: line-leading "* " (with a space after) is a Markdown
    # list bullet in standard Markdown but a bold opener in Telegram's
    # legacy parser. LLMs default to standard-Markdown habits, so this
    # pattern is everywhere in advisory output. Escape it before the
    # main pass so the bullet stays literal.
    text = _escape_list_bullets(text)

    out: list[str] = []
    i = 0
    n = len(text)

    while i < n:
        ch = text[i]

        # Already-escaped char (from the list-bullet pre-pass or from
        # the LLM itself emitting ``\*``). Pass the backslash + next
        # char through verbatim so we don't try to match the entity.
        if ch == "\\" and i + 1 < n and text[i + 1] in "*_`[]()\\":
            out.append(text[i : i + 2])
            i += 2
            continue

        # Triple-backtick code block — must be matched before single
        # backticks. Content inside is verbatim per Telegram spec.
        if text.startswith("```", i):
            close = text.find("```", i + 3)
            if close == -1:
                # No closer — escape the whole opener so the literal
                # backticks render and parse stays balanced.
                out.append("\\`\\`\\`")
                i += 3
            else:
                out.append(text[i : close + 3])
                i = close + 3
            continue

        # Single-backtick code span.
        if ch == "`":
            close = _find_unescaped(text, "`", i + 1)
            if close == -1:
                out.append("\\`")
                i += 1
            else:
                out.append(text[i : close + 1])
                i = close + 1
            continue

        # Link: requires the full ``[text](url)`` shape. Anything less
        # than complete gets the bracket escaped.
        if ch == "[":
            close_bracket = _find_unescaped(text, "]", i + 1)
            if (
                close_bracket != -1
                and close_bracket + 1 < n
                and text[close_bracket + 1] == "("
            ):
                close_paren = _find_unescaped(text, ")", close_bracket + 2)
                if close_paren != -1:
                    out.append(text[i : close_paren + 1])
                    i = close_paren + 1
                    continue
            out.append("\\[")
            i += 1
            continue

        # Bold (``*``) and italic (``_``) — single-char paired entities.
        if ch in ("*", "_"):
            close = _find_unescaped(text, ch, i + 1)
            if close == -1:
                out.append("\\" + ch)
                i += 1
            else:
                out.append(text[i : close + 1])
                i = close + 1
            continue

        out.append(ch)
        i += 1

    return "".join(out)


def _find_unescaped(text: str, target: str, start: int) -> int:
    """Find the next occurrence of ``target`` in ``text`` from ``start``,
    skipping any preceded by a backslash.

    Needed because the list-bullet pre-pass inserts ``\\*`` markers and
    LLMs occasionally emit ``\\*`` themselves; the main pass must not
    treat those as real entity delimiters.
    """
    i = start
    n = len(text)
    while i < n:
        idx = text.find(target, i)
        if idx == -1:
            return -1
        if idx > 0 and text[idx - 1] == "\\":
            i = idx + 1
            continue
        return idx
    return -1


def _escape_list_bullets(text: str) -> str:
    """Escape ``*`` at line-start followed by a space.

    Standard Markdown writes lists as ``* item`` / ``- item``. The
    ``-`` form passes through Telegram untouched. The ``*`` form is
    parsed as a bold opener and eats the following text up to the
    next ``*``, which is exactly the failure we keep seeing in
    advisory output. Escape only this very specific shape so we
    don't disturb inline ``*emphasis*``.
    """
    lines = text.split("\n")
    for idx, line in enumerate(lines):
        stripped = line.lstrip(" \t")
        if stripped.startswith("* "):
            # Replace exactly the first non-whitespace ``*``.
            leading_ws_len = len(line) - len(stripped)
            lines[idx] = line[:leading_ws_len] + "\\*" + stripped[1:]
    return "\n".join(lines)
