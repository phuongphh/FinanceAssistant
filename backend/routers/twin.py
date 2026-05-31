"""Financial Twin public API routes for Mini App clients."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.life_events.impact import parse_event_ids
from backend.miniapp.auth import require_miniapp_auth
from backend.miniapp.routes import _resolve_user
from backend.twin.services import causality_service, twin_api_service, twin_projection_service
from backend.models.twin_view_event import TwinViewEvent
from backend.services.feature_events import record_feature_event
from backend.utils.analytics_sanitizer import sanitize_properties

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/twin", tags=["twin"])

_ALLOWED_TWIN_VIEW_EVENTS = {
    "story_opened",
    "screen_viewed",
    "story_skipped",
    "story_completed",
    "chart_opened",
}


class TwinViewEventIn(BaseModel):
    event_type: str = Field(..., max_length=40)
    screen_id: str | None = Field(default=None, max_length=40)
    flow_mode: str | None = Field(default=None, max_length=20)
    metadata: dict | None = None



@router.get("")
async def get_twin(
    response: Response,
    scenario: str = Query(
        twin_projection_service.SCENARIO_CURRENT,
        pattern="^(current|optimal)$",
        description="Projection scenario: current or optimal",
    ),
    exclude_event_ids: str | None = Query(
        None,
        max_length=512,
        description=(
            "Comma-separated life-event UUIDs to exclude from the cone. "
            "Used by the Mini App's toggle UX — invalid IDs are silently dropped."
        ),
    ),
    if_none_match: str | None = Header(None, alias="If-None-Match"),
    auth: dict = Depends(require_miniapp_auth),
    db: AsyncSession = Depends(get_db),
):
    """Return latest Twin projection JSON for the authenticated Mini App user."""
    user = await _resolve_user(auth, db)
    excluded = parse_event_ids(exclude_event_ids)
    try:
        if excluded:
            payload = await twin_api_service.build_twin_payload(
                db, user.id, scenario=scenario, exclude_event_ids=excluded
            )
        else:
            payload = await twin_api_service.build_twin_payload(
                db, user.id, scenario=scenario
            )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    etag = twin_api_service.etag_for_payload(payload)
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "private, max-age=30"
    if if_none_match == etag:
        response.status_code = 304
        return None
    return {"data": payload, "error": None}


@router.get("/causality")
async def get_twin_causality(
    auth: dict = Depends(require_miniapp_auth),
    db: AsyncSession = Depends(get_db),
):
    """Explain the latest Twin net-worth change for the Mini App status pill.

    Lazy companion to ``GET /api/twin``: the main projection payload stays
    lean, and the causality breakdown is only computed when a user actually
    taps the status pill. ``attribute_delta`` is read-only and server-cached
    by projection id, so repeat taps within a session are cheap.
    """
    user = await _resolve_user(auth, db)
    try:
        breakdown = await causality_service.attribute_delta(db, user.id)
    except Exception as exc:
        logger.exception("twin causality failed user=%s", user.id)
        raise HTTPException(status_code=503, detail="causality_unavailable") from exc
    return {
        "data": {
            "text": breakdown.text,
            "direction": breakdown.direction,
            "show_breakdown": breakdown.show_breakdown,
        },
        "error": None,
    }


@router.post("/events")
async def record_twin_view_event(
    event: TwinViewEventIn,
    auth: dict = Depends(require_miniapp_auth),
    db: AsyncSession = Depends(get_db),
):
    """Record a Twin storytelling/navigation event for funnel analytics."""
    if event.event_type not in _ALLOWED_TWIN_VIEW_EVENTS:
        raise HTTPException(status_code=422, detail="Unsupported Twin view event")
    user = await _resolve_user(auth, db)
    metadata = sanitize_properties(event.metadata)
    db.add(
        TwinViewEvent(
            user_id=user.id,
            event_type=event.event_type,
            screen_id=event.screen_id,
            flow_mode=event.flow_mode,
            metadata_=metadata or None,
        )
    )
    record_feature_event(
        "twin_storytelling",
        user_id=user.id,
        metadata={
            "event_type": event.event_type,
            "screen_id": event.screen_id,
            "flow_mode": event.flow_mode,
        },
    )
    return {"data": {"ok": True}, "error": None}
