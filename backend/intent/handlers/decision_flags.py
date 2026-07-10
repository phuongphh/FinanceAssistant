"""Feature flags for Phase 4.5 Decision Engine surfaces.

These helpers are read at the handler / API-router / worker edge only — never
inside a service (layer contract §"Service NEVER reads env"). Each Decision
Engine capability ships dark so the operator can flip it on per-surface once
validated in prod. Same pattern as ``onboarding_v2.is_v2_enabled``.
"""

from __future__ import annotations

import os

_TRUTHY = ("1", "true", "yes", "on")
_FALSY = ("0", "false", "no", "off")


def _enabled(env: str, *, default: bool) -> bool:
    raw = os.environ.get(env, "true" if default else "false").lower()
    return raw not in _FALSY if default else raw in _TRUTHY


CLARITY_METER_ENABLED_ENV = "CLARITY_METER_ENABLED"


def is_clarity_meter_enabled() -> bool:
    """Độ Nét meter (E3). OFF by default — when dark, every surface renders
    exactly as it did before Phase 4.5."""
    return _enabled(CLARITY_METER_ENABLED_ENV, default=False)
