"""Resolve Twin probability labels for presentation only.

Phase 4.3 keeps Monte Carlo payloads/logs in p10/p50/p90, but mass-affluent
Vietnamese users see weather labels by default. Technical labels remain opt-in.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_MAPPING_PATH = (
    Path(__file__).resolve().parents[2] / "content" / "twin" / "twin_label_mapping.yaml"
)
_ALLOWED_CODES = ("p10", "p50", "p90")


@dataclass(frozen=True, slots=True)
class TwinScenarioLabel:
    key: str
    internal_code: str
    vi_label: str
    emoji: str
    en_fallback: str
    description: str

    @property
    def display_label(self) -> str:
        return f"{self.emoji} {self.vi_label}"


@lru_cache(maxsize=1)
def load_label_mapping() -> dict[str, TwinScenarioLabel]:
    with open(_MAPPING_PATH, encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}
    labels = raw.get("labels") or {}
    resolved: dict[str, TwinScenarioLabel] = {}
    for key in _ALLOWED_CODES:
        item = labels.get(key) or {}
        resolved[key] = TwinScenarioLabel(
            key=key,
            internal_code=str(item.get("internal_code") or key.upper()),
            vi_label=str(item.get("vi_label") or key.upper()),
            emoji=str(item.get("emoji") or ""),
            en_fallback=str(item.get("en_fallback") or key.upper()),
            description=str(item.get("description") or ""),
        )
    return resolved


def resolve_label(key: str, *, show_technical_terms: bool = False) -> str:
    normalized = (key or "").lower()
    mapping = load_label_mapping()
    if normalized not in mapping:
        raise ValueError(f"Unsupported Twin label key: {key!r}")
    label = mapping[normalized]
    if show_technical_terms:
        return label.internal_code
    return label.display_label


def labels_for_payload(
    *, show_technical_terms: bool = False
) -> dict[str, dict[str, str]]:
    return {
        key: {
            "internal_code": label.internal_code,
            "label": resolve_label(key, show_technical_terms=show_technical_terms),
            "vi_label": label.vi_label,
            "emoji": label.emoji,
            "description": label.description,
        }
        for key, label in load_label_mapping().items()
    }
