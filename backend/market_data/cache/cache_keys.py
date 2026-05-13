"""Redis key helpers for market data."""
from __future__ import annotations

PREFIX = "market_data"


def quote_key(asset_type: str, symbol: str) -> str:
    return f"{PREFIX}:{asset_type.lower()}:{symbol.upper()}"


def last_known_key(asset_type: str, symbol: str) -> str:
    return f"{quote_key(asset_type, symbol)}:last_known"


def asset_pattern(asset_type: str) -> str:
    return f"{PREFIX}:{asset_type.lower()}:*"


def health_failures_key(provider_name: str) -> str:
    return f"{PREFIX}:health:{provider_name}:failures"


def health_open_until_key(provider_name: str) -> str:
    return f"{PREFIX}:health:{provider_name}:open_until"
