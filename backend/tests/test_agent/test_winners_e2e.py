"""End-to-end winners-only test through the full Orchestrator.

This is THE test the entire phase exists to pass. Before Phase 3.7,
Phase 3.5's intent classifier would route "Mã đang lãi?" to
``query_assets`` which returned the FULL portfolio — losers and all.

Phase 3.7 adds a Tier 2 path: heuristic detects "đang lãi" → DBAgent
picks ``get_assets`` with ``filter.gain_pct.gt = 0`` → tool filters →
formatter renders only winners. We bypass the actual DeepSeek call
(stub the agent's tool selection) but exercise everything else
end-to-end: tool registry, GetAssetsTool filter logic, formatter.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.agent.orchestrator import TIER_2, Orchestrator
from backend.agent.rate_limit import DailyCostTracker, RateLimiter
from backend.agent.tier2.db_agent import DBAgentResult
from backend.wealth.models.asset import Asset
from backend.wealth.services import asset_service


def _stock(name: str, current: int, initial: int) -> Asset:
    """Asset with explicit current/initial → deterministic gain%."""
    return Asset(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        asset_type="stock",
        name=name,
        initial_value=Decimal(initial),
        current_value=Decimal(current),
        acquired_at=date.today(),
        last_valued_at=datetime.utcnow(),
        extra={"ticker": name, "quantity": 100},
        is_active=True,
    )


def _mixed_portfolio() -> list[Asset]:
    """The canonical fixture — 2 winners, 2 losers."""
    return [
        _stock("VNM", current=110_000_000, initial=100_000_000),  # +10%
        _stock("HPG", current=95_000_000, initial=100_000_000),   # -5%
        _stock("NVDA", current=120_000_000, initial=100_000_000),  # +20%
        _stock("FPT", current=97_000_000, initial=100_000_000),   # -3%
    ]


def _user():
    u = MagicMock()
    u.id = uuid.uuid4()
    u.display_name = "Hà"
    u.wealth_level = "young_prof"
    return u


def _mock_db(rows: list[Asset]) -> MagicMock:
    """Stub session: any SELECT returns ``rows`` via .scalars().all()."""
    db = MagicMock()
    scalars = MagicMock()
    scalars.all = MagicMock(return_value=rows)
    result = MagicMock()
    result.scalars = MagicMock(return_value=scalars)
    db.execute = AsyncMock(return_value=result)
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


def _stub_db_agent_picks_winners_filter():
    """A DBAgent whose ``answer`` returns the ideal tool selection
    for 'mã đang lãi?' WITHOUT calling DeepSeek."""
    from backend.agent.tools.get_assets import GetAssetsTool

    db_agent = MagicMock()

    async def fake_answer(query, user, db):
        # Mimic what a healthy DeepSeek call would emit: tool name,
        # validated args, and the actual executed tool result. We
        # call the real GetAssetsTool to keep the filter logic in
        # the loop (this is the bit that fixes the bug).
        tool = GetAssetsTool()
        from backend.agent.tools.schemas import (
            AssetFilter, GetAssetsInput, NumericFilter, SortOrder,
        )
        input_obj = GetAssetsInput(
            filter=AssetFilter(
                asset_type="stock", gain_pct=NumericFilter(gt=0),
            ),
            sort=SortOrder.GAIN_PCT_DESC,
        )
        output = await tool.execute(input_obj, user, db)
        return DBAgentResult(
            success=True,
            tool_called="get_assets",
            tool_args=input_obj.model_dump(mode="json"),
            result=output.model_dump(mode="json"),
            input_tokens=120,
            output_tokens=40,
        )

    db_agent.answer = fake_answer
    return db_agent


@pytest.mark.asyncio
class TestWinnersOnlyE2E:
    """The critical bug — Phase 3.5 returned ALL stocks; Phase 3.7
    must return ONLY the winners (gain_pct > 0)."""

    async def test_winners_query_returns_only_winners(self):
        rows = _mixed_portfolio()
        db = _mock_db(rows)

        orch = Orchestrator(
            intent_pipeline=MagicMock(),  # not used; tier-2 short-circuits
            intent_dispatcher=MagicMock(),
            db_agent=_stub_db_agent_picks_winners_filter(),
            reasoning_agent=MagicMock(),
            rate_limiter=RateLimiter(),
            cost_tracker=DailyCostTracker(),
            cache_enabled=False,  # don't pollute the test DB stub
        )

        result = await orch.route(
            "Mã chứng khoán nào của tôi đang lãi?",
            _user(),
            db,
            audit=False,
        )

        assert result.tier == TIER_2
        assert result.text is not None
        text = result.text

        # The bug: HPG (−5%) and FPT (−3%) MUST NOT appear.
        assert "HPG" not in text, (
            "Loser HPG appeared in winners response — Phase 3.5 bug "
            "regression. Check AssetFilter.gain_pct flow."
        )
        assert "FPT" not in text, "Loser FPT appeared — same regression."

        # The right answer: VNM (+10%) and NVDA (+20%) DO appear.
        assert "VNM" in text
        assert "NVDA" in text

        # Sort matters: NVDA (best) before VNM.
        assert text.index("NVDA") < text.index("VNM")

        # Header gives the user the framing.
        assert "lãi" in text.lower() or "🟢" in text

    async def test_losers_query_returns_only_losers(self):
        """Inverse case — 'mã đang lỗ?' → only HPG / FPT."""
        rows = _mixed_portfolio()
        db = _mock_db(rows)

        # Hand-build a stub that picks the losers filter.
        from backend.agent.tools.get_assets import GetAssetsTool
        from backend.agent.tools.schemas import (
            AssetFilter, GetAssetsInput, NumericFilter, SortOrder,
        )

        async def loser_answer(query, user, db):
            tool = GetAssetsTool()
            input_obj = GetAssetsInput(
                filter=AssetFilter(
                    asset_type="stock", gain_pct=NumericFilter(lt=0),
                ),
                sort=SortOrder.GAIN_PCT_ASC,
            )
            output = await tool.execute(input_obj, user, db)
            return DBAgentResult(
                success=True,
                tool_called="get_assets",
                tool_args=input_obj.model_dump(mode="json"),
                result=output.model_dump(mode="json"),
                input_tokens=120,
                output_tokens=40,
            )

        agent = MagicMock()
        agent.answer = loser_answer
        orch = Orchestrator(
            intent_pipeline=MagicMock(),
            intent_dispatcher=MagicMock(),
            db_agent=agent,
            reasoning_agent=MagicMock(),
            rate_limiter=RateLimiter(),
            cost_tracker=DailyCostTracker(),
            cache_enabled=False,
        )

        result = await orch.route(
            "Mã đang lỗ?", _user(), db, audit=False,
        )
        text = result.text or ""
        assert "HPG" in text and "FPT" in text
        assert "VNM" not in text and "NVDA" not in text

    async def test_top_3_winners_respects_limit(self):
        """5 winners — top_3 returns only the best 3."""
        rows = [
            _stock("A", current=200_000_000, initial=100_000_000),  # +100%
            _stock("B", current=180_000_000, initial=100_000_000),  # +80%
            _stock("C", current=160_000_000, initial=100_000_000),  # +60%
            _stock("D", current=140_000_000, initial=100_000_000),  # +40%
            _stock("E", current=120_000_000, initial=100_000_000),  # +20%
        ]
        db = _mock_db(rows)

        from backend.agent.tools.get_assets import GetAssetsTool
        from backend.agent.tools.schemas import (
            AssetFilter, GetAssetsInput, SortOrder,
        )

        async def top3_answer(query, user, db):
            tool = GetAssetsTool()
            input_obj = GetAssetsInput(
                filter=AssetFilter(asset_type="stock"),
                sort=SortOrder.GAIN_PCT_DESC,
                limit=3,
            )
            output = await tool.execute(input_obj, user, db)
            return DBAgentResult(
                success=True,
                tool_called="get_assets",
                tool_args=input_obj.model_dump(mode="json"),
                result=output.model_dump(mode="json"),
            )

        agent = MagicMock()
        agent.answer = top3_answer
        orch = Orchestrator(
            intent_pipeline=MagicMock(),
            intent_dispatcher=MagicMock(),
            db_agent=agent,
            reasoning_agent=MagicMock(),
            rate_limiter=RateLimiter(),
            cost_tracker=DailyCostTracker(),
            cache_enabled=False,
        )

        result = await orch.route(
            "Top 3 mã lãi nhất", _user(), db, audit=False,
        )
        text = result.text or ""
        assert "A" in text and "B" in text and "C" in text
        # D and E ARE winners, but exceed the limit — must NOT appear.
        # Use word-boundary check by looking for the listing line shape.
        for absent in ("D —", "E —"):
            assert absent not in text, (
                f"Top-3 limit was not respected; saw {absent!r}"
            )
        assert "Top 3" in text
