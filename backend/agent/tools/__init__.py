"""Agent tools — typed wrappers around existing Phase 3A/3.5 services.

Tools are the only way the LLM interacts with the database. The LLM
selects a tool + extracts typed parameters; deterministic Python code
executes the tool. This keeps things safe (no SQL injection),
auditable (every call logged), and testable (tools have unit tests).
"""

from backend.agent.tools.base import Tool, ToolRegistry
from backend.agent.tools.compare_periods import ComparePeriodsTool
from backend.agent.tools.compute_metric import ComputeMetricTool
from backend.agent.tools.forecast_cashflow import ForecastCashflowTool
from backend.agent.tools.get_assets import GetAssetsTool
from backend.agent.tools.get_income import GetIncomeTool
from backend.agent.tools.get_market_data import GetMarketDataTool
from backend.agent.tools.get_transactions import GetTransactionsTool


def build_default_registry() -> ToolRegistry:
    """Wire up the agent tools into a fresh registry.

    Phase 3.7 shipped 5 tools (assets, transactions, compute_metric,
    compare_periods, market_data). Phase 3.8 Epic 2 adds
    ``get_income``; Epic 4 adds ``forecast_cashflow`` so the agent
    can answer future-tense queries ("tháng tới tiết kiệm bao
    nhiêu?", "bao giờ tôi âm tài khoản?") without bouncing through
    the legacy intent path.
    """
    registry = ToolRegistry()
    registry.register(GetAssetsTool())
    registry.register(GetTransactionsTool())
    registry.register(ComputeMetricTool())
    registry.register(ComparePeriodsTool())
    registry.register(GetMarketDataTool())
    registry.register(GetIncomeTool())
    registry.register(ForecastCashflowTool())
    return registry


__all__ = [
    "Tool",
    "ToolRegistry",
    "GetAssetsTool",
    "GetTransactionsTool",
    "ComputeMetricTool",
    "ComparePeriodsTool",
    "GetMarketDataTool",
    "GetIncomeTool",
    "ForecastCashflowTool",
    "build_default_registry",
]
