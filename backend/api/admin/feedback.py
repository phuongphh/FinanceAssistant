from __future__ import annotations

import csv
import io
import uuid
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.admin.analytics import DEFAULT_TENANT_ID, PERIOD_DAYS, VN_TZ
from backend.api.admin.deps import get_current_admin
from backend.database import get_db
from backend.feedback.models.feedback import (
    FEEDBACK_STATUS_ACTIONED,
    FEEDBACK_STATUS_DISMISSED,
    FEEDBACK_STATUS_NEW,
    FEEDBACK_STATUS_REVIEWING,
    Feedback,
)
from backend.feedback.services.classifier import (
    VALID_CATEGORIES,
    VALID_PRIORITIES,
    VALID_SENTIMENTS,
)
from backend.models.admin_user import AdminUser
from backend.models.user import User
from backend.services.admin_audit import log_action
from backend.utils.pii import mask_name

router = APIRouter(prefix="/feedback", tags=["admin-feedback"])

# "all" surfaces every feedback ever recorded — the default the operator
# requested ("show mọi feedback từ trước đến giờ"). The narrower windows
# reuse the shared PERIOD_DAYS map so behaviour stays identical to the rest
# of the admin portal.
_RANGE_RE = r"^(7d|14d|30d|90d|custom|all)$"
FEEDBACK_STATUSES = {
    FEEDBACK_STATUS_NEW,
    FEEDBACK_STATUS_REVIEWING,
    FEEDBACK_STATUS_ACTIONED,
    FEEDBACK_STATUS_DISMISSED,
}
SORT_KEYS = {"newest", "oldest"}
# Hard cap on a single CSV export so one operator cannot stream the entire
# table into memory. Mirrors the twin-metrics export contract (X-* headers).
CSV_ROW_CAP = 50_000
CSV_COLUMNS = [
    "id",
    "created_at",
    "user_id",
    "category",
    "sentiment",
    "priority",
    "status",
    "trigger",
    "classification_confidence",
    "onboarding_emoji_signal",
    "first_responded_at",
    "content",
]


class FeedbackListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    display_name: str
    telegram_id: int | None = None
    content: str
    category: str | None = None
    sentiment: str | None = None
    priority: str | None = None
    status: str
    trigger: str
    classification_confidence: float | None = None
    onboarding_emoji_signal: str | None = None
    created_at: str
    first_responded_at: str | None = None


class FeedbackListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[FeedbackListItem]


def _admin_tenant_id(admin: AdminUser) -> int:
    return admin.tenant_id or DEFAULT_TENANT_ID


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_window(
    period: str, start_date: date | None, end_date: date | None
) -> tuple[datetime | None, datetime | None, str]:
    """Translate the requested period into a UTC half-open window.

    ``all`` returns ``(None, None)`` so no time predicate is applied — the
    operator sees every feedback ever recorded. Custom ranges are anchored to
    Vietnam-time midnight (the timezone the operator picks dates in) before
    being converted to UTC, matching the twin-metrics window helper.
    """
    if period == "all":
        return None, None, "all"
    if period == "custom" and start_date and end_date:
        start = datetime.combine(start_date, time.min, tzinfo=VN_TZ).astimezone(
            timezone.utc
        )
        end = datetime.combine(
            end_date + timedelta(days=1), time.min, tzinfo=VN_TZ
        ).astimezone(timezone.utc)
        if end <= start:
            end = start + timedelta(days=1)
        return start, end, f"custom:{start_date.isoformat()}:{end_date.isoformat()}"
    days = PERIOD_DAYS.get(period, 30)
    return _now() - timedelta(days=days), _now(), period


