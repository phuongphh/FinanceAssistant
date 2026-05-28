"""Tests for ``backend.services.expense_source_resolver`` (Issue #891).

Cover the three behaviours that the confirmation flow depends on:

1. ``_parse_source_key`` decodes the four key shapes plus garbage.
2. ``apply_default_source`` is a no-op for money-in, for callers that
   already populated a source, and for users without a profile default.
3. ``resolve_source_label_for_expense`` returns the right VN label, with
   bank/card suffix when available.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.models.credit_card import CreditCard
from backend.models.expense import Expense
from backend.profile.models.user_profile import UserProfile
from backend.schemas.expense import ExpenseCreate
from backend.services import expense_source_resolver as resolver
from backend.wealth.models.asset import Asset


def _mk_user_id() -> uuid.UUID:
    return uuid.uuid4()


def _db_with_profile(profile: UserProfile | None, **extra) -> MagicMock:
    db = MagicMock()
    db.get = AsyncMock(return_value=profile)
    return db


def _base_expense_payload() -> ExpenseCreate:
    return ExpenseCreate(
        amount=120_000.0,
        merchant="Phở",
        note="phở",
        source="manual",
        expense_date=date.today(),
    )


# -------------------- _parse_source_key --------------------


class TestParseSourceKey:
    def test_cash(self):
        assert resolver._parse_source_key("cash") == ("cash", None, None)

    def test_bank_account(self):
        aid = uuid.uuid4()
        assert resolver._parse_source_key(f"bank_account:{aid}") == (
            "bank_account",
            aid,
            None,
        )

    def test_e_wallet(self):
        aid = uuid.uuid4()
        assert resolver._parse_source_key(f"e_wallet:{aid}") == (
            "e_wallet",
            aid,
            None,
        )

    def test_credit_card(self):
        cid = uuid.uuid4()
        assert resolver._parse_source_key(f"credit_card:{cid}") == (
            "credit_card",
            None,
            cid,
        )

    @pytest.mark.parametrize(
        "key", [None, "", "garbage", "bank_account:notauuid", "unknown:abc"]
    )
    def test_invalid(self, key):
        assert resolver._parse_source_key(key) == (None, None, None)


# -------------------- apply_default_source --------------------


@pytest.mark.asyncio
class TestApplyDefaultSource:
    async def test_noop_for_money_in(self):
        data = _base_expense_payload().model_copy(
            update={"transaction_type": "money_in"}
        )
        db = _db_with_profile(
            UserProfile(user_id=_mk_user_id(), default_expense_source="cash")
        )
        result = await resolver.apply_default_source(db, _mk_user_id(), data)
        assert result is data  # untouched

    async def test_noop_when_source_already_set(self):
        data = _base_expense_payload().model_copy(update={"source_type": "cash"})
        db = _db_with_profile(
            UserProfile(
                user_id=_mk_user_id(),
                default_expense_source=f"bank_account:{uuid.uuid4()}",
            )
        )
        result = await resolver.apply_default_source(db, _mk_user_id(), data)
        assert result is data

    async def test_noop_when_no_profile(self):
        data = _base_expense_payload()
        db = _db_with_profile(None)
        result = await resolver.apply_default_source(db, _mk_user_id(), data)
        assert result is data

    async def test_noop_when_profile_has_no_default(self):
        data = _base_expense_payload()
        db = _db_with_profile(
            UserProfile(user_id=_mk_user_id(), default_expense_source=None)
        )
        result = await resolver.apply_default_source(db, _mk_user_id(), data)
        assert result is data

    async def test_applies_cash(self):
        data = _base_expense_payload()
        db = _db_with_profile(
            UserProfile(user_id=_mk_user_id(), default_expense_source="cash")
        )
        result = await resolver.apply_default_source(db, _mk_user_id(), data)
        assert result.source_type == "cash"
        assert result.source_asset_id is None
        assert result.source_credit_card_id is None

    async def test_applies_credit_card(self):
        card_id = uuid.uuid4()
        data = _base_expense_payload()
        db = _db_with_profile(
            UserProfile(
                user_id=_mk_user_id(),
                default_expense_source=f"credit_card:{card_id}",
            )
        )
        result = await resolver.apply_default_source(db, _mk_user_id(), data)
        assert result.source_type == "credit_card"
        assert result.source_credit_card_id == card_id
        assert result.source_asset_id is None

    async def test_applies_bank_account(self):
        asset_id = uuid.uuid4()
        data = _base_expense_payload()
        db = _db_with_profile(
            UserProfile(
                user_id=_mk_user_id(),
                default_expense_source=f"bank_account:{asset_id}",
            )
        )
        result = await resolver.apply_default_source(db, _mk_user_id(), data)
        assert result.source_type == "bank_account"
        assert result.source_asset_id == asset_id


# -------------------- resolve_source_label_for_expense --------------------


def _expense(
    *,
    user_id: uuid.UUID,
    source_type: str | None = None,
    source_asset_id: uuid.UUID | None = None,
    source_credit_card_id: uuid.UUID | None = None,
    transaction_type: str = "expense",
) -> Expense:
    e = Expense(
        user_id=user_id,
        amount=Decimal("100000"),
        category="food",
        merchant="x",
        source="manual",
        expense_date=date.today(),
    )
    e.source_type = source_type
    e.source_asset_id = source_asset_id
    e.source_credit_card_id = source_credit_card_id
    e.transaction_type = transaction_type
    return e


@pytest.mark.asyncio
class TestResolveSourceLabel:
    async def test_money_in_returns_none(self):
        uid = _mk_user_id()
        exp = _expense(user_id=uid, source_type="cash", transaction_type="money_in")
        db = MagicMock()
        assert await resolver.resolve_source_label_for_expense(db, exp) is None

    async def test_no_source_type(self):
        exp = _expense(user_id=_mk_user_id())
        db = MagicMock()
        assert await resolver.resolve_source_label_for_expense(db, exp) is None

    async def test_cash_label(self):
        exp = _expense(user_id=_mk_user_id(), source_type="cash")
        db = MagicMock()
        db.get = AsyncMock(return_value=None)
        assert (
            await resolver.resolve_source_label_for_expense(db, exp) == "Tiền mặt"
        )

    async def test_credit_card_with_bank_suffix(self):
        uid = _mk_user_id()
        card_id = uuid.uuid4()
        card = CreditCard(
            user_id=uid,
            bank_name="Vietcombank",
            credit_limit=Decimal("50000000"),
            closing_date=15,
        )
        card.id = card_id
        exp = _expense(
            user_id=uid, source_type="credit_card", source_credit_card_id=card_id
        )
        db = MagicMock()
        db.get = AsyncMock(return_value=card)
        label = await resolver.resolve_source_label_for_expense(db, exp)
        assert label == "Thẻ tín dụng [Vietcombank]"

    async def test_bank_account_with_name_suffix(self):
        uid = _mk_user_id()
        aid = uuid.uuid4()
        asset = Asset(
            user_id=uid,
            asset_type="cash",
            name="VCB Premier",
            current_value=Decimal("10000000"),
        )
        asset.id = aid
        exp = _expense(
            user_id=uid, source_type="bank_account", source_asset_id=aid
        )
        db = MagicMock()
        db.get = AsyncMock(return_value=asset)
        label = await resolver.resolve_source_label_for_expense(db, exp)
        assert label == "Tài khoản thanh toán [VCB Premier]"

    async def test_e_wallet_with_name_suffix(self):
        uid = _mk_user_id()
        aid = uuid.uuid4()
        asset = Asset(
            user_id=uid,
            asset_type="cash",
            name="Momo",
            current_value=Decimal("500000"),
        )
        asset.id = aid
        exp = _expense(user_id=uid, source_type="e_wallet", source_asset_id=aid)
        db = MagicMock()
        db.get = AsyncMock(return_value=asset)
        label = await resolver.resolve_source_label_for_expense(db, exp)
        assert label == "Ví điện tử [Momo]"

    async def test_ignores_foreign_user_asset(self):
        uid = _mk_user_id()
        other = _mk_user_id()
        aid = uuid.uuid4()
        asset = Asset(
            user_id=other,
            asset_type="cash",
            name="Stolen",
            current_value=Decimal("0"),
        )
        asset.id = aid
        exp = _expense(
            user_id=uid, source_type="bank_account", source_asset_id=aid
        )
        db = MagicMock()
        db.get = AsyncMock(return_value=asset)
        label = await resolver.resolve_source_label_for_expense(db, exp)
        assert label == "Tài khoản thanh toán"
