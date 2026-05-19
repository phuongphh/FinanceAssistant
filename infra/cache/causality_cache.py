from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class _Entry:
    value: Any
    expires_at: float


_CACHE: dict[str, _Entry] = {}


def get(key: str) -> Any | None:
    entry = _CACHE.get(key)
    if entry is None:
        return None
    if entry.expires_at < time.time():
        _CACHE.pop(key, None)
        return None
    return entry.value


def set(key: str, value: Any, ttl_seconds: int = 86_400) -> None:
    _CACHE[key] = _Entry(value=value, expires_at=time.time() + ttl_seconds)


def clear() -> None:
    _CACHE.clear()
