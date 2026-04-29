"""Asset type enum + YAML-backed config loader.

The YAML at ``content/asset_categories.yaml`` is single source of
truth for icons, labels, and per-type required/optional fields. Both
the wizard keyboards and the Mini App breakdown read from this file,
so adding an asset type only requires a YAML edit + an enum entry.
"""
from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path

import yaml


class AssetType(str, Enum):
    CASH = "cash"
    STOCK = "stock"
    REAL_ESTATE = "real_estate"
    CRYPTO = "crypto"
    GOLD = "gold"
    OTHER = "other"


_ASSET_CATEGORIES_PATH = (
    Path(__file__).resolve().parents[2] / "content" / "asset_categories.yaml"
)


@lru_cache(maxsize=1)
def load_asset_categories() -> dict:
    """Read the YAML once per process; tests can call ``cache_clear()``."""
    with open(_ASSET_CATEGORIES_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_asset_config(asset_type: str) -> dict:
    """Full config for one asset type (icon, label_vi, subtypes, ...).

    Returns ``{}`` if the type is unknown — callers may render a
    fallback icon / label so the UI stays robust to typos.
    """
    return load_asset_categories().get("asset_types", {}).get(asset_type, {})


def get_subtypes(asset_type: str) -> dict:
    """Subtype-code → human label map for one asset type."""
    return get_asset_config(asset_type).get("subtypes", {}) or {}


def get_icon(asset_type: str) -> str:
    return get_asset_config(asset_type).get("icon", "📌")


def get_label(asset_type: str) -> str:
    return get_asset_config(asset_type).get("label_vi", asset_type)


_SUBTYPE_ICONS: dict[str, str] = {
    "bank_savings": "🏦",
    "bank_checking": "💳",
    "cash": "💵",
    "e_wallet": "📱",
    "vn_stock": "📈",
    "fund": "📊",
    "etf": "📊",
    "foreign_stock": "📈",
}

_SUBTYPE_SHORT_LABELS: dict[str, str] = {
    "bank_savings": "Tiết kiệm",
    "bank_checking": "Thanh toán",
    "cash": "Tiền mặt",
    "e_wallet": "Ví điện tử",
    "vn_stock": "Cổ phiếu VN",
    "fund": "Quỹ đầu tư",
    "etf": "ETF",
    "foreign_stock": "Cổ phiếu nước ngoài",
    "house_primary": "Nhà ở",
    "land": "Đất",
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "stablecoin": "Stablecoin",
    "altcoin": "Altcoin",
    "sjc": "Vàng SJC",
    "pnj": "Vàng PNJ",
    "nhan": "Vàng nhẫn",
    "trang_suc": "Trang sức",
    "vehicle": "Xe cộ",
    "collection": "Đồ sưu tầm",
    "business": "Kinh doanh",
}


def get_subtype_icon(asset_type: str, subtype: str | None) -> str:
    """Return a subtype-specific icon, falling back to the asset_type icon."""
    if subtype and subtype in _SUBTYPE_ICONS:
        return _SUBTYPE_ICONS[subtype]
    return get_icon(asset_type)


def get_subtype_label(subtype: str | None) -> str | None:
    """Return a short Vietnamese label for the subtype, or None if unknown."""
    if not subtype:
        return None
    return _SUBTYPE_SHORT_LABELS.get(subtype)
