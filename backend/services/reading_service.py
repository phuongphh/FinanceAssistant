"""The Reading (Phase 4.4, Epic 1, WOW #1) — service layer.

Generates the minute-1 "đoán thử" message Bé Tiền sends right after the
user picks a goal (v0, zero data) and again once a real asset number is
known (v1). Composes a guaranteed user-facing string:

    open line (YAML)  +  LLM-generated guess  +  disclaimer/CTA (YAML)

Design choices that matter:

- **Never fails the moment.** If the LLM errors, times out, or returns
  garbage, we fall back to fixed YAML copy so onboarding always moves
  forward. The caller can render the return value unconditionally.
- **Flush-only.** This service performs no writes; it has no
  ``db.commit()`` and reads no env (the ``READING_ENABLED`` flag is
  checked by the handler, per the layer contract).
- **Groq for latency.** The minute-1 beat can't stall, so the LLM call
  goes to Groq (sub-second) with a tight timeout; DeepSeek's 4-12s
  first-token tail would break the rhythm.
- **Per-user cache.** ``shared_cache=False`` — the guess embeds the
  user's name + goal and must never leak across tenants.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.personality.reading_prompt import (
    build_reading_prompt,
    parse_reading_response,
)
from backend.services.llm_service import LLMError, call_llm

logger = logging.getLogger(__name__)

# Groq is sub-second; cap the wait so a slow call can't stall minute-1.
_READING_TIMEOUT_SECONDS = 3.0

_CONTENT_PATH = (
    Path(__file__).resolve().parents[2]
    / "content"
    / "onboarding"
    / "welcome_v2.yaml"
)


def _load_reading_copy() -> dict[str, Any]:
    with open(_CONTENT_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)["reading"]


def goal_label_for(goal_code: str | None) -> str:
    """Map an onboarding goal code to the Vietnamese phrase fed to the LLM.

    Falls back to a neutral phrase for unknown / missing codes so the
    Reading still has something to anchor on.
    """
    copy = _load_reading_copy()
    labels = copy.get("goal_labels", {})
    return labels.get(goal_code or "", copy["goal_label_default"])


async def generate_reading(
    *,
    db: AsyncSession | None,
    user_id: Any,
    salutation: str,
    display_name: str,
    goal_label: str,
    amount_text: str | None = None,
) -> str:
    """Return the full Reading message (open + guess + disclaimer).

    Always returns a renderable string. On any LLM failure it returns
    the fixed YAML fallback copy so the onboarding beat never breaks.
    ``amount_text`` present → v1 (reads the real number); absent → v0.
    """
    copy = _load_reading_copy()
    is_v1 = bool(amount_text)
    fmt = {"salutation": salutation, "Salutation": salutation.capitalize()}

    body = await _generate_body(
        db=db,
        user_id=user_id,
        salutation=salutation,
        display_name=display_name,
        goal_label=goal_label,
        amount_text=amount_text,
    )

    if body is None:
        fallback_key = "fallback_v1" if is_v1 else "fallback_v0"
        return copy[fallback_key].format(**fmt).strip()

    open_line = copy["open"].format(**fmt).strip()
    disclaimer_key = "disclaimer_v1" if is_v1 else "disclaimer_v0"
    disclaimer = copy[disclaimer_key].format(**fmt).strip()
    return f"{open_line}\n\n{body}\n\n{disclaimer}"


async def _generate_body(
    *,
    db: AsyncSession | None,
    user_id: Any,
    salutation: str,
    display_name: str,
    goal_label: str,
    amount_text: str | None,
) -> str | None:
    """Run the LLM and return the sanitised guess, or None on failure."""
    prompt = build_reading_prompt(
        salutation=salutation,
        display_name=display_name,
        goal_label=goal_label,
        amount_text=amount_text,
    )
    try:
        raw = await call_llm(
            prompt,
            task_type="reading",
            db=db,
            user_id=user_id,
            use_cache=db is not None,
            shared_cache=False,
            provider="groq",
            timeout=_READING_TIMEOUT_SECONDS,
        )
    except LLMError:
        logger.warning("reading: LLM call failed — using fallback copy")
        return None
    except Exception:  # noqa: BLE001 — never propagate to the onboarding flow
        logger.exception("reading: unexpected error from LLM")
        return None

    return parse_reading_response(raw)
