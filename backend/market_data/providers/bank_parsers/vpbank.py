"""VPBank savings-rate parser."""
from __future__ import annotations

from backend.market_data.providers.bank_parsers.common import BankRate, generic_parse_rates


def parse_rates(html: str) -> list[BankRate]:
    return generic_parse_rates(html, bank_code="VPB", bank_name="VPBank")
