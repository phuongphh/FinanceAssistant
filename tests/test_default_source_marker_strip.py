"""Tests for stripping the profile-default markers on explicit source edits.

When a user edits the source of a transaction that was created from a
profile default, the ``(mặc định)`` marker must be cleared — for BOTH the
expense (``default_expense_source``) and money-in
(``default_money_in_source``) markers.
"""

from backend.services.expense_service import (
    _raw_data_without_default_source_marker,
)
from backend.services.expense_source_resolver import (
    DEFAULT_MONEY_IN_SOURCE_RAW_DATA_KEY,
    DEFAULT_SOURCE_RAW_DATA_KEY,
)


def test_strips_expense_default_marker():
    cleaned = _raw_data_without_default_source_marker(
        {DEFAULT_SOURCE_RAW_DATA_KEY: True, "keep": 1}
    )
    assert cleaned == {"keep": 1}


def test_strips_money_in_default_marker():
    cleaned = _raw_data_without_default_source_marker(
        {DEFAULT_MONEY_IN_SOURCE_RAW_DATA_KEY: True, "keep": 1}
    )
    assert cleaned == {"keep": 1}


def test_strips_both_markers():
    cleaned = _raw_data_without_default_source_marker(
        {
            DEFAULT_SOURCE_RAW_DATA_KEY: True,
            DEFAULT_MONEY_IN_SOURCE_RAW_DATA_KEY: True,
        }
    )
    assert cleaned is None


def test_noop_when_no_markers():
    assert _raw_data_without_default_source_marker(None) is None
    assert _raw_data_without_default_source_marker({}) is None
