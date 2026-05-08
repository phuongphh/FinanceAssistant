from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from backend.market_data.providers.bank_parsers import BANKS
from backend.market_data.providers.bank_parsers.vcb import parse_rates
from backend.market_data.providers.bank_rates_scraper import BankRatesScraper

FIXTURES = Path(__file__).parents[1] / "fixtures"


def test_vcb_parser_parses_supported_tenors():
    rates = parse_rates((FIXTURES / "vcb_rates.html").read_text())
    assert [rate.tenor_months for rate in rates] == [1, 3, 6, 12, 24]
    assert rates[0].bank_code == "VCB"
    assert rates[0].rate_pct == Decimal("3.1")


@pytest.mark.parametrize("bank_key", sorted(BANKS))
def test_all_bank_fixtures_parse(bank_key):
    module = __import__(f"backend.market_data.providers.bank_parsers.{bank_key}", fromlist=["parse_rates"])
    rates = module.parse_rates((FIXTURES / f"{bank_key}_rates.html").read_text())
    assert len(rates) == 5


@pytest.mark.asyncio
async def test_bank_scraper_skips_failed_bank():
    async def fetch_html(bank_key: str) -> str:
        if bank_key == "bidv":
            raise RuntimeError("down")
        return (FIXTURES / "vcb_rates.html").read_text()

    rates = await BankRatesScraper(fetch_html=fetch_html).fetch_all(["vcb", "bidv"])
    assert {rate.bank_code for rate in rates} == {"VCB"}
