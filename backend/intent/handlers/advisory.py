"""Advisory handler — context-aware financial advice via DeepSeek.

This is the only Phase 3.5 handler that calls an LLM in the hot path
(everything else is rule-based or uses the cheap LLM classifier). The
advisory call costs ~500 tokens vs ~50 for classification, so we
guard it with:

  - **Rate limit**: 5 advisory queries per user per day. The events
    table is the source of truth — if we've already emitted 5
    ``advisory_response_sent`` events for ``user_id`` in the last 24h
    we serve a friendly "đến mai nhé" instead.
  - **Context-rich prompt**: build the user's net worth, breakdown,
    income, goals, recent transactions BEFORE the LLM call so the
    answer is personal, not generic.
  - **Hard legal constraints in the prompt**: never name a specific
    ticker, never promise returns. Tone-of-voice instructions keep
    Bé Tiền sounding like Bé Tiền.
  - **Mandatory disclaimer footer** appended in code (not delegated
    to the LLM) — the test suite asserts every response contains it.

The handler is wired in the dispatcher under ``IntentType.ADVISORY``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.money import format_money_full, format_money_short
from backend.intent.handlers.base import IntentHandler
from backend.intent.intents import IntentResult
from backend.intent.wealth_adapt import resolve_style
from backend.models.event import Event
from backend.models.expense import Expense
from backend.models.goal import Goal
from backend.models.user import User
from backend.services import (
    conversation_context_service,
    goal_roadmap,
    goal_templates,
)
from backend.services.llm_service import LLMError, call_llm
from backend.wealth.models.income_stream import IncomeStream
from backend.wealth.services import asset_service

logger = logging.getLogger(__name__)

ADVISORY_RATE_LIMIT_PER_DAY = 5
ADVISORY_EVENT_RESPONSE = "advisory_response_sent"
ADVISORY_EVENT_RATE_LIMITED = "advisory_rate_limited"
ADVISORY_EVENT_ROADMAP_SERVED = "advisory_roadmap_served"

# Footer is appended in code (not the prompt) so a misbehaving LLM
# can't strip it. The test suite asserts presence on every response.
DISCLAIMER = (
    "_Đây là gợi ý dựa trên data cá nhân, không phải lời khuyên đầu tư "
    "chuyên nghiệp._"
)


ADVISORY_PROMPT = """Bạn là Bé Tiền — trợ lý tài chính cá nhân thân thiện cho người Việt.

{conversation_history}User vừa hỏi: "{query}"

Context về user:
- Tên: {name}
- Wealth level: {level}
- Tổng tài sản: {net_worth}
- Phân bổ tài sản: {breakdown}
- Thu nhập tháng (trung bình): {income}
- Mục tiêu hiện tại: {goals}
- Chi tiêu lớn 30 ngày qua: {recent_spend}

NGUYÊN TẮC TRẢ LỜI:
1. Tone: ấm áp, xưng "mình", gọi "{name}" - "bạn"
2. Cụ thể: dựa trên context user, không generic advice
3. KHÔNG khuyên cổ phiếu cụ thể (lý do pháp lý)
4. KHÔNG hứa hẹn lợi nhuận (vd: "sẽ tăng X%", "chắc chắn lời")
5. Đưa 2-3 options, không 1 prescription
6. Nếu cần thông tin thêm, hỏi lại
7. Trả lời ngắn gọn, max 200 từ. Không kết bằng disclaimer (mình tự thêm).

