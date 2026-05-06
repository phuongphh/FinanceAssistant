"""Agent tools — typed wrappers around existing Phase 3A/3.5 services.

Tools are the only way the LLM interacts with the database. The LLM
selects a tool + extracts typed parameters; deterministic Python code
executes the tool. This keeps things safe (no SQL injection),
auditable (every call logged), and testable (tools have unit tests).
"""

from backend.agent.tools.base import Tool, ToolRegistry
from backend.agent.tools.compare_periods import ComparePeriodsTool
from backend.agent.tools.compute_metric import ComputeMetricTool
from backend.agent.tools.get_assets import GetAssetsTool
from backend.agent.tools.get_income import GetIncomeTool
from backend.agent.tools.get_market_data import GetMarketDataTool
from backend.agent.tools.get_transactions import GetTransactionsTool


def build_default_registry() -> ToolRegistry:
    """Wire up the agent tools into a fresh registry.

    Phase 3.7 shipped 5 tools (assets, transactions, compute_metric,
    compare_periods, market_data). Phase 3.8 Epic 2 adds
    ``get_income`` so the agent can answer "thu nhập thụ động" /
    "thu nhập từ thuê BĐS" without falling back to the legacy
    intent path. Centralising registration here means callers
    (DBAgent, future Orchestrator, tests) all see the same tool
    surface without each re-instantiating the catalog.
    """
    registry = ToolRegistry()
    registry.register(GetAssetsTool())
    registry.register(GetTransactionsTool())
    registry.register(ComputeMetricTool())
    registry.register(ComparePeriodsTool())
    registry.register(GetMarketDataTool())
    registry.register(GetIncomeTool())
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
    "build_default_registry",
]
