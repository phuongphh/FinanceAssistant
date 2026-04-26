"""Schema-level checks for the morning-briefing dependencies.

The runtime briefing code (``daily_snapshot_job``, ``morning_briefing_job``,
``BriefingFormatter``) makes assumptions about table / column names that
only break in production if a future migration drifts. These tests
pin those assumptions at unit-test time so we don't ship a green test
suite against a missing schema.

What's pinned:

- ``AssetSnapshot`` model exists, has the columns the daily-snapshot
  job inserts, and the unique constraint name the job's
  ``ON CONFLICT DO NOTHING`` clause references is exactly
  ``uq_asset_snapshot_date``.
- The model is multi-tenant ready: ``user_id`` is non-nullable on
  ``AssetSnapshot`` so per-user filtering can never miss rows.
- The Phase 3A ``users`` columns (``briefing_enabled``,
  ``briefing_time``, ``wealth_level``, ``expense_threshold_*``)
  exist on the SQLAlchemy ``User`` model and their defaults match
  what ``backend.config`` documents.
- The current alembic head includes the migration that adds these
  tables/columns — protects against a half-merged rebase that drops
  ``f5a6b7c8d9e0_phase3a_wealth_foundation``.
"""
from __future__ import annotations

from datetime import time
from pathlib import Path

import pytest

from backend.models.user import User
from backend.wealth.models.asset import Asset
from backend.wealth.models.asset_snapshot import AssetSnapshot


# ── AssetSnapshot model ──────────────────────────────────────────────


class TestAssetSnapshotModel:
    def test_table_name_matches_daily_snapshot_job_target(self):
        # ``daily_snapshot_job.create_daily_snapshots`` does
        # ``pg_insert(AssetSnapshot)`` — the bound table name must be
        # the one in the migration.
        assert AssetSnapshot.__tablename__ == "asset_snapshots"

    def test_unique_constraint_name_matches_on_conflict_clause(self):
        """``daily_snapshot_job`` references the constraint by name in
        ``on_conflict_do_nothing(constraint="uq_asset_snapshot_date")``
        — Postgres raises if that name doesn't exist on the table.
        """
        constraint_names = {
            c.name for c in AssetSnapshot.__table__.constraints if c.name
        }
        assert "uq_asset_snapshot_date" in constraint_names

    def test_user_id_is_non_nullable_for_multi_tenant_safety(self):
        col = AssetSnapshot.__table__.columns["user_id"]
        assert col.nullable is False, (
            "AssetSnapshot.user_id must be NOT NULL — see CLAUDE.md § 3 "
            "(every table has user_id, indexed)."
        )

    def test_required_columns_present(self):
        """Daily-snapshot job inserts these exact column keys; if any
        get renamed by a future migration, the test fails before the
        job hits production."""
        cols = AssetSnapshot.__table__.columns.keys()
        for required in (
            "asset_id", "user_id", "snapshot_date", "value", "source",
        ):
            assert required in cols, f"missing column {required}"

    def test_value_uses_numeric_not_float(self):
        """Money column — CLAUDE.md § 13 requires Decimal, never float."""
        col = AssetSnapshot.__table__.columns["value"]
        # SQLAlchemy Numeric type, precision (20, 2) — accept either
        # raw type-name introspection or precision check.
        type_name = type(col.type).__name__
        assert type_name in ("Numeric", "NUMERIC"), (
            f"AssetSnapshot.value should be NUMERIC, got {type_name}"
        )

    def test_asset_id_cascades_on_delete(self):
        """Soft-delete on assets keeps history, but a hard delete (e.g.
        admin cleanup of an orphan asset) should drop snapshots — the
        FK has ON DELETE CASCADE per the migration."""
        fks = AssetSnapshot.__table__.columns["asset_id"].foreign_keys
        assert any(fk.ondelete == "CASCADE" for fk in fks)


# ── User model: Phase 3A briefing fields ─────────────────────────────


class TestUserBriefingFields:
    def test_briefing_enabled_field_present_with_default_true(self):
        col = User.__table__.columns["briefing_enabled"]
        assert col.nullable is False
        # Default: opt-in by default. Users opt out via /settings.
        assert col.default.arg is True

    def test_briefing_time_field_present_with_seven_am_default(self):
        col = User.__table__.columns["briefing_time"]
        assert col.nullable is False
        assert col.default.arg == time(7, 0)

    def test_wealth_level_field_nullable(self):
        # Nullable: a user may not have any assets yet, in which case
        # we don't pre-classify them. The formatter handles None.
        col = User.__table__.columns["wealth_level"]
        assert col.nullable is True

    def test_expense_thresholds_have_phase_3a_defaults(self):
        """Defaults match docs/current/phase-3a-detailed.md § 3.1
        and CLAUDE.md § 3 (200k micro / 2tr major).
        """
        micro = User.__table__.columns["expense_threshold_micro"]
        major = User.__table__.columns["expense_threshold_major"]
        assert micro.default.arg == 200_000
        assert major.default.arg == 2_000_000

    def test_monthly_income_field_present(self):
        """``BriefingFormatter._format_cashflow`` reads
        ``user.monthly_income`` to compute the saving rate. The
        column has lived on ``users`` since the initial schema —
        pin it so a future column rename would surface here.
        """
        assert "monthly_income" in User.__table__.columns


# ── Alembic head sanity check ────────────────────────────────────────


_MIGRATIONS_DIR = (
    Path(__file__).resolve().parents[2] / "alembic" / "versions"
)


def test_phase_3a_wealth_migration_is_present():
    """The migration that creates ``asset_snapshots`` + adds the
    briefing columns must be present in the ``alembic/versions``
    tree. Catches a half-resolved rebase that drops the file.
    """
    expected = _MIGRATIONS_DIR / "f5a6b7c8d9e0_phase3a_wealth_foundation.py"
    assert expected.exists(), (
        f"Expected Phase 3A wealth foundation migration at {expected}; "
        "without it the briefing job has no asset_snapshots table to "
        "write to."
    )


def test_phase_3a_migration_creates_required_objects():
    """The migration must reference the same column / table / constraint
    names the runtime code uses. We grep the source rather than
    invoking alembic so this test stays fast and offline.
    """
    migration_file = (
        _MIGRATIONS_DIR / "f5a6b7c8d9e0_phase3a_wealth_foundation.py"
    )
    source = migration_file.read_text(encoding="utf-8")

    required_strings = [
        "'asset_snapshots'",            # table created
        "'briefing_enabled'",            # users column added
        "'briefing_time'",               # users column added
        "'wealth_level'",                # users column added
        "'expense_threshold_micro'",     # users column added
        "'expense_threshold_major'",     # users column added
    ]
    missing = [s for s in required_strings if s not in source]
    assert not missing, (
        "Phase 3A migration is missing required objects: "
        + ", ".join(missing)
    )
