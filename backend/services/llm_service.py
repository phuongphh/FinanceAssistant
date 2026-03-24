import hashlib
import logging
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
    use_cache: bool = True,
) -> str:
    prompt_hash = _hash_prompt(prompt)
    cache_key = f"{task_type}:{prompt_hash}"

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
    prompt = CATEGORIZE_PROMPT.format(
        merchant=merchant or "N/A",
        description=description or "N/A",
        amount=amount,
    )
    try:
        result = await call_llm(prompt, task_type="categorize", db=db)
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
