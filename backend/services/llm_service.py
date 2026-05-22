import hashlib
import logging
import uuid
from datetime import datetime, timedelta

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
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

# Groq powers the Tier 1 NLU classifier — Llama 3.3 70B at $0.59/$0.79 per
# 1M tokens with sub-second first-token latency. DeepSeek V4-Flash is fast
# in throughput but takes 4-12s for first token by design (batch-oriented),
# which is too slow for interactive intent classification.
groq_client = AsyncOpenAI(
    api_key=settings.groq_api_key,
    base_url=settings.groq_base_url,
) if settings.groq_api_key else None

# Tasks that use Claude (only OCR and complex analysis)
USE_CLAUDE = {"ocr", "complex_analysis"}
TASK_MAX_TOKENS = {
    # Monthly reports contain multiple sections + bullets and were
    # getting cut mid-sentence at 500 tokens in production.
    "report_text": 900,
}


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
    expires_at = datetime.utcnow() + timedelta(days=ttl_days)
    stmt = insert(LLMCache).values(
        cache_key=cache_key,
        model=model,
        prompt_hash=prompt_hash,
        response=response,
        tokens_used=tokens_used,
        expires_at=expires_at,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[LLMCache.cache_key],
        set_={
            "model": model,
            "prompt_hash": prompt_hash,
            "response": response,
            "tokens_used": tokens_used,
            "expires_at": expires_at,
        },
    )
    await db.execute(stmt)
    await db.flush()


async def call_llm(
    prompt: str,
    task_type: str,
    db: AsyncSession | None = None,
    user_id: uuid.UUID | None = None,
    use_cache: bool = True,
    shared_cache: bool = False,
    cache_ttl_days: int = 30,
    timeout: float | None = None,
    provider: str = "deepseek",
) -> str:
    """Call an LLM with optional caching.

    Cache key is scoped by ``user_id`` unless ``shared_cache=True``.
    Callers MUST pass either ``user_id`` (normal case) or
    ``shared_cache=True`` (prompt has no user context) when
    ``use_cache=True`` — enforced by a lint test, not runtime, so
    short-lived scripts and background jobs don't have to thread a
    user id through when they genuinely don't have one.

    ``provider`` selects between ``"deepseek"`` (default, V4-Flash) and
    ``"groq"`` (Llama 3.3 70B). Use Groq for latency-sensitive Tier 1
    classification — V4-Flash is fast in throughput but takes 4-12s to
    first token by design, which is too slow for interactive paths.

    ``timeout`` overrides ``settings.llm_timeout_seconds`` per call.
    Tier 1 callers pass ~3s (Groq is sub-second). Everything else uses
    the ~60s default so the 4-12s first-token tail on DeepSeek V4-Flash
    doesn't false-alarm.

    See docs/archive/scaling-refactor-B.md §B4 for rationale.
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

    if provider == "groq":
        if not groq_client:
            raise LLMError("GROQ_API_KEY not configured")
        client = groq_client
        model_name = settings.groq_model
    elif provider == "deepseek":
        if not deepseek_client:
            raise LLMError("DEEPSEEK_API_KEY not configured")
        client = deepseek_client
        model_name = "deepseek-v4-flash"
    else:
        raise LLMError(f"Unknown LLM provider '{provider}'")

    effective_timeout = (
        timeout if timeout is not None else settings.llm_timeout_seconds
    )

    # Phase 4.1 Story A.3 — wrap every API call in the cost-tracking
    # context manager. Preflight raises BudgetExceededError BEFORE the
    # upstream HTTP call when the user hit 100% cap; we let it bubble
    # so callers can convert it to the user-facing "tạm dừng" message
    # via content/cost/budget_messages.yaml.
    from backend.adapters.llm.cost_tracking_adapter import tracked_call

    max_tokens = TASK_MAX_TOKENS.get(task_type, 500)

    async with tracked_call(
        db, user_id, provider=provider, operation=task_type
    ) as recorder:
        try:
            response = await client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=max_tokens,
                timeout=effective_timeout,
            )
            result = response.choices[0].message.content.strip()
            tokens_used = response.usage.total_tokens if response.usage else None
            if response.usage:
                recorder.tokens_in = response.usage.prompt_tokens or 0
                recorder.tokens_out = response.usage.completion_tokens or 0
            recorder.model_version = getattr(response, "model", model_name)
        except Exception as e:
            logger.error("%s API error: %s", provider, e)
            raise LLMError(f"{provider} API call failed: {e}") from e

    # Save to cache
    if use_cache and db:
        await _set_cache(
            db, cache_key, model_name, prompt_hash, result, tokens_used, ttl_days=cache_ttl_days
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
