import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import NamedTuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.models.expense import Expense
from backend.wealth.models.asset import Asset
from backend.schemas.expense import ExpenseCreate, ExpenseUpdate

logger = logging.getLogger(__name__)


TRANSACTION_TYPE_EXPENSE = "expense"
TRANSACTION_TYPE_MONEY_IN = "money_in"
SOURCE_TYPES = {"cash", "bank_account", "e_wallet"}
EWALLET_PROVIDERS = {"momo", "vnpay", "zalopay", "viettelpay"}
SOURCE_TYPE_SUBTYPE_ALIASES = {
    "cash": ("cash",),
    # The source picker uses the product-level label "Tài khoản" while
    # the asset wizard stores bank accounts with more specific subtypes.
    # Keep the legacy ``bank_account`` subtype too for older auto-created rows.
    "bank_account": ("bank_checking", "bank_account"),
}


class SourceResolution(NamedTuple):
    source_asset_id: uuid.UUID | None
    warning: dict | None
    source_type: str | None
    e_wallet_provider: str | None


def _transaction_direction(transaction_type: str | None) -> int:
    return 1 if transaction_type == TRANSACTION_TYPE_MONEY_IN else -1


def _source_asset_delta(expense: Expense) -> Decimal:
    return Decimal(str(expense.amount or 0)) * _transaction_direction(
        expense.transaction_type
    )


async def _adjust_source_asset(
    db: AsyncSession, expense: Expense, multiplier: int = 1
) -> None:
    if not expense.source_asset_id:
        return
    stmt = (
        select(Asset)
        .where(
            Asset.id == expense.source_asset_id,
            Asset.user_id == expense.user_id,
        )
        .with_for_update()
    )
    asset = (await db.execute(stmt)).scalar_one_or_none()
    if asset is None:
        return
    asset.current_value = Decimal(asset.current_value or 0) + (
        _source_asset_delta(expense) * multiplier
    )
    asset.last_valued_at = datetime.utcnow()


def _subtypes_for_source_type(
    source_type: str, e_wallet_provider: str | None = None
) -> tuple[str, ...]:
    if source_type == "e_wallet":
        if e_wallet_provider not in EWALLET_PROVIDERS:
            raise ValueError("e_wallet_provider is not supported")
        # New source rows use provider-specific subtypes (``momo``), while
        # assets added via the cash wizard historically used generic
        # ``e_wallet`` plus a user-entered name ("MoMo 2tr"). Match both.
        return (e_wallet_provider, "e_wallet")
    if source_type not in SOURCE_TYPE_SUBTYPE_ALIASES:
        raise ValueError("source_type is not supported")
    return SOURCE_TYPE_SUBTYPE_ALIASES[source_type]


def _choose_best_source_asset(
    assets: list[Asset], *, amount: Decimal | None = None
) -> Asset | None:
    if not assets:
        return None

    def sort_key(asset: Asset) -> tuple[int, int, Decimal, float]:
        balance = Decimal(asset.current_value or 0)
        covers_amount = amount is not None and balance >= amount
        is_user_confirmed = bool(asset.is_confirmed) and not bool(
            asset.is_placeholder_asset
        )
        created_at = asset.created_at or datetime.min
        return (
            1 if covers_amount else 0,
            1 if is_user_confirmed else 0,
            balance,
            # Keep a stable tie-breaker without letting an older empty
            # auto-created row beat a funded user-entered cash asset.
            -float(created_at.toordinal()),
        )

    return max(assets, key=sort_key)


