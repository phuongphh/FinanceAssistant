"""Wealth-level detection — drives ladder-aware UI / messaging.

Five bands (2026 revision — bands rescaled to fit VN mass-affluent reality):

    Starter            : 0      – 30tr
    Young Professional : 30tr   – 300tr
    Mass Affluent      : 300tr  – 3 tỷ
    High Net Worth     : 3 tỷ   – 30 tỷ
    Đỉnh Cao (VIP)     : 30 tỷ+

Boundaries are inclusive on the lower bound, exclusive on the upper —
so 30tr exactly is Young Professional, not Starter.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user import User


class WealthLevel(str, Enum):
    STARTER = "starter"
    YOUNG_PROFESSIONAL = "young_prof"
    MASS_AFFLUENT = "mass_affluent"
    HIGH_NET_WORTH = "hnw"
    VIP = "vip"


_WEALTH_LEVELS_PATH = (
    Path(__file__).resolve().parents[2] / "content" / "wealth_levels.yaml"
)
_LEVEL_ID_BY_ENUM = {
    WealthLevel.STARTER: "starter",
    WealthLevel.YOUNG_PROFESSIONAL: "young_prof",
    WealthLevel.MASS_AFFLUENT: "mass_affluent",
    WealthLevel.HIGH_NET_WORTH: "hnw",
    WealthLevel.VIP: "vip",
}


@lru_cache(maxsize=1)
def _load_wealth_level_content() -> dict[str, dict[str, Any]]:
    data = yaml.safe_load(_WEALTH_LEVELS_PATH.read_text(encoding="utf-8")) or {}
    rows = data.get("levels") or []
    return {str(row.get("id")): row for row in rows if row.get("id")}


def wealth_level_meta(level: WealthLevel | str) -> dict[str, Any]:
    """Return VN-native display metadata from ``content/wealth_levels.yaml``."""
    enum_level = level if isinstance(level, WealthLevel) else WealthLevel(str(level))
    level_id = _LEVEL_ID_BY_ENUM[enum_level]
    row = _load_wealth_level_content().get(level_id) or {}
    fallback = {
        WealthLevel.STARTER: ("Khởi Đầu", "🌱"),
        WealthLevel.YOUNG_PROFESSIONAL: ("Trẻ Năng Động", "🚀"),
        WealthLevel.MASS_AFFLUENT: ("Trung Lưu Vững", "💎"),
        WealthLevel.HIGH_NET_WORTH: ("Tinh Hoa", "🏆"),
        WealthLevel.VIP: ("Đỉnh Cao", "👑"),
    }[enum_level]
    return {
        "id": level_id,
        "name_vn": row.get("name_vn") or fallback[0],
        "icon": row.get("icon") or fallback[1],
        "description": row.get("description") or "",
    }


def wealth_level_label(level: WealthLevel | str, *, with_icon: bool = False) -> str:
    meta = wealth_level_meta(level)
    label = str(meta["name_vn"])
    return f"{meta['icon']} {label}" if with_icon else label


# User-facing Vietnamese labels loaded from Phase 3.8.5 content. Both
# styles intentionally use the same VN-native product name for consistency
# across profile, dashboard and briefing surfaces.
LEVEL_LABELS: dict[WealthLevel, dict[str, str]] = {
    level: {"short": wealth_level_label(level), "full": wealth_level_label(level)}
    for level in WealthLevel
}


# Order of levels for "higher than" comparisons. STARTER < YOUNG_PROF < ...
LEVEL_ORDER: list[WealthLevel] = [
    WealthLevel.STARTER,
    WealthLevel.YOUNG_PROFESSIONAL,
    WealthLevel.MASS_AFFLUENT,
    WealthLevel.HIGH_NET_WORTH,
    WealthLevel.VIP,
]


def format_level(level: WealthLevel, style: str = "short") -> str:
    """Return the Vietnamese label for ``level``.

    ``style="short"`` and ``style="full"`` both return the VN-native
    product name today — kept as a single source so message templates
    can interpolate either without divergence.
    """
    return LEVEL_LABELS[level][style]


# Band boundaries. Keep names aligned with the magnitude (M = triệu,
# B = tỷ) so call-sites read as intent rather than arithmetic.
_BAND_30M = Decimal("30_000_000")
_BAND_100M = Decimal("100_000_000")
_BAND_300M = Decimal("300_000_000")
_BAND_1B = Decimal("1_000_000_000")
_BAND_3B = Decimal("3_000_000_000")
_BAND_10B = Decimal("10_000_000_000")
_BAND_30B = Decimal("30_000_000_000")


def detect_level(net_worth: Decimal | int | float) -> WealthLevel:
    """Map a net-worth amount to a ``WealthLevel`` band."""
    nw = Decimal(net_worth or 0)
    if nw < _BAND_30M:
        return WealthLevel.STARTER
    if nw < _BAND_300M:
        return WealthLevel.YOUNG_PROFESSIONAL
    if nw < _BAND_3B:
        return WealthLevel.MASS_AFFLUENT
    if nw < _BAND_30B:
        return WealthLevel.HIGH_NET_WORTH
    return WealthLevel.VIP


def next_milestone(
    net_worth: Decimal | int | float,
) -> tuple[Decimal, WealthLevel]:
    """Next round target the user is climbing toward + the level it unlocks.

    One sub-milestone + one level-up per band so every user always has
    a near-term goal:

        0      – 30tr   → 30tr   (level-up to Trẻ Năng Động)
        30tr   – 100tr  → 100tr  (sub-milestone in YP)
        100tr  – 300tr  → 300tr  (level-up to Trung Lưu Vững)
        300tr  – 1 tỷ   → 1 tỷ   (sub-milestone in MA)
        1 tỷ   – 3 tỷ   → 3 tỷ   (level-up to Tinh Hoa)
        3 tỷ   – 10 tỷ  → 10 tỷ  (sub-milestone in HNW)
        10 tỷ  – 30 tỷ  → 30 tỷ  (level-up to Đỉnh Cao)
        30 tỷ+         → round up to next +10 tỷ (sub-milestone in VIP)

    ``target_level`` equals the *current* level for sub-milestones, so
    callers can distinguish "đạt level mới" from "cán mốc trong band".
    """
    nw = Decimal(net_worth or 0)

    if nw < _BAND_30M:
        return _BAND_30M, WealthLevel.YOUNG_PROFESSIONAL
    if nw < _BAND_100M:
        return _BAND_100M, WealthLevel.YOUNG_PROFESSIONAL
    if nw < _BAND_300M:
        return _BAND_300M, WealthLevel.MASS_AFFLUENT
    if nw < _BAND_1B:
        return _BAND_1B, WealthLevel.MASS_AFFLUENT
    if nw < _BAND_3B:
        return _BAND_3B, WealthLevel.HIGH_NET_WORTH
    if nw < _BAND_10B:
        return _BAND_10B, WealthLevel.HIGH_NET_WORTH
    if nw < _BAND_30B:
        return _BAND_30B, WealthLevel.VIP

    # VIP: tick up by the next round 10 tỷ. So 30 tỷ → 40 tỷ, 47 tỷ →
    # 50 tỷ, 100 tỷ → 110 tỷ. Granularity stays meaningful without
    # going stale for super-rich balances.
    current_tens = int(nw // _BAND_10B)
    return _BAND_10B * (current_tens + 1), WealthLevel.VIP


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
