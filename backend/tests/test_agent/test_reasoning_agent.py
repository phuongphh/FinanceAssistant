"""ReasoningAgent unit tests — multi-tool loop, disclaimer enforcement,
streaming callback, error handling, hard caps.

The Anthropic client is fully stubbed: each test feeds a scripted
list of ``messages.create`` responses (mixing ``tool_use`` and
``end_turn`` stop reasons). This lets us drive the loop deterministically
without network access."""
from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.agent.tier3.prompts import DISCLAIMER
from backend.agent.tier3.reasoning_agent import ReasoningAgent
from backend.agent.tools import build_default_registry
from backend.agent.tools.schemas import GetAssetsOutput
from backend.wealth.services import net_worth_calculator


def _text_block(text: str):
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(name: str, args: dict, id: str = "tu1"):
    return SimpleNamespace(type="tool_use", name=name, input=args, id=id)


def _response(*, content, stop_reason: str, in_tok=200, out_tok=80):
    return SimpleNamespace(
        content=content,
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=in_tok, output_tokens=out_tok),
    )


def _stub_client(responses: list):
    """Each ``messages.create`` consumes one response from the list."""
    iterator = iter(responses)
    client = MagicMock()
    client.messages = MagicMock()

    async def create(**kwargs):
        return next(iterator)

    client.messages.create = AsyncMock(side_effect=create)
    return client


def _user(name="Hà"):
    u = MagicMock()
    u.id = uuid.uuid4()
    u.display_name = name
    return u


def _empty_breakdown():
    br = net_worth_calculator.NetWorthBreakdown()
    br.total = Decimal("100_000_000")
    return br


@pytest.fixture(autouse=True)
def _patch_net_worth(monkeypatch):
    """Stub net_worth_calculator so prompt build works without DB."""
    async def fake(_db, _uid):
        return _empty_breakdown()

    monkeypatch.setattr(net_worth_calculator, "calculate", fake)


@pytest.mark.asyncio
class TestSingleTurn:
    async def test_text_only_response_appends_disclaimer(self):
        agent = ReasoningAgent(
            build_default_registry(),
            client=_stub_client([
                _response(
                    content=[_text_block("Net worth của bạn là 100tr đồng.")],
                    stop_reason="end_turn",
                )
            ]),
        )
        chunks: list[str] = []

        async def cap(c: str): chunks.append(c)

        trace = await agent.answer_streaming(
            "tài sản của tôi", _user(), MagicMock(), cap
        )
        assert trace.success is True
        assert trace.tool_call_count == 0
        assert chunks  # something was emitted
        assert DISCLAIMER in trace.final_text

    async def test_disclaimer_not_doubled(self):
        text = (
            f"Bạn nên xem xét diversify thêm.\n\n"
            f"Đây là gợi ý dựa trên data, không phải lời khuyên đầu tư chuyên nghiệp."
        )
        agent = ReasoningAgent(
            build_default_registry(),
            client=_stub_client([
                _response(content=[_text_block(text)], stop_reason="end_turn")
            ]),
        )
        async def cap(_): pass
        trace = await agent.answer_streaming(
            "có nên diversify không", _user(), MagicMock(), cap
        )
        # Disclaimer marker appears only once (heuristic match, not strict).
        assert trace.final_text.lower().count(
            "không phải lời khuyên đầu tư"
        ) == 1


@pytest.mark.asyncio
class TestMultiToolLoop:
    async def test_tool_use_then_final(self, monkeypatch):
        # Stub tool execution so we don't hit AssetService.
        registry = build_default_registry()
        async def fake_exec(_input, _user, _db):
            return GetAssetsOutput(
                assets=[], total_value=Decimal(0), count=0
            )
        registry.get("get_assets").execute = fake_exec  # type: ignore

        agent = ReasoningAgent(
            registry,
            client=_stub_client([
                # Round 1: Claude asks for get_assets.
                _response(
                    content=[
                        _tool_use_block("get_assets", {}, id="tu1"),
                    ],
                    stop_reason="tool_use",
                ),
                # Round 2: Claude composes final answer.
                _response(
                    content=[_text_block("Bạn chưa có tài sản nào.")],
                    stop_reason="end_turn",
                ),
            ]),
        )
        chunks: list[str] = []

        async def cap(c): chunks.append(c)

        trace = await agent.answer_streaming(
            "phân tích portfolio", _user(), MagicMock(), cap
        )
        assert trace.success is True
        assert trace.tool_call_count == 1
        assert trace.tool_calls[0]["name"] == "get_assets"
        assert "Bạn chưa có tài sản nào." in trace.final_text

    async def test_unknown_tool_surfaces_as_error(self):
        registry = build_default_registry()
        agent = ReasoningAgent(
            registry,
            client=_stub_client([
                _response(
                    content=[_tool_use_block("nonexistent_tool", {})],
                    stop_reason="tool_use",
                ),
                _response(
                    content=[_text_block("Mình không có công cụ đó.")],
                    stop_reason="end_turn",
                ),
            ]),
        )
        async def cap(_): pass
        trace = await agent.answer_streaming(
            "x", _user(), MagicMock(), cap
        )
        assert trace.tool_call_count == 1
        assert "error" in trace.tool_calls[0]
        assert trace.success is True  # final answer still composed

    async def test_invalid_tool_args_surface_as_error(self):
        registry = build_default_registry()
        agent = ReasoningAgent(
            registry,
            client=_stub_client([
                _response(
                    content=[
                        _tool_use_block(
                            "get_assets", {"limit": 99999}  # > 100 → fails
                        )
                    ],
                    stop_reason="tool_use",
                ),
                _response(
                    content=[_text_block("Sẽ tạm dừng và hỏi lại.")],
                    stop_reason="end_turn",
                ),
            ]),
        )
        async def cap(_): pass
        trace = await agent.answer_streaming(
            "?", _user(), MagicMock(), cap
        )
        assert "error" in trace.tool_calls[0]


