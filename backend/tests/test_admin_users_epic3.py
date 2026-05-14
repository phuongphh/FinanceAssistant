from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.api.admin import users as admin_users
from backend.utils.pii import mask_name
from backend.utils.time_human import humanize_vi


def test_mask_name_keeps_first_token_and_initializes_rest():
    assert mask_name("Nguyễn Văn An") == "Nguyễn V. A."
    assert mask_name("Phuong") == "Phuong"
    assert mask_name(None) == "—"


def test_humanize_vi_localizes_recent_and_empty_times():
    assert humanize_vi(None) == "Chưa hoạt động"
    assert humanize_vi(datetime.now(timezone.utc) - timedelta(minutes=5)).endswith(
        "phút trước"
    )


def test_classify_status_prefers_manual_suspension():
    now = datetime.now(timezone.utc)
    assert admin_users._classify_status(now, now, "suspended") == "suspended"
    assert (
        admin_users._classify_status(now - timedelta(days=10), None, None) == "dormant"
    )
    assert (
        admin_users._classify_status(
            now - timedelta(days=5), now - timedelta(days=4), None
        )
        == "at_risk"
    )


def test_status_change_reason_requires_minimum_context():
    with pytest.raises(ValidationError):
        admin_users.StatusChangeRequest(status="suspended", reason="too short")
    assert (
        admin_users.StatusChangeRequest(
            status="active", reason="User appeal approved"
        ).status
        == "active"
    )


def test_user_list_item_masks_pii_and_computes_tier():
    row = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001",
        telegram_id=123,
        telegram_handle="secret_handle",
        display_name="Nguyễn Văn An",
        created_at=datetime.now(timezone.utc) - timedelta(days=5),
        manual_status=None,
        last_active_at=datetime.now(timezone.utc),
        messages_total=7,
        tokens_total=100,
        cost_vnd=25_000,
        assets_count=1,
        total_asset_vnd=600_000_000,
    )

    item = admin_users._row_to_list_item(row)

    assert item.display_name == "Nguyễn V. A."
    assert item.tier == "mass_affluent"
    assert item.status == "active"
    assert item.llm_cost_total_usd == 1.0
