from __future__ import annotations

import hashlib
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.admin.analytics import DEFAULT_TENANT_ID, PERIOD_DAYS, VN_TZ
from backend.api.admin.deps import get_current_admin
from backend.api.admin.twin_alerts import evaluate_delta_bias_alert, evaluate_loop_alerts
from backend.database import get_db
from backend.models.admin_user import AdminUser
from backend.models.event import Event
from backend.models.portfolio_asset import PortfolioAsset
from backend.models.twin_calibration import TwinCalibrationSnapshot
from backend.models.twin_habit_loop import TwinDeltaThresholdConfig, TwinRecomputeLog
from backend.models.twin_projection import TwinProjection
from backend.models.twin_view_event import TwinViewEvent
from backend.models.user import User
from backend.services.admin_audit import log_action
from backend.services.admin_cache import cache_get, cache_invalidate_pattern, cache_set

router = APIRouter(prefix="/twin-metrics", tags=["admin-twin-metrics"])
CACHE_TTL_SECONDS = 15 * 60
# Calibration / CSV row caps. The previous 500/5000 limits were silently
# truncating the dataset operators rely on. The new caps are generous and
# we expose a ``truncated`` flag so the UI can show "showing first N rows".
CALIBRATION_ROW_CAP = 5000
CSV_ROW_CAP = 50_000
TWIN_SECTIONS = ("funnel", "loop", "comprehension", "delta")
_RANGE_RE = r"^(7d|14d|30d|90d|custom)$"
_SEGMENTS = {"starter", "young_pro", "mass_affluent", "hnw"}
_ACTION_EVENT_KEYS = {
    "action_suggestion.shown": "suggested",
    "action_suggestion.complete": "completed",
}


def _admin_tenant_id(admin: AdminUser) -> int:
    return admin.tenant_id or DEFAULT_TENANT_ID


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_window(period: str, start_date: date | None, end_date: date | None) -> tuple[datetime, datetime, str]:
    if period == "custom" and start_date and end_date:
        start = datetime.combine(start_date, time.min, tzinfo=VN_TZ).astimezone(timezone.utc)
        end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=VN_TZ).astimezone(timezone.utc)
        if end <= start:
            end = start + timedelta(days=1)
        return start, min(end, _now()), f"custom:{start_date.isoformat()}:{end_date.isoformat()}"
    days = PERIOD_DAYS.get(period, 30)
    return _now() - timedelta(days=days), _now(), period


def _to_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _pct(numerator: int | float, denominator: int | float) -> float:
    return round((float(numerator) / float(denominator) * 100), 1) if denominator else 0.0


def _safe_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value or 0)


def _segment_case(total_value):
    return case(
        (total_value < 100_000_000, "starter"),
        (total_value < 500_000_000, "young_pro"),
        (total_value < 5_000_000_000, "mass_affluent"),
        else_="hnw",
    )


def _wealth_subquery():
    asset_value = func.coalesce(PortfolioAsset.quantity, 0) * func.coalesce(PortfolioAsset.current_price, 0)
    return (
        select(
            PortfolioAsset.user_id.label("user_id"),
            func.coalesce(func.sum(asset_value), 0).label("net_worth"),
        )
        .where(PortfolioAsset.deleted_at.is_(None))
        .group_by(PortfolioAsset.user_id)
        .subquery()
    )


def _user_filters(tenant_id: int, cohort_week: date | None, segment: str | None, wealth_sq):
    filters = [User.deleted_at.is_(None), User.tenant_id == tenant_id]
    if cohort_week:
        # ``cohort_week`` is a calendar date the operator picks in the
        # Vietnam-time UI. Anchor the 7-day window to VN_TZ midnight,
        # converted to UTC for storage comparison — otherwise we
        # silently drift by 7 hours and the cohort filter loses users
        # who signed up between 17:00-23:59 ICT on the boundary days.
        start = datetime.combine(cohort_week, time.min, tzinfo=VN_TZ).astimezone(timezone.utc)
        filters.append(User.created_at >= start)
        filters.append(User.created_at < start + timedelta(days=7))
    if segment in _SEGMENTS:
        filters.append(_segment_case(func.coalesce(wealth_sq.c.net_worth, 0)) == segment)
    return filters