@pytest.mark.asyncio
class TestHardCaps:
    async def test_max_tool_calls_enforced(self, monkeypatch):
        from backend.agent import limits as lim
        monkeypatch.setattr(lim, "MAX_TOOL_CALLS_PER_QUERY", 2)
        # Re-import to pick up patch — actually our agent reads at import
        # time. Patch the imported alias directly:
        from backend.agent.tier3 import reasoning_agent
        monkeypatch.setattr(reasoning_agent, "MAX_TOOL_CALLS_PER_QUERY", 2)

        registry = build_default_registry()
        async def fake_exec(_input, _user, _db):
            return GetAssetsOutput(assets=[], total_value=Decimal(0), count=0)
        registry.get("get_assets").execute = fake_exec  # type: ignore

        # Always return tool_use → triggers cap.
        agent = ReasoningAgent(
            registry,
            client=_stub_client([
                _response(
                    content=[_tool_use_block("get_assets", {}, id=f"tu{i}")],
                    stop_reason="tool_use",
                )
                for i in range(5)
            ]),
        )
        chunks: list[str] = []

        async def cap(c): chunks.append(c)

        trace = await agent.answer_streaming("?", _user(), MagicMock(), cap)
        assert trace.hit_tool_cap is True
        assert trace.success is False
        assert chunks  # we still surfaced something

    async def test_timeout_caught(self, monkeypatch):
        # Make the inner loop hang so wait_for raises.
        async def hang(*args, **kwargs):
            await asyncio.sleep(60)

        agent = ReasoningAgent(
            build_default_registry(),
            client=MagicMock(messages=MagicMock(create=AsyncMock(side_effect=hang))),
        )
        from backend.agent.tier3 import reasoning_agent
        monkeypatch.setattr(reasoning_agent, "QUERY_TIMEOUT_SECONDS", 0.05)

        chunks: list[str] = []

        async def cap(c): chunks.append(c)

        trace = await agent.answer_streaming("?", _user(), MagicMock(), cap)
        assert trace.timed_out is True
        assert trace.success is False
        assert any("thử lại" in c.lower() for c in chunks)


@pytest.mark.asyncio
class TestNoCredentials:
    async def test_no_anthropic_key_returns_graceful(self, monkeypatch):
        from backend.config import get_settings
        s = get_settings()
        original = s.anthropic_api_key
        s.anthropic_api_key = ""
        try:
            agent = ReasoningAgent(build_default_registry())
            chunks: list[str] = []

            async def cap(c): chunks.append(c)

            trace = await agent.answer_streaming("?", _user(), MagicMock(), cap)
        finally:
            s.anthropic_api_key = original

        assert trace.success is False
        assert trace.error == "anthropic_not_configured"
        assert any("chưa bật" in c.lower() for c in chunks)


@pytest.mark.asyncio
class TestCallbackResilience:
    async def test_callback_exception_doesnt_crash_agent(self):
        agent = ReasoningAgent(
            build_default_registry(),
            client=_stub_client([
                _response(
                    content=[_text_block("Final answer.")],
                    stop_reason="end_turn",
                )
            ]),
        )

        async def bad_callback(_):
            raise RuntimeError("connection lost")

        trace = await agent.answer_streaming(
            "?", _user(), MagicMock(), bad_callback
        )
        # Agent still completes successfully even if streamer dies.
        assert trace.success is True
