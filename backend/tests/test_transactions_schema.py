"""Schema-level guards for the ``Transaction`` ledger.

Issue #801 reproduced after #799: a money-in larger than ~2.1 tỷ VND
(INT4 max = 2,147,483,647) failed with asyncpg ``value out of range``.
The model declared ``amount: Mapped[int]``, which SQLAlchemy compiles
to ``Integer`` for parameter binding regardless of the column's actual
SQL type. Even after the migration created the column as BIGINT, the
ORM still bound INT4 and asyncpg rejected the value.

The #799 regression test mocked ``create_expense``, so it never
exercised the ORM bind path and could not catch this. These checks
verify the model definition directly — no DB or mocks needed — so a
future contributor who switches the column back to ``int`` or
``BigInteger`` will see a red test, not a production crash on big
salary money-ins.

CLAUDE.md mandates ``NUMERIC(20, 2)`` for money columns. The asserts
below pin that contract.
"""
from __future__ import annotations

from sqlalchemy import Numeric

from backend.models.transaction import Transaction


class TestTransactionAmountColumn:
    def test_amount_is_numeric_not_integer(self):
        """Bug #801: ``Mapped[int]`` made SQLAlchemy bind INT4, which
        asyncpg rejects for values > 2,147,483,647 (≈2.1 tỷ VND).
        Money columns must be ``Numeric`` — see CLAUDE.md."""
        col = Transaction.__table__.columns["amount"]
        assert isinstance(col.type, Numeric), (
            f"Transaction.amount must be Numeric (CLAUDE.md money "
            f"convention); got {type(col.type).__name__}. Reverting to "
            f"Integer/BigInteger reintroduces issue #801."
        )

    def test_amount_precision_holds_practical_vnd_amounts(self):
        """NUMERIC(20, 2) holds values up to ~10^18 — well beyond any
        plausible single-transaction VND amount, and matches the
        precision used by ``expenses.amount`` family columns."""
        col = Transaction.__table__.columns["amount"]
        assert col.type.precision == 20, (
            f"Transaction.amount precision must be 20 to match the money "
            f"convention; got {col.type.precision}."
        )
        assert col.type.scale == 2

    def test_amount_is_not_null(self):
        """Every ledger row must have an amount — half-written
        transactions would corrupt the wealth rollup."""
        col = Transaction.__table__.columns["amount"]
        assert col.nullable is False