Trả lời:"""


class AdvisoryHandler(IntentHandler):
    async def handle(self, intent: IntentResult, user: User, db: AsyncSession) -> str:
        # Issue #450 §5 fast path — roadmap queries ("lộ trình mua nhà"
        # etc.) bypass the heavy context builder and the per-user cache.
        # We use a shared cache keyed by (template_id, wealth_level), and
        # a rule-based fallback on timeout. Roadmap responses do NOT
        # consume the daily advisory quota — they're cacheable and not
        # personalized enough to count as bespoke advice.
        template_id = goal_roadmap.match_roadmap_query(intent.raw_text or "")
        if template_id is not None:
            return await self._handle_roadmap(db, user, intent, template_id)

        # Rate-limit BEFORE building context so the expensive queries
        # don't run for capped users.
        used = await _advisory_calls_in_last_24h(db, user.id)
        if used >= ADVISORY_RATE_LIMIT_PER_DAY:
            from backend import analytics

            analytics.track(
                ADVISORY_EVENT_RATE_LIMITED,
                user_id=user.id,
                properties={"used": used},
            )
            return _rate_limited_message(user)

        context = await _build_context(db, user)
        prompt = ADVISORY_PROMPT.format(query=intent.raw_text, **context)

        try:
            raw = await call_llm(
                prompt,
                task_type="advisory",
                db=db,
                user_id=user.id,
                use_cache=False,  # advice depends on live wealth state
            )
        except LLMError:
            logger.exception("Advisory LLM call failed")
            return _llm_error_message(user)
        except Exception:
            logger.exception("Advisory call crashed")
            return _llm_error_message(user)

        body = (raw or "").strip()
        # Defensive — strip any disclaimer the LLM may have hallucinated
        # at the end so we don't end up with two of them.
        body = _strip_trailing_disclaimer(body)

        from backend import analytics

        analytics.track(
            ADVISORY_EVENT_RESPONSE,
            user_id=user.id,
            properties={"chars": len(body)},
        )
        return f"{body}\n\n{DISCLAIMER}"

    async def _handle_roadmap(
        self,
        db: AsyncSession,
        user: User,
        intent: IntentResult,
        template_id: str,
    ) -> str:
        """Issue #450 §5 — roadmap shortcut: shared cache + LLM with
        hard timeout + rule-based fallback.

        Three sources of truth, in priority order:
          1. ``call_roadmap_llm`` (DeepSeek with ``shared_cache=True``,
             10s timeout) — cache hits land in <100ms.
          2. Rule-based ``RoadmapFallback`` from
             ``content/goal_roadmap_templates.yaml``.
          3. The generic LLM error message (only when fallback YAML is
             missing the entry — defensive, shouldn't happen in
             prod).
        """
        from backend import analytics

        template = goal_templates.get_template(template_id)
        goal_name = template.name if template else template_id
        # Use the persisted ``user.wealth_level`` column directly — it
        # was set by the asset wizard via ``ladder.update_user_level``
        # and only mutates on real life events. Avoiding ``resolve_style``
        # saves a net-worth recompute + market-data fetch on the cache
        # path so the P50 stays well under 200ms.
        level = _level_to_vi(user.wealth_level or "young_prof")

        source = "fallback"
        llm_response = await goal_roadmap.call_roadmap_llm(
            db,
            template_id=template_id,
            goal_name=goal_name,
            wealth_level=level,
        )
        if llm_response:
            source = "llm"
            body = _strip_trailing_disclaimer(llm_response.strip())
        else:
            fallback = goal_roadmap.get_fallback(template_id)
            if fallback is None:
                logger.warning(
                    "roadmap fallback missing for template_id=%s", template_id,
                )
                return _llm_error_message(user)
            body = (
                f"{fallback.render()}\n\n"
                "_Gợi ý này dựa trên mẫu phổ biến. Bé Tiền có thể phân "
                "tích chi tiết hơn nếu bạn thử lại sau._"
            )

        analytics.track(
            ADVISORY_EVENT_ROADMAP_SERVED,
            user_id=user.id,
            properties={"template_id": template_id, "source": source},
        )
        return f"{body}\n\n{DISCLAIMER}"


# -------------------- context builders --------------------


async def _build_context(db: AsyncSession, user: User) -> dict:
    """Assemble the prompt's context block.

    Each component degrades gracefully — a user with no income streams
    sees ``income="chưa rõ"`` rather than the prompt failing.
    """
    style = await resolve_style(db, user)
    net_worth = style.net_worth

    breakdown_str = await _format_breakdown(db, user)
    income_str = await _format_income(db, user)
    goals_str = await _format_goals(db, user)
    recent_str = await _format_recent_spend(db, user)
    history_str = await _format_conversation_history(db, user)

    return {
        "name": (user.display_name or "bạn"),
        "level": _level_to_vi(style.level.value),
        "net_worth": format_money_full(net_worth) if net_worth > 0 else "chưa rõ",
        "breakdown": breakdown_str,
        "income": income_str,
        "goals": goals_str,
        "recent_spend": recent_str,
        "conversation_history": history_str,
    }


async def _format_conversation_history(db: AsyncSession, user: User) -> str:
    """Render recent conversation as a prelude block.

    Returns "" when the buffer is empty so the prompt template
    collapses cleanly. Otherwise wraps the rendered transcript in a
    labelled section the LLM can clearly distinguish from the current
    query.
    """
    history = await conversation_context_service.get_recent_messages(
        db, user_id=user.id
    )
    if not history:
        return ""
    transcript = conversation_context_service.format_history_for_prompt(history)
    return f"Cuộc hội thoại gần đây (theo thứ tự thời gian):\n{transcript}\n\n"


def _level_to_vi(level: str) -> str:
    # Bilingual labels keep the LLM grounded (it knows the standard
    # finance-industry tier names in English) while exposing the
    # Vietnamese half to the user-visible report. Without the second
    # part the LLM has been observed to echo "Mass Affluent" verbatim
    # into the Vietnamese-language report — the parenthetical anchors it.
    return {
        "starter": "Khởi Đầu",
        "young_prof": "Trẻ Năng Động",
        "mass_affluent": "Trung Lưu Vững",
        "hnw": "Tinh Hoa",
    }.get(level, level)


async def _format_breakdown(db: AsyncSession, user: User) -> str:
    assets = await asset_service.get_user_assets(db, user.id)
    if not assets:
        return "chưa có tài sản"
    by_type: dict[str, Decimal] = {}
    for a in assets:
        by_type[a.asset_type] = by_type.get(a.asset_type, Decimal(0)) + Decimal(
            a.current_value or 0
        )
    parts = [
        f"{kind}: {format_money_short(value)}"
        for kind, value in sorted(by_type.items(), key=lambda kv: kv[1], reverse=True)
    ]
    return ", ".join(parts)


async def _format_income(db: AsyncSession, user: User) -> str:
    stmt = select(IncomeStream).where(
        IncomeStream.user_id == user.id,
        IncomeStream.is_active.is_(True),
    )
    streams = list((await db.execute(stmt)).scalars().all())
    # Phase 3.8 Epic 2: ``amount_monthly`` was replaced by raw
    # ``amount`` + ``schedule_type``. Aggregate via the canonical
    # ``monthly_equivalent`` so quarterly dividends and annual
    # interest contribute their correct share of the headline.
    total = sum((s.monthly_equivalent for s in streams), Decimal(0))
    if total > 0:
        return f"{format_money_full(total)}/tháng ({len(streams)} nguồn)"
    if user.monthly_income:
        return f"{format_money_full(user.monthly_income)}/tháng"
    return "chưa rõ"


async def _format_goals(db: AsyncSession, user: User) -> str:
    # Phase 3.8 Epic 5: ``is_active`` → ``status='active'``,
    # ``goal_name`` → ``name``.
    stmt = (
        select(Goal)
        .where(
            Goal.user_id == user.id,
            Goal.status == "active",
            Goal.deleted_at.is_(None),
        )
        .order_by(Goal.created_at.desc())
        .limit(3)
    )
    goals = list((await db.execute(stmt)).scalars().all())
    if not goals:
        return "chưa đặt mục tiêu"
    return "; ".join(
        f"{g.name} ({format_money_short(g.current_amount)}/{format_money_short(g.target_amount)})"
        for g in goals
    )


async def _format_recent_spend(db: AsyncSession, user: User) -> str:
    """Top 5 expenses in the last 30 days — gives the LLM a feel for
    where the user's money is going without dumping the full ledger."""
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=30)
    stmt = (
        select(Expense)
        .where(
            Expense.user_id == user.id,
            Expense.deleted_at.is_(None),
            Expense.expense_date >= cutoff,
        )
        .order_by(Expense.amount.desc())
        .limit(5)
    )
    rows = list((await db.execute(stmt)).scalars().all())
    if not rows:
        return "không có giao dịch lớn"
    return "; ".join(
        f"{tx.merchant or tx.category}: {format_money_short(tx.amount)}" for tx in rows
    )


