from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Date, and_, false, true, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.admin.deps import get_current_admin
from backend.database import get_db
from backend.models.admin_user import AdminUser
from backend.models.agent_audit_log import AgentAuditLog
from backend.models.cost_budget import LLMCostLog
from backend.models.decision_query_log import DecisionQueryLog
from backend.models.event import Event
from backend.models.feature_event import FeatureEvent
from backend.models.portfolio_asset import PortfolioAsset
from backend.models.user import User
from backend.schemas.admin import (
    CohortRetentionResponse,
    DauChartResponse,
    DecisionAdoptionResponse,
    FeatureClicksResponse,
    IntentBreakdownResponse,
    OverviewStatsResponse,
    UserGrowthResponse,
    UserTiersResponse,
)
from backend.services.admin_cache import cache_get, cache_set
from backend.services.feature_events import feature_name
from backend.services.intent_metrics import EVENT_INTENT_CLASSIFIED, EVENT_INTENT_CLARIFY_SENT

router = APIRouter(tags=["admin-analytics"])

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
PERIOD_DAYS = {"7d": 7, "14d": 14, "30d": 30, "90d": 90}
VND_PER_USD = Decimal("25000")
TIER_LABELS = {
    "starter": "Starter",
    "young_pro": "Young Pro",
    "mass_affluent": "Mass Affluent",
    "hnw": "HNW",
}
INTENT_LABELS = {
    "rule": "Rule-based (zero cost)",
    "llm_classifier": "LLM classified",
    "clarification": "Cần clarify",
}
# Onboarding cohort of the decision-adoption chart. ``unattributed`` buckets the
# NULL-cohort rows (pre-4.6 logs + users who never chose an onboarding goal).
# Ordered so the new first-life segment reads first, legacy second.
COHORT_UNATTRIBUTED = "unattributed"
DECISION_COHORT_LABELS = {
    "reset": "Segment mới (reset)",
    "legacy": "Cohort cũ (legacy)",
    COHORT_UNATTRIBUTED: "Chưa gắn cohort",
}
DEFAULT_TENANT_ID = 1


def _admin_tenant_id(admin: AdminUser) -> int:
    return admin.tenant_id or DEFAULT_TENANT_ID


def _tenant_filter(model, tenant_id: int):
    """Return a SQLAlchemy condition that prevents cross-tenant reads.

    Tables that expose ``tenant_id`` are filtered explicitly. The fallback
    keeps default-tenant legacy rows readable but returns ``false()`` for
    non-default tenants to avoid accidental cross-tenant leakage.
    """
    tenant_column = getattr(model, "tenant_id", None)
    if tenant_column is not None:
        return tenant_column == tenant_id
    return true() if tenant_id == DEFAULT_TENANT_ID else false()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _start_of_vn_day(days_ago: int = 0) -> datetime:
    local_day = datetime.now(VN_TZ).date() - timedelta(days=days_ago)
    return datetime.combine(local_day, time.min, tzinfo=VN_TZ).astimezone(timezone.utc)


def _date_range(days: int) -> list[date]:
    today = datetime.now(VN_TZ).date()
    return [today - timedelta(days=offset) for offset in range(days - 1, -1, -1)]


def _pct(current: float, previous: float) -> float:
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return round(((current - previous) / previous) * 100, 1)


def _wealth_expr():
    asset_value = func.coalesce(PortfolioAsset.quantity, 0) * func.coalesce(PortfolioAsset.current_price, 0)
    return func.coalesce(func.sum(asset_value), 0)


def _tier_for_value(value: float) -> str:
    if value < 100_000_000:
        return "starter"
    if value < 500_000_000:
        return "young_pro"
    if value < 5_000_000_000:
        return "mass_affluent"
    return "hnw"


