"""strip legacy type-label prefix from rental income_streams.name

Revision ID: 20261201rentalname
Revises: 20261101p4bzalo
Create Date: 2026-12-01 00:00:00.000000

Context
-------
Pre-PR #460 ``rental_service._sync_rental_income_stream`` denormalised the
Vietnamese type label into ``income_streams.name`` (e.g. ``"Thuê BĐS — Nhà
cho thuê mỹ đình"``). PR #460 corrected the wording to ``"BĐS cho thuê — …"``
but only for newly-synced rows — existing rentals kept the old string and
surfaced it through the cashflow card (issue: "Bé Tiền vẫn hiển thị 'Thuê
BĐS' sau khi merge fix").

Root cause is architectural: presentation strings should not live in DB
columns. The accompanying code change drops the prefix entirely — the
display layer composes ``"{icon} {type_label} — {asset.name}"`` from
``income_types.yaml`` at render time so future YAML edits propagate
without touching data.

This migration normalises existing rows to match the new invariant
(``income_streams.name`` holds the bare asset name) so legacy rentals
render identically to ones created post-PR.

Idempotent + safe to rerun:
- Only mutates rows where ``stream_type = 'rental'``.
- Only strips known historical prefixes.
- ``downgrade`` is a no-op — the original prefix is unrecoverable from the
  asset table without ambiguity (an asset may have been renamed since),
  and reverting would re-introduce the user-visible bug.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20261201rentalname"
down_revision = "20261101p4bzalo"
branch_labels = None
depends_on = None


_LEGACY_PREFIXES = (
    "Thuê BĐS — ",
    "BĐS cho thuê — ",
)


def upgrade() -> None:
    # One UPDATE per prefix keeps the SQL trivially auditable in logs and
    # avoids a CASE expression. Rentals are low-cardinality (one row per
    # rental property) so this is cheap even at scale.
    bind = op.get_bind()
    for prefix in _LEGACY_PREFIXES:
        bind.execute(
            sa.text(
                """
                UPDATE income_streams
                SET name = TRIM(SUBSTRING(name FROM :start_pos))
                WHERE stream_type = 'rental'
                  AND name LIKE :like_pattern
                """
            ),
            {"start_pos": len(prefix) + 1, "like_pattern": f"{prefix}%"},
        )


def downgrade() -> None:
    # No-op: restoring the legacy prefix would re-introduce the bug we
    # shipped this migration to fix.
    pass
