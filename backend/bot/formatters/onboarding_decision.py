"""Render the in-onboarding decision moment (Phase 4.6, E3).

Pure formatting. Right after the Twin reveal Bé Tiền poses ONE goal-specific
decision question and answers it on the spot with **exactly one** number, then
tells the truth about how sharp the picture is (độ nét). It reuses the Phase
4.5 outputs — :class:`PlanFeasibility` from ``plan_feasibility_service`` and
:class:`ClarityResult` from ``clarity_service`` — so there is no new engine
here: this module only picks the honest answer shape and threads the numbers in.

Answer shapes, in decreasing order of how much we actually know:

    on_track   (achievable band / already there) → 1 number = months to goal.
    building   (some saving rate, still a reach)  → 1 number = reachable target
                                                     the user is trending toward.
    direction  (no saving-rate signal yet)        → 1 number = the typical
                                                     milestone, framed as a
                                                     starting direction not a "no".

Every string lives in ``content/onboarding/decision_moment.yaml`` (never
hardcoded). Layer note: this is a formatter — no I/O, no DB, no env. The
``ONBOARDING_DECISION_MOMENT_ENABLED`` flag is decided at the handler edge
before we are called.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import yaml

from backend.bot.formatters.money import format_money_short
from backend.schemas.goal import FeasibilityBand
from backend.services.decision.clarity_service import ClarityResult
from backend.services.decision.plan_feasibility_service import PlanFeasibility

_COPY_PATH = (
    Path(__file__).resolve().parents[3]
    / "content"
    / "onboarding"
    / "decision_moment.yaml"
)

# Bands that mean "you can hit the actual target" — show months, no pivot.
_ACHIEVABLE_BANDS = frozenset({FeasibilityBand.EASY, FeasibilityBand.FEASIBLE})


@dataclass(frozen=True)
class GoalDecisionConfig:
    """The question + feasibility inputs for one goal, pulled from content.

    ``target_vnd`` / ``horizon_years`` are typical first-life milestones for the
    22-35 / Level 0→1 segment, not a promise — the honest-clarity line makes
    that explicit. Money is a ``Decimal`` (layer contract), coerced from the
    plain integer in the YAML.
    """

    question: str
    goal_label: str
    target_vnd: Decimal
    horizon_years: Decimal


@lru_cache(maxsize=1)
def _copy() -> dict:
    with _COPY_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _decision_copy() -> dict:
    return dict(_copy().get("decision_moment") or {})


def goal_config(goal_code: str | None) -> GoalDecisionConfig:
    """Resolve the decision-moment config for ``goal_code``.

    Unknown / legacy goals fall back to ``default_goal`` so the moment always
    has a question to ask — the flag can never strand a user at a dead end.
    """
    copy = _decision_copy()
    goals = copy.get("goals") or {}
    block = goals.get(goal_code) if goal_code else None
    if not block:
        block = copy.get("default_goal") or {}
    return GoalDecisionConfig(
        question=block.get("question", ""),
        goal_label=block.get("goal_label", "mục tiêu"),
        target_vnd=Decimal(str(block.get("target_vnd", 0))),
        horizon_years=Decimal(str(block.get("horizon_years", 3))),
    )


def render_question(config: GoalDecisionConfig, *, salutation: str = "bạn") -> str:
    """The single goal-specific decision question."""
    return config.question.format(salutation=salutation)


def render_answer(
    result: PlanFeasibility,
    config: GoalDecisionConfig,
    clarity: ClarityResult,
    *,
    salutation: str = "bạn",
) -> str:
    """Answer with exactly one number for the goal, plus an honest độ nét line.

    Picks the answer shape from how much the feasibility engine could actually
    conclude, then always appends the clarity line so the user knows how much
    to trust the number. Never ends on a flat "no" — thin data pivots to a
    directional milestone.
    """
    answers = _decision_copy().get("answers") or {}
    label = config.goal_label
    label_cap = (label[:1].upper() + label[1:]) if label else label
    target = format_money_short(config.target_vnd)

    if result.already_reached:
        # ``months`` here is the horizon fallback (the finished projection has no
        # ``months_remaining``), so never phrase it as "còn X tháng" — celebrate
        # instead of inventing a countdown.
        body = answers.get("already_reached", "").format(
            salutation=salutation,
            goal_label=label,
        )
    elif result.band in _ACHIEVABLE_BANDS:
        body = answers.get("on_track", "").format(
            months=result.months,
            salutation=salutation,
            goal_label=label,
        )
    elif result.actual_monthly_savings > 0 and result.reachable_target is not None:
        # Exactly one number: the amount the user is trending toward. The real
        # milestone lives in the question above — repeating it here would turn
        # the moment into a mini feasibility report.
        body = answers.get("building", "").format(
            reachable=format_money_short(result.reachable_target),
            salutation=salutation,
            goal_label=label,
        )
    else:
        # No saving-rate signal (the common onboarding case) → don't invent a
        # timeline; point at the milestone and call the picture a start.
        body = answers.get("direction", "").format(
            salutation=salutation,
            goal_label=label,
            goal_label_cap=label_cap,
            target=target,
        )

    return _join(body, _render_clarity(clarity, salutation=salutation))


def _render_clarity(clarity: ClarityResult, *, salutation: str) -> str:
    """The độ nét line — honest about how sharp the picture is, with the single
    highest-leverage thing the user could add to sharpen it."""
    cl = _decision_copy().get("clarity") or {}
    sharpen_map = cl.get("sharpen") or {}
    top = clarity.top_sharpen()
    sharpen_text = sharpen_map.get(top.key, "") if top is not None else ""

    if clarity.is_below_threshold:
        return cl.get("below", "").format(
            salutation=salutation, score=clarity.score, sharpen=sharpen_text
        )
    tail = (
        cl.get("sharpen_tail", "").format(sharpen=sharpen_text) if sharpen_text else ""
    )
    return cl.get("above", "").format(
        salutation=salutation, score=clarity.score, sharpen_tail=tail
    )


def _join(*parts: str) -> str:
    return "\n\n".join(p for p in parts if p)


__all__ = ["GoalDecisionConfig", "goal_config", "render_answer", "render_question"]
