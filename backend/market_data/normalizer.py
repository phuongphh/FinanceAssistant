"""Normalized quote model used across providers, cache, and consumers."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Self


@dataclass(slots=True)
class PriceQuote:
    """Unified representation for a market price.

    ``price`` is intentionally a ``Decimal`` to avoid float rounding in money
    calculations. ``is_stale`` supports the Phase 3.9 stale-while-revalidate
    fallback while keeping the core schema additive.
    """

    symbol: str
    price: Decimal
    currency: str
    asset_type: str
    fetched_at: datetime
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)
    is_stale: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.price, Decimal):
            self.price = Decimal(str(self.price))
        self.symbol = self.symbol.upper()
        self.currency = self.currency.upper()
        self.asset_type = self.asset_type.lower()
        if self.fetched_at.tzinfo is None:
            self.fetched_at = self.fetched_at.replace(tzinfo=timezone.utc)

    @staticmethod
    def _json_safe(value: Any) -> Any:
        """Convert nested Decimal/datetime metadata to JSON-safe values."""
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {key: PriceQuote._json_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [PriceQuote._json_safe(item) for item in value]
        return value

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dictionary representation."""
        return {
            "symbol": self.symbol,
            "price": str(self.price),
            "currency": self.currency,
            "asset_type": self.asset_type,
            "fetched_at": self.fetched_at.isoformat(),
            "source": self.source,
            "metadata": self._json_safe(self.metadata),
            "is_stale": self.is_stale,
        }

    def to_json(self) -> str:
        """Serialize quote to a Redis-friendly JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Build a quote from a dictionary produced by ``to_dict``."""
        return cls(
            symbol=str(data["symbol"]),
            price=Decimal(str(data["price"])),
            currency=str(data["currency"]),
            asset_type=str(data["asset_type"]),
            fetched_at=datetime.fromisoformat(str(data["fetched_at"])),
            source=str(data["source"]),
            metadata=dict(data.get("metadata") or {}),
            is_stale=bool(data.get("is_stale", False)),
        )

    @classmethod
    def from_json(cls, value: str | bytes) -> Self:
        """Deserialize a quote from a Redis string/bytes payload."""
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        return cls.from_dict(json.loads(value))

    def mark_stale(self) -> Self:
        """Return a copy marked as stale for fallback responses."""
        data = self.to_dict()
        data["is_stale"] = True
        return self.from_dict(data)
