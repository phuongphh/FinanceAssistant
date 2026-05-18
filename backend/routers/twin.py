"""Financial Twin public API routes for Mini App clients."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.life_events.impact import parse_event_ids
from backend.miniapp.auth import require_miniapp_auth
from backend.miniapp.routes import _resolve_user
from backend.twin.services import twin_api_service, twin_projection_service

router = APIRouter(prefix="/twin", tags=["twin"])


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
