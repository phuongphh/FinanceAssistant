"""Resolve and render tone-dial copy variants (Phase 4.5, E4 #4.3).

Pure formatting: no I/O beyond the one cached YAML read, no DB, no env. The
``TONE_DIAL_ENABLED`` flag is decided at the handler / job edge before we are
ever called — the edge either passes a resolved ``tone`` ("gentle"/"strict")
or ``None`` (dial dark), and ``None`` means every surface renders its legacy
copy without consulting this module.

Two entry points:

``resolve_tone(pref)``
    Collapse ``users.tone_preference`` (nullable VARCHAR) to a canonical
    ``"gentle"`` / ``"strict"``. Only the exact value ``"strict"`` reads as
    strict; NULL and any other value fall back to gentle. Called at the edge.

``render_tone_variant(key, tone, *, salutation, **ctx)``
    Look up ``key`` (dotted, e.g. ``"empathy.large_transaction"``) in
    ``content/tone_variants.yaml``, pick the block for ``tone``, and format it.
    Lists (empathy nudges) are sampled with ``random.choice``; plain strings
    (decision verdicts) are used as-is. Returns ``None`` when the key or the
    tone block is absent, so the caller can safely fall back to legacy copy.

Persona floor lives in the YAML and is guarded by ``test_strict_never_
humiliates`` — "strict" is thẳng thắn, never sỉ nhục.
"""

from __future__ import annotations

import random
from functools import lru_cache
from pathlib import Path

import yaml

_COPY_PATH = Path(__file__).resolve().parents[3] / "content" / "tone_variants.yaml"

GENTLE = "gentle"
STRICT = "strict"


@lru_cache(maxsize=1)
def _tone_copy() -> dict:
    with _COPY_PATH.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return dict(data)


def resolve_tone(pref: str | None) -> str:
    """Canonicalise ``users.tone_preference`` to ``"gentle"`` / ``"strict"``.

    Only an exact ``"strict"`` reads as strict; NULL and every other value
    (including a legacy ``"gentle"``) fall back to gentle — the safe default.
    """
    return STRICT if pref == STRICT else GENTLE


def _lookup(key: str) -> dict | None:
    """Navigate a dotted ``key`` into the tone-variant tree; None if absent."""
    node: object = _tone_copy()
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, dict) else None


def render_tone_variant(
    key: str,
    tone: str | None,
    *,
    salutation: str = "bạn",
    **ctx: object,
) -> str | None:
    """Render the ``tone`` block at ``key``, or ``None`` for legacy fallback.

    ``tone`` of ``None`` (dial dark) always returns ``None`` — the caller keeps
    its legacy copy. A live ``tone`` with no matching block also returns
    ``None``, so adding a tone-aware surface never forces us to author every
    variant up front.
    """
    if tone is None:
        return None

    block = _lookup(key)
    if block is None:
        return None

    variant = block.get(tone)
    if variant is None:
        return None

    template = random.choice(variant) if isinstance(variant, list) else variant
    if not isinstance(template, str) or not template:
        return None

    return template.format(salutation=salutation, **ctx)


__all__ = ["GENTLE", "STRICT", "render_tone_variant", "resolve_tone"]
