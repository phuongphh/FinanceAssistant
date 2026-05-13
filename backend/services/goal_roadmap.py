"""Roadmap advisory shortcut (Issue #450 §5).

Free-text queries like "lộ trình mua nhà" are advisory in shape but
deeply cacheable — the answer depends on goal type + wealth level,
not on the user's exact net worth or recent transactions. This module
provides:

  * ``match_roadmap_query`` — pattern match "lộ trình <goal>" against
    the 7 goal templates, returning a template id (or ``None``).
  * ``get_fallback`` — rule-based copy per template id from
    ``content/goal_roadmap_templates.yaml`` for when the LLM is slow
    / down.
  * ``call_roadmap_llm`` — short, deterministic prompt + shared cache
    + hard timeout, so the first user pays the latency once and every
    subsequent (template_id, wealth_level) cache hit lands in <100ms.

Layer contract: read-only service. The caller (advisory handler)
owns the DB session and rate-limit policy.
"""
from __future__ import annotations

import asyncio
import logging
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services import goal_templates
from backend.services.llm_service import LLMError, call_llm

logger = logging.getLogger(__name__)


# Hard cap on the LLM call. Per issue acceptance "Gợi ý lộ trình
# response trong < 8s (P95)" — we set the timeout slightly above the
# P95 budget so a marginal slow call still completes, while a true
# stall hits the fallback. The shared cache pulls P50 down further.
LLM_TIMEOUT_SECONDS = 10.0

# Cache TTL. 24h is long enough that one cold call serves a day of
# users on the same (template_id, wealth_level), short enough that
# YAML-only edits propagate within a day in production.
CACHE_TTL_DAYS = 1


_ROADMAP_TEMPLATES_PATH = (
    Path(__file__).resolve().parents[2]
    / "content"
    / "goal_roadmap_templates.yaml"
)


@dataclass(frozen=True)
class RoadmapFallback:
    """Rule-based answer used when the LLM path fails."""

    title: str
    steps: tuple[str, ...]

    def render(self) -> str:
        """Format as a Telegram-ready Markdown body. Each step is its
        own bullet so the user can skim quickly."""
        bullets = "\n".join(f"• {s}" for s in self.steps)
        return f"*{self.title}*\n\n{bullets}"


@lru_cache(maxsize=1)
def _load_fallbacks() -> dict[str, RoadmapFallback]:
    """Parse the YAML once per process. The file is small (7 entries)
    so we hold all of it in memory."""
    if not _ROADMAP_TEMPLATES_PATH.exists():
        logger.warning("goal_roadmap_templates.yaml missing: %s",
                       _ROADMAP_TEMPLATES_PATH)
        return {}
    with open(_ROADMAP_TEMPLATES_PATH, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    out: dict[str, RoadmapFallback] = {}
    for tid, entry in (raw.get("roadmaps") or {}).items():
        title = entry.get("title") or tid
        steps = tuple(entry.get("steps") or ())
        out[tid] = RoadmapFallback(title=title, steps=steps)
    return out


def get_fallback(template_id: str) -> Optional[RoadmapFallback]:
    """Look up the rule-based template for ``template_id``. Returns
    ``None`` when the YAML has no matching entry — the caller should
    then surface a generic "thử lại sau" message instead of crashing."""
    return _load_fallbacks().get(template_id)


# ---------------------------------------------------------------------
# Query matching
# ---------------------------------------------------------------------

# Vietnamese cue words that signal a roadmap intent rather than a
# narrow query. "Kế hoạch" / "lộ trình" are the natural ones; we
# include "roadmap" because some users mix English.
_ROADMAP_CUES = ("lộ trình", "lo trinh", "kế hoạch", "ke hoach", "roadmap")


def _strip_accents(text: str) -> str:
    """Lowercase + strip Vietnamese accents for fuzzy matching.

    A user types "lộ trình mua nhà" but the template name is "Mua nhà"
    — exact substring doesn't match because of the accents in the input
    vs. accents-on-different-words in the template name. Folding both
    sides to ASCII lower lets us match on the meaningful tokens.
    """
    nfkd = unicodedata.normalize("NFD", text)
    no_marks = "".join(c for c in nfkd if not unicodedata.combining(c))
    return no_marks.lower()


def match_roadmap_query(text: str) -> Optional[str]:
    """Return a ``template_id`` if ``text`` looks like a roadmap query
    for one of the 7 goal templates, else ``None``.

    Heuristic: text must contain at least one roadmap cue word AND
    enough of the template name to disambiguate (substring match on
    the accent-stripped template name).
    """
    if not text:
        return None
    folded = _strip_accents(text)
    if not any(cue in folded for cue in _ROADMAP_CUES):
        return None
    # Score by template-name length so the longest match wins (avoids
    # "mua xe" matching when user said "lộ trình mua xe máy gia đình").
    best_id: str | None = None
    best_len = 0
    for tpl in goal_templates.list_templates():
        folded_name = _strip_accents(tpl.name)
        if folded_name and folded_name in folded and len(folded_name) > best_len:
            best_id = tpl.id
            best_len = len(folded_name)
    return best_id


# ---------------------------------------------------------------------
# LLM path
# ---------------------------------------------------------------------

# Roadmap-specific prompt — deliberately TINY relative to the full
# advisory prompt. We pass only (template name + wealth level) so the
# prompt hash is the same across all users at that (id, level) tier,
# which makes ``shared_cache=True`` actually share entries between
# users instead of multiplying by user_id.
ROADMAP_PROMPT = """Bạn là Bé Tiền — trợ lý tài chính cho người Việt.

User muốn lộ trình đạt mục tiêu: {goal_name}.
Wealth level: {level}.

Trả lời 4-6 bước cụ thể, dễ làm theo, ngắn gọn (max 180 từ).
Tone: ấm áp, xưng "mình", gọi "bạn".
KHÔNG khuyên cổ phiếu / quỹ cụ thể. KHÔNG hứa hẹn lợi nhuận.

Trả lời:"""


async def call_roadmap_llm(
    db: AsyncSession,
    *,
    template_id: str,
    goal_name: str,
    wealth_level: str,
) -> Optional[str]:
    """Issue raw LLM call for a roadmap query with shared cache and a
    hard timeout.

    Returns the response text on success, ``None`` on failure (caller
    falls back to the rule-based template). The shared cache key is
    a function of (task_type, prompt_hash) only, where prompt_hash
    derives from (template_id, wealth_level) — so every user at the
    same level shares the same cached answer.
    """
    prompt = ROADMAP_PROMPT.format(
        goal_name=goal_name, level=wealth_level,
    )
    try:
        return await asyncio.wait_for(
            call_llm(
                prompt,
                task_type="roadmap_advisory",
                db=db,
                shared_cache=True,
                cache_ttl_days=CACHE_TTL_DAYS,
            ),
            timeout=LLM_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "roadmap LLM timed out (template=%s level=%s)",
            template_id, wealth_level,
        )
        return None
    except LLMError:
        logger.warning(
            "roadmap LLM error (template=%s level=%s)",
            template_id, wealth_level,
        )
        return None
    except Exception:
        logger.exception(
            "roadmap LLM crashed (template=%s level=%s)",
            template_id, wealth_level,
        )
        return None


__all__ = [
    "CACHE_TTL_DAYS",
    "LLM_TIMEOUT_SECONDS",
    "RoadmapFallback",
    "call_roadmap_llm",
    "get_fallback",
    "match_roadmap_query",
]
