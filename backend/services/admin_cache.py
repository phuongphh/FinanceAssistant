from __future__ import annotations

import json
import logging
from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
from typing import Any

import redis.asyncio as redis

from backend.config import get_settings

logger = logging.getLogger(__name__)


def _json_default(value: Any) -> str | float | int | None:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


@lru_cache(maxsize=1)
def _client() -> redis.Redis:
    return redis.from_url(get_settings().admin_redis_url, decode_responses=True)


async def cache_get(key: str) -> Any | None:
    try:
        raw = await _client().get(key)
    except Exception:
        logger.debug("admin cache get failed for %s", key, exc_info=True)
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def cache_set(key: str, value: Any, ttl_seconds: int) -> None:
    try:
        await _client().setex(key, ttl_seconds, json.dumps(value, default=_json_default))
    except Exception:
        logger.debug("admin cache set failed for %s", key, exc_info=True)
