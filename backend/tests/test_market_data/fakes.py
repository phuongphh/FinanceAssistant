from __future__ import annotations

import fnmatch
import time
from collections.abc import AsyncIterator


class FakeAsyncRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.expires: dict[str, float] = {}

    def _expired(self, key: str) -> bool:
        expires_at = self.expires.get(key)
        if expires_at is None or expires_at > time.time():
            return False
        self.store.pop(key, None)
        self.expires.pop(key, None)
        return True

    async def get(self, key: str):
        if self._expired(key):
            return None
        return self.store.get(key)

    async def set(self, key: str, value: str):
        self.store[key] = value
        self.expires.pop(key, None)
        return True

    async def setex(self, key: str, ttl: int, value: str):
        self.store[key] = value
        self.expires[key] = time.time() + ttl
        return True

    async def incr(self, key: str):
        current = await self.get(key)
        value = int(current or 0) + 1
        self.store[key] = str(value)
        return value

    async def expire(self, key: str, ttl: int):
        if key not in self.store:
            return False
        self.expires[key] = time.time() + ttl
        return True

    async def delete(self, *keys: str):
        deleted = 0
        for key in keys:
            if key in self.store:
                deleted += 1
            self.store.pop(key, None)
            self.expires.pop(key, None)
        return deleted

    async def scan_iter(self, match: str) -> AsyncIterator[str]:
        for key in list(self.store):
            if not self._expired(key) and fnmatch.fnmatch(key, match):
                yield key
