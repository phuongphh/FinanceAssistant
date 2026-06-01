"""Apply the user's ``default_expense_source`` profile setting to expense payloads.

The profile picker stores a source key encoded as one of:
    ``cash``
    ``bank_account:<asset_uuid>``
    ``credit_card:<credit_card_uuid>``
    ``e_wallet:<asset_uuid>``

This module turns that key into the ``ExpenseCreate`` fields the
expense service understands, and renders a human-friendly Vietnamese
label for the confirmation card. Both quick-transaction and the manual
fast-path go through here so behaviour stays consistent.
"""

from __future__ import annotations

import logging
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.credit_card import CreditCard
from backend.models.expense import Expense
from backend.profile.models.user_profile import UserProfile
from backend.schemas.expense import ExpenseCreate
from backend.wealth.models.asset import Asset

logger = logging.getLogger(__name__)

DEFAULT_SOURCE_RAW_DATA_KEY = "source_from_default_expense_source"
DEFAULT_SOURCE_SUFFIX = " (mặc định)"

_CONTENT_PATH = (
    Path(__file__).resolve().parents[2] / "content" / "transaction_copy.yaml"
)


@lru_cache(maxsize=1)
def _copy() -> dict[str, Any]:
    with open(_CONTENT_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _source_label_template(source_type: str | None) -> str:
    labels = _copy().get("source_labels", {})
    if source_type and source_type in labels:
        return labels[source_type]
    return labels.get("unknown", "Nguồn khác")


def _parse_source_key(
    key: str | None,
) -> tuple[str | None, uuid.UUID | None, uuid.UUID | None]:
    """Decode the profile key into (source_type, asset_id, credit_card_id)."""
    if not key:
        return None, None, None
    if key == "cash":
        return "cash", None, None
    if ":" not in key:
        return None, None, None
    kind, _, raw_id = key.partition(":")
    try:
        parsed_id = uuid.UUID(raw_id)
    except ValueError:
        return None, None, None
    if kind == "bank_account":
        return "bank_account", parsed_id, None
    if kind == "e_wallet":
        # The asset's extra metadata carries the provider — the
        # service-layer resolver re-reads it via ``_asset_source_metadata``.
        return "e_wallet", parsed_id, None
    if kind == "credit_card":
        return "credit_card", None, parsed_id
    return None, None, None


async def apply_default_source(
    db: AsyncSession, user_id: uuid.UUID, data: ExpenseCreate
) -> ExpenseCreate:
    """Return a copy of ``data`` with the user's default source applied.

    No-op when:
      - the transaction is money-in (incoming flow keeps current UX);
      - the user has no default configured;
      - the caller has already specified a source (explicit > default).
    """
    if data.transaction_type != "expense":
        return data
    if (
        data.source_type
        or data.source_asset_id
        or data.source_credit_card_id
    ):
        return data

    profile = await db.get(UserProfile, user_id)
    key = profile.default_expense_source if profile else None
    source_type, asset_id, card_id = _parse_source_key(key)
    if not source_type:
        return data

    raw_data = dict(data.raw_data or {})
    raw_data[DEFAULT_SOURCE_RAW_DATA_KEY] = True
    return data.model_copy(
        update={
            "source_type": source_type,
            "source_asset_id": asset_id,
            "source_credit_card_id": card_id,
            "raw_data": raw_data,
        }
    )


def _with_default_suffix(label: str, expense: Expense) -> str:
    """Append the UI marker when the source came from profile default."""
    raw_data = expense.raw_data or {}
    if raw_data.get(DEFAULT_SOURCE_RAW_DATA_KEY):
        return f"{label}{DEFAULT_SOURCE_SUFFIX}"
    return label


async def resolve_source_label_for_expense(
    db: AsyncSession, expense: Expense
) -> str | None:
    """Build the Vietnamese label shown on the confirmation card.

    Returns ``None`` for money-in or when no source could be resolved.
    The card line is decorative — silently dropping it is preferable
    to surfacing a stale or wrong-looking label.
    """
    if expense.transaction_type != "expense":
        return None
    source_type = expense.source_type
    if not source_type:
        return None

    base = _source_label_template(source_type)

    if source_type == "credit_card" and expense.source_credit_card_id:
        card = await db.get(CreditCard, expense.source_credit_card_id)
        if card and card.user_id == expense.user_id:
            bank = (card.bank_name or "").strip()
            if bank:
                return _with_default_suffix(f"{base} [{bank}]", expense)
        return _with_default_suffix(base, expense)

    if expense.source_asset_id:
        asset = await db.get(Asset, expense.source_asset_id)
        if asset and asset.user_id == expense.user_id:
            name = (asset.name or "").strip()
            if name:
                return _with_default_suffix(f"{base} [{name}]", expense)
    return _with_default_suffix(base, expense)