async def get_or_create_source_asset(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    source_type: str,
    e_wallet_provider: str | None = None,
    amount: Decimal | float | int | str | None = None,
) -> Asset:
    """Resolve a user's cash-like source asset, creating a zero-balance one if needed.

    When multiple matching assets exist, prefer a funded, confirmed asset that
    can cover the transaction. This avoids false low-balance warnings caused by
    old auto-created zero-balance source rows.
    """
    if source_type not in SOURCE_TYPES:
        raise ValueError("source_type is not supported")
    if source_type != "e_wallet":
        e_wallet_provider = None
    subtypes = _subtypes_for_source_type(source_type, e_wallet_provider)
    amount_decimal = Decimal(str(amount)) if amount is not None else None

    stmt = (
        select(Asset)
        .where(
            Asset.user_id == user_id,
            Asset.asset_type == "cash",
            Asset.subtype.in_(subtypes),
            Asset.is_active.is_(True),
        )
        .order_by(Asset.created_at.asc())
    )
    result = await db.execute(stmt)
    assets = list(result.scalars().all())
    asset = _choose_best_source_asset(assets, amount=amount_decimal)
    if asset is not None:
        return asset

    subtype = e_wallet_provider if source_type == "e_wallet" else source_type
    names = {
        "cash": "Tiền mặt",
        "bank_account": "Tài khoản ngân hàng",
        "momo": "Ví Momo",
        "vnpay": "Ví VNPay",
        "zalopay": "Ví ZaloPay",
        "viettelpay": "Ví ViettelPay",
    }
    asset = Asset(
        user_id=user_id,
        asset_type="cash",
        subtype=subtype,
        name=names.get(subtype, "Nguồn tiền"),
        description="Tự tạo từ luồng ghi nhận giao dịch",
        initial_value=Decimal("0"),
        current_value=Decimal("0"),
        acquired_at=datetime.utcnow().date(),
        extra={"source_type": source_type, "e_wallet_provider": e_wallet_provider},
    )
    db.add(asset)
    await db.flush()
    await db.refresh(asset)
    return asset


def _asset_source_metadata(asset: Asset) -> tuple[str | None, str | None]:
    extra = asset.extra or {}
    source_type = extra.get("source_type")
    provider = extra.get("e_wallet_provider")
    if not source_type:
        if asset.subtype in EWALLET_PROVIDERS:
            source_type = "e_wallet"
            provider = asset.subtype
        elif asset.subtype in SOURCE_TYPES:
            source_type = asset.subtype
    if source_type != "e_wallet":
        provider = None
    return source_type, provider


def _source_warning(asset: Asset, data: ExpenseCreate) -> dict | None:
    if data.transaction_type != TRANSACTION_TYPE_EXPENSE:
        return None
    if Decimal(asset.current_value or 0) >= Decimal(str(data.amount)):
        return None
    return {
        "insufficient_balance": True,
        "balance": float(asset.current_value or 0),
    }


async def resolve_source_asset_for_payload(
    db: AsyncSession, user_id: uuid.UUID, data: ExpenseCreate
) -> SourceResolution:
    if data.source_asset_id:
        asset = await db.get(Asset, data.source_asset_id)
        if asset is None or asset.user_id != user_id or not asset.is_active:
            raise ValueError("source_asset_id không hợp lệ")
        inferred_type, inferred_provider = _asset_source_metadata(asset)
        source_type = data.source_type or inferred_type
        provider = data.e_wallet_provider
        if source_type == "e_wallet":
            provider = provider or inferred_provider
            if provider not in EWALLET_PROVIDERS:
                raise ValueError("e_wallet_provider is not supported")
        else:
            provider = None
        return SourceResolution(
            asset.id,
            _source_warning(asset, data),
            source_type,
            provider,
        )
    if not data.source_type:
        return SourceResolution(None, None, None, None)
    asset = await get_or_create_source_asset(
        db,
        user_id,
        source_type=data.source_type,
        e_wallet_provider=data.e_wallet_provider,
        amount=(
            data.amount if data.transaction_type == TRANSACTION_TYPE_EXPENSE else None
        ),
    )
    provider = data.e_wallet_provider if data.source_type == "e_wallet" else None
    return SourceResolution(
        asset.id,
        _source_warning(asset, data),
        data.source_type,
        provider,
    )


