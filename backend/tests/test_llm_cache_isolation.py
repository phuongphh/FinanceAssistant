"""Tests for per-user LLM cache isolation (Phase B4).

Two guarantees:
1. Same prompt with different ``user_id`` → different cache entries
   (no cross-user leakage when the prompt is personalised).
2. ``shared_cache=True`` → single entry reused across users (kept for
   user-agnostic prompts like ``categorize_expense`` where cache hit
   rate is the biggest cost lever).

Plus a lint test that grep-audits every ``call_llm(`` in the codebase
for at least one of ``user_id=`` / ``shared_cache=True`` so the
convention can't silently regress in a future PR.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from backend.services.llm_service import _build_cache_key, _hash_prompt


# ---------------------------------------------------------------------------
# _build_cache_key — deterministic, scoped correctly per mode.
# ---------------------------------------------------------------------------

class TestCacheKeyIsolation:
    def test_different_users_produce_different_keys(self):
        h = _hash_prompt("some prompt")
        u1 = uuid.uuid4()
        u2 = uuid.uuid4()

        k1 = _build_cache_key("report_text", h, u1, shared_cache=False)
        k2 = _build_cache_key("report_text", h, u2, shared_cache=False)

        assert k1 != k2
        assert str(u1) in k1
        assert str(u2) in k2

    def test_same_user_same_prompt_produces_same_key(self):
        h = _hash_prompt("some prompt")
        u = uuid.uuid4()

        k1 = _build_cache_key("report_text", h, u, shared_cache=False)
        k2 = _build_cache_key("report_text", h, u, shared_cache=False)

        assert k1 == k2

    def test_shared_cache_ignores_user_id(self):
        """``shared_cache=True`` means the prompt contains no user
        context — one entry must serve every caller regardless of
        user_id (or lack thereof). This is what keeps the
        categorize_expense cache hit rate high."""
        h = _hash_prompt("Highland 45000")
        u1 = uuid.uuid4()
        u2 = uuid.uuid4()

        k_shared_u1 = _build_cache_key("categorize", h, u1, shared_cache=True)
        k_shared_u2 = _build_cache_key("categorize", h, u2, shared_cache=True)
        k_shared_none = _build_cache_key("categorize", h, None, shared_cache=True)

        assert k_shared_u1 == k_shared_u2 == k_shared_none
        assert k_shared_u1.startswith("shared:")

    def test_shared_and_scoped_do_not_collide(self):
        """A scoped "anon" key must not match the shared-cache key
        for the same prompt — otherwise a user-specific anonymous
        request could read a shared-cache entry (or vice versa)."""
        h = _hash_prompt("prompt")
        k_shared = _build_cache_key("t", h, None, shared_cache=True)
        k_anon = _build_cache_key("t", h, None, shared_cache=False)
        assert k_shared != k_anon


# ---------------------------------------------------------------------------
# Lint: every call_llm call site must pass either user_id= or
# shared_cache=True. Prevents a future PR from silently regressing to
# the old cross-user-leakage shape.
# ---------------------------------------------------------------------------

class TestCallLLMAuditConvention:
    # Files where a call_llm invocation lives today. The audit walks the
    # whole backend/ tree so new call sites are picked up automatically.
    CODE_ROOT = Path(__file__).resolve().parents[2] / "backend"

    # Skip the definition itself and the tests directory.
    SKIP_FILES = {
        "llm_service.py",
    }

    @staticmethod
    def _extract_calls(source: str) -> list[str]:
        """Return the text of every ``call_llm(...)`` invocation.

        A naive parenthesis walker is enough because our calls are
        multi-line kwargs, not nested function calls in the first arg.
        """
        calls = []
        i = 0
        while True:
            # Only match the callable, not definitions like ``def call_llm(``.
            match = re.search(r"(?<!def )\bcall_llm\s*\(", source[i:])
            if not match:
                break
            start = i + match.end()
            depth = 1
            j = start
            while j < len(source) and depth > 0:
                if source[j] == "(":
                    depth += 1
                elif source[j] == ")":
                    depth -= 1
                j += 1
            calls.append(source[start:j - 1])
            i = j
        return calls

    def test_every_call_llm_is_tenant_scoped(self):
        offenders: list[str] = []

        for path in self.CODE_ROOT.rglob("*.py"):
            if path.name in self.SKIP_FILES:
                continue
            if "tests" in path.parts:
                continue

            source = path.read_text()
            if "call_llm" not in source:
                continue

            for call in self._extract_calls(source):
                has_user_id = "user_id=" in call
                has_shared = "shared_cache=True" in call
                if not (has_user_id or has_shared):
                    rel = path.relative_to(self.CODE_ROOT.parent)
                    offenders.append(f"{rel}: call_llm({call.strip()[:80]}...)")

        assert not offenders, (
            "Every call_llm(...) must pass user_id= or shared_cache=True "
            "so the cache key is correctly tenant-scoped. Offenders:\n  "
            + "\n  ".join(offenders)
        )
