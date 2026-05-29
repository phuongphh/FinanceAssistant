"""phase 4.4 epic 0: add users.salutation + merge release-7 heads

Adds the nullable ``users.salutation`` column (how Bé Tiền addresses the
user — anh/chị/bạn) for the First-5-Minutes WOW flow.

Doubles as the release-7 head merge: at the time of writing the tree had
two open heads (``20260523_insurance_backfill`` and
``20260528defaultexpsource``) so ``alembic upgrade head`` (singular,
used by ``scripts/deploy_admin.sh``) aborts with "Multiple head
revisions" until a revision joins them. This migration revises both,
collapsing them back to a single head.

Revision ID: 20260529salutation
Revises: 20260523_insurance_backfill, 20260528defaultexpsource
Create Date: 2026-05-29
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260529salutation"
down_revision = (
    "20260523_insurance_backfill",
    "20260528defaultexpsource",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("salutation", sa.String(length=10), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "salutation")
