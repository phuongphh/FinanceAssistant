"""Tier 3 — Claude Sonnet, multi-step tool use, streaming output.

Why this is its own tier (not just "more retries on Tier 2"):

Tier 2 picks ONE tool and returns the structured result. Tier 3
*reasons* across multiple tools — call ``get_assets`` to see the
position, call ``get_market_data`` to see the trend, then synthesise
"here's what you might consider". The cost ratio (Sonnet ~30× DeepSeek
per token) only makes sense when reasoning is genuinely needed.

Streaming is via callback (``on_chunk``). The agent itself is
delivery-agnostic; ``TelegramStreamer`` (S7) plugs in here. Tests can
plug in a list-appending callback to assert the chunks.

Compliance is enforced both ways:
1. Prompt-side — see ``tier3/prompts.py``.
2. Code-side — we auto-append the disclaimer if it's missing,
   regardless of what Claude produced. Belt + suspenders because
   prompt-only enforcement is bypassable.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.limits import (
    MAX_TOOL_CALLS_PER_QUERY,
    QUERY_TIMEOUT_SECONDS,
    estimate_cost_usd,
)
from backend.agent.tier3.prompts import DISCLAIMER, build_reasoning_prompt
from backend.agent.tools.base import ToolRegistry
from backend.config import get_settings
from backend.models.user import User
from backend.wealth.ladder import detect_level
from backend.wealth.services import net_worth_calculator

logger = logging.getLogger(__name__)

# Use the Sonnet model named in the phase doc. Kept as a module
# constant so swapping models is a one-line change, and so the
# audit log's ``llm_model`` field has a single source of truth.
_CLAUDE_MODEL = "claude-sonnet-4-5-20250929"
_MAX_TOKENS_PER_TURN = 2000


OnChunk = Callable[[str], Awaitable[None]]


@dataclass
class ReasoningTrace:
    """What happened during one Tier 3 invocation.

    Streaming means the body of the answer goes via ``on_chunk``;
    this trace captures everything else (tool calls, tokens, latency)
    so audit logs (Epic 3) and tests can inspect the run without
    reconstructing the response from chunks."""

    success: bool
    tool_calls: list[dict] = field(default_factory=list)
    tool_call_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    final_text: str = ""  # Full text after disclaimer enforcement.
    error: str | None = None
    timed_out: bool = False
    hit_tool_cap: bool = False


class ReasoningAgent:
    """Claude-Sonnet-backed reasoning agent.

    Construction is cheap. The Anthropic client is lazily built so
    importing without ``ANTHROPIC_API_KEY`` set doesn't fail (matches
    DBAgent's pattern)."""

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        client: AsyncAnthropic | None = None,
    ) -> None:
        self.registry = registry
        self._client = client

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    async def answer_streaming(
        self,
        query: str,
        user: User,
        db: AsyncSession,
        on_chunk: OnChunk,
    ) -> ReasoningTrace:
        """Process ``query`` with multi-tool reasoning, stream output.

        Wraps the inner loop in ``asyncio.wait_for`` so a hung Claude
        call or runaway tool sequence can't block the worker forever.
        On timeout we still return a trace with ``timed_out=True`` so
        the caller can log it without re-raising."""
        started = time.monotonic()
        trace = ReasoningTrace(success=False)
        try:
            inner = self._answer_inner(query, user, db, on_chunk, trace)
            await asyncio.wait_for(inner, timeout=QUERY_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            trace.timed_out = True
            trace.error = "timeout"
            await _emit(
                on_chunk,
                "Mình cần thêm thời gian — bạn cho mình thử lại sau nhé 🙏",
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("ReasoningAgent unexpected failure: %s", e)
            trace.error = f"agent_error: {e!r}"
            await _emit(
                on_chunk,
                "Mình gặp lỗi khi suy luận. Thử cách hỏi khác xem bạn?",
            )
        finally:
            trace.latency_ms = int((time.monotonic() - started) * 1000)
            trace.cost_usd = estimate_cost_usd(
                model=_CLAUDE_MODEL,
                input_tokens=trace.input_tokens,
                output_tokens=trace.output_tokens,
            )
        return trace

    # ------------------------------------------------------------------
    # core loop
    # ------------------------------------------------------------------

    async def _answer_inner(
        self,
        query: str,
        user: User,
        db: AsyncSession,
        on_chunk: OnChunk,
        trace: ReasoningTrace,
    ) -> None:
        client = self._get_client()
        if client is None:
            trace.error = "anthropic_not_configured"
            await _emit(
                on_chunk,
                "Tính năng tư vấn nâng cao chưa bật. Bạn vẫn xem được "
                "data tài sản qua menu nhé 💚",
            )
            return

        # Build user-specific system prompt.
        breakdown = await net_worth_calculator.calculate(db, user.id)
        level = detect_level(breakdown.total)
        system_prompt = build_reasoning_prompt(
            user_name=user.display_name or "bạn",
            wealth_level=level,
            net_worth=breakdown.total,
            tool_descriptions=self._format_tool_descriptions(),
        )

        claude_tools = self._to_claude_tools()
        messages: list[dict[str, Any]] = [{"role": "user", "content": query}]

        for round_idx in range(MAX_TOOL_CALLS_PER_QUERY + 1):
            response = await client.messages.create(
                model=_CLAUDE_MODEL,
                max_tokens=_MAX_TOKENS_PER_TURN,
                system=system_prompt,
                tools=claude_tools,
                messages=messages,
            )

            # Token accounting accumulates across rounds — multi-turn
            # tool use sends the conversation each time, so each round
            # bills both directions.
            if getattr(response, "usage", None):
                trace.input_tokens += int(response.usage.input_tokens or 0)
                trace.output_tokens += int(response.usage.output_tokens or 0)

            stop = getattr(response, "stop_reason", None)

            if stop == "tool_use":
                # We deliberately handle ALL tool_use blocks in this
                # message before re-asking Claude — Claude can request
                # more than one tool per round and skipping the extras
                # would force it to retry.
                if round_idx >= MAX_TOOL_CALLS_PER_QUERY:
                    # Hit the cap after this turn would put us over.
                    trace.hit_tool_cap = True
                    await _emit(
                        on_chunk,
                        "Mình cần thêm thông tin để trả lời chính xác. "
                        "Bạn có thể hỏi cụ thể hơn được không?",
                    )
                    return

                tool_results = await self._dispatch_tool_uses(
                    response.content, user, db, trace
                )
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})
                continue

            # Final answer. Anthropic returns ``content`` as a list of
            # blocks — concatenate text blocks (Claude doesn't usually
            # emit multiple in a final turn, but tolerate it).
            text = self._extract_text(response.content)
            text = self._enforce_disclaimer(text)
            trace.final_text = text
            trace.success = True
            await _emit(on_chunk, text)
            return

        # Loop should exit via ``return`` above; if we fall through
        # the for loop hit the safety bound — defensive only.
        trace.hit_tool_cap = True
        await _emit(on_chunk, "Mình đã thử nhiều cách nhưng chưa tổng hợp được câu trả lời.")

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    async def _dispatch_tool_uses(
        self,
        content_blocks: list[Any],
        user: User,
        db: AsyncSession,
        trace: ReasoningTrace,
    ) -> list[dict[str, Any]]:
        """Run every ``tool_use`` block from a Claude turn.

        Returns the ``tool_result`` blocks Claude expects in the next
        user message. Bad inputs (Pydantic validation, unknown tool)
        are surfaced as ``tool_result`` errors rather than raised —
        that lets Claude self-correct in the next round."""
        results: list[dict[str, Any]] = []
        for block in content_blocks:
            if getattr(block, "type", None) != "tool_use":
                continue
            tool_name = block.name
            args = block.input or {}
            tool_started = time.monotonic()

            tool = self.registry.get(tool_name)
            if tool is None:
                err = f"Unknown tool: {tool_name}"
                trace.tool_calls.append(
                    {
                        "name": tool_name,
                        "args": args,
                        "error": err,
                        "latency_ms": 0,
                    }
                )
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": err,
                        "is_error": True,
                    }
                )
                trace.tool_call_count += 1
                continue

            try:
                validated = tool.input_schema(**args)
                output = await tool.execute(validated, user, db)
                payload = output.model_dump_json()
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": payload,
                    }
                )
                trace.tool_calls.append(
                    {
                        "name": tool_name,
                        "args": validated.model_dump(mode="json"),
                        "latency_ms": int(
                            (time.monotonic() - tool_started) * 1000
                        ),
                    }
                )
            except Exception as e:  # noqa: BLE001
                trace.tool_calls.append(
                    {
                        "name": tool_name,
                        "args": args,
                        "error": str(e),
                        "latency_ms": int(
                            (time.monotonic() - tool_started) * 1000
                        ),
                    }
                )
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": f"Tool error: {e}",
                        "is_error": True,
                    }
                )
            trace.tool_call_count += 1
        return results

    def _format_tool_descriptions(self) -> str:
        """Compact tool list for the system prompt.

        We give Claude the FULL description (with examples) — those
        examples are how Claude learns argument shapes. The OpenAI
        function-call schema goes through separately in the ``tools``
        param; descriptions here are for selection."""
        lines = []
        for t in self.registry.list_all():
            # First line of the description is enough for an at-a-glance
            # menu; arg-level detail flows via the JSON schema.
            first_line = t.description.split("\n")[0]
            lines.append(f"- {t.name}: {first_line}")
        return "\n".join(lines)

    def _to_claude_tools(self) -> list[dict[str, Any]]:
        """Anthropic's tool format (no nested ``function`` wrapper)."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema.model_json_schema(),
            }
            for t in self.registry.list_all()
        ]

    @staticmethod
    def _extract_text(content_blocks: list[Any]) -> str:
        parts: list[str] = []
        for block in content_blocks or []:
            if getattr(block, "type", None) == "text":
                parts.append(block.text)
        return "".join(parts).strip() or (
            "Mình đang chưa rõ — bạn hỏi lại cụ thể hơn được không?"
        )

    @staticmethod
    def _enforce_disclaimer(text: str) -> str:
        """Append disclaimer if Claude didn't.

        Match heuristic: any plausible variant of "không phải lời
        khuyên đầu tư" — covers Claude paraphrasing slightly. Good
        enough to avoid double-disclaimers without missing real
        omissions."""
        marker = "không phải lời khuyên đầu tư"
        if marker in text.lower():
            return text
        return f"{text.rstrip()}\n\n{DISCLAIMER}"

    def _get_client(self) -> AsyncAnthropic | None:
        if self._client is not None:
            return self._client
        settings = get_settings()
        if not settings.anthropic_api_key:
            return None
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        return self._client


async def _emit(on_chunk: OnChunk, text: str) -> None:
    """Defensive wrapper — never let a chunk callback exception kill
    the agent. Streamers can be flaky (Telegram rate limits, network
    hiccups); that's their problem, not ours."""
    try:
        await on_chunk(text)
    except Exception as e:  # noqa: BLE001
        logger.warning("on_chunk callback raised: %s", e)
