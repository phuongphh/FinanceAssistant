"""Polite out-of-scope reply handler.

Picks an OOS bucket from the raw query (weather / entertainment /
US market / personal-advice / general-knowledge / general) and returns
one of the YAML-loaded variations. Logs the query for future pattern
expansion (does NOT log to the events table — uses Python logger only,
so the analytics PII guard isn't tripped).
"""
from __future__ import annotations

import logging
import random
from functools import lru_cache
from pathlib import Path

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.intent.extractors._normalize import strip_diacritics
from backend.intent.handlers.base import IntentHandler
from backend.intent.intents import IntentResult
from backend.models.user import User

logger = logging.getLogger(__name__)

_RESPONSES_PATH = (
    Path(__file__).resolve().parents[3]
    / "content"
    / "out_of_scope_responses.yaml"
)

# Each bucket has a list of (compiled keyword, ...). First match wins.
# Order matters — `us_market` before `general_knowledge` so "thị
# trường Mỹ" doesn't slip into the catch-all bucket.
_BUCKET_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    (
        "weather",
        (
            "thoi tiet", "troi mua", "troi nang", "weather", "nhiet do",
            "mua to", "mua nho", "rain", "sunny",
        ),
    ),
    (
        "entertainment",
        (
            "ke chuyen", "chuyen cuoi", "hat cho", "lam tho",
            "joke", "tell me a joke", "sing",
        ),
    ),
    (
        "us_market",
        (
            "co phieu my", "thi truong my", "us stock", "nasdaq",
            "wall street", "dow jones", "s&p", "sp500",
            "aapl", "googl", "msft", "tsla", "amzn", "meta", "nvda",
        ),
    ),
    (
        "personal_advice",
        (
            "co nen ket hon", "ket hon khong", "lam ban voi",
            "lam ban gai", "ly hon", "co nen yeu",
        ),
    ),
    (
        "general_knowledge",
        (
            "thu do", "tong thong", "vua", "lich su", "khoa hoc",
            "ai la nguoi", "capital of", "wikipedia",
        ),
    ),
]


@lru_cache(maxsize=1)
def _load_responses() -> dict[str, list[str]]:
    if not _RESPONSES_PATH.exists():
        logger.warning("OOS responses YAML missing at %s", _RESPONSES_PATH)
        return {}
    with _RESPONSES_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {k: list(v) for k, v in data.items() if isinstance(v, list)}


def detect_bucket(text: str) -> str:
    """Return the OOS bucket for ``text`` — defaults to ``general``."""
    if not text:
        return "general"
    needle = strip_diacritics(text.lower())
    for bucket, keywords in _BUCKET_KEYWORDS:
        if any(kw in needle for kw in keywords):
            return bucket
    return "general"


class OutOfScopeHandler(IntentHandler):
    """Replaces the legacy meta OutOfScopeHandler with bucket-aware
    responses. Registered in the dispatcher under ``IntentType.OUT_OF_SCOPE``.
    """

    async def handle(
        self, intent: IntentResult, user: User, db: AsyncSession
    ) -> str:
        bucket = detect_bucket(intent.raw_text or "")
        templates = _load_responses().get(bucket) or _load_responses().get(
            "general"
        )
        if not templates:
            # Final fallback — YAML missing entirely.
            return (
                "Mình chưa biết trả lời câu này, nhưng mình giúp được về "
                "tài sản, chi tiêu, thị trường, mục tiêu."
            )

        # Truncate raw_text for analytics — the PII guard will drop
        # ``raw_text`` anyway (matches the PII regex), so we log under
        # a non-protected key instead.
        analytics.track(
            "intent_oos_declined",
            user_id=user.id,
            properties={
                "oos_category": bucket,
                "query_length": len(intent.raw_text or ""),
                "classifier": intent.classifier_used,
            },
        )

        template = random.choice(templates)
        name = user.display_name or "bạn"
        truncated = (intent.raw_text or "")[:80]
        return template.format(name=name, raw_text=truncated)
