"""Asset CRUD + soft-delete service.

All methods follow the layer contract from CLAUDE.md § 0.1:

    Service flushes only — caller (router/worker) owns the transaction
    boundary and calls ``session.commit()``. Tests assert the boundary
    by checking ``flush`` was awaited and ``commit`` was NOT.

Snapshots are auto-managed:
- ``create_asset`` writes the first snapshot at ``current_value``.
- ``update_current_value`` upserts today's snapshot — multiple updates
  in the same day overwrite, they don't duplicate.

Security: every read/mutate path takes ``user_id`` and verifies
ownership before returning or modifying. ``ValueError`` is raised
when an asset doesn't exist or belongs to another user, so the
router can map it to a 404.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.wealth.models.asset import Asset
from backend.wealth.models.asset_snapshot import AssetSnapshot

SOURCE_USER_INPUT = "user_input"
SOURCE_MARKET_API = "market_api"
SOURCE_AUTO_DAILY = "auto_daily"
SOURCE_INTERPOLATED = "interpolated"


async def create_asset(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    asset_type: str,
    name: str,
    initial_value: Decimal,
    current_value: Decimal | None = None,
    acquired_at: date | None = None,
    subtype: str | None = None,
    extra: dict | None = None,
    description: str | None = None,
    source: str = SOURCE_USER_INPUT,
) -> Asset:
    """Create asset + first snapshot in one transaction.

    ``current_value`` defaults to ``initial_value`` (a freshly added
    asset is worth what the user paid until they tell us otherwise).
    """
    if initial_value is None or Decimal(initial_value) <= 0:
        raise ValueError("initial_value must be positive")

    effective_current = (
        Decimal(current_value) if current_value is not None else Decimal(initial_value)
    )
    asset = Asset(
        user_id=user_id,
        asset_type=asset_type,
        subtype=subtype,
        name=name,
        description=description,
        initial_value=Decimal(initial_value),
        current_value=effective_current,
        acquired_at=acquired_at or date.today(),
        last_valued_at=datetime.utcnow(),
        extra=extra or {},
        is_active=True,
    )
    db.add(asset)
    # flush() so the asset gets an id (UUID generated client-side here, but
    # flushing also surfaces any constraint violation before we add the
    # snapshot row).
    await db.flush()

    snapshot = AssetSnapshot(
        asset_id=asset.id,
        user_id=user_id,
        snapshot_date=date.today(),
        value=effective_current,
        source=source,
    )
    db.add(snapshot)
    # TRANSACTION_OWNED_BY_CALLER — worker/router commits at the boundary.
    await db.flush()
    return asset


async def get_asset_by_id(
    db: AsyncSession, user_id: uuid.UUID, asset_id: uuid.UUID
) -> Asset | None:
    """Ownership-checked single-asset fetch. Returns None if not found
    or owned by another user (we deliberately don't distinguish to
    avoid leaking existence)."""
    stmt = select(Asset).where(
        Asset.id == asset_id,
        Asset.user_id == user_id,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_user_assets(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    include_inactive: bool = False,
    asset_type: str | None = None,
) -> list[Asset]:
    """List assets for a user. By default only active (non-sold) assets."""
    stmt = select(Asset).where(Asset.user_id == user_id)
    if not include_inactive:
        stmt = stmt.where(Asset.is_active.is_(True))
    if asset_type is not None:
        stmt = stmt.where(Asset.asset_type == asset_type)
    stmt = stmt.order_by(Asset.created_at.desc())
    return list((await db.execute(stmt)).scalars().all())


async def update_current_value(
    db: AsyncSession,
    user_id: uuid.UUID,
    asset_id: uuid.UUID,
    new_value: Decimal,
    *,
    source: str = SOURCE_USER_INPUT,
) -> Asset:
    """Update ``current_value`` and upsert today's snapshot.

    Re-running on the same day overwrites the snapshot rather than
    inserting a duplicate (the unique constraint would fail anyway,
    but explicit is friendlier to logs).
    """
    if new_value is None or Decimal(new_value) < 0:
        raise ValueError("new_value must be non-negative")

    asset = await get_asset_by_id(db, user_id, asset_id)
    if asset is None:
        raise ValueError(f"Asset {asset_id} not found for user {user_id}")

    asset.current_value = Decimal(new_value)
    asset.last_valued_at = datetime.utcnow()

    today = date.today()
    existing_stmt = select(AssetSnapshot).where(
        AssetSnapshot.asset_id == asset_id,
        AssetSnapshot.snapshot_date == today,
    )
    snapshot = (await db.execute(existing_stmt)).scalar_one_or_none()
    if snapshot is not None:
        snapshot.value = Decimal(new_value)
        snapshot.source = source
    else:
        db.add(
            AssetSnapshot(
                asset_id=asset_id,
                user_id=user_id,
                snapshot_date=today,
                value=Decimal(new_value),
                source=source,
            )
        )

    # TRANSACTION_OWNED_BY_CALLER — worker/router commits at the boundary.
    await db.flush()
    return asset


async def update_asset_metadata(
    db: AsyncSession,
    user_id: uuid.UUID,
    asset_id: uuid.UUID,
    *,
    name: str | None = None,
    description: str | None = None,
    extra: dict | None = None,
) -> Asset:
    """Mutate descriptive fields without touching value / snapshots."""
    asset = await get_asset_by_id(db, user_id, asset_id)
    if asset is None:
        raise ValueError(f"Asset {asset_id} not found for user {user_id}")

    if name is not None:
        asset.name = name
    if description is not None:
        asset.description = description
    if extra is not None:
        asset.extra = extra

    await db.flush()
    return asset


async def soft_delete(
    db: AsyncSession,
    user_id: uuid.UUID,
    asset_id: uuid.UUID,
    *,
    sold_value: Decimal | None = None,
    sold_at: date | None = None,
) -> Asset:
    """Mark asset as sold/inactive without deleting history.

    Snapshots remain — that's the point: net-worth-at-date queries
    must still be reproducible after a sale.
    """
    asset = await get_asset_by_id(db, user_id, asset_id)
    if asset is None:
        raise ValueError(f"Asset {asset_id} not found for user {user_id}")

    asset.is_active = False
    asset.sold_at = sold_at or date.today()
    if sold_value is not None:
        asset.sold_value = Decimal(sold_value)

    await db.flush()
    return asset