def _parse_user_id(user_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(user_id)
    except (ValueError, AttributeError) as exc:
        raise HTTPException(status_code=422, detail="Invalid user_id") from exc


def _build_filters(
    tenant_id: int,
    *,
    start: datetime | None,
    end: datetime | None,
    category: str | None,
    sentiment: str | None,
    priority: str | None,
    status_: str | None,
    user_uuid: uuid.UUID | None,
    search: str | None,
) -> list:
    """Tenant-scoped predicate list shared by the list, count and CSV queries.

    Feedback has no ``tenant_id`` column, so isolation is enforced by joining
    to ``users`` and pinning ``User.tenant_id`` — an operator can never read
    another tenant's feedback. Soft-deleted users are excluded for parity with
    every other admin view.
    """
    filters = [User.tenant_id == tenant_id, User.deleted_at.is_(None)]
    if start is not None:
        filters.append(Feedback.created_at >= start)
    if end is not None:
        filters.append(Feedback.created_at < end)
    if category:
        filters.append(Feedback.category == category)
    if sentiment:
        filters.append(Feedback.sentiment == sentiment)
    if priority:
        filters.append(Feedback.priority == priority)
    if status_:
        filters.append(Feedback.status == status_)
    if user_uuid is not None:
        filters.append(Feedback.user_id == user_uuid)
    if search:
        pattern = f"%{search.strip()}%"
        filters.append(
            or_(
                Feedback.content.ilike(pattern),
                cast(Feedback.user_id, String).ilike(pattern),
            )
        )
    return filters


def _validate_enums(
    category: str | None,
    sentiment: str | None,
    priority: str | None,
    status_: str | None,
    sort: str,
) -> None:
    if category is not None and category not in VALID_CATEGORIES:
        raise HTTPException(status_code=422, detail="Invalid category")
    if sentiment is not None and sentiment not in VALID_SENTIMENTS:
        raise HTTPException(status_code=422, detail="Invalid sentiment")
    if priority is not None and priority not in VALID_PRIORITIES:
        raise HTTPException(status_code=422, detail="Invalid priority")
    if status_ is not None and status_ not in FEEDBACK_STATUSES:
        raise HTTPException(status_code=422, detail="Invalid status")
    if sort not in SORT_KEYS:
        raise HTTPException(status_code=422, detail="Invalid sort")


def _order_by(sort: str):
    # id is the deterministic tie-breaker so paging never repeats or skips a
    # row when many feedbacks share a created_at timestamp.
    if sort == "oldest":
        return Feedback.created_at.asc(), Feedback.id.asc()
    return Feedback.created_at.desc(), Feedback.id.desc()


def _row_to_item(row) -> FeedbackListItem:
    return FeedbackListItem(
        id=str(row.id),
        user_id=str(row.user_id),
        display_name=mask_name(row.display_name or row.telegram_handle),
        telegram_id=row.telegram_id,
        content=row.content,
        category=row.category,
        sentiment=row.sentiment,
        priority=row.priority,
        status=row.status,
        trigger=row.trigger,
        classification_confidence=(
            float(row.classification_confidence)
            if row.classification_confidence is not None
            else None
        ),
        onboarding_emoji_signal=row.onboarding_emoji_signal,
        created_at=row.created_at.isoformat(),
        first_responded_at=(
            row.first_responded_at.isoformat() if row.first_responded_at else None
        ),
    )


@router.get("", response_model=FeedbackListResponse)
async def list_feedback(
    request: Request,
    period: str = Query(default="all", pattern=_RANGE_RE),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    category: str | None = Query(default=None, max_length=50),
    sentiment: str | None = Query(default=None, max_length=20),
    priority: str | None = Query(default=None, max_length=20),
    status: str | None = Query(default=None, max_length=20),
    user_id: str | None = Query(default=None, max_length=64),
    search: str | None = Query(default=None, max_length=200),
    sort: str = Query(default="newest"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> FeedbackListResponse:
    _validate_enums(category, sentiment, priority, status, sort)
    user_uuid = _parse_user_id(user_id) if user_id else None
    tenant_id = _admin_tenant_id(admin)
    start, end, label = _parse_window(period, start_date, end_date)

    filters = _build_filters(
        tenant_id,
        start=start,
        end=end,
        category=category,
        sentiment=sentiment,
        priority=priority,
        status_=status,
        user_uuid=user_uuid,
        search=search,
    )

    total_stmt = (
        select(func.count())
        .select_from(Feedback)
        .join(User, User.id == Feedback.user_id)
        .where(*filters)
    )
    list_stmt = (
        select(
            Feedback.id,
            Feedback.user_id,
            Feedback.content,
            Feedback.category,
            Feedback.sentiment,
            Feedback.priority,
            Feedback.status,
            Feedback.trigger,
            Feedback.classification_confidence,
            Feedback.onboarding_emoji_signal,
            Feedback.created_at,
            Feedback.first_responded_at,
            User.display_name,
            User.telegram_handle,
            User.telegram_id,
        )
        .join(User, User.id == Feedback.user_id)
        .where(*filters)
        .order_by(*_order_by(sort))
        .limit(limit)
        .offset(offset)
    )

    total = await db.scalar(total_stmt)
    rows = (await db.execute(list_stmt)).all()
    items = [_row_to_item(row) for row in rows]

    await log_action(
        db,
        admin.id,
        "feedback_list",
        target_type="feedback",
        payload={
            "period": label,
            "category": category,
            "sentiment": sentiment,
            "priority": priority,
            "status": status,
            "user_id": str(user_uuid) if user_uuid else None,
            "search": bool(search),
            "limit": limit,
            "offset": offset,
            "returned": len(items),
        },
        request=request,
    )
    await db.commit()

    return FeedbackListResponse(
        total=int(total or 0), limit=limit, offset=offset, items=items
    )


@router.get("/export.csv")
async def export_feedback_csv(
    request: Request,
    period: str = Query(default="all", pattern=_RANGE_RE),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    category: str | None = Query(default=None, max_length=50),
    sentiment: str | None = Query(default=None, max_length=20),
    priority: str | None = Query(default=None, max_length=20),
    status: str | None = Query(default=None, max_length=20),
    user_id: str | None = Query(default=None, max_length=64),
    search: str | None = Query(default=None, max_length=200),
    sort: str = Query(default="newest"),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> Response:
    _validate_enums(category, sentiment, priority, status, sort)
    user_uuid = _parse_user_id(user_id) if user_id else None
    tenant_id = _admin_tenant_id(admin)
    start, end, label = _parse_window(period, start_date, end_date)

    filters = _build_filters(
        tenant_id,
        start=start,
        end=end,
        category=category,
        sentiment=sentiment,
        priority=priority,
        status_=status,
        user_uuid=user_uuid,
        search=search,
    )

    total = int(
        await db.scalar(
            select(func.count())
            .select_from(Feedback)
            .join(User, User.id == Feedback.user_id)
            .where(*filters)
        )
        or 0
    )
    rows = (
        await db.execute(
            select(
                Feedback.id,
                Feedback.created_at,
                Feedback.user_id,
                Feedback.category,
                Feedback.sentiment,
                Feedback.priority,
                Feedback.status,
                Feedback.trigger,
                Feedback.classification_confidence,
                Feedback.onboarding_emoji_signal,
                Feedback.first_responded_at,
                Feedback.content,
            )
            .join(User, User.id == Feedback.user_id)
            .where(*filters)
            .order_by(*_order_by(sort))
            .limit(CSV_ROW_CAP)
        )
    ).all()

    # csv.writer handles quoting/escaping for content that contains commas,
    # quotes or newlines — far safer than hand-joining strings.
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    for row in rows:
        writer.writerow(
            [
                str(row.id),
                row.created_at.isoformat() if row.created_at else "",
                str(row.user_id),
                row.category or "",
                row.sentiment or "",
                row.priority or "",
                row.status or "",
                row.trigger or "",
                row.classification_confidence
                if row.classification_confidence is not None
                else "",
                row.onboarding_emoji_signal or "",
                row.first_responded_at.isoformat() if row.first_responded_at else "",
                row.content or "",
            ]
        )

    truncated = total > len(rows)
    await log_action(
        db,
        admin.id,
        "feedback_export",
        target_type="feedback",
        payload={
            "period": label,
            "category": category,
            "sentiment": sentiment,
            "priority": priority,
            "status": status,
            "user_id": str(user_uuid) if user_uuid else None,
            "search": bool(search),
            "rows_returned": len(rows),
            "rows_total": total,
            "truncated": truncated,
        },
        request=request,
        commit=True,
    )

    headers = {
        "Content-Disposition": "attachment; filename=feedback-export.csv",
        "X-Rows-Returned": str(len(rows)),
        "X-Rows-Total": str(total),
        "X-Truncated": "true" if truncated else "false",
    }
    return Response(buffer.getvalue(), media_type="text/csv", headers=headers)