async def create_expense(
    db: AsyncSession, user_id: uuid.UUID, data: ExpenseCreate
) -> Expense:
    # Auto-categorize only outflows. Inflows are not spending categories,
    # and letting the expense classifier see salary/bonus text can leak
    # money-in rows into report buckets if a caller forgets to set category.
    category = data.category
    if (
        data.transaction_type == TRANSACTION_TYPE_MONEY_IN
        and category == "needs_review"
    ):
        category = "income"
    if (
        data.transaction_type == TRANSACTION_TYPE_EXPENSE
        and category == "needs_review"
        and (data.merchant or data.note)
    ):
        from backend.services.llm_service import categorize_expense

        category = await categorize_expense(
            merchant=data.merchant,
            description=data.note,
            amount=data.amount,
            db=db,
        )

    month_key = data.expense_date.strftime("%Y-%m")
    source_resolution = await resolve_source_asset_for_payload(db, user_id, data)
    raw_data = dict(data.raw_data or {})
    if source_resolution.warning:
        raw_data["source_warning"] = source_resolution.warning
    expense = Expense(
        user_id=user_id,
        amount=data.amount,
        transaction_type=data.transaction_type,
        currency=data.currency,
        merchant=data.merchant,
        category=category,
        source=data.source,
        source_asset_id=source_resolution.source_asset_id,
        source_type=source_resolution.source_type,
        e_wallet_provider=source_resolution.e_wallet_provider,
        expense_date=data.expense_date,
        month_key=month_key,
        note=data.note,
        raw_data=raw_data or None,
        needs_review=data.needs_review,
        gmail_message_id=data.gmail_message_id,
    )
    db.add(expense)
    await db.flush()
    await _adjust_source_asset(db, expense, multiplier=1)
    await db.refresh(expense)

    analytics.track(
        analytics.EventType.TRANSACTION_CREATED,
        user_id=user_id,
        properties={
            "source": data.source,
            "transaction_type": data.transaction_type,
            "source_type": data.source_type,
            "category": category,
            "needs_review": bool(data.needs_review),
            "auto_categorized": data.category == "needs_review",
        },
    )

    # Phase 4.3 Story 3.1 — fire-and-forget Twin recompute trigger. Only
    # outflows matter for Twin (money_in is captured via income.added).
    # Publish-time floor is 100k (Starter); the worker re-checks segment.
    if data.transaction_type == TRANSACTION_TYPE_EXPENSE:
        try:
            from decimal import Decimal as _D

            from infra.event_bus.twin_events import TwinEvent, publish

            await publish(
                TwinEvent(
                    event_type="expense.added",
                    user_id=user_id,
                    amount_vnd=_D(str(data.amount)),
                    metadata={"category": category, "source": data.source},
                )
            )
        except Exception:
            logger.warning("twin event publish failed for expense", exc_info=True)

    # Phase 2 — streak tracking. Wrapped in a SAVEPOINT so a DB error
    # inside the streak path (missing table, transient failure) doesn't
    # leave the outer transaction in an errored state — if the savepoint
    # rolls back, the caller's subsequent commit still lands the expense.
    # This preserves the intended "streak blip must never roll back a
    # receipt" semantics that a bare try/except does NOT provide with
    # SQLAlchemy's async transaction state model.
    from backend.services import streak_service

    try:
        async with db.begin_nested():
            result = await streak_service.record_activity(db, user_id)
    except Exception:
        logger.warning("streak record_activity failed", exc_info=True)
    else:
        if result.is_milestone:
            analytics.track(
                analytics.EventType.STREAK_MILESTONE_HIT,
                user_id=user_id,
                properties={"streak": result.current},
            )

    return expense


