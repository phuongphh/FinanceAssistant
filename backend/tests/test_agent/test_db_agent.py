"""DBAgent tests — mock DeepSeek, verify the full pipeline:

  message → tool selection → arg validation → tool execute → result dict.

We never hit the network. The OpenAI client is replaced with a stub
that returns a hand-crafted ``ChatCompletion`` shape."""
from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.agent.tier2.db_agent import DBAgent, DBAgentResult
from backend.agent.tools import build_default_registry
from backend.agent.tools.schemas import GetAssetsOutput


def _make_chat_response(
    *,
    tool_name: str | None = None,
    tool_args: dict | None = None,
    content: str | None = None,
):
    """Build a fake ChatCompletion mirror that ``DBAgent`` consumes."""
    if tool_name:
        tool_call = SimpleNamespace(
            function=SimpleNamespace(
                name=tool_name,
                arguments=json.dumps(tool_args or {}),
            )
        )
        message = SimpleNamespace(content=None, tool_calls=[tool_call])
    else:
        message = SimpleNamespace(content=content, tool_calls=[])

    choice = SimpleNamespace(message=message)
    usage = SimpleNamespace(prompt_tokens=120, completion_tokens=40)
    return SimpleNamespace(choices=[choice], usage=usage)


def _stub_client(response) -> MagicMock:
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)
    return client


@pytest.mark.asyncio
class TestDBAgent:
    async def test_routes_to_tool_and_executes(self, monkeypatch):
        registry = build_default_registry()
        # Stub the GetAssetsTool execute so we don't hit AssetService.
        async def fake_execute(_input, _user, _db):
            from decimal import Decimal
            return GetAssetsOutput(assets=[], total_value=Decimal(0), count=0)

        registry.get("get_assets").execute = fake_execute  # type: ignore

        agent = DBAgent(
            registry,
            client=_stub_client(
                _make_chat_response(
                    tool_name="get_assets",
                    tool_args={"sort": "value_desc", "limit": 3},
                )
            ),
        )

        result = await agent.answer("top 3 tài sản lớn nhất", _user(), MagicMock())

        assert result.success is True
        assert result.tool_called == "get_assets"
        assert result.tool_args == {"filter": None, "sort": "value_desc", "limit": 3}
        assert result.result == {"assets": [], "total_value": "0", "count": 0}
        assert result.input_tokens == 120
        assert result.output_tokens == 40

    async def test_no_tool_returns_fallback(self):
        registry = build_default_registry()
        agent = DBAgent(
            registry,
            client=_stub_client(
                _make_chat_response(content="mình chưa hiểu ý bạn")
            ),
        )
        result = await agent.answer("hỏi gì đó vu vơ", _user(), MagicMock())
        assert result.success is False
        assert result.error == "no_tool_selected"
        assert result.fallback_text == "mình chưa hiểu ý bạn"

    async def test_invalid_args_fail_validation(self):
        registry = build_default_registry()
        agent = DBAgent(
            registry,
            client=_stub_client(
                _make_chat_response(
                    tool_name="get_assets",
                    # ``limit`` exceeds the max — Pydantic should reject.
                    tool_args={"limit": 9999},
                )
            ),
        )
        result = await agent.answer("top 9999", _user(), MagicMock())
        assert result.success is False
        assert result.error and result.error.startswith("invalid_args")
        assert result.tool_called == "get_assets"

    async def test_unknown_tool_handled(self):
        registry = build_default_registry()
        agent = DBAgent(
            registry,
            client=_stub_client(
                _make_chat_response(
                    tool_name="not_a_tool",
                    tool_args={},
                )
            ),
        )
        result = await agent.answer("?", _user(), MagicMock())
        assert result.success is False
        assert result.error == "unknown_tool:not_a_tool"

    async def test_invalid_args_json(self):
        # Force malformed JSON.
        registry = build_default_registry()
        bad_call = SimpleNamespace(
            function=SimpleNamespace(name="get_assets", arguments="{not-json")
        )
        message = SimpleNamespace(content=None, tool_calls=[bad_call])
        choice = SimpleNamespace(message=message)
        response = SimpleNamespace(
            choices=[choice], usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5)
        )
        agent = DBAgent(registry, client=_stub_client(response))
        result = await agent.answer("?", _user(), MagicMock())
        assert result.success is False
        assert result.error and result.error.startswith("invalid_args_json")

    async def test_no_deepseek_key_returns_graceful_failure(self, monkeypatch):
        # No client passed in, and config has no API key.
        from backend.config import get_settings

        get_settings.cache_clear()
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        registry = build_default_registry()
        agent = DBAgent(registry)  # client=None, will lazily try settings

        # Force settings to have empty API key
        s = get_settings()
        original = s.deepseek_api_key
        s.deepseek_api_key = ""
        try:
            result = await agent.answer("test", _user(), MagicMock())
        finally:
            s.deepseek_api_key = original

        assert result.success is False
        assert result.error == "deepseek_not_configured"

    async def test_to_dict_excludes_raw(self):
        r = DBAgentResult(
            success=True,
            tool_called="get_assets",
            tool_args={"limit": 1},
            result={"count": 0},
            latency_ms=12,
            raw_llm_message={"big": "blob"},
        )
        d = r.to_dict()
        assert "raw_llm_message" not in d
        assert d["tool_called"] == "get_assets"


def _user():
    u = MagicMock()
    u.id = uuid.uuid4()
    u.display_name = "Hà"
    return u
