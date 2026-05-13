"""Phase 4.2 financial-data quality guardrails.

Pure-ish helpers used by onboarding and asset-entry flows to catch typo-sized
amounts, ambiguous currency, demo placeholders, and rapid duplicate assets
before downstream Twin / net-worth computation trusts the data.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.onboarding_session import SEGMENT_STARTER
from backend.wealth.models.asset import Asset

LOW_AMOUNT_REVIEW_VND = Decimal("10000")
HIGH_AMOUNT_REVIEW_VND = Decimal("100000000000")  # 100 tỷ
CURRENCY_REVIEW_VND = Decimal("10000000")  # 10 triệu
DUPLICATE_WINDOW_MINUTES = 10
DUPLICATE_TOLERANCE = Decimal("0.10")

WARNING_LOW_AMOUNT = "low_amount"
WARNING_HIGH_AMOUNT = "high_amount"
WARNING_CURRENCY_AMBIGUOUS = "currency_ambiguous"
WARNING_DUPLICATE = "duplicate_recent"


@dataclass(frozen=True)
class QualityWarning:
    warning_type: str
    message: str


def amount_warning(value_vnd: Decimal, *, segment: str | None = None) -> QualityWarning | None:
    value = Decimal(value_vnd)
    if value < LOW_AMOUNT_REVIEW_VND:
        return QualityWarning(
            WARNING_LOW_AMOUNT,
            "Số này khá nhỏ cho tài sản. Bạn muốn xác nhận lại đơn vị không?",
        )
    if value > HIGH_AMOUNT_REVIEW_VND:
        return QualityWarning(
            WARNING_HIGH_AMOUNT,
            "Số này rất lớn. Bé Tiền muốn xác nhận để tránh nhập nhầm số 0.",
        )
    if value < CURRENCY_REVIEW_VND and segment and segment != SEGMENT_STARTER:
        return QualityWarning(
            WARNING_CURRENCY_AMBIGUOUS,
            "Số này dưới 10 triệu VND. Bạn đang nhập VND hay USD?",
        )
    return None


def estimate_options(value_vnd: Decimal) -> list[tuple[str, Decimal]]:
    value = Decimal(value_vnd)
    options = [value]
    if value < LOW_AMOUNT_REVIEW_VND:
        options.extend([value * Decimal("1000"), value * Decimal("1000000")])
    elif value > HIGH_AMOUNT_REVIEW_VND:
        options.extend([value / Decimal("1000"), value / Decimal("1000000")])
    else:
        options.extend([value * Decimal("25000"), value])  # ambiguous USD/VND fallback
    # Preserve order and uniqueness.
    seen: set[Decimal] = set()
    result: list[tuple[str, Decimal]] = []
    for candidate in options:
        normalized = candidate.quantize(Decimal("1"))
        if normalized > 0 and normalized not in seen:
            seen.add(normalized)
            result.append((f"confirm_{len(result)}", normalized))
        if len(result) == 3:
            break
    return result


async def find_recent_duplicate(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    asset_type: str,
    amount_vnd: Decimal,
) -> Asset | None:
    lower = Decimal(amount_vnd) * (Decimal("1") - DUPLICATE_TOLERANCE)
    upper = Decimal(amount_vnd) * (Decimal("1") + DUPLICATE_TOLERANCE)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=DUPLICATE_WINDOW_MINUTES)
    stmt = (
        select(Asset)
        .where(
            Asset.user_id == user_id,
            Asset.asset_type == asset_type,
            Asset.is_active.is_(True),
            Asset.is_placeholder_asset.is_(False),
            Asset.is_confirmed.is_(True),
            Asset.current_value >= lower,
            Asset.current_value <= upper,
            Asset.created_at >= cutoff,
        )
        .order_by(Asset.created_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def first_warning(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    asset_type: str,
    amount_vnd: Decimal,
    segment: str | None = None,
) -> QualityWarning | None:
    warning = amount_warning(amount_vnd, segment=segment)
    if warning is not None:
        return warning
    duplicate = await find_recent_duplicate(
        db, user_id, asset_type=asset_type, amount_vnd=amount_vnd
    )
    if duplicate is not None:
        return QualityWarning(
            WARNING_DUPLICATE,
            "Bạn vừa thêm một tài sản gần giống trong vài phút trước. Có phải nhập trùng không?",
        )
    return None
