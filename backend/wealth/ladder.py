"""Wealth-level detection — drives ladder-aware UI / messaging.

Four bands from CLAUDE.md § 0:

    Starter            : 0 – 30tr
    Young Professional : 30tr – 200tr
    Mass Affluent      : 200tr – 1 tỷ
    High Net Worth     : 1 tỷ+

Boundaries are inclusive on the lower bound, exclusive on the upper —
so 30tr exactly is Young Professional, not Starter.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user import User


class WealthLevel(str, Enum):
    STARTER = "starter"
    YOUNG_PROFESSIONAL = "young_prof"
    MASS_AFFLUENT = "mass_affluent"
    HIGH_NET_WORTH = "hnw"


# User-facing Vietnamese labels (Issue #155). Theme nông nghiệp/giàu sang —
# "short" form xuất hiện trong tin chúc mừng, "full" form cho UI dài hơn.
LEVEL_LABELS: dict[WealthLevel, dict[str, str]] = {
    WealthLevel.STARTER: {"short": "Trồng lúa", "full": "Bắt đầu tích luỹ"},
    WealthLevel.YOUNG_PROFESSIONAL: {"short": "Kho thóc", "full": "Có chút tiết kiệm"},
    WealthLevel.MASS_AFFLUENT: {"short": "Phú hộ", "full": "Của ăn của để"},
    WealthLevel.HIGH_NET_WORTH: {"short": "Vương giả", "full": "Giàu sang phú quý"},
}


# Order of levels for "higher than" comparisons. STARTER < YOUNG_PROF < ...
LEVEL_ORDER: list[WealthLevel] = [
    WealthLevel.STARTER,
    WealthLevel.YOUNG_PROFESSIONAL,
    WealthLevel.MASS_AFFLUENT,
    WealthLevel.HIGH_NET_WORTH,
]


def format_level(level: WealthLevel, style: str = "short") -> str:
    """Return the Vietnamese label for ``level``.

    ``style="short"`` → "Kho thóc" (themed, used in messages).
    ``style="full"`` → "Có chút tiết kiệm" (descriptive, used in dashboards).
    """
    return LEVEL_LABELS[level][style]


_BAND_30M = Decimal("30_000_000")
_BAND_200M = Decimal("200_000_000")
_BAND_1B = Decimal("1_000_000_000")


def detect_level(net_worth: Decimal | int | float) -> WealthLevel:
    """Map a net-worth amount to a ``WealthLevel`` band."""
    nw = Decimal(net_worth or 0)
    if nw < _BAND_30M:
        return WealthLevel.STARTER
    if nw < _BAND_200M:
        return WealthLevel.YOUNG_PROFESSIONAL
    if nw < _BAND_1B:
        return WealthLevel.MASS_AFFLUENT
    return WealthLevel.HIGH_NET_WORTH


def next_milestone(
    net_worth: Decimal | int | float,
) -> tuple[Decimal, WealthLevel]:
    """Next round target the user is climbing toward + the level it unlocks.

    Sub-milestones inside a band keep early users motivated (Starter who
    hits 10tr sees "30tr next" not "1 tỷ"). For HNW we tick up by 1 tỷ
    each — the spec assumes those users are interested in 1B granularity.
    """
    nw = Decimal(net_worth or 0)

    if nw < _BAND_30M:
        return _BAND_30M, WealthLevel.YOUNG_PROFESSIONAL
    if nw < Decimal("100_000_000"):
        return Decimal("100_000_000"), WealthLevel.YOUNG_PROFESSIONAL
    if nw < _BAND_200M:
        return _BAND_200M, WealthLevel.MASS_AFFLUENT
    if nw < Decimal("500_000_000"):
        return Decimal("500_000_000"), WealthLevel.MASS_AFFLUENT
    if nw < _BAND_1B:
        return _BAND_1B, WealthLevel.HIGH_NET_WORTH

    # HNW: round up to the next whole billion.
    current_billions = int(nw // _BAND_1B)
    return _BAND_1B * (current_billions + 1), WealthLevel.HIGH_NET_WORTH


async def update_user_level(
    db: AsyncSession, user_id: uuid.UUID, net_worth: Decimal
) -> WealthLevel | None:
    """Persist the detected level on ``users.wealth_level``.

    Service flushes only — the calling worker owns the transaction
    boundary. Returns the new level on change, ``None`` if unchanged
    (so callers can decide whether to fire ``wealth_level_up`` events).
    """
    user = await db.get(User, user_id)
    if user is None:
        return None
    new_level = detect_level(net_worth)
    if user.wealth_level == new_level.value:
        return None
    user.wealth_level = new_level.value
    # TRANSACTION_OWNED_BY_CALLER — worker/router commits at the boundary.
    await db.flush()
    return new_level