def _anonymize_user_id(user_id: uuid.UUID) -> str:
    digest = hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()
    return f"usr_{digest[:10]}"


async def _cached(key: str, builder):
    cached = await cache_get(key)
    if cached is not None:
        return cached
    payload = await builder()
    await cache_set(key, payload, CACHE_TTL_SECONDS)
    return payload


@router.get("/engagement-funnel")
async def engagement_funnel(
    period: str = Query(default="30d", pattern=_RANGE_RE),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    cohort_week: date | None = Query(default=None),
    segment: str | None = Query(default=None, pattern="^(starter|young_pro|mass_affluent|hnw)?$"),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    tenant_id = _admin_tenant_id(admin)
    start, end, label = _parse_window(period, start_date, end_date)
    cache_key = f"admin:tenant:{tenant_id}:twin:funnel:{label}:{cohort_week}:{segment}"

    async def build() -> dict:
        wealth_sq = _wealth_subquery()
        rows = (await db.execute(
            select(TwinViewEvent.user_id, func.count(TwinViewEvent.id).label("views"), func.max(TwinViewEvent.created_at).label("last_view"))
            .join(User, User.id == TwinViewEvent.user_id)
            .outerjoin(wealth_sq, wealth_sq.c.user_id == User.id)
            .where(
                TwinViewEvent.created_at >= start,
                TwinViewEvent.created_at < end,
                TwinViewEvent.event_type.in_(["story_opened", "screen_viewed", "chart_opened"]),
                *_user_filters(tenant_id, cohort_week, segment, wealth_sq),
            )
            .group_by(TwinViewEvent.user_id)
        )).all()
        first_view = len(rows)
        second_view = sum(1 for row in rows if int(row.views or 0) >= 2)
        # Habit = ≥3 views/week sustained across the window. Compute as
        # average views per ISO week ≥ 3 (window width in days / 7).
        window_days = max((end - start).total_seconds() / 86400.0, 1.0)
        weeks = max(window_days / 7.0, 1.0)
        habit = sum(1 for row in rows if (int(row.views or 0) / weeks) >= 3)
        abandon = sum(1 for row in rows if int(row.views or 0) == 1)
        stages = [
            {"key": "first_view", "label": "First view", "users": first_view},
            {"key": "second_view", "label": "2nd view", "users": second_view},
            {"key": "habit", "label": "Habit ≥3/week", "users": habit},
            {"key": "abandonment", "label": "Abandonment", "users": abandon},
        ]
        # Conversion is sequential from first_view → second_view → habit.
        # Abandonment is NOT a sequential downstream of habit; it's the
        # share of first-viewers who never came back, so it's computed
        # against ``first_view``.
        previous = None
        for stage in stages:
            if stage["key"] == "abandonment":
                stage["conversion_pct"] = _pct(stage["users"], first_view)
                continue
            stage["conversion_pct"] = 100.0 if previous is None else _pct(stage["users"], previous)
            previous = stage["users"]
        return {"generated_at": _now(), "refresh_seconds": CACHE_TTL_SECONDS, "stages": stages}

    return await _cached(cache_key, build)


@router.get("/engagement-funnel/users")
async def engagement_funnel_users(
    stage: str = Query(pattern="^(first_view|second_view|habit|abandonment)$"),
    period: str = Query(default="30d", pattern=_RANGE_RE),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    tenant_id = _admin_tenant_id(admin)
    start, end, _ = _parse_window(period, start_date, end_date)
    view_count = func.count(TwinViewEvent.id)
    having = {
        "first_view": view_count >= 1,
        "second_view": view_count >= 2,
        "habit": view_count >= 3,
        "abandonment": view_count == 1,
    }[stage]
    rows = (await db.execute(
        select(TwinViewEvent.user_id, view_count.label("views"), func.max(TwinViewEvent.created_at).label("last_view"))
        .join(User, User.id == TwinViewEvent.user_id)
        .where(
            User.tenant_id == tenant_id,
            User.deleted_at.is_(None),
            TwinViewEvent.created_at >= start,
            TwinViewEvent.created_at < end,
            TwinViewEvent.event_type.in_(["story_opened", "screen_viewed", "chart_opened"]),
        )
        .group_by(TwinViewEvent.user_id)
        .having(having)
        .order_by(desc(func.max(TwinViewEvent.created_at)))
        .limit(limit)
    )).all()
    return {
        "users": [
            {"anon_user_id": _anonymize_user_id(row.user_id), "views": int(row.views or 0), "last_view_at": row.last_view}
            for row in rows
        ]
    }


@router.get("/loop-health")
async def loop_health(
    period: str = Query(default="30d", pattern=_RANGE_RE),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    cohort_week: date | None = Query(default=None),
    segment: str | None = Query(default=None, pattern="^(starter|young_pro|mass_affluent|hnw)?$"),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    tenant_id = _admin_tenant_id(admin)
    start, end, label = _parse_window(period, start_date, end_date)
    cache_key = f"admin:tenant:{tenant_id}:twin:loop:{label}:{cohort_week}:{segment}"

    async def build() -> dict:
        wealth_sq = _wealth_subquery()
        user_filter = _user_filters(tenant_id, cohort_week, segment, wealth_sq)
        trigger_rows = (await db.execute(
            select(TwinRecomputeLog.event_type, func.count(TwinRecomputeLog.id))
            .join(User, User.id == TwinRecomputeLog.user_id)
            .outerjoin(wealth_sq, wealth_sq.c.user_id == User.id)
            .where(TwinRecomputeLog.created_at >= start, TwinRecomputeLog.created_at < end, *user_filter)
            .group_by(TwinRecomputeLog.event_type)
        )).all()
        source_map = {"briefing_tap": "briefing tap", "action_completed": "action-triggered", "manual": "voluntary"}
        trigger_sources = [
            {"source": source_map.get(str(name), str(name or "voluntary")), "count": int(count or 0)}
            for name, count in trigger_rows
        ]
        day_counts: dict[date, Counter] = defaultdict(Counter)
        view_rows = (await db.execute(
            select(func.date(TwinViewEvent.created_at), func.count(func.distinct(TwinViewEvent.user_id)))
            .join(User, User.id == TwinViewEvent.user_id)
            .outerjoin(wealth_sq, wealth_sq.c.user_id == User.id)
            .where(TwinViewEvent.created_at >= start, TwinViewEvent.created_at < end, TwinViewEvent.event_type.in_(["story_opened", "screen_viewed"]), *user_filter)
            .group_by(func.date(TwinViewEvent.created_at))
        )).all()
        for day, count in view_rows:
            day_counts[day]["views"] = int(count or 0)
        action_rows = (await db.execute(
            select(func.date(Event.timestamp), Event.event_type, func.count(func.distinct(Event.user_id)))
            .join(User, User.id == Event.user_id)
            .outerjoin(wealth_sq, wealth_sq.c.user_id == User.id)
            .where(
                Event.timestamp >= start,
                Event.timestamp < end,
                Event.event_type.in_(list(_ACTION_EVENT_KEYS.keys())),
                *user_filter,
            )
            .group_by(func.date(Event.timestamp), Event.event_type)
        )).all()
        totals = Counter()
        for day, event_type, count in action_rows:
            key = _ACTION_EVENT_KEYS.get(str(event_type))
            if not key:
                continue
            day_counts[day][key] += int(count or 0)
            totals[key] += int(count or 0)
        trend = []
        current = start.astimezone(VN_TZ).date()
        last = (end - timedelta(seconds=1)).astimezone(VN_TZ).date()
        while current <= last:
            row = day_counts[current]
            suggested = row.get("suggested", 0)
            completed = row.get("completed", 0)
            returned = row.get("return_after_action", row.get("return_after", 0))
            trend.append({
                "date": current,
                "action_completion_pct": _pct(completed, suggested),
                "return_rate_pct": _pct(returned, completed),
            })
            current += timedelta(days=1)
        triggered_users = set((await db.execute(
            select(TwinRecomputeLog.user_id).join(User, User.id == TwinRecomputeLog.user_id).outerjoin(wealth_sq, wealth_sq.c.user_id == User.id).where(TwinRecomputeLog.created_at >= start, TwinRecomputeLog.created_at < end, *user_filter)
        )).scalars().all())
        viewed_users = set((await db.execute(
            select(TwinViewEvent.user_id).join(User, User.id == TwinViewEvent.user_id).outerjoin(wealth_sq, wealth_sq.c.user_id == User.id).where(TwinViewEvent.created_at >= start, TwinViewEvent.created_at < end, TwinViewEvent.event_type.in_(["story_opened", "screen_viewed"]), *user_filter)
        )).scalars().all())
        completed_users = set((await db.execute(
            select(Event.user_id).join(User, User.id == Event.user_id).outerjoin(wealth_sq, wealth_sq.c.user_id == User.id).where(Event.timestamp >= start, Event.timestamp < end, Event.event_type == "action_suggestion.complete", *user_filter)
        )).scalars().all())
        # "Returned" = users who came back to the twin (view event) AFTER
        # completing an action. Implemented as the set of users who have a
        # TwinViewEvent strictly later than their first
        # ``action_suggestion.complete`` in the window.
        complete_first = (await db.execute(
            select(Event.user_id, func.min(Event.timestamp).label("first_complete"))
            .join(User, User.id == Event.user_id)
            .outerjoin(wealth_sq, wealth_sq.c.user_id == User.id)
            .where(
                Event.timestamp >= start,
                Event.timestamp < end,
                Event.event_type == "action_suggestion.complete",
                *user_filter,
            )
            .group_by(Event.user_id)
        )).all()
        returned_users: set = set()
        for user_id, first_complete in complete_first:
            if first_complete is None:
                continue
            later_view = (await db.execute(
                select(TwinViewEvent.id)
                .where(
                    TwinViewEvent.user_id == user_id,
                    TwinViewEvent.created_at > first_complete,
                    TwinViewEvent.created_at < end,
                    TwinViewEvent.event_type.in_(["story_opened", "screen_viewed"]),
                )
                .limit(1)
            )).first()
            if later_view is not None:
                returned_users.add(user_id)
        loop_closed = len(triggered_users & viewed_users & completed_users & returned_users)
        loop_rate = _pct(loop_closed, len(triggered_users))
        action_completion = _pct(totals["completed"], totals["suggested"])
        alerts = evaluate_loop_alerts(loop_rate, action_completion)
        return {
            "generated_at": _now(),
            "refresh_seconds": CACHE_TTL_SECONDS,
            "trigger_sources": trigger_sources,
            "trend": trend,
            "kpis": {
                "full_loop_close_rate_pct": loop_rate,
                "loop_closed_users": loop_closed,
                "triggered_users": len(triggered_users),
                "action_completion_pct": action_completion,
                "return_after_action_pct": _pct(len(returned_users), max(len(completed_users), 1)),
            },
            "alerts": alerts,
        }

    return await _cached(cache_key, build)


@router.get("/comprehension")
async def comprehension(
    period: str = Query(default="30d", pattern=_RANGE_RE),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    cohort_week: date | None = Query(default=None),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    tenant_id = _admin_tenant_id(admin)
    start, end, label = _parse_window(period, start_date, end_date)
    cache_key = f"admin:tenant:{tenant_id}:twin:comprehension:{label}:{cohort_week}"

    async def build() -> dict:
        filters = [User.deleted_at.is_(None), User.tenant_id == tenant_id]
        if cohort_week:
            cohort_start = datetime.combine(cohort_week, time.min, tzinfo=VN_TZ).astimezone(timezone.utc)
            filters.append(User.created_at >= cohort_start)
            filters.append(User.created_at < cohort_start + timedelta(days=7))
        reaction_rows = (await db.execute(
            select(Event.event_type, func.count(Event.id))
            .join(User, User.id == Event.user_id)
            .where(Event.timestamp >= start, Event.timestamp < end, Event.event_type.in_(["twin_reaction_positive", "twin_reaction_neutral", "twin_reaction_confused"]), *filters)
            .group_by(Event.event_type)
        )).all()
        reaction_labels = {
            "twin_reaction_positive": "😍 Hiểu / thích",
            "twin_reaction_neutral": "🙂 Bình thường",
            "twin_reaction_confused": "🤔 Chưa hiểu",
        }
        reactions = [{"label": reaction_labels.get(name, name), "count": int(count or 0)} for name, count in reaction_rows]
        events = (await db.execute(
            select(TwinViewEvent.user_id, TwinViewEvent.event_type, TwinViewEvent.screen_id, TwinViewEvent.metadata_, TwinViewEvent.created_at)
            .join(User, User.id == TwinViewEvent.user_id)
            .where(TwinViewEvent.created_at >= start, TwinViewEvent.created_at < end, *filters)
            .order_by(TwinViewEvent.user_id, TwinViewEvent.created_at)
        )).all()
        sessions: dict[uuid.UUID, list[datetime]] = defaultdict(list)
        why_taps = 0
        views = set()
        for user_id, event_type, screen_id, metadata, created_at in events:
            if event_type in {"story_opened", "screen_viewed"}:
                views.add(user_id)
                sessions[user_id].append(_to_utc(created_at))
            if event_type == "screen_viewed" and screen_id in {"why", "causality"}:
                why_taps += 1
            if event_type == "chart_opened" and screen_id == "why":
                why_taps += 1
            if metadata and metadata.get("duration_ms"):
                sessions[user_id].append(_to_utc(created_at) + timedelta(milliseconds=float(metadata["duration_ms"])))
        durations = []
        for times in sessions.values():
            if len(times) >= 2:
                durations.append(max(0, (_to_utc(max(times)) - _to_utc(min(times))).total_seconds()))
        durations.sort()
        median = durations[len(durations) // 2] if durations else 0
        followups = int((await db.execute(
            select(func.count(Event.id)).join(User, User.id == Event.user_id).where(Event.timestamp >= start, Event.timestamp < end, Event.event_type.in_(["twin_followup_question", "intent_followup_tapped"]), *filters)
        )).scalar() or 0)
        return {
            "generated_at": _now(),
            "refresh_seconds": CACHE_TTL_SECONDS,
            "reactions": reactions,
            "time_on_twin": [{"date": start.date(), "median_seconds": round(median, 1)}],
            "kpis": {
                "why_tap_rate_pct": _pct(why_taps, len(views)),
                "followup_question_rate_pct": _pct(followups, len(views)),
                "views": len(views),
            },
        }

    return await _cached(cache_key, build)


@router.get("/delta-distribution")
async def delta_distribution(
    period: str = Query(default="30d", pattern=_RANGE_RE),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    segment: str | None = Query(default=None, pattern="^(starter|young_pro|mass_affluent|hnw)?$"),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    tenant_id = _admin_tenant_id(admin)
    start, end, label = _parse_window(period, start_date, end_date)
    cache_key = f"admin:tenant:{tenant_id}:twin:delta:{label}:{segment}"

    async def build() -> dict:
        wealth_sq = _wealth_subquery()
        filters = _user_filters(tenant_id, None, segment, wealth_sq)
        threshold_rows = (await db.execute(select(TwinDeltaThresholdConfig.wealth_segment, TwinDeltaThresholdConfig.positive_threshold_pct, TwinDeltaThresholdConfig.negative_threshold_pct))).all()
        thresholds = {row.wealth_segment: {"positive_pct": _safe_float(row.positive_threshold_pct), "negative_pct": _safe_float(row.negative_threshold_pct)} for row in threshold_rows}
        segment_expr = _segment_case(func.coalesce(wealth_sq.c.net_worth, 0))
        recompute_rows = (await db.execute(
            select(segment_expr.label("segment"), TwinRecomputeLog.delta_pct, func.count(TwinRecomputeLog.id))
            .join(User, User.id == TwinRecomputeLog.user_id)
            .outerjoin(wealth_sq, wealth_sq.c.user_id == User.id)
            .where(TwinRecomputeLog.created_at >= start, TwinRecomputeLog.created_at < end, *filters)
            .group_by(segment_expr, TwinRecomputeLog.delta_pct)
        )).all()
        buckets: dict[str, Counter] = defaultdict(Counter)
        positive = 0
        total = 0
        for seg, delta_pct, count in recompute_rows:
            delta = _safe_float(delta_pct)
            bucket = "<-5%" if delta < -5 else "-5..-1%" if delta < -1 else "-1..1%" if delta <= 1 else "1..5%" if delta <= 5 else ">5%"
            buckets[seg][bucket] += int(count or 0)
            total += int(count or 0)
            if delta > 0:
                positive += int(count or 0)
        histogram = [{"segment": seg, "bucket": bucket, "count": count, "thresholds": thresholds.get(seg, {})} for seg, counts in buckets.items() for bucket, count in counts.items()]
        projection_rows = (await db.execute(
            select(func.date(TwinProjection.computed_at), func.avg(TwinProjection.base_net_worth), func.count(TwinProjection.id))
            .join(User, User.id == TwinProjection.user_id)
            .outerjoin(wealth_sq, wealth_sq.c.user_id == User.id)
            .where(TwinProjection.computed_at >= start, TwinProjection.computed_at < end, TwinProjection.scenario == "current", *filters)
            .group_by(func.date(TwinProjection.computed_at))
            .order_by(func.date(TwinProjection.computed_at))
        )).all()
        p50_distribution = [{"date": day, "p50_vnd": round(_safe_float(avg), 2), "count": int(count or 0)} for day, avg, count in projection_rows]
        calibration_total = int((await db.execute(
            select(func.count(TwinCalibrationSnapshot.id))
            .join(User, User.id == TwinCalibrationSnapshot.user_id)
            .where(
                TwinCalibrationSnapshot.predicted_at >= start - timedelta(days=90),
                TwinCalibrationSnapshot.predicted_at < end,
                TwinCalibrationSnapshot.actual_vnd.is_not(None),
                User.tenant_id == tenant_id,
                User.deleted_at.is_(None),
            )
        )).scalar() or 0)
        calibration_rows = (await db.execute(
            select(TwinCalibrationSnapshot.p50_vnd, TwinCalibrationSnapshot.actual_vnd, TwinCalibrationSnapshot.within_band)
            .join(User, User.id == TwinCalibrationSnapshot.user_id)
            .where(TwinCalibrationSnapshot.predicted_at >= start - timedelta(days=90), TwinCalibrationSnapshot.predicted_at < end, TwinCalibrationSnapshot.actual_vnd.is_not(None), User.tenant_id == tenant_id, User.deleted_at.is_(None))
            .order_by(desc(TwinCalibrationSnapshot.predicted_at))
            .limit(CALIBRATION_ROW_CAP)
        )).all()
        calibration = [{"predicted_vnd": _safe_float(predicted), "actual_vnd": _safe_float(actual), "within_band": bool(within)} for predicted, actual, within in calibration_rows]
        alerts = evaluate_delta_bias_alert((positive / total) if total else 0)
        return {
            "generated_at": _now(),
            "refresh_seconds": CACHE_TTL_SECONDS,
            "histogram": histogram,
            "p50_distribution": p50_distribution,
            "calibration": calibration,
            "calibration_meta": {
                "rows_total": calibration_total,
                "rows_returned": len(calibration),
                "truncated": calibration_total > len(calibration),
                "cap": CALIBRATION_ROW_CAP,
            },
            "alerts": alerts,
        }

    return await _cached(cache_key, build)


@router.get("/delta-distribution.csv")
async def delta_distribution_csv(
    period: str = Query(default="30d", pattern=_RANGE_RE),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> Response:
    tenant_id = _admin_tenant_id(admin)
    start, end, _ = _parse_window(period, None, None)
    total = int((await db.execute(
        select(func.count(TwinRecomputeLog.id))
        .join(User, User.id == TwinRecomputeLog.user_id)
        .where(User.tenant_id == tenant_id, User.deleted_at.is_(None), TwinRecomputeLog.created_at >= start, TwinRecomputeLog.created_at < end)
    )).scalar() or 0)
    rows = (await db.execute(
        select(TwinRecomputeLog.created_at, TwinRecomputeLog.user_id, TwinRecomputeLog.delta_pct, TwinRecomputeLog.delta_absolute_vnd, TwinRecomputeLog.event_type)
        .join(User, User.id == TwinRecomputeLog.user_id)
        .where(User.tenant_id == tenant_id, User.deleted_at.is_(None), TwinRecomputeLog.created_at >= start, TwinRecomputeLog.created_at < end)
        .order_by(desc(TwinRecomputeLog.created_at))
        .limit(CSV_ROW_CAP)
    )).all()
    lines = ["created_at,anon_user_id,delta_pct,delta_absolute_vnd,event_type"]
    for created_at, user_id, delta_pct, delta_abs, event_type in rows:
        lines.append(f"{created_at.isoformat()},{_anonymize_user_id(user_id)},{_safe_float(delta_pct)},{_safe_float(delta_abs)},{event_type}")
    truncated = total > len(rows)
    headers = {
        "Content-Disposition": "attachment; filename=twin-delta-distribution.csv",
        "X-Rows-Returned": str(len(rows)),
        "X-Rows-Total": str(total),
        "X-Truncated": "true" if truncated else "false",
    }
    return Response("\n".join(lines) + "\n", media_type="text/csv", headers=headers)


@router.post("/cache/invalidate")
async def invalidate_twin_cache(
    sections: list[str] | None = Query(default=None),
    request: Request = None,  # type: ignore[assignment]
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Force-invalidate Twin admin cache for the caller's tenant.

    Operator-driven freshness: the 15-minute TTL is a soft ceiling — when
    the operator needs current numbers (e.g. immediately after a fix),
    they hit this endpoint and the next read paints fresh data. Scope is
    pinned to ``admin.tenant_id`` so an operator cannot ever evict
    another tenant's cache.
    """
    tenant_id = _admin_tenant_id(admin)
    targets = [s for s in (sections or list(TWIN_SECTIONS)) if s in TWIN_SECTIONS]
    if not targets:
        targets = list(TWIN_SECTIONS)
    removed = 0
    for section in targets:
        pattern = f"admin:tenant:{tenant_id}:twin:{section}:*"
        removed += await cache_invalidate_pattern(pattern)
    await log_action(
        db,
        admin.id,
        "twin_cache_invalidate",
        target_type="twin_metrics_cache",
        target_id=str(tenant_id),
        payload={"sections": targets, "keys_removed": removed},
        request=request,
        commit=True,
    )
    return {"tenant_id": tenant_id, "sections": targets, "keys_removed": removed}
