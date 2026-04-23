import hashlib
import logging
import uuid
from datetime import datetime, timedelta

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.models.llm_cache import LLMCache

logger = logging.getLogger(__name__)
settings = get_settings()

# DeepSeek uses OpenAI-compatible API
deepseek_client = AsyncOpenAI(
    api_key=settings.deepseek_api_key,
    base_url=settings.deepseek_base_url,
) if settings.deepseek_api_key else None

# Tasks that use Claude (only OCR and complex analysis)
USE_CLAUDE = {"ocr", "complex_analysis"}


class LLMError(Exception):
    pass


def _hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()


def _build_cache_key(
    task_type: str,
    prompt_hash: str,
    user_id: uuid.UUID | None,
    shared_cache: bool,
) -> str:
    """Build a cache key scoped to the right tenant.

    - ``shared_cache=True`` → one entry shared across all users. Use
      only when the prompt contains no user-specific context (e.g.
      ``categorize_expense`` sees only merchant + amount).
    - ``shared_cache=False`` (default) → per-user entry. Prevents one
      user's cached response leaking through to another when the
      prompt is personalised (display_name, goals, income, etc.).
      Falls back to ``anon`` when caller hasn't provided a user_id
      yet, giving those pre-auth responses their own isolated bucket.
    """
    if shared_cache:
        return f"shared:{task_type}:{prompt_hash}"
    uid_part = str(user_id) if user_id else "anon"
    return f"{task_type}:{uid_part}:{prompt_hash}"


async def _get_cached(db: AsyncSession, cache_key: str) -> str | None:
    stmt = select(LLMCache).where(
        LLMCache.cache_key == cache_key,
        LLMCache.expires_at > datetime.utcnow(),
    )
    result = await db.execute(stmt)
    cached = result.scalar_one_or_none()
    if cached:
        logger.debug("LLM cache hit: %s", cache_key)
        return cached.response
    return None


async def _set_cache(
    db: AsyncSession,
    cache_key: str,
    model: str,
    prompt_hash: str,
    response: str,
    tokens_used: int | None,
    ttl_days: int = 30,
) -> None:
    entry = LLMCache(
        cache_key=cache_key,
        model=model,
        prompt_hash=prompt_hash,
        response=response,
        tokens_used=tokens_used,
        expires_at=datetime.utcnow() + timedelta(days=ttl_days),
    )
    db.add(entry)
    await db.flush()


async def call_llm(
    prompt: str,
    task_type: str,
    db: AsyncSession | None = None,
    user_id: uuid.UUID | None = None,
    use_cache: bool = True,
    shared_cache: bool = False,
) -> str:
    """Call an LLM with optional caching.

    Cache key is scoped by ``user_id`` unless ``shared_cache=True``.
    Callers MUST pass either ``user_id`` (normal case) or
    ``shared_cache=True`` (prompt has no user context) when
    ``use_cache=True`` — enforced by a lint test, not runtime, so
    short-lived scripts and background jobs don't have to thread a
    user id through when they genuinely don't have one.

    See docs/strategy/scaling-refactor-B.md §B4 for rationale.
    """
    prompt_hash = _hash_prompt(prompt)
    cache_key = _build_cache_key(task_type, prompt_hash, user_id, shared_cache)

    # Check cache
    if use_cache and db:
        cached = await _get_cached(db, cache_key)
        if cached:
            return cached

    if task_type in USE_CLAUDE:
        raise LLMError(
            f"Task '{task_type}' requires Claude API — use ocr_service directly"
        )

    # DeepSeek for everything else
    if not deepseek_client:
        raise LLMError("DEEPSEEK_API_KEY not configured")

    try:
        response = await deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=500,
        )
        result = response.choices[0].message.content.strip()
        tokens_used = response.usage.total_tokens if response.usage else None
    except Exception as e:
        logger.error("DeepSeek API error: %s", e)
        raise LLMError(f"DeepSeek API call failed: {e}") from e

    # Save to cache
    if use_cache and db:
        await _set_cache(
            db, cache_key, "deepseek-chat", prompt_hash, result, tokens_used
        )

    return result


CATEGORIZE_PROMPT = """Phân loại chi tiêu sau vào MỘT trong các category:
food_drink, transport, shopping, health, entertainment, utilities, investment, savings, other

Thông tin:
- Merchant: {merchant}
- Mô tả: {description}
- Số tiền: {amount}

Chỉ trả về đúng 1 từ category, không giải thích."""


async def categorize_expense(
    merchant: str | None,
    description: str | None,
    amount: float,
    db: AsyncSession | None = None,
) -> str:
    """Categorize an expense via LLM.

    Uses ``shared_cache=True`` — the prompt only contains merchant +
    description + amount, never user-identifying context, so caching
    "Highland coffee 45000" once serves every user. This keeps the
    cache hit rate high (it's our biggest LLM cost driver).
    """
    prompt = CATEGORIZE_PROMPT.format(
        merchant=merchant or "N/A",
        description=description or "N/A",
        amount=amount,
    )
    try:
        result = await call_llm(
            prompt, task_type="categorize", db=db, shared_cache=True
        )
        category = result.strip().lower().replace(" ", "_")
        valid = {
            "food_drink", "transport", "shopping", "health",
            "entertainment", "utilities", "investment",
            "savings", "other",
        }
        if category in valid:
            return category
        logger.warning("LLM returned invalid category '%s', defaulting to needs_review", category)
        return "needs_review"
    except LLMError:
        logger.warning("LLM categorization failed, defaulting to needs_review")
        return "needs_review"
