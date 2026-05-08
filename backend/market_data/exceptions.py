"""Exception hierarchy for market data providers and cache consumers."""
from __future__ import annotations


class MarketDataError(Exception):
    """Base class for all market data errors."""


class ProviderUnavailable(MarketDataError):
    """Provider is temporarily unavailable or returned a server error."""


class RateLimitError(MarketDataError):
    """Provider rate limit was reached."""


class ParserError(MarketDataError):
    """Provider response could not be parsed into the normalized schema."""


class SymbolNotFound(MarketDataError):
    """Provider does not know the requested symbol."""


class StaleDataWarning(Warning):
    """Warning emitted when callers receive last-known stale market data."""
