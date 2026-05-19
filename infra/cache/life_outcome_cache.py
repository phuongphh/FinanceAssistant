"""Cache-key helpers for Phase 4.3 life outcome translations."""
from __future__ import annotations

import hashlib
from decimal import Decimal

BUCKET_SIZE_VND = Decimal("200000000")
TTL_DAYS = 7
PREFIX = "twin_life_outcome"


def bucket_amount(amount_vnd: Decimal | int | str) -> Decimal:
    amount = Decimal(str(amount_vnd or 0))
    if amount <= 0:
        return Decimal(0)
    return (amount / BUCKET_SIZE_VND).quantize(Decimal("1")) * BUCKET_SIZE_VND


def cache_key(*, amount_vnd: Decimal | int | str, target_year: int, user_segment: str, location: str) -> str:
    basis = "|".join(
        [
            str(bucket_amount(amount_vnd)),
            str(target_year),
            (user_segment or "unknown").strip().lower(),
            (location or "vn").strip().lower(),
        ]
    )
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:24]
    return f"{PREFIX}:{digest}"
