"""Translate future money amounts into short, safe life-outcome examples."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.llm_service import LLMError, call_llm
from infra.cache.life_outcome_cache import TTL_DAYS, bucket_amount, cache_key

_PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "life_outcome_v1.txt"
_FALLBACK_PATH = (
    Path(__file__).resolve().parents[3]
    / "content"
    / "twin"
    / "life_outcome_fallback.yaml"
)
_MAX_WORDS = 30
_FORBIDDEN_ACTIONS = ("nên", "hãy", "mua ngay", "đầu tư vào", "chắc chắn", "sẽ đủ")


@dataclass(frozen=True, slots=True)
class LifeOutcomeContext:
    location: str = "TP.HCM"
    known_goals: list[str] = field(default_factory=list)
    age: int | None = None
    dependents: int | None = None
    user_segment: str = "mass_affluent"


async def translate(
    db: AsyncSession | None,
    *,
    amount_vnd: Decimal | int | str,
    target_year: int,
    user_context: LifeOutcomeContext | dict[str, Any] | None = None,
) -> str:
    """Return a Vietnamese phrase <= 30 words, with deterministic fallback."""
    ctx = _coerce_context(user_context)
    amount = bucket_amount(amount_vnd)
    fallback = fallback_phrase(amount, location=ctx.location)
    prompt = _prompt_template().format(
        amount_vnd=f"{int(amount):,}".replace(",", "."),
        target_year=target_year,
        location=ctx.location,
        user_segment=ctx.user_segment,
        age=ctx.age or "không rõ",
        dependents=ctx.dependents if ctx.dependents is not None else "không rõ",
        known_goals=", ".join(ctx.known_goals) if ctx.known_goals else "chưa rõ",
    )
    if db is None:
        return fallback
    try:
        phrase = await call_llm(
            prompt,
            task_type="twin_life_outcome",
            db=db,
            user_id=None,
            use_cache=True,
            shared_cache=True,
            cache_ttl_days=TTL_DAYS,
        )
    except (LLMError, Exception):
        return fallback
    cleaned = sanitize_phrase(phrase)
    return cleaned or fallback


def build_cache_key(
    *,
    amount_vnd: Decimal | int | str,
    target_year: int,
    user_context: LifeOutcomeContext | dict[str, Any] | None = None,
) -> str:
    ctx = _coerce_context(user_context)
    return cache_key(
        amount_vnd=amount_vnd,
        target_year=target_year,
        user_segment=ctx.user_segment,
        location=ctx.location,
    )


def sanitize_phrase(phrase: str) -> str:
    text = re.sub(r'[\r\n*_`#>"]+', " ", (phrase or "")).strip()
    text = re.sub(r"\s+", " ", text)
    lowered = text.lower()
    if not text or any(term in lowered for term in _FORBIDDEN_ACTIONS):
        return ""
    words = text.split()
    if len(words) > _MAX_WORDS:
        text = " ".join(words[:_MAX_WORDS])
    if "có thể" not in lowered and "tương đương" not in lowered:
        text = f"có thể tương đương {text[0].lower() + text[1:] if text else text}"
    return text


def fallback_phrase(
    amount_vnd: Decimal | int | str, *, location: str = "TP.HCM"
) -> str:
    amount = Decimal(str(amount_vnd or 0))
    data = _fallback_data()
    buckets = data.get("buckets") or []
    for bucket in buckets:
        max_vnd = bucket.get("max_vnd")
        if max_vnd is None or amount <= Decimal(str(max_vnd)):
            phrases = bucket.get("phrases") or []
            if phrases:
                return sanitize_phrase(str(phrases[0]))
    return "có thể giúp bạn có thêm lựa chọn tài chính, nhưng vẫn là dự phóng"


@lru_cache(maxsize=1)
def _prompt_template() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _fallback_data() -> dict[str, Any]:
    with open(_FALLBACK_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _coerce_context(
    raw: LifeOutcomeContext | dict[str, Any] | None,
) -> LifeOutcomeContext:
    if isinstance(raw, LifeOutcomeContext):
        return raw
    if isinstance(raw, dict):
        return LifeOutcomeContext(
            location=str(raw.get("location") or "TP.HCM"),
            known_goals=list(raw.get("known_goals") or []),
            age=raw.get("age"),
            dependents=raw.get("dependents"),
            user_segment=str(
                raw.get("user_segment") or raw.get("wealth_level") or "mass_affluent"
            ),
        )
    return LifeOutcomeContext()
