"""Render the Độ Nét (clarity) meter into Bé Tiền's voice (Phase 4.5, E3).

Pure formatting: takes a :class:`ClarityResult` from ``clarity_service`` and
turns it into user-facing Vietnamese. All strings live in
``content/decision_copy.yaml`` (never hardcoded) — this module only threads the
score and the single most useful "làm nét thêm" suggestion into that copy.

Layer note: this is a formatter, not a service — no I/O, no DB, no env. The
``CLARITY_METER_ENABLED`` flag is decided by the handler/router edge before we
are ever called.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from backend.services.decision.clarity_service import ClarityResult

_COPY_PATH = Path(__file__).resolve().parents[3] / "content" / "decision_copy.yaml"


@lru_cache(maxsize=1)
def _clarity_copy() -> dict:
    with _COPY_PATH.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return dict(data.get("clarity") or {})


def _component_label(key: str | None) -> str:
    """Vietnamese name for a component key, falling back to the key itself."""
    if not key:
        return ""
    components = _clarity_copy().get("components") or {}
    return str(components.get(key, key))


def render_clarity_line(result: ClarityResult) -> str:
    """Return the one-line clarity headline (e.g. "🔍 Ảnh tương lai đang nét ~62%")."""
    template = _clarity_copy().get("line", "Ảnh tương lai đang nét khoảng {score}%")
    return template.format(score=result.score)


def render_clarity_block(result: ClarityResult) -> str:
    """Return the headline plus at most one humble/sharpen nudge.

    Below the threshold → humble mode: admit the picture is blurry and name the
    single highest-value missing component. Above the threshold → offer one
    gentle suggestion for the highest-weight component not yet complete. When
    nothing is left to sharpen, only the headline is returned.
    """
    copy = _clarity_copy()
    line = render_clarity_line(result)

    if result.is_below_threshold:
        parts = [line]
        intro = copy.get("humble_intro", "")
        if intro:
            parts.append(intro)
        missing = result.top_missing()
        suggest = copy.get("humble_suggest", "")
        if missing is not None and suggest:
            parts.append(suggest.format(component=_component_label(missing.key)))
        return "\n".join(parts)

    sharpen = result.top_sharpen()
    suggest = copy.get("sharpen_suggest", "")
    if sharpen is not None and suggest:
        return line + "\n" + suggest.format(component=_component_label(sharpen.key))
    return line
