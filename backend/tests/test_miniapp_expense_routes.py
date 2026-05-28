"""Tests for the Expense Dashboard overview route.

Regression guard for the multi-account source picker: ``_build_source_options``
must (a) actually resolve ``list_assets`` / ``list_credit_cards`` (a missing
import raised ``NameError`` → blanket 500 → "Không tải được dữ liệu" in the
Mini App), and (b) degrade gracefully so a failure in the *auxiliary* source
picker never blanks the *primary* spending payload.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from backend.database import get_db
from backend.main import app
from backend.miniapp import routes as miniapp_routes
from backend.miniapp.auth import require_miniapp_auth

client = TestClient(app)


async def _stub_db():
    yield MagicMock()


def _fake_user(telegram_id: int = 12345):
    return SimpleNamespace(id=uuid.uuid4(), telegram_id=telegram_id)


def _override_auth(user_id: int = 12345):
    async def _ok():
        return {"user_id": user_id, "first_name": "Test"}

    app.dependency_overrides[require_miniapp_auth] = _ok
    app.dependency_overrides[get_db] = _stub_db


def _clear_overrides():
    app.dependency_overrides.pop(require_miniapp_auth, None)
    app.dependency_overrides.pop(get_db, None)
    miniapp_routes._wealth_cache_clear()


def _patch_primary_payload(stack):
    """Stub the primary spending aggregates so the test focuses on
    source-option behavior. Returns nothing extra to serialize (empty
    expense lists) so we don't need full ORM rows."""
    ds = miniapp_routes.dashboard_service
    stack.enter_context(
        patch.object(ds, "get_month_total", AsyncMock(return_value=0.0))
    )
    stack.enter_context(
        patch.object(ds, "get_month_transaction_count", AsyncMock(return_value=0))
    )
    stack.enter_context(
        patch.object(ds, "get_category_breakdown", AsyncMock(return_value=[]))
    )
    stack.enter_context(patch.object(ds, "get_daily_trend", AsyncMock(return_value=[])))
    stack.enter_context(
        patch(
            "backend.services.expense_service.list_expenses",
            AsyncMock(return_value=[]),
        )
    )


class TestExpenseOverviewSourceOptions:
    def teardown_method(self):
        _clear_overrides()

    def test_overview_includes_dynamic_source_options(self):
        """Happy path: assets/cards are turned into picker options. Patching
        ``miniapp_routes.list_assets`` also proves the symbol is imported —
        ``patch.object`` raises ``AttributeError`` if it were missing."""
        from contextlib import ExitStack

        _override_auth()
        user = _fake_user()
        asset = SimpleNamespace(id=uuid.uuid4(), name="VCB", subtype="bank_checking")
        card = SimpleNamespace(id=uuid.uuid4(), bank_name="TPBank")

        with ExitStack() as stack:
            stack.enter_context(
                patch.object(
                    miniapp_routes, "_resolve_user", AsyncMock(return_value=user)
                )
            )
            _patch_primary_payload(stack)
            stack.enter_context(
                patch.object(
                    miniapp_routes,
                    "list_assets",
                    AsyncMock(return_value=[asset]),
                )
            )
            stack.enter_context(
                patch.object(
                    miniapp_routes,
                    "list_credit_cards",
                    AsyncMock(return_value=[card]),
                )
            )
            resp = client.get(
                "/miniapp/api/expense-dashboard/overview?month=2026-05",
                headers={"X-Telegram-Init-Data": "stub"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["error"] is None
        opts = body["data"]["source_options"]
        # Base "no source" choice is always first.
        assert opts["expense"][0]["value"] == ""
        assert opts["money_in"][0]["value"] == ""
        # The bank asset appears in both expense and money-in pickers.
        assert any(o["value"] == f"asset:{asset.id}" for o in opts["expense"])
        assert any(o["value"] == f"asset:{asset.id}" for o in opts["money_in"])
        # Credit cards are expense-only.
        assert any(o["value"] == f"credit_card:{card.id}" for o in opts["expense"])
        assert all(not o["value"].startswith("credit_card:") for o in opts["money_in"])

    def test_source_option_failure_does_not_blank_dashboard(self):
        """Resilience: if the assets query blows up, the primary spending
        payload must still load (200) with ``source_options: null`` — never a
        500 that blanks the whole dashboard, and never a degenerate
        "no source"-only list (which the frontend treats as authoritative,
        suppressing its static FALLBACK_SOURCE_OPTIONS)."""
        from contextlib import ExitStack

        _override_auth()
        user = _fake_user()

        with ExitStack() as stack:
            stack.enter_context(
                patch.object(
                    miniapp_routes, "_resolve_user", AsyncMock(return_value=user)
                )
            )
            _patch_primary_payload(stack)
            stack.enter_context(
                patch.object(
                    miniapp_routes,
                    "list_assets",
                    AsyncMock(side_effect=RuntimeError("schema drift")),
                )
            )
            resp = client.get(
                "/miniapp/api/expense-dashboard/overview?month=2026-05",
                headers={"X-Telegram-Init-Data": "stub"},
            )

        assert resp.status_code == 200
        # ``null`` (not a degenerate list) so the frontend falls through to its
        # static FALLBACK_SOURCE_OPTIONS instead of treating this as the
        # authoritative — and only — choice.
        assert resp.json()["data"]["source_options"] is None

    def test_requires_auth(self):
        app.dependency_overrides[get_db] = _stub_db
        try:
            resp = client.get(
                "/miniapp/api/expense-dashboard/overview",
                headers={"X-Telegram-Init-Data": "invalid"},
            )
            assert resp.status_code == 401
        finally:
            app.dependency_overrides.pop(get_db, None)


def test_clean_expense_payload_keeps_credit_card_source_fields():
    card_id = str(uuid.uuid4())
    payload = {
        "amount": 120000,
        "transaction_type": "expense",
        "source_type": "credit_card",
        "source_credit_card_id": card_id,
        "source": "ignored-by-cleaner",
    }

    cleaned = miniapp_routes._clean_expense_payload(payload)

    assert cleaned["source_type"] == "credit_card"
    assert cleaned["source_credit_card_id"] == card_id
    assert cleaned["source"] == "manual"
