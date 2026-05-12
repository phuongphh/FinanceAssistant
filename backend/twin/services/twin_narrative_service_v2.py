"""Twin narrative composer for the onboarding intro (Phase 4.1, A.2).

Composes the "3 con đường tương lai" mascot intro that runs BEFORE
the cone chart image. Pure composer — no LLM call, just YAML + the
user's display name.

Separated from the existing ``twin_narrative_service`` (Phase 4A LLM
narrative) because the onboarding intro must NEVER hit an LLM:
- TTFT budget is tight (5 min from /start).
- Cost guardrail (Story A.3) blocks LLM on free tier near month-end.
- First impression cannot fail; YAML never times out.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_CONTENT_PATH = (
    Path(__file__).resolve().parents[3]
    / "content"
    / "onboarding"
    / "first_twin_intro.yaml"
)


def load_copy() -> dict[str, Any]:
    with open(_CONTENT_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def narrative_text() -> str:
    return load_copy()["narrative"]


def chart_caption(*, name: str, horizon_years: int) -> str:
    return load_copy()["caption"].format(name=name, horizon=horizon_years)


def feedback_keyboard() -> dict:
    """Inline keyboard for the in-moment 😍 / 🤔 / 😕 prompt."""
    copy = load_copy()["feedback_prompt"]
    prefix = copy["callback_prefix"]
    return {
        "inline_keyboard": [
            [
                {"text": copy["buttons"]["love"], "callback_data": f"{prefix}love"},
                {
                    "text": copy["buttons"]["confused"],
                    "callback_data": f"{prefix}confused",
                },
                {
                    "text": copy["buttons"]["dislike"],
                    "callback_data": f"{prefix}dislike",
                },
            ]
        ]
    }


def feedback_prompt_text() -> str:
    return load_copy()["feedback_prompt"]["body"]


def feedback_ack_text() -> str:
    return load_copy()["feedback_prompt"]["ack"]


def completion_text() -> str:
    return load_copy()["completion"]


def compute_failed_text() -> str:
    return load_copy()["compute_failed"]