# -------------------- rate limiting --------------------


async def _advisory_calls_in_last_24h(db: AsyncSession, user_id) -> int:
    """Count this user's advisory responses in the last 24h.

    Uses the events table directly so the rate limit survives restarts
    without needing a separate counter store. The event was emitted
    only on SUCCESSFUL responses, so failed LLM calls don't burn the
    user's quota.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    stmt = (
        select(func.count())
        .select_from(Event)
        .where(
            Event.event_type == ADVISORY_EVENT_RESPONSE,
            Event.user_id == user_id,
            Event.timestamp >= cutoff,
        )
    )
    return int((await db.execute(stmt)).scalar() or 0)


def _rate_limited_message(user: User) -> str:
    name = user.display_name or "bạn"
    return (
        f"Mình đã trả lời tư vấn cho {name} {ADVISORY_RATE_LIMIT_PER_DAY} "
        "lần trong 24h qua rồi 🌱\n\n"
        "Mai mình tươi mới hơn — bạn ghé lại nhé. Hoặc gõ /menu để xem "
        "các báo cáo / tài sản đã có sẵn.\n\n"
        f"{DISCLAIMER}"
    )


def _llm_error_message(user: User) -> str:
    name = user.display_name or "bạn"
    return (
        f"Mình đang nghĩ chưa ra đáp án rõ ràng cho {name} 😔\n"
        "Bạn thử lại sau vài phút, hoặc hỏi mình câu cụ thể hơn nhé.\n\n"
        f"{DISCLAIMER}"
    )


def _strip_trailing_disclaimer(text: str) -> str:
    """Drop any disclaimer-like trailing line so we don't double up."""
    lines = text.rstrip().splitlines()
    while lines and (
        "không phải lời khuyên" in lines[-1].lower()
        or "không phải tư vấn" in lines[-1].lower()
        or "investment advice" in lines[-1].lower()
    ):
        lines.pop()
    return "\n".join(lines).rstrip()


__all__ = [
    "ADVISORY_EVENT_RATE_LIMITED",
    "ADVISORY_EVENT_RESPONSE",
    "ADVISORY_EVENT_ROADMAP_SERVED",
    "ADVISORY_PROMPT",
    "ADVISORY_RATE_LIMIT_PER_DAY",
    "AdvisoryHandler",
    "DISCLAIMER",
]
