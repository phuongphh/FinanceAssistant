"""Response cache for the Phase 3.7 agent stack.

Cuts cost + latency on repeat queries:

- **Tier 2** (5-minute TTL): keyed by ``user_id + query_hash``. The
  cached entry holds the full ``DBAgentResult`` dump so we replay the
  same answer without re-calling DeepSeek AND without re-running the
  tool (which means a stale DB write within 5 minutes won't show up;
  acceptable for filter/sort queries that move slowly).
- **Tier 3** (1-hour TTL): keyed by ``user_id + query_hash``. Stores
  the final response text. The 1-hour bucket is generous because
  reasoning is expensive (~$0.005/call) and users rarely change
  their mind faster than that.

Storage backend: ``LLMCache`` table (Postgres). The phase doc calls
for Redis; Redis isn't a project dependency yet (CLAUDE.md flags it
as Phase 1+). Postgres is fine for Phase 0/1 single-user; Redis swap
is a one-class change behind this module's interface.

Per-user keying is mandatory — never use ``shared_cache=True`` here,
since the answer always references the user's own data.
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.llm_cache import LLMCache

logger = logging.getLogger(__name__)

# TTLs (seconds) — exposed as constants so tests can monkey-patch.
TIER2_TTL_SECONDS = 5 * 60
TIER3_TTL_SECONDS = 60 * 60

# Cache key prefixes — change these to invalidate ALL entries for
# one tier (e.g. after a breaking schema change to DBAgentResult).
TIER2_PREFIX = "agent:t2"
TIER3_PREFIX = "agent:t3"

_MODEL_TIER2 = "agent_tier2"
_MODEL_TIER3 = "agent_tier3"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def get_tier2(
    db: AsyncSession, *, user_id: uuid.UUID, query: str
) -> dict | None:
    """Return cached Tier 2 result dict, or None on miss / expiry."""
    raw = await _get(db, _key_tier2(user_id, query))
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Don't crash on a corrupted entry — treat as a miss.
        logger.warning("tier2 cache entry is not JSON; treating as miss")
        return None


async def set_tier2(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    query: str,
    result: dict,
) -> None:
    """Store a Tier 2 result dict for ``TIER2_TTL_SECONDS``.

    The result must be JSON-serialisable; the orchestrator hands us
    the Pydantic ``model_dump(mode='json')`` output so it always is.
    Service flushes only — caller commits."""
    await _set(
        db,
        key=_key_tier2(user_id, query),
        value=json.dumps(result, default=str),
        model=_MODEL_TIER2,
        ttl_seconds=TIER2_TTL_SECONDS,
    )


async def get_tier3(
    db: AsyncSession, *, user_id: uuid.UUID, query: str
) -> str | None:
    """Return cached Tier 3 response text, or None on miss / expiry."""
    return await _get(db, _key_tier3(user_id, query))


async def set_tier3(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    query: str,
    response: str,
) -> None:
    """Store a Tier 3 response for ``TIER3_TTL_SECONDS``."""
    await _set(
        db,
        key=_key_tier3(user_id, query),
        value=response,
        model=_MODEL_TIER3,
        ttl_seconds=TIER3_TTL_SECONDS,
    )


async def invalidate_user(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Drop every cached entry for ``user_id``. Returns count deleted.

    Called on writes that change the user's data (asset add/edit,
    transaction add). Pattern delete is cheap on Postgres — the
    ``cache_key`` index makes the LIKE selective.
    """
    pattern = f"%:{user_id}:%"
    stmt = delete(LLMCache).where(LLMCache.cache_key.like(pattern))
    result = await db.execute(stmt)
    return int(result.rowcount or 0)


# ---------------------------------------------------------------------------
# Key construction — short, deterministic, per-user
# ---------------------------------------------------------------------------


def _key_tier2(user_id: uuid.UUID, query: str) -> str:
    return f"{TIER2_PREFIX}:{user_id}:{_query_hash(query)}"


def _key_tier3(user_id: uuid.UUID, query: str) -> str:
    return f"{TIER3_PREFIX}:{user_id}:{_query_hash(query)}"


def _query_hash(query: str) -> str:
    """Lowercase + strip + sha256[:16]. The lower/strip means
    "VNM giá?" and " vnm giá ? " hit the same cache entry — useful
    for typos / casing variation; ignored for actual semantic
    differences (those should miss anyway)."""
    norm = (query or "").strip().lower()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Storage primitives
# ---------------------------------------------------------------------------


async def _get(db: AsyncSession, key: str) -> str | None:
    stmt = select(LLMCache).where(
        LLMCache.cache_key == key,
        LLMCache.expires_at > datetime.utcnow(),
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    return row.response if row is not None else None


async def _set(
    db: AsyncSession,
    *,
    key: str,
    value: str,
    model: str,
    ttl_seconds: int,
) -> None:
    """Upsert an entry. Uses delete-then-insert because LLMCache has
    a unique constraint on cache_key — Postgres ``ON CONFLICT`` would
    be cleaner but means coupling to dialect-specific syntax which
    the rest of this module avoids. Two queries is fine for a cache
    write."""
    expires = datetime.utcnow() + timedelta(seconds=ttl_seconds)
    # Replace any prior entry with the same key.
    await db.execute(delete(LLMCache).where(LLMCache.cache_key == key))
    db.add(
        LLMCache(
            cache_key=key,
            model=model,
            prompt_hash=key.split(":")[-1],
            response=value,
            tokens_used=None,
            expires_at=expires,
        )
    )
    # Service flushes only — caller commits per layer contract.
    await db.flush()
