from __future__ import annotations

import time
from collections import defaultdict

from redis import Redis
from redis.exceptions import RedisError

from backend.config import get_settings

RATE_LIMIT_MAX = 5
RATE_LIMIT_WINDOW_SECONDS = 15 * 60
_RATE_LIMIT_PREFIX = "admin:login_attempts:"
_BLACKLIST_PREFIX = "admin:token_blacklist:"

_memory_attempts: dict[str, list[float]] = defaultdict(list)
_memory_blacklist: dict[str, float] = {}
_redis_client: Redis | None = None


def _redis() -> Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis.from_url(get_settings().admin_redis_url, decode_responses=True)
    return _redis_client


def _prune_memory(now: float) -> None:
    for key, expires_at in list(_memory_blacklist.items()):
        if expires_at <= now:
            _memory_blacklist.pop(key, None)


def check_login_rate_limit(ip_address: str) -> bool:
    key = f"{_RATE_LIMIT_PREFIX}{ip_address}"
    try:
        value = _redis().get(key)
        return int(value or 0) < RATE_LIMIT_MAX
    except (RedisError, OSError, ValueError):
        now = time.time()
        _memory_attempts[ip_address] = [ts for ts in _memory_attempts[ip_address] if ts > now - RATE_LIMIT_WINDOW_SECONDS]
        return len(_memory_attempts[ip_address]) < RATE_LIMIT_MAX


def record_login_attempt(ip_address: str) -> None:
    key = f"{_RATE_LIMIT_PREFIX}{ip_address}"
    try:
        pipe = _redis().pipeline()
        pipe.incr(key)
        pipe.expire(key, RATE_LIMIT_WINDOW_SECONDS)
        pipe.execute()
    except (RedisError, OSError):
        now = time.time()
        _memory_attempts[ip_address] = [ts for ts in _memory_attempts[ip_address] if ts > now - RATE_LIMIT_WINDOW_SECONDS]
        _memory_attempts[ip_address].append(now)


def blacklist_token(jti: str, ttl_seconds: int) -> None:
    if ttl_seconds <= 0:
        return
    key = f"{_BLACKLIST_PREFIX}{jti}"
    try:
        _redis().setex(key, ttl_seconds, "1")
    except (RedisError, OSError):
        now = time.time()
        _prune_memory(now)
        _memory_blacklist[jti] = now + ttl_seconds


def is_token_blacklisted(jti: str) -> bool:
    key = f"{_BLACKLIST_PREFIX}{jti}"
    try:
        return bool(_redis().exists(key))
    except (RedisError, OSError):
        now = time.time()
        _prune_memory(now)
        return _memory_blacklist.get(jti, 0) > now