async def get_expense(
    db: AsyncSession, user_id: uuid.UUID, expense_id: uuid.UUID
) -> Expense | None:
    stmt = select(Expense).where(
        Expense.id == expense_id,
        Expense.user_id == user_id,
        Expense.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_expenses(
    db: AsyncSession,
    user_id: uuid.UUID,
    month: str | None = None,
    category: str | None = None,
    transaction_type: str | None = TRANSACTION_TYPE_EXPENSE,
    limit: int = 50,
    offset: int = 0,
) -> list[Expense]:
    stmt = select(Expense).where(
        Expense.user_id == user_id,
        Expense.deleted_at.is_(None),
    )
    if month:
        stmt = stmt.where(Expense.month_key == month)
    if category:
        stmt = stmt.where(Expense.category == category)
    if transaction_type:
        stmt = stmt.where(Expense.transaction_type == transaction_type)
    stmt = stmt.order_by(Expense.expense_date.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_expense(
    db: AsyncSession,
    user_id: uuid.UUID,
    expense_id: uuid.UUID,
    data: ExpenseUpdate,
) -> Expense | None:
    expense = await get_expense(db, user_id, expense_id)
    if not expense:
        return None
    await _adjust_source_asset(db, expense, multiplier=-1)
    update_data = data.model_dump(exclude_unset=True)
    if (
        "source_asset_id" in update_data
        or "source_type" in update_data
        or "e_wallet_provider" in update_data
    ):
        clear_source = (
            "source_asset_id" in update_data and update_data["source_asset_id"] is None
        ) or ("source_type" in update_data and update_data["source_type"] is None)
        if clear_source:
            update_data["source_asset_id"] = None
            update_data["source_type"] = None
            update_data["e_wallet_provider"] = None
            raw_data = dict(update_data.get("raw_data", expense.raw_data) or {})
            raw_data.pop("source_warning", None)
            update_data["raw_data"] = raw_data or None
        else:
            merged = ExpenseCreate(
                amount=float(update_data.get("amount", expense.amount)),
                transaction_type=update_data.get(
                    "transaction_type", expense.transaction_type
                ),
                currency=update_data.get("currency", expense.currency),
                merchant=update_data.get("merchant", expense.merchant),
                category=update_data.get("category", expense.category),
                source=expense.source,
                source_asset_id=update_data.get(
                    "source_asset_id", expense.source_asset_id
                ),
                source_type=update_data.get("source_type", expense.source_type),
                e_wallet_provider=update_data.get(
                    "e_wallet_provider", expense.e_wallet_provider
                ),
                expense_date=update_data.get("expense_date", expense.expense_date),
                note=update_data.get("note", expense.note),
                raw_data=update_data.get("raw_data", expense.raw_data),
                needs_review=update_data.get("needs_review", expense.needs_review),
            )
            source_resolution = await resolve_source_asset_for_payload(
                db, user_id, merged
            )
            update_data["source_asset_id"] = source_resolution.source_asset_id
            update_data["source_type"] = source_resolution.source_type
            update_data["e_wallet_provider"] = source_resolution.e_wallet_provider
            raw_data = dict(update_data.get("raw_data", expense.raw_data) or {})
            if source_resolution.warning:
                raw_data["source_warning"] = source_resolution.warning
            else:
                raw_data.pop("source_warning", None)
            update_data["raw_data"] = raw_data or None
    for field, value in update_data.items():
        setattr(expense, field, value)
    if "expense_date" in update_data and expense.expense_date is not None:
        expense.month_key = expense.expense_date.strftime("%Y-%m")
    await db.flush()
    await _adjust_source_asset(db, expense, multiplier=1)
    await db.refresh(expense)
    return expense


async def delete_expense(
    db: AsyncSession, user_id: uuid.UUID, expense_id: uuid.UUID
) -> bool:
    expense = await get_expense(db, user_id, expense_id)
    if not expense:
        return False
    expense.deleted_at = datetime.utcnow()
    await _adjust_source_asset(db, expense, multiplier=-1)
    await db.flush()
    analytics.track(
        analytics.EventType.TRANSACTION_DELETED,
        user_id=user_id,
        properties={"via": "api", "source": expense.source},
    )
    return True


async def get_expense_summary(db: AsyncSession, user_id: uuid.UUID, month: str) -> dict:
    stmt = (
        select(
            Expense.category,
            func.sum(Expense.amount).label("total"),
            func.count().label("count"),
        )
        .where(
            Expense.user_id == user_id,
            Expense.month_key == month,
            Expense.deleted_at.is_(None),
            Expense.transaction_type == TRANSACTION_TYPE_EXPENSE,
        )
        .group_by(Expense.category)
    )
    result = await db.execute(stmt)
    rows = result.all()

    by_category = {row.category: float(row.total) for row in rows}
    total = sum(by_category.values())
    count = sum(row.count for row in rows)

    return {
        "month_key": month,
        "total": total,
        "by_category": by_category,
        "count": count,
    }
