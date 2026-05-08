"""Common bank-rate parser primitives."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from bs4 import BeautifulSoup

from backend.market_data.exceptions import ParserError

TENORS = (1, 3, 6, 12, 24)


@dataclass(frozen=True, slots=True)
class BankRate:
    bank_code: str
    bank_name: str
    tenor_months: int
    rate_pct: Decimal
    deposit_type: str
    fetched_at: datetime
    notes: str | None = None


def parse_rate_decimal(text: str) -> Decimal | None:
    match = re.search(r"\d+(?:[.,]\d+)?", text.replace("\xa0", " "))
    if not match:
        return None
    return Decimal(match.group(0).replace(",", "."))


def parse_tenor_months(text: str) -> int | None:
    lower = text.lower()
    if "không kỳ hạn" in lower or "overnight" in lower:
        return None
    match = re.search(r"(\d+)\s*(?:tháng|month|m\b)", lower)
    if match:
        return int(match.group(1))
    if lower.strip() in {str(t) for t in TENORS}:
        return int(lower.strip())
    return None


def generic_parse_rates(html: str, *, bank_code: str, bank_name: str) -> list[BankRate]:
    """Parse simple tenor/rate HTML tables used by fixtures and many bank pages."""
    soup = BeautifulSoup(html, "lxml")
    rows = soup.find_all("tr")
    if not rows:
        raise ParserError(f"{bank_code} rates table not found")
    parsed: list[BankRate] = []
    fetched_at = datetime.now(timezone.utc)
    for row in rows:
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["td", "th"])]
        if len(cells) < 2:
            continue
        tenor = parse_tenor_months(cells[0])
        if tenor not in TENORS:
            continue
        rate = None
        deposit_type = "regular"
        notes = None
        for idx, cell in enumerate(cells[1:], start=1):
            candidate = parse_rate_decimal(cell)
            if candidate is None:
                continue
            rate = candidate
            header = cells[idx].lower() if idx < len(cells) else ""
            deposit_type = "online" if "online" in header else "regular"
            break
        if rate is None:
            continue
        if len(cells) > 2:
            notes = " | ".join(cells[2:])[:500] or None
        parsed.append(BankRate(bank_code, bank_name, tenor, rate, deposit_type, fetched_at, notes))
    if not parsed:
        raise ParserError(f"{bank_code} rates table contained no supported tenors")
    return parsed
