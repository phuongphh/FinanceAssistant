"""Manual live-provider checks for Phase 3.9.

These tests are skipped in CI/local default runs because they call public market
APIs. Run explicitly with ``pytest ... -rs`` after removing the skip marker when
validating provider endpoints against live data.
"""
from __future__ import annotations

import pytest

from backend.market_data.providers.stock_ssi import SSIStockProvider


@pytest.mark.asyncio
@pytest.mark.skip(reason="Manual live SSI iBoard check; do not run in CI")
async def test_ssi_live_vnm_quote_manual():
    quote = await SSIStockProvider().fetch_quote("VNM")

    assert quote.symbol == "VNM"
    assert quote.price > 0
