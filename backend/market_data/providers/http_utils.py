"""HTTP parsing helpers shared by market data providers."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from backend.market_data.exceptions import ParserError


def decimal_or_none(value: Any) -> Decimal | None:
    """Convert provider value to ``Decimal``; blank/non-numeric values become None."""
    if value is None or value == "":
        return None
    if isinstance(value, str):
        value = value.replace(",", "").strip()
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def require_decimal(value: Any, field: str) -> Decimal:
    """Convert provider value to ``Decimal`` or raise ``ParserError``."""
    parsed = decimal_or_none(value)
    if parsed is None:
        raise ParserError(f"Missing or invalid decimal field: {field}")
    return parsed


def first_present(data: dict[str, Any], names: tuple[str, ...]) -> Any:
    """Return the first present/non-empty value from provider payload."""
    for name in names:
        value = data.get(name)
        if value is not None and value != "":
            return value
    return None


def unwrap_first_record(payload: Any) -> dict[str, Any]:
    """Extract one quote-like record from common API response envelopes."""
    if isinstance(payload, list):
        if not payload:
            raise ParserError("Provider returned an empty list")
        record = payload[0]
    elif isinstance(payload, dict):
        record = payload
        for key in ("data", "items", "result", "rows", "list"):
            nested = payload.get(key)
            if isinstance(nested, list):
                if not nested:
                    raise ParserError(f"Provider returned empty {key}")
                record = nested[0]
                break
            if isinstance(nested, dict):
                record = nested
                break
    else:
        raise ParserError("Provider returned unsupported payload")

    if not isinstance(record, dict):
        raise ParserError("Provider record is not an object")
    return record
