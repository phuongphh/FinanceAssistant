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
from backend.agent.tools.get_market_data import GetMarketDataTool
from backend.agent.tools.get_transactions import GetTransactionsTool


def build_default_registry() -> ToolRegistry:
    """Wire up the five Epic 1 tools into a fresh registry.

    Centralising registration here means callers (DBAgent, future
    Orchestrator, tests) all see the same tool surface without each
    re-instantiating the same handful of tools.
    """
    registry = ToolRegistry()
    registry.register(GetAssetsTool())
    registry.register(GetTransactionsTool())
    registry.register(ComputeMetricTool())
    registry.register(ComparePeriodsTool())
    registry.register(GetMarketDataTool())
    return registry


__all__ = [
    "Tool",
    "ToolRegistry",
    "GetAssetsTool",
    "GetTransactionsTool",
    "ComputeMetricTool",
    "ComparePeriodsTool",
    "GetMarketDataTool",
    "build_default_registry",
]