@router.get("/stats/overview", response_model=OverviewStatsResponse)
async def overview_stats(
    period: str = Query(default="30d", pattern="^(7d|14d|30d|90d)$"),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    tenant_id = _admin_tenant_id(admin)
    cache_key = f"admin:tenant:{tenant_id}:stats:overview:{period}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    days = PERIOD_DAYS[period]
    now = _now()
    start = now - timedelta(days=days)
    previous_start = now - timedelta(days=days * 2)
    today_start = _start_of_vn_day()
    yesterday_start = _start_of_vn_day(1)
    week_start = now - timedelta(days=7)
    month_start = now - timedelta(days=30)

    total_users = int((await db.execute(select(func.count()).select_from(User).where(User.deleted_at.is_(None), _tenant_filter(User, tenant_id)))).scalar() or 0)
    users_before = int((await db.execute(select(func.count()).select_from(User).where(User.deleted_at.is_(None), _tenant_filter(User, tenant_id), User.created_at < start))).scalar() or 0)
    new_users = int((await db.execute(select(func.count()).select_from(User).where(User.deleted_at.is_(None), _tenant_filter(User, tenant_id), User.created_at >= start))).scalar() or 0)
    previous_new_users = int((await db.execute(select(func.count()).select_from(User).where(User.deleted_at.is_(None), _tenant_filter(User, tenant_id), User.created_at >= previous_start, User.created_at < start))).scalar() or 0)

    dau = int((await db.execute(select(func.count(func.distinct(Event.user_id))).where(Event.user_id.is_not(None), _tenant_filter(Event, tenant_id), Event.timestamp >= today_start))).scalar() or 0)
    previous_dau = int((await db.execute(select(func.count(func.distinct(Event.user_id))).where(Event.user_id.is_not(None), _tenant_filter(Event, tenant_id), Event.timestamp >= yesterday_start, Event.timestamp < today_start))).scalar() or 0)
    wau = int((await db.execute(select(func.count(func.distinct(Event.user_id))).where(Event.user_id.is_not(None), _tenant_filter(Event, tenant_id), Event.timestamp >= week_start))).scalar() or 0)
    mau = int((await db.execute(select(func.count(func.distinct(Event.user_id))).where(Event.user_id.is_not(None), _tenant_filter(Event, tenant_id), Event.timestamp >= month_start))).scalar() or 0)
    activated = int((await db.execute(select(func.count()).select_from(User).where(User.deleted_at.is_(None), _tenant_filter(User, tenant_id), or_(User.onboarding_completed_at.is_not(None), User.onboarding_skipped.is_(True))))).scalar() or 0)

    cost_vnd = Decimal((await db.execute(select(func.coalesce(func.sum(LLMCostLog.cost_vnd), 0)).where(_tenant_filter(LLMCostLog, tenant_id), LLMCostLog.created_at >= start))).scalar() or 0)
    previous_cost_vnd = Decimal((await db.execute(select(func.coalesce(func.sum(LLMCostLog.cost_vnd), 0)).where(_tenant_filter(LLMCostLog, tenant_id), LLMCostLog.created_at >= previous_start, LLMCostLog.created_at < start))).scalar() or 0)
    agent_cost_usd = Decimal((await db.execute(select(func.coalesce(func.sum(AgentAuditLog.cost_usd), 0)).where(_tenant_filter(AgentAuditLog, tenant_id), AgentAuditLog.query_timestamp >= start))).scalar() or 0)
    previous_agent_cost_usd = Decimal((await db.execute(select(func.coalesce(func.sum(AgentAuditLog.cost_usd), 0)).where(_tenant_filter(AgentAuditLog, tenant_id), AgentAuditLog.query_timestamp >= previous_start, AgentAuditLog.query_timestamp < start))).scalar() or 0)
    total_cost_usd = float((cost_vnd / VND_PER_USD) + agent_cost_usd)
    previous_cost_usd = float((previous_cost_vnd / VND_PER_USD) + previous_agent_cost_usd)

    users_with_assets = int((await db.execute(select(func.count(func.distinct(PortfolioAsset.user_id))).where(PortfolioAsset.deleted_at.is_(None), _tenant_filter(PortfolioAsset, tenant_id)))).scalar() or 0)
    sent = int((await db.execute(select(func.count()).where(_tenant_filter(Event, tenant_id), Event.event_type == "morning_briefing_sent", Event.timestamp >= start))).scalar() or 0)
    opened = int((await db.execute(select(func.count()).where(_tenant_filter(Event, tenant_id), Event.event_type == "morning_briefing_opened", Event.timestamp >= start))).scalar() or 0)
    failures = int((await db.execute(select(func.count()).select_from(LLMCostLog).where(_tenant_filter(LLMCostLog, tenant_id), LLMCostLog.created_at >= start, LLMCostLog.success.is_(False)))).scalar() or 0)
    total_ops = int((await db.execute(select(func.count()).select_from(LLMCostLog).where(_tenant_filter(LLMCostLog, tenant_id), LLMCostLog.created_at >= start))).scalar() or 0)
    agent_failures = int((await db.execute(select(func.count()).select_from(AgentAuditLog).where(_tenant_filter(AgentAuditLog, tenant_id), AgentAuditLog.query_timestamp >= start, AgentAuditLog.success.is_(False)))).scalar() or 0)
    agent_ops = int((await db.execute(select(func.count()).select_from(AgentAuditLog).where(_tenant_filter(AgentAuditLog, tenant_id), AgentAuditLog.query_timestamp >= start))).scalar() or 0)

    response = {
        "period": period,
        "generated_at": datetime.now(VN_TZ),
        "metrics": {
            "total_users": total_users,
            "total_users_delta_pct": _pct(total_users, users_before),
            "new_users_period": new_users,
            "new_users_delta_pct": _pct(new_users, previous_new_users),
            "dau": dau,
            "dau_delta_pct": _pct(dau, previous_dau),
            "wau": wau,
            "mau": mau,
            "stickiness_pct": round((dau / mau) * 100, 1) if mau else 0.0,
            "activation_rate_pct": round((activated / total_users) * 100, 1) if total_users else 0.0,
            "total_llm_cost_usd": round(total_cost_usd, 4),
            "cost_delta_pct": _pct(total_cost_usd, previous_cost_usd),
            "avg_cost_per_active_user": round(total_cost_usd / mau, 4) if mau else 0.0,
            "asset_coverage_pct": round((users_with_assets / total_users) * 100, 1) if total_users else 0.0,
            "briefing_open_rate_pct": round((opened / sent) * 100, 1) if sent else 0.0,
            "error_rate_pct": round(((failures + agent_failures) / (total_ops + agent_ops)) * 100, 1) if (total_ops + agent_ops) else 0.0,
        },
    }
    await cache_set(cache_key, response, 300)
    return response


@router.get("/charts/user-growth", response_model=UserGrowthResponse)
async def user_growth(
    days: int = Query(default=30, ge=1, le=90),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    tenant_id = _admin_tenant_id(admin)
    key = f"admin:tenant:{tenant_id}:charts:user-growth:{days}"
    cached = await cache_get(key)
    if cached is not None:
        return cached
    dates = _date_range(days)
    start_dt = datetime.combine(dates[0], time.min, tzinfo=VN_TZ).astimezone(timezone.utc)
    before = int((await db.execute(select(func.count()).select_from(User).where(User.deleted_at.is_(None), _tenant_filter(User, tenant_id), User.created_at < start_dt))).scalar() or 0)
    day_col = cast(func.timezone("Asia/Ho_Chi_Minh", User.created_at), Date)
    rows = (await db.execute(select(day_col.label("day"), func.count()).where(User.deleted_at.is_(None), _tenant_filter(User, tenant_id), User.created_at >= start_dt).group_by(day_col))).all()
    new_by_day = {row.day: int(row[1]) for row in rows}
    cumulative = before
    data = []
    for d in dates:
        new_users = new_by_day.get(d, 0)
        cumulative += new_users
        data.append({"date": d, "cumulative": cumulative, "new_users": new_users})
    response = {"data": data}
    await cache_set(key, response, 1800)
    return response


@router.get("/charts/dau", response_model=DauChartResponse)
async def dau_chart(
    days: int = Query(default=14, ge=1, le=90),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    tenant_id = _admin_tenant_id(admin)
    key = f"admin:tenant:{tenant_id}:charts:dau:{days}"
    cached = await cache_get(key)
    if cached is not None:
        return cached
    dates = _date_range(days)
    start_dt = datetime.combine(dates[0], time.min, tzinfo=VN_TZ).astimezone(timezone.utc)
    day_col = cast(func.timezone("Asia/Ho_Chi_Minh", Event.timestamp), Date)
    rows = (await db.execute(select(day_col.label("day"), func.count(func.distinct(Event.user_id))).where(Event.user_id.is_not(None), _tenant_filter(Event, tenant_id), Event.timestamp >= start_dt).group_by(day_col))).all()
    dau_by_day = {row.day: int(row[1]) for row in rows}
    response = {"data": [{"date": d, "dau": dau_by_day.get(d, 0)} for d in dates]}
    await cache_set(key, response, 1800)
    return response


@router.get("/charts/feature-clicks", response_model=FeatureClicksResponse)
async def feature_clicks(
    days: int = Query(default=30, ge=1, le=90),
    limit: int = Query(default=10, ge=1, le=50),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    tenant_id = _admin_tenant_id(admin)
    key = f"admin:tenant:{tenant_id}:charts:feature-clicks:{days}:{limit}"
    cached = await cache_get(key)
    if cached is not None:
        return cached
    since = _now() - timedelta(days=days)
    rows = (await db.execute(select(FeatureEvent.feature_key, func.count().label("clicks")).where(_tenant_filter(FeatureEvent, tenant_id), FeatureEvent.created_at >= since).group_by(FeatureEvent.feature_key).order_by(func.count().desc()).limit(limit))).all()
    response = {"data": [{"feature_key": key, "feature_name": feature_name(key), "clicks": int(clicks)} for key, clicks in rows]}
    await cache_set(key, response, 1800)
    return response


@router.get("/charts/intent-breakdown", response_model=IntentBreakdownResponse)
async def intent_breakdown(
    days: int = Query(default=7, ge=1, le=90),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    tenant_id = _admin_tenant_id(admin)
    key = f"admin:tenant:{tenant_id}:charts:intent-breakdown:{days}"
    cached = await cache_get(key)
    if cached is not None:
        return cached
    since = _now() - timedelta(days=days)
    classifier = Event.properties["classifier"].astext
    rows = (await db.execute(select(classifier.label("resolved_by"), func.count()).where(_tenant_filter(Event, tenant_id), Event.event_type == EVENT_INTENT_CLASSIFIED, Event.timestamp >= since).group_by(classifier))).all()
    counts = Counter({(row.resolved_by or "unknown"): int(row[1]) for row in rows})
    clarification_count = int((await db.execute(select(func.count()).where(_tenant_filter(Event, tenant_id), Event.event_type == EVENT_INTENT_CLARIFY_SENT, Event.timestamp >= since))).scalar() or 0)
    counts["clarification"] += clarification_count
    if "llm" in counts:
        counts["llm_classifier"] += counts.pop("llm")
    total = sum(counts[k] for k in ("rule", "llm_classifier", "clarification"))
    data = []
    for resolved_by in ("rule", "llm_classifier", "clarification"):
        count = counts[resolved_by]
        data.append({"resolved_by": resolved_by, "label": INTENT_LABELS[resolved_by], "count": count, "pct": round((count / total) * 100, 1) if total else 0.0})
    response = {"data": data}
    await cache_set(key, response, 1800)
    return response


@router.get("/charts/user-tiers", response_model=UserTiersResponse)
async def user_tiers(
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    tenant_id = _admin_tenant_id(admin)
    key = f"admin:tenant:{tenant_id}:charts:user-tiers"
    cached = await cache_get(key)
    if cached is not None:
        return cached
    rows = (await db.execute(select(User.id, _wealth_expr().label("wealth")).select_from(User).outerjoin(PortfolioAsset, and_(PortfolioAsset.user_id == User.id, PortfolioAsset.deleted_at.is_(None), _tenant_filter(PortfolioAsset, tenant_id))).where(User.deleted_at.is_(None), _tenant_filter(User, tenant_id)).group_by(User.id))).all()
    counts = Counter(_tier_for_value(float(row.wealth or 0)) for row in rows)
    response = {"data": [{"tier": tier, "label": label, "count": counts[tier]} for tier, label in TIER_LABELS.items()]}
    await cache_set(key, response, 1800)
    return response


@router.get("/charts/cohort-retention", response_model=CohortRetentionResponse)
async def cohort_retention(
    weeks: int = Query(default=8, ge=1, le=26),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    tenant_id = _admin_tenant_id(admin)
    key = f"admin:tenant:{tenant_id}:charts:cohort-retention:{weeks}"
    cached = await cache_get(key)
    if cached is not None:
        return cached
    today = datetime.now(VN_TZ).date()
    current_week = today - timedelta(days=today.weekday())
    first_week = current_week - timedelta(weeks=weeks - 1)

    cohort_expr = cast(func.date_trunc("week", func.timezone("Asia/Ho_Chi_Minh", User.created_at)), Date)
    user_rows = (await db.execute(select(User.id, cohort_expr.label("cohort_week")).where(User.deleted_at.is_(None), _tenant_filter(User, tenant_id), User.created_at >= datetime.combine(first_week, time.min, tzinfo=VN_TZ).astimezone(timezone.utc)))).all()
    cohorts: dict[date, set] = defaultdict(set)
    user_cohort = {}
    for uid, cohort_week in user_rows:
        cohorts[cohort_week].add(uid)
        user_cohort[uid] = cohort_week

    activity_expr = cast(func.date_trunc("week", func.timezone("Asia/Ho_Chi_Minh", Event.timestamp)), Date)
    if user_cohort:
        activity_rows = (
            await db.execute(
                select(Event.user_id, activity_expr.label("active_week"))
                .where(
                    Event.user_id.in_(list(user_cohort.keys())),
                    _tenant_filter(Event, tenant_id),
                    Event.timestamp >= datetime.combine(first_week, time.min, tzinfo=VN_TZ).astimezone(timezone.utc),
                )
                .distinct()
            )
        ).all()
    else:
        activity_rows = []
    retained: dict[tuple[date, int], set] = defaultdict(set)
    for uid, active_week in activity_rows:
        cohort_week = user_cohort.get(uid)
        if cohort_week is None or active_week < cohort_week:
            continue
        offset = int((active_week - cohort_week).days / 7)
        if offset < weeks:
            retained[(cohort_week, offset)].add(uid)

    out = []
    for cohort_week in sorted(cohorts.keys(), reverse=True):
        size = len(cohorts[cohort_week])
        retention = {}
        max_elapsed = int((current_week - cohort_week).days / 7)
        for offset in range(weeks):
            key_name = f"w{offset}"
            if offset > max_elapsed:
                retention[key_name] = None
            elif offset == 0:
                retention[key_name] = 100 if size else 0
            else:
                retention[key_name] = round((len(retained[(cohort_week, offset)]) / size) * 100) if size else 0
        out.append({"cohort_week": cohort_week, "cohort_size": size, "retention": retention})
    response = {"cohorts": out}
    await cache_set(key, response, 86400)
    return response


@router.get("/charts/decision-adoption", response_model=DecisionAdoptionResponse)
async def decision_adoption(
    weeks: int = Query(default=8, ge=1, le=26),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Weekly Decision-Engine adoption, split by onboarding cohort.

    Reads the append-only ``decision_query_logs`` (Phase 4.5) tagged with the
    onboarding cohort in #4.1, and reports per week × cohort: interactions (row
    count), active users (distinct ``user_id``), interactions/user, and the
    average độ nét. Feeds gates G1/G2 — does the new first-life ``reset`` segment
    engage the decision surfaces differently from the ``legacy`` cohort?

    Output is aggregate-only (counts + averages) so no PII ever leaves the
    query; tenant isolation and JWT auth match the other admin charts.
    """
    tenant_id = _admin_tenant_id(admin)
    key = f"admin:tenant:{tenant_id}:charts:decision-adoption:{weeks}"
    cached = await cache_get(key)
    if cached is not None:
        return cached

    today = datetime.now(VN_TZ).date()
    current_week = today - timedelta(days=today.weekday())
    first_week = current_week - timedelta(weeks=weeks - 1)
    start_dt = datetime.combine(first_week, time.min, tzinfo=VN_TZ).astimezone(timezone.utc)
    week_list = [first_week + timedelta(weeks=offset) for offset in range(weeks)]

    week_col = cast(func.date_trunc("week", func.timezone("Asia/Ho_Chi_Minh", DecisionQueryLog.created_at)), Date)
    cohort_col = func.coalesce(DecisionQueryLog.cohort, COHORT_UNATTRIBUTED)
    # Per-user rollup first so độ nét is averaged over *active users* (G2), not
    # over raw interactions — a chatty user must not skew the cohort's độ nét.
    # Join ``users`` and scope by ``users.tenant_id`` like the other user-facing
    # charts: ``decision_query_logs`` has no tenant column, so filtering it alone
    # would leak other tenants' rows.
    per_user = (
        select(
            week_col.label("week"),
            cohort_col.label("cohort"),
            DecisionQueryLog.user_id.label("user_id"),
            func.count().label("user_interactions"),
            func.avg(DecisionQueryLog.clarity_score).label("user_clarity"),
        )
        .join(User, User.id == DecisionQueryLog.user_id)
        .where(
            User.deleted_at.is_(None),
            _tenant_filter(User, tenant_id),
            DecisionQueryLog.created_at >= start_dt,
        )
        .group_by(week_col, cohort_col, DecisionQueryLog.user_id)
        .subquery()
    )
    rows = (
        await db.execute(
            select(
                per_user.c.week.label("week"),
                per_user.c.cohort.label("cohort"),
                func.sum(per_user.c.user_interactions).label("interactions"),
                func.count().label("active_users"),
                func.avg(per_user.c.user_clarity).label("avg_clarity"),
            )
            .group_by(per_user.c.week, per_user.c.cohort)
        )
    ).all()

    # (cohort, week) -> metrics, so we can emit a dense series per cohort.
    by_cohort: dict[str, dict[date, dict]] = defaultdict(dict)
    for row in rows:
        interactions = int(row.interactions)
        active_users = int(row.active_users)
        by_cohort[row.cohort][row.week] = {
            "week": row.week,
            "interactions": interactions,
            "active_users": active_users,
            "interactions_per_user": round(interactions / active_users, 2) if active_users else 0.0,
            "avg_clarity": round(float(row.avg_clarity), 1) if row.avg_clarity is not None else None,
        }

    cohorts = []
    for cohort, label in DECISION_COHORT_LABELS.items():
        weeks_seen = by_cohort.get(cohort)
        if not weeks_seen:
            continue  # skip a cohort with zero interactions in the window
        points = [
            weeks_seen.get(
                week,
                {
                    "week": week,
                    "interactions": 0,
                    "active_users": 0,
                    "interactions_per_user": 0.0,
                    "avg_clarity": None,
                },
            )
            for week in week_list
        ]
        cohorts.append({"cohort": cohort, "label": label, "points": points})

    response = {"weeks": week_list, "cohorts": cohorts}
    await cache_set(key, response, 1800)
    return response
