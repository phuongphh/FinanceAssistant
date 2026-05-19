"""Mascot-aware Twin scenario cards for Phase 4.3 Epic 2."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_MAP_PATH = Path(__file__).resolve().parents[3] / "content" / "mascot" / "mascot_version_map.yaml"
_ALLOWED = ("p10", "p50", "p90")


@dataclass(frozen=True, slots=True)
class MascotVariant:
    p_code: str
    label: str
    emoji: str
    mood: str
    outfit: str
    asset_url: str
    telegram_cdn_url: str | None
    alt: str

    @property
    def display_url(self) -> str:
        return self.telegram_cdn_url or self.asset_url


@lru_cache(maxsize=1)
def load_mascot_variants() -> dict[str, MascotVariant]:
    with open(_MAP_PATH, encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}
    variants = raw.get("variants") or {}
    resolved: dict[str, MascotVariant] = {}
    for p_code in _ALLOWED:
        item = variants.get(p_code) or {}
        resolved[p_code] = MascotVariant(
            p_code=p_code,
            label=str(item.get("label") or p_code.upper()),
            emoji=str(item.get("emoji") or ""),
            mood=str(item.get("mood") or "cân bằng"),
            outfit=str(item.get("outfit") or ""),
            asset_url=str(item.get("asset_url") or ""),
            telegram_cdn_url=item.get("telegram_cdn_url"),
            alt=str(item.get("alt") or f"Bé Tiền 2030 {p_code.upper()}"),
        )
    return resolved


def mascot_for(p_code: str) -> MascotVariant:
    normalized = (p_code or "").lower()
    variants = load_mascot_variants()
    if normalized not in variants:
        raise ValueError(f"Unsupported mascot p_code: {p_code!r}")
    return variants[normalized]


def scenario_card_to_payload(
    p_code: str,
    *,
    amount: str | int | None = None,
    year: int | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    """Return a channel-safe card payload with image fallback metadata."""
    mascot = mascot_for(p_code)
    return {
        "p_code": mascot.p_code,
        "label": label or f"{mascot.emoji} {mascot.label}",
        "amount": str(amount or "0"),
        "year": year,
        "mascot": {
            "emoji": mascot.emoji,
            "mood": mascot.mood,
            "outfit": mascot.outfit,
            "asset_url": mascot.display_url,
            "fallback": mascot.emoji,
            "alt": mascot.alt,
        },
    }


def scenario_cards_for_point(
    point: dict[str, Any], labels: dict[str, dict[str, str]] | None = None
) -> list[dict[str, Any]]:
    labels = labels or {}
    return [
        scenario_card_to_payload(
            p_code,
            amount=point.get(p_code),
            year=int(point.get("year", 0) or 0),
            label=(labels.get(p_code) or {}).get("label"),
        )
        for p_code in _ALLOWED
    ]
