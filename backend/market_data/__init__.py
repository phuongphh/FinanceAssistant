"""Market data foundation for Phase 3.9.

This package contains provider abstractions, normalized quote models,
Redis-backed caching, and dispatcher utilities used by concrete market data
integrations.
"""

from backend.market_data.base import BaseProvider
from backend.market_data.normalizer import PriceQuote

__all__ = ["BaseProvider", "PriceQuote"]
