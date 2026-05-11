"""FastAPI routes for Life Events (Phase 4B Epic 2, S11).

Two surfaces share this module:
- The Mini App's "Kế hoạch" panel: list, create, update, soft-delete events
  for the authenticated user.
- The /api/twin handler reuses ``adjust_cone_with_events`` from this module's
  service layer to honour the ``exclude_event_ids`` query param — no MC
  recompute needed for toggle UX.

Auth: Telegram WebApp initData via ``require_miniapp_auth`` (same as the
other Mini App endpoints). User scoping is enforced inside the service.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.life_events import service as life_event_service
from backend.life_events.impact import build_impact_summary, base_year_from_computed_at
from backend.life_events.schemas import (
    LifeEventCreate,
    LifeEventRead,
    LifeEventUpdate,
)
from backend.miniapp.auth import require_miniapp_auth
from backend.miniapp.routes import _resolve_user
from backend.twin.services.twin_projection_service import (
    DEFAULT_HORIZON_YEARS,
    SCENARIO_CURRENT,
)
from backend.twin.services.twin_query_service import get_latest_projection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/life-events", tags=["life-events"])


def _project_horizon_and_base_year(projection) -> tuple[int, int]:
    horizon = (
        projection.horizon_years
        if projection is not None
        else DEFAULT_HORIZON_YEARS
    )
    base_year = base_year_from_computed_at(
        projection.computed_at if projection is not None else None
    )
    return horizon, base_year


@router.get("")
async def list_life_events(
    auth: dict = Depends(require_miniapp_auth),
    db: AsyncSession = Depends(get_db),
):
    """Return the authenticated user's active life events with impact summaries."""
    user = await _resolve_user(auth, db)
    events = await life_event_service.list_for_user(db, user.id)
    projection = await get_latest_projection(db, user.id, scenario=SCENARIO_CURRENT)
    horizon, base_year = _project_horizon_and_base_year(projection)
    items = []
    for event in events:
        read = LifeEventRead.model_validate(event).model_dump(mode="json")
        impact = build_impact_summary(event, base_year=base_year, horizon_years=horizon)
        # Convert Decimal year_deltas to strings for stable wire format.
        impact_payload = impact.model_dump(mode="json")
        impact_payload["year_deltas"] = [str(d) for d in impact.year_deltas]
        items.append({"event": read, "impact": impact_payload})
    return {
        "data": {
            "events": items,
            "base_year": base_year,
            "horizon_years": horizon,
        },
        "error": None,
    }


@router.post("", status_code=201)
async def create_life_event(
    payload: LifeEventCreate,
    auth: dict = Depends(require_miniapp_auth),
    db: AsyncSession = Depends(get_db),
):
    """Create a new life event for the authenticated user."""
    user = await _resolve_user(auth, db)
    try:
        event = await life_event_service.create_life_event(db, user.id, payload)
        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception("life-event create failed user=%s", user.id)
        raise HTTPException(status_code=500, detail="Failed to save life event")
    read = LifeEventRead.model_validate(event).model_dump(mode="json")
    return {"data": read, "error": None}


@router.patch("/{event_id}")
async def update_life_event(
    payload: LifeEventUpdate,
    event_id: uuid.UUID = Path(...),
    auth: dict = Depends(require_miniapp_auth),
    db: AsyncSession = Depends(get_db),
):
    user = await _resolve_user(auth, db)
    try:
        event = await life_event_service.update_life_event(
            db, user.id, event_id, payload
        )
        if event is None:
            raise HTTPException(status_code=404, detail="Life event not found")
        await db.commit()
    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        logger.exception("life-event update failed user=%s id=%s", user.id, event_id)
        raise HTTPException(status_code=500, detail="Failed to update life event")
    read = LifeEventRead.model_validate(event).model_dump(mode="json")
    return {"data": read, "error": None}


@router.delete("/{event_id}", status_code=200)
async def delete_life_event(
    event_id: uuid.UUID = Path(...),
    auth: dict = Depends(require_miniapp_auth),
    db: AsyncSession = Depends(get_db),
):
    user = await _resolve_user(auth, db)
    try:
        ok = await life_event_service.soft_delete(db, user.id, event_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Life event not found")
        await db.commit()
    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        logger.exception("life-event delete failed user=%s id=%s", user.id, event_id)
        raise HTTPException(status_code=500, detail="Failed to delete life event")
    return {"data": {"id": str(event_id), "deleted": True}, "error": None}


@router.get("/{event_id}/impact", response_model=None)
async def get_life_event_impact(
    event_id: uuid.UUID = Path(...),
    auth: dict = Depends(require_miniapp_auth),
    db: AsyncSession = Depends(get_db),
):
    """Return the deterministic year-by-year impact deltas for one event.

    The Mini App calls this to apply an event delta onto a base cone
    locally, without a Twin recompute round-trip.
    """
    user = await _resolve_user(auth, db)
    event = await life_event_service.get_by_id(db, user.id, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Life event not found")
    projection = await get_latest_projection(db, user.id, scenario=SCENARIO_CURRENT)
    horizon, base_year = _project_horizon_and_base_year(projection)
    impact = build_impact_summary(event, base_year=base_year, horizon_years=horizon)
    payload = impact.model_dump(mode="json")
    payload["year_deltas"] = [str(d) for d in impact.year_deltas]
    return {
        "data": {
            "impact": payload,
            "base_year": base_year,
            "horizon_years": horizon,
        },
        "error": None,
    }
