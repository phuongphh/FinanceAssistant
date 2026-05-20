from __future__ import annotations

import pytest

from backend.market_data.providers.stock_dispatcher import _is_likely_foreign_symbol


@pytest.mark.parametrize(
    ("symbol", "expected"),
    [
        ("NVDA", True),
        ("IBM", True),
        ("TCEF", True),
        ("E120", True),
        ("VNM", False),
        ("FPT", False),
        ("QQQ.US", True),
    ],
)
def test_foreign_symbol_heuristics(symbol: str, expected: bool):
    assert _is_likely_foreign_symbol(symbol) is expected
