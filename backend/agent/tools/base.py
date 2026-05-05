"""Base tool interface + registry.

A ``Tool`` is the unit the LLM can invoke. The contract:

- ``name`` / ``description`` / ``input_schema`` are serialised into
  the function-calling spec sent to the LLM.
- ``execute()`` runs deterministic Python — no LLM calls inside,
  no extra data fetching that the schema doesn't advertise.
- ``execute()`` receives ``(input, user, db)`` so tests can pass a
  fresh AsyncSession and the layer contract (services flush only,
  caller commits) is preserved transitively. Tools are read-only in
  Epic 1 so the commit boundary doesn't matter, but the signature is
  ready for write tools later.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Type

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user import User


class Tool(ABC):
    """Abstract base for all agent tools.

    Subclasses MUST be cheap to construct — the orchestrator
    instantiates a registry per request (or once at startup). Heavy
    setup (e.g. HTTP clients) should live in module-level singletons
    or be lazy-initialised."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable identifier the LLM uses to call the tool."""

    @property
    @abstractmethod
    def description(self) -> str:
        """LLM-facing description.

        This is the single biggest lever on tool-selection accuracy:
        include 3-5 concrete query → tool-call examples per tool."""

    @property
    @abstractmethod
    def input_schema(self) -> Type[BaseModel]:
        """Pydantic model describing accepted inputs."""

    @property
    @abstractmethod
    def output_schema(self) -> Type[BaseModel]:
        """Pydantic model describing the result shape."""

    @abstractmethod
    async def execute(
        self,
        input_data: BaseModel,
        user: User,
        db: AsyncSession,
    ) -> BaseModel:
        """Run the tool. Must be deterministic given (input, user, db)."""

    def to_openai_function(self) -> dict:
        """Serialise to OpenAI function-calling format.

        DeepSeek follows the same shape, so this works for Tier 2.
        Claude (Tier 3) has a slightly different schema; that
        conversion lives in the ReasoningAgent in Epic 2.
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema.model_json_schema(),
            },
        }


class ToolRegistry:
    """In-memory tool registry.

    A registry is just a name→Tool map, but isolating it behind a
    class makes it trivial to swap (e.g. test registry with mocks)
    and exposes ``to_openai_functions`` so the agent can hand the
    whole catalog to the LLM in one call."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_all(self) -> list[Tool]:
        return list(self._tools.values())

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def to_openai_functions(self) -> list[dict]:
        return [t.to_openai_function() for t in self._tools.values()]
