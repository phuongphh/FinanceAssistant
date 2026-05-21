"""Unit tests for ``_parse_quantity`` thousands/decimal disambiguation.

Release-6 fix: "1,000 cổ" must parse as 1000 (thousands separator), not
1 (the old behaviour treated every comma as a decimal mark). The same
rule applies to a single dot.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture(scope="module")
def parse_quantity():
    # Stub out adapters that the module imports at top-level so we can
    # exercise the pure parser without spinning up the full backend.
    fake = MagicMock()
    for name in (
        "backend.services.telegram_service",
        "backend.bot.formatters.money",
        "backend.bot.handlers.asset_entry",
        "backend.intent.extractors._normalize",
        "backend.intent.handlers.base",
        "backend.intent.intents",
        "backend.models.user",
        "backend.wealth.amount_parser",
        "backend.wealth.services",
        "sqlalchemy.ext.asyncio",
    ):
        sys.modules.setdefault(name, fake)
    # strip_diacritics is called by the parser — provide a passthrough
    # since the test inputs have no diacritics anyway.
    sys.modules["backend.intent.extractors._normalize"].strip_diacritics = lambda s: s

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from backend.intent.handlers.action_edit_asset import _parse_quantity

    return _parse_quantity


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1,000 co", Decimal("1000")),
        ("1.000 co", Decimal("1000")),
        ("1,000,000 co", Decimal("1000000")),
        ("200 co", Decimal("200")),
        ("10 btc", Decimal("10")),
    ],
)
def test_thousands_separator_yields_integer(parse_quantity, text, expected):
    assert parse_quantity(text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1,5 btc", Decimal("1.5")),
        ("1.5 btc", Decimal("1.5")),
        ("2.5 oz", Decimal("2.5")),
    ],
)
def test_decimal_separator_yields_fraction(parse_quantity, text, expected):
    assert parse_quantity(text) == expected


def test_no_unit_returns_none(parse_quantity):
    # Plain monetary input — no quantity unit suffix.
    assert parse_quantity("50tr") is None
    assert parse_quantity("") is None
