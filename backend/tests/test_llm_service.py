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


def test_report_text_has_higher_token_budget():
    assert TASK_MAX_TOKENS.get("report_text") == 900


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
