"""Access to ``content/zalo.yaml`` (Phase 5.0).

One loader for the Zalo channel's user-facing strings. Vietnamese copy
never lives in code (CLAUDE.md), and the inbound path touches several
sections — linking, capture, fallback — so a per-call ``yaml.safe_load``
would parse the file on every message.

The file is read once and cached for the process's life: it ships with
the code, so a change always arrives with a deploy.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

ZALO_CONTENT_PATH = Path(__file__).resolve().parents[2] / "content" / "zalo.yaml"


@lru_cache(maxsize=1)
def load_copy() -> dict[str, Any]:
    """Parse ``content/zalo.yaml`` once.

    A missing or malformed file degrades to ``{}`` rather than raising:
    the webhook has already answered 200 by the time copy is read, and a
    silent send is a better failure than a crashed background task that
    loses the inbound message entirely. :func:`text` logs the miss so the
    gap is still visible.
    """
    try:
        with open(ZALO_CONTENT_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        logger.exception("zalo.copy unable to read %s — falling back to empty", ZALO_CONTENT_PATH)
        return {}


def text(section: str, key: str, **fmt: Any) -> str:
    """Return one string, or ``""`` when it is missing.

    ``**fmt`` is applied with :meth:`str.format`; a template referring to
    a placeholder the caller didn't pass returns the raw template rather
    than raising, so a copy edit can never take the channel down.
    """
    value = (load_copy().get(section) or {}).get(key)
    if not isinstance(value, str) or not value:
        logger.warning("zalo.copy missing string section=%s key=%s", section, key)
        return ""
    if not fmt:
        return value
    try:
        return value.format(**fmt)
    except (KeyError, IndexError, ValueError):
        logger.warning(
            "zalo.copy unformattable template section=%s key=%s — sending raw",
            section,
            key,
        )
        return value


def linking(key: str, **fmt: Any) -> str:
    """Shorthand for the ``linking`` section — the busiest caller."""
    return text("linking", key, **fmt)
