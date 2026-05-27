"""Unit tests for backend.services.llm_service.

Exercises the new branches added when Tier 1 NLU moved to Groq:
provider routing (deepseek vs groq), the timeout override, and the
"provider not configured" error path. We don't hit any real upstream
— ``client.chat.completions.create`` is mocked directly. No DB is
passed, so ``tracked_call`` skips preflight + spend recording.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.llm_service import (
    DEFAULT_MAX_TOKENS,
    TASK_MAX_TOKENS,
    LLMError,
    call_llm,
    settings as llm_settings,
)


def _make_response(text: str, model: str, prompt_tokens: int = 10, completion_tokens: int = 5):
    """Build a MagicMock that quacks like an OpenAI ChatCompletion."""
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = text
    response.usage = MagicMock()
    response.usage.total_tokens = prompt_tokens + completion_tokens
    response.usage.prompt_tokens = prompt_tokens
    response.usage.completion_tokens = completion_tokens
    response.model = model
    return response


def _fake_client(text: str, model: str):
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_make_response(text, model)
    )
    return client


def test_default_max_tokens_is_generous():
    # The 500-token default truncated Vietnamese prose mid-sentence. A
    # generous default is the root-cause fix (max_tokens is a ceiling, not a
    # target) so new generative task_types are safe without registration.
    assert DEFAULT_MAX_TOKENS >= 1000


def test_report_text_falls_back_to_generous_default():
    # report_text used to need an explicit 900 entry just to beat the old
    # 500 default; the generous default now covers it (and all prose tasks),
    # so it no longer needs a dedicated entry.
    assert TASK_MAX_TOKENS.get("report_text", DEFAULT_MAX_TOKENS) >= 900


def test_parse_receipt_has_higher_token_budget():
    # 500 truncated the structuring JSON mid-object in production. This one
    # genuinely needs MORE than the default, so it stays registered.
    assert TASK_MAX_TOKENS["parse_receipt"] > DEFAULT_MAX_TOKENS


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "task_type", ["advisory", "investment_advice", "roadmap_advisory"]
)
async def test_advisory_tasks_get_generous_token_ceiling(task_type):
    """Regression: the 500-token default cut Bé Tiền's advisory replies
    mid-sentence (the 'Tư vấn tối ưu' / 'Cơ hội đầu tư' buttons). Every
    generative advisory task must reach the model with a ceiling well above
    500 — assert against the real wiring, not just the lookup table."""
    client = _fake_client("ok", "deepseek-v4-flash")
    with patch("backend.services.llm_service.deepseek_client", client):
        await call_llm(
            "prompt",
            task_type=task_type,
            use_cache=False,
            shared_cache=True,
        )
    assert client.chat.completions.create.await_args.kwargs["max_tokens"] >= 1000


@pytest.mark.asyncio
async def test_call_llm_groq_provider_uses_groq_client():
    client = _fake_client("ok", "llama-3.3-70b-versatile")
    with patch("backend.services.llm_service.groq_client", client):
        result = await call_llm(
            "prompt",
            task_type="categorize_expense",
            provider="groq",
            use_cache=False,
            shared_cache=True,
        )
    assert result == "ok"
    kwargs = client.chat.completions.create.await_args.kwargs
    assert kwargs["model"] == llm_settings.groq_model


@pytest.mark.asyncio
async def test_call_llm_groq_provider_raises_when_not_configured():
    with patch("backend.services.llm_service.groq_client", None):
        with pytest.raises(LLMError, match="GROQ_API_KEY"):
            await call_llm(
                "prompt",
                task_type="categorize_expense",
                provider="groq",
                use_cache=False,
                shared_cache=True,
            )


@pytest.mark.asyncio
async def test_call_llm_deepseek_provider_uses_v4_flash_model():
    client = _fake_client("ds", "deepseek-v4-flash")
    with patch("backend.services.llm_service.deepseek_client", client):
        result = await call_llm(
            "prompt",
            task_type="categorize_expense",
            provider="deepseek",
            use_cache=False,
            shared_cache=True,
        )
    assert result == "ds"
    kwargs = client.chat.completions.create.await_args.kwargs
    assert kwargs["model"] == "deepseek-v4-flash"


@pytest.mark.asyncio
async def test_call_llm_unknown_provider_raises():
    with pytest.raises(LLMError, match="Unknown LLM provider"):
        await call_llm(
            "prompt",
            task_type="categorize_expense",
            provider="bogus",
            use_cache=False,
            shared_cache=True,
        )


@pytest.mark.asyncio
async def test_call_llm_explicit_timeout_overrides_default():
    client = _fake_client("ok", "deepseek-v4-flash")
    with patch("backend.services.llm_service.deepseek_client", client):
        await call_llm(
            "prompt",
            task_type="categorize_expense",
            use_cache=False,
            shared_cache=True,
            timeout=2.5,
        )
    assert client.chat.completions.create.await_args.kwargs["timeout"] == 2.5


@pytest.mark.asyncio
async def test_call_llm_default_timeout_falls_back_to_settings():
    client = _fake_client("ok", "deepseek-v4-flash")
    with patch("backend.services.llm_service.deepseek_client", client):
        await call_llm(
            "prompt",
            task_type="categorize_expense",
            use_cache=False,
            shared_cache=True,
        )
    assert (
        client.chat.completions.create.await_args.kwargs["timeout"]
        == llm_settings.llm_timeout_seconds
    )
