"""Rental property service — Case A (landlord perspective).

Responsibilities:

- ``mark_as_rental`` — flip a real-estate asset into rental mode and
  link a recurring ``IncomeStream`` so cashflow / briefing / agent
  queries see the rent automatically.
- ``update_occupancy`` — react to "tenant moved out" / "found a new
  tenant" by pausing or resuming the linked income stream.
- ``unmark_as_rental`` — back to a non-rental real-estate asset; the
  income stream is paused, not deleted, so re-marking later restores
  history.
- ``get_rental_yield_summary`` — aggregate stats (count, totals,
  blended yield) for a user across every active rental.

Invariants enforced:

- Only ``asset_type == "real_estate"`` can be a rental. Any other
  type → ``ValueError`` (caller maps to 422).
- The linked income stream's ``extra.source_asset_id`` is the source
  of truth for "which stream belongs to this rental"; we never trust
  name matching. This means renaming a property, moving it between
  users, or having two properties with identical names is safe.
- ``RentalMetadata`` is always validated through Pydantic before
  hitting the JSONB column — junk metadata can't sneak in via a
  unit test that bypasses the wizard.

Layer contract (CLAUDE.md § 0.1):
- Service flushes only; the worker / router commits.
- Service does not call Telegram, LLMs, or env vars.
- Service receives an ``AsyncSession`` — never opens its own.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.wealth.models.asset import Asset
from backend.wealth.models.income_stream import IncomeStream
from backend.wealth.schemas.rental import (
    OccupancyStatus,
    RentalMetadata,
    RentalYieldSummary,
)
from backend.wealth.services import asset_service

REAL_ESTATE_TYPE = "real_estate"
RENTAL_INCOME_SOURCE = "rental"
# Phase 3.8 Epic 2 promoted ``source_asset_id`` from JSONB to a real
# FK column on IncomeStream. The constant lingers for the JSONB
# ``extra`` payload that still snapshots occupancy / rent / expenses
# for read-only consumers (briefing, agent tool) that don't want to
# join through Asset.
SOURCE_ASSET_ID_KEY = "source_asset_id"


# ---------------------------------------------------------------------
# Mutation API
# ---------------------------------------------------------------------


async def mark_as_rental(
    db: AsyncSession,
    user_id: uuid.UUID,
    asset_id: uuid.UUID,
    metadata: RentalMetadata,
) -> Asset:
    """Convert an existing real-estate asset to a rental property.

    Idempotent: re-calling on an already-rental asset updates the
    metadata (and the linked income stream) instead of erroring.
    This matches user expectation — "I changed the rent from 15tr to
    16tr" should just work without an unmark/remark dance.

    Side effect: ensures exactly one active ``IncomeStream`` exists
    for this rental. Multiple calls don't duplicate.
    """
    asset = await asset_service.get_asset_by_id(db, user_id, asset_id)
    if asset is None:
        raise ValueError(f"Asset {asset_id} not found for user {user_id}")
    if asset.asset_type != REAL_ESTATE_TYPE:
        raise ValueError(
            f"Only real_estate assets can be marked as rental; got "
            f"asset_type={asset.asset_type!r}"
        )

    # ``model_dump(mode='json')`` serialises Decimal → str and date →
    # ISO string so the JSONB column round-trips through asyncpg
    # without coercion warnings. Loading it back via
    # ``RentalMetadata.model_validate`` parses those back into
    # Decimal/date.
    asset.is_rental = True
    asset.rental_metadata = metadata.model_dump(mode="json")

    await _sync_rental_income_stream(db, user_id, asset, metadata)

    await db.flush()
    return asset


async def update_occupancy(
    db: AsyncSession,
    user_id: uuid.UUID,
    asset_id: uuid.UUID,
    new_status: OccupancyStatus | str,
    *,
    tenant_name: str | None = None,
    lease_start_date: date | None = None,
    lease_end_date: date | None = None,
) -> Asset:
    """Update the occupancy status (and optionally tenant info).

    Pauses or resumes the linked income stream depending on the new
    status. Optional tenant fields are passed through so a "found a
    new tenant" UI can update everything in one call.

    Raises ``ValueError`` if the asset isn't a rental — callers
    should mark-as-rental first.
    """
    status_value = (
        new_status.value if isinstance(new_status, OccupancyStatus) else str(new_status)
    )
    if status_value not in {s.value for s in OccupancyStatus}:
        raise ValueError(f"Invalid occupancy_status: {status_value!r}")

    asset = await asset_service.get_asset_by_id(db, user_id, asset_id)
    if asset is None:
        raise ValueError(f"Asset {asset_id} not found for user {user_id}")
    if not asset.is_rental:
        raise ValueError(
            f"Asset {asset_id} is not a rental; mark_as_rental first"
        )

    metadata = _load_metadata(asset)
    # Build a fresh dict so Pydantic re-validates the lease-date
    # invariant after the change.
    payload: dict[str, Any] = metadata.model_dump(mode="json")
    payload["occupancy_status"] = status_value
    if tenant_name is not None:
        payload["tenant_name"] = tenant_name or None
    if lease_start_date is not None:
        payload["lease_start_date"] = lease_start_date.isoformat()
    if lease_end_date is not None:
        payload["lease_end_date"] = lease_end_date.isoformat()

    new_metadata = RentalMetadata.model_validate(payload)
    asset.rental_metadata = new_metadata.model_dump(mode="json")

    await _sync_rental_income_stream(db, user_id, asset, new_metadata)
    await db.flush()
    return asset


async def unmark_as_rental(
    db: AsyncSession,
    user_id: uuid.UUID,
    asset_id: uuid.UUID,
) -> Asset:
    """Revert a rental back to a plain real-estate asset.

    Pauses (not deletes) the linked income stream so that re-marking
    later — e.g. user moves into a self-use property and later rents
    it out again — restores the existing stream history rather than
    creating a fresh one. Metadata is cleared since "is rental? no"
    makes the rest meaningless; if the user re-marks, the wizard
    collects fresh values.
    """
    asset = await asset_service.get_asset_by_id(db, user_id, asset_id)
    if asset is None:
        raise ValueError(f"Asset {asset_id} not found for user {user_id}")
    if not asset.is_rental:
        # Already a non-rental — nothing to do, return as-is.
        return asset

    asset.is_rental = False
    asset.rental_metadata = None
    await _pause_streams_for_asset(db, user_id, asset_id)
    await db.flush()
    return asset


# ---------------------------------------------------------------------
# Read API
# ---------------------------------------------------------------------


async def get_user_rentals(
    db: AsyncSession, user_id: uuid.UUID
) -> list[Asset]:
    """Return every active rental owned by ``user_id``.

    Active = ``is_active = true AND is_rental = true``. Sold rentals
    are excluded — the partial index ``idx_assets_rental_active``
    gates this query in O(rentals) time.
    """
    stmt = (
        select(Asset)
        .where(
            Asset.user_id == user_id,
            Asset.is_active.is_(True),
            Asset.is_rental.is_(True),
        )
        .order_by(Asset.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def get_rental_yield_summary(
    db: AsyncSession, user_id: uuid.UUID
) -> RentalYieldSummary:
    """Aggregate yields across every active rental.

    Returns zeros (and ``None`` for blended yield) when the user has
    no rentals — callers can display "Bạn chưa có BĐS cho thuê" rather
    than a misleading 0% number.
    """
    rentals = await get_user_rentals(db, user_id)

    occupied = vacant = self_use = 0
    total_rent = Decimal(0)
    total_expenses = Decimal(0)
    total_value = Decimal(0)

    for asset in rentals:
        meta = _load_metadata(asset)
        if meta.occupancy_status == OccupancyStatus.RENTED.value:
            occupied += 1
        elif meta.occupancy_status == OccupancyStatus.VACANT.value:
            vacant += 1
        else:
            self_use += 1
        total_rent += Decimal(meta.monthly_rent)
        total_expenses += Decimal(meta.monthly_expenses)
        total_value += Decimal(asset.current_value or 0)

    net_monthly = total_rent - total_expenses
    annual = net_monthly * Decimal(12)
    blended_pct: float | None
    if not rentals or total_value <= 0:
        blended_pct = None
    else:
        blended_pct = float(annual / total_value * Decimal(100))

    return RentalYieldSummary(
        property_count=len(rentals),
        occupied_count=occupied,
        vacant_count=vacant,
        self_use_count=self_use,
        total_monthly_rent=total_rent,
        total_monthly_expenses=total_expenses,
        net_monthly_yield=net_monthly,
        annual_passive_income=annual,
        total_property_value=total_value,
        blended_annual_yield_pct=blended_pct,
    )


# ---------------------------------------------------------------------
# IncomeStream linkage helpers (private)
# ---------------------------------------------------------------------


async def _sync_rental_income_stream(
    db: AsyncSession,
    user_id: uuid.UUID,
    asset: Asset,
    metadata: RentalMetadata,
) -> IncomeStream:
    """Ensure exactly one IncomeStream tracks this rental's net income.

    - Creates one on first call.
    - Updates ``amount`` / ``is_active`` / ``extra`` on subsequent
      calls (e.g. rent change, tenant moved out).
    - Re-uses the existing row even if the user previously
      ``unmark_as_rental``-ed and the stream was paused.

    Linkage: Epic 2 promoted ``source_asset_id`` to a real FK column,
    so lookups are O(1) via ``idx_income_source_asset`` rather than a
    Python-side JSONB walk. ``extra`` still carries occupancy +
    rent/expense snapshot for read-only consumers (briefing, agent)
    that don't want to round-trip through Asset.
    """
    stream = await _find_stream_for_asset(db, user_id, asset.id)

    monthly_amount = metadata.net_monthly_yield
    is_active = metadata.is_income_active()
    name = f"Thuê BĐS — {asset.name}"
    # Snapshot fields stay in ``extra`` for read-only consumers; the
    # canonical pointer is now ``source_asset_id`` FK above.
    extra = {
        SOURCE_ASSET_ID_KEY: str(asset.id),
        "occupancy_status": metadata.occupancy_status,
        "monthly_rent": str(Decimal(metadata.monthly_rent)),
        "monthly_expenses": str(Decimal(metadata.monthly_expenses)),
    }

    if stream is None:
        stream = IncomeStream(
            user_id=user_id,
            stream_type=RENTAL_INCOME_SOURCE,
            is_passive=True,
            name=name,
            # Rental cashflow is monthly by definition (Case A); the
            # raw ``amount`` equals the monthly equivalent.
            amount=monthly_amount,
            currency="VND",
            schedule_type="monthly",
            start_date=date.today(),
            is_active=is_active,
            source_asset_id=asset.id,
            extra=extra,
        )
        db.add(stream)
    else:
        stream.name = name
        stream.amount = monthly_amount
        stream.is_active = is_active
        stream.extra = extra
        # Belt-and-braces: enforce the FK on existing rows in case a
        # legacy stream had only the JSONB pointer set (pre-Epic-2).
        if stream.source_asset_id is None:
            stream.source_asset_id = asset.id

    return stream


async def _pause_streams_for_asset(
    db: AsyncSession,
    user_id: uuid.UUID,
    asset_id: uuid.UUID,
) -> None:
    """Set every linked income stream to ``is_active=False``.

    "Pause" rather than "delete" so re-marking restores the same row
    (preserves ``created_at`` and any future Phase 2 income history
    that joins through ``source_asset_id``).
    """
    stream = await _find_stream_for_asset(db, user_id, asset_id)
    if stream is not None and stream.is_active:
        stream.is_active = False


async def _find_stream_for_asset(
    db: AsyncSession,
    user_id: uuid.UUID,
    asset_id: uuid.UUID,
) -> IncomeStream | None:
    """Locate the IncomeStream linked to ``asset_id``.

    Epic 2 made ``source_asset_id`` a real FK column with a partial
    index (``idx_income_source_asset`` WHERE NOT NULL), so this is
    now an O(1) indexed lookup instead of the JSONB-walk fallback
    Epic 1 needed. We accept inactive streams (no ``is_active``
    filter) so an ``unmark_as_rental`` → ``mark_as_rental`` round-
    trip revives the same row instead of creating a duplicate.
    """
    stmt = select(IncomeStream).where(
        IncomeStream.user_id == user_id,
        IncomeStream.source_asset_id == asset_id,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


def _load_metadata(asset: Asset) -> RentalMetadata:
    """Parse ``asset.rental_metadata`` into a validated schema.

    Raises ``ValueError`` if the JSON is malformed — that should be
    impossible given every write goes through ``model_dump`` here,
    but defensively we never trust JSONB content.
    """
    if not asset.rental_metadata:
        raise ValueError(
            f"Asset {asset.id} marked is_rental but has no rental_metadata"
        )
    return RentalMetadata.model_validate(asset.rental_metadata)
