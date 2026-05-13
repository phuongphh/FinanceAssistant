"""Guard tests for the handler/service boundary (Phase B2).

Handlers route intents, extract Telegram data, and delegate to
services. They must NOT build SQLAlchemy queries against domain
models directly — every lookup belongs in the service layer so we
don't end up with two competing implementations of the same query
(we already hit that exact bug in ``onboarding_service`` and in
``callbacks.py`` before this refactor).

This test greps for the pattern and fails the build if a new
handler regresses it. Not perfect — AST would be stricter — but
it's fast, dependency-free, and catches the classes of drift we've
actually seen.
"""
from __future__ import annotations

import re
from pathlib import Path


HANDLER_DIR = Path(__file__).resolve().parents[1] / "bot" / "handlers"

# Patterns that indicate a handler is running raw ORM queries against
# the User model — the thing the service layer should own.
FORBIDDEN_PATTERNS = [
    # select(User).where(User.telegram_id == ...) — classic duplication
    # of dashboard_service.get_user_by_telegram_id.
    re.compile(r"\bselect\s*\(\s*User\b"),
    re.compile(r"\bUser\.telegram_id\s*=="),
]


def test_handlers_do_not_query_user_directly():
    offenders: list[str] = []

    for path in HANDLER_DIR.rglob("*.py"):
        source = path.read_text()
        for pattern in FORBIDDEN_PATTERNS:
            for match in pattern.finditer(source):
                line_no = source.count("\n", 0, match.start()) + 1
                offenders.append(
                    f"{path.name}:{line_no}  matches {pattern.pattern!r}"
                )

    assert not offenders, (
        "Handlers must go through the service layer for User lookups "
        "(use backend.services.dashboard_service.get_user_by_telegram_id). "
        "Found raw queries:\n  " + "\n  ".join(offenders)
    )
