"""Wealth segment inference from first-asset value (Phase 4.1, Story A.1).

Pure function — no DB, no side effects. Callers map an Asia-VN-mass-
affluent value into one of four segments which the content layer then
uses to pick tone (starter copy is warmer / more guided; HNW copy is
more deferential / professional).

The breakpoints are intentionally coarse:

- < 100tr           → starter
- 100tr – 500tr     → young_pro
- 500tr – 5 tỷ      → mass_affluent (Bé Tiền's primary persona)
- > 5 tỷ            → hnw

Inference is a soft signal — the user can correct via /profile later.
"""

from __future__ import annotations

from decimal import Decimal

from backend.models.onboarding_session import (
    SEGMENT_HNW,
    SEGMENT_MASS_AFFLUENT,
    SEGMENT_STARTER,
    SEGMENT_YOUNG_PRO,
)


# Breakpoints in VND (Decimal so we never compare float ↔ Decimal).
_BP_STARTER = Decimal("100_000_000")
_BP_YOUNG_PRO = Decimal("500_000_000")
_BP_MASS_AFFLUENT = Decimal("5_000_000_000")


def infer_segment(asset_value_vnd: Decimal | int | float) -> str:
    """Return one of the four segment constants from
    :mod:`backend.models.onboarding_session`. ``asset_value_vnd`` is
    coerced to ``Decimal`` defensively (handlers may pass plain int).

    Edge: negative or zero values fall to ``starter`` — the answer
    "0 tài sản" is a real signal, not an error.
    """
    value = (
        Decimal(str(asset_value_vnd))
        if not isinstance(asset_value_vnd, Decimal)
        else asset_value_vnd
    )

    if value < _BP_STARTER:
        return SEGMENT_STARTER
    if value < _BP_YOUNG_PRO:
        return SEGMENT_YOUNG_PRO
    if value < _BP_MASS_AFFLUENT:
        return SEGMENT_MASS_AFFLUENT
    return SEGMENT_HNW
