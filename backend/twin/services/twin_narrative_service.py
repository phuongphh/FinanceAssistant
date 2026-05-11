"""Short Financial Twin narrative generation with conservative fallback."""
from __future__ import annotations

import hashlib
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.money import format_money_short
from backend.models.user import User
from backend.services.llm_service import LLMError, call_llm

_COPY_PATH = Path(__file__).resolve().parents[3] / "content" / "twin_copy.yaml"


@lru_cache(maxsize=1)
def _copy() -> dict[str, Any]:
    with open(_COPY_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)["narrative"]


def cone_hash(cone: list[dict[str, Any]]) -> str:
    payload = "|".join(
        f"{p.get('year')}:{p.get('p10')}:{p.get('p50')}:{p.get('p90')}" for p in cone
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _clean_output(text: str) -> str:
    cleaned = " ".join(text.replace("*", "").replace("_", "").split())
    if 50 <= len(cleaned) <= 200:
        return cleaned
    return _copy()["fallback"]


async def build_twin_narrative(
    db: AsyncSession,
    user: User,
    cone: list[dict[str, Any]],
    *,
    cone_age_days: int | None,
) -> str:
    if not cone:
        return _copy()["fallback"]
    target = cone[-1]
    prompt = _copy()["prompt"].format(
        target_year=target.get("year"),
        p10=format_money_short(Decimal(str(target.get("p10", 0)))),
        p50=format_money_short(Decimal(str(target.get("p50", 0)))),
        p90=format_money_short(Decimal(str(target.get("p90", 0)))),
        cone_age_days=cone_age_days or 0,
        cone_hash=cone_hash(cone),
    )
    try:
        text = await call_llm(
            prompt,
            task_type="twin_narrative",
            db=db,
            user_id=user.id,
            use_cache=True,
            cache_ttl_days=7,
        )
        return _clean_output(text)
    except (LLMError, Exception):
        return _copy()["fallback"]
