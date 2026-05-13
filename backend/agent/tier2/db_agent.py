"""Tier 2 DB-Agent — DeepSeek function calling, single-step.

Pipeline:

    user query
       │
       ▼  DeepSeek (chat.completions w/ tools=…, tool_choice="auto")
    tool_call (name, JSON args)
       │
       ▼  Pydantic validation against tool.input_schema
    typed input
       │
       ▼  tool.execute(input, user, db) — pure Python, deterministic
    typed output (Pydantic dump)
       │
       ▼  formatter (separate module, S5)
    user-facing string

Why "single-step" here: Tier 2 trades reasoning for cost. If the LLM
needs to chain tool calls, that's by definition a Tier 3 query and
the orchestrator (Epic 2) will route it there. Locking Tier 2 to
the FIRST tool call keeps cost predictable and rejects ambiguous
inputs cleanly.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.tools.base import ToolRegistry
from backend.agent.tier2.prompts import build_db_agent_prompt
from backend.config import get_settings
from backend.models.conversation_context import ROLE_ASSISTANT, ROLE_USER
from backend.models.user import User

logger = logging.getLogger(__name__)

# Cost / latency caps. Hard-coded here rather than pulled from
# settings because changing them is a code review event — they shape
# the worst case of every query.
_DEEPSEEK_MODEL = "deepseek-chat"
_MAX_TOKENS = 500
_TEMPERATURE = 0.0
_TIMEOUT_SECONDS = 15.0


@dataclass
class DBAgentResult:
    """Structured outcome of one Tier 2 invocation.

    A dataclass instead of a dict because callers (formatter, audit
    log, tests) inspect specific fields and dataclass attribute
    access keeps mistakes obvious."""

    success: bool
    tool_called: str | None = None
    tool_args: dict | None = None
    result: dict | None = None
    error: str | None = None
    fallback_text: str | None = None
    # Telemetry — populated even on failure so the audit log
    # (Epic 3) can spot expensive failures.
    latency_ms: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    raw_llm_message: dict | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        """Serialise for logging / response formatting.

        Excludes ``raw_llm_message`` from the default dump because it
        can be large and isn't needed downstream — callers that want
        it can grab it directly."""
        return {
            "success": self.success,
            "tool_called": self.tool_called,
            "tool_args": self.tool_args,
            "result": self.result,
            "error": self.error,
            "fallback_text": self.fallback_text,
            "latency_ms": self.latency_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }


class DBAgent:
    """DeepSeek-backed function-calling agent.

    Construction is cheap — the OpenAI async client is lazy and
    cached, and the tool schema list is computed once. Re-instantiating
    per request is fine; sharing across requests is fine too."""

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self.registry = registry
        self._client = client
        self._tool_specs = registry.to_openai_functions()

    # ------------------------------------------------------------------
    # public
    # ------------------------------------------------------------------

    async def answer(
        self,
        query: str,
        user: User,
        db: AsyncSession,
        *,
        history: list | None = None,
    ) -> DBAgentResult:
        """Translate ``query`` to a tool call, execute, return result.

        ``history`` is the user's recent conversation buffer (oldest
        → newest). When provided, the prior turns are injected as
        chat-completion messages so a follow-up like "so với tháng 3
        thì sao?" carries context from the previous answer.

        On any exception we still return a ``DBAgentResult`` (with
        ``success=False`` and an ``error`` string) so the orchestrator
        can decide between fallback and re-raise. Letting exceptions
        propagate would force every caller to wrap us in try/except —
        the agent is the right place to consolidate that."""
        started = time.monotonic()
        try:
            return await self._answer_inner(query, user, db, started, history)
        except Exception as e:  # noqa: BLE001
            logger.exception("DBAgent unexpected failure: %s", e)
            return DBAgentResult(
                success=False,
                error=f"agent_error: {e!r}",
                latency_ms=int((time.monotonic() - started) * 1000),
            )

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    async def _answer_inner(
        self,
        query: str,
        user: User,
        db: AsyncSession,
        started: float,
        history: list | None,
    ) -> DBAgentResult:
        client = self._get_client()
        if client is None:
            return DBAgentResult(
                success=False,
                error="deepseek_not_configured",
                latency_ms=int((time.monotonic() - started) * 1000),
            )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": build_db_agent_prompt()},
        ]
        # Inject prior turns so follow-up questions carry context.
        # OpenAI chat-completions accepts free-form user/assistant
        # text alongside tools; the model uses it for grounding only.
        for turn in history or []:
            role = turn.role
            if role not in (ROLE_USER, ROLE_ASSISTANT):
                continue
            messages.append({"role": role, "content": turn.content})
        messages.append({"role": "user", "content": query})

        response = await client.chat.completions.create(
            model=_DEEPSEEK_MODEL,
            messages=messages,
            tools=self._tool_specs,
            tool_choice="auto",
            max_tokens=_MAX_TOKENS,
            temperature=_TEMPERATURE,
            timeout=_TIMEOUT_SECONDS,
        )

        message = response.choices[0].message
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", None) if usage else None
        output_tokens = getattr(usage, "completion_tokens", None) if usage else None

        # No tool selected — graceful fallback. Phase 3.5 dispatcher
        # or Tier 3 (Epic 2) handles the rest.
        if not message.tool_calls:
            return DBAgentResult(
                success=False,
                error="no_tool_selected",
                fallback_text=message.content,
                latency_ms=int((time.monotonic() - started) * 1000),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        # Tier 2 = single-step. We only honour the first tool call.
        # If the LLM proposes a chain, that's an orchestrator routing
        # mistake; Epic 2 will catch it via heuristics + escalate.
        call = message.tool_calls[0]
        tool_name = call.function.name
        tool_args_raw = call.function.arguments or "{}"

        tool = self.registry.get(tool_name)
        if tool is None:
            return DBAgentResult(
                success=False,
                tool_called=tool_name,
                error=f"unknown_tool:{tool_name}",
                latency_ms=int((time.monotonic() - started) * 1000),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        try:
            args_dict = json.loads(tool_args_raw)
        except json.JSONDecodeError as e:
            return DBAgentResult(
                success=False,
                tool_called=tool_name,
                error=f"invalid_args_json:{e.msg}",
                latency_ms=int((time.monotonic() - started) * 1000),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        try:
            validated = tool.input_schema(**args_dict)
        except Exception as e:  # noqa: BLE001 - pydantic ValidationError
            return DBAgentResult(
                success=False,
                tool_called=tool_name,
                tool_args=args_dict,
                error=f"invalid_args:{e!s}",
                latency_ms=int((time.monotonic() - started) * 1000),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        result = await tool.execute(validated, user, db)

        return DBAgentResult(
            success=True,
            tool_called=tool_name,
            tool_args=validated.model_dump(mode="json"),
            result=result.model_dump(mode="json"),
            latency_ms=int((time.monotonic() - started) * 1000),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    # ------------------------------------------------------------------

    def _get_client(self) -> AsyncOpenAI | None:
        """Lazily build the DeepSeek client.

        Returns None when ``deepseek_api_key`` isn't set so tests and
        local environments without LLM credentials can still import
        + instantiate the agent without raising."""
        if self._client is not None:
            return self._client
        settings = get_settings()
        if not settings.deepseek_api_key:
            return None
        self._client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )
        return self._client
