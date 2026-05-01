"""Handler interface for Phase 3.5.

Every concrete handler implements ``async handle(intent, user, db)``
and returns a Telegram-ready text string. Why we pass ``db`` rather
than letting the handler open one:

  - Honours the layer contract from CLAUDE.md § 0.1: the worker (caller)
    owns the transaction boundary, the handler only reads/flushes.
  - Lets tests pass a fake AsyncSession without monkey-patching globals.

If a handler needs personality or formatting helpers, import them in
the concrete module — the base interface stays bare on purpose.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession

from backend.intent.intents import IntentResult
from backend.models.user import User


class IntentHandler(ABC):
    @abstractmethod
    async def handle(
        self, intent: IntentResult, user: User, db: AsyncSession
    ) -> str:
        """Execute the intent and return the user-facing reply."""
