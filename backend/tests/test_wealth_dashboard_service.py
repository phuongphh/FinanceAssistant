"""Tests for ``backend.services.wealth_dashboard_service``.

Covers:
- ``_serialize_group`` — happy path, missing initial value, unknown type fallback.
- ``_group_assets`` — name+subtype merging, case/whitespace normalization,
  same-name-different-subtype stays split, sort order, change aggregation.
- ``_build_breakdown`` — sort order, percentage math, zero-total guard.
- ``get_trend`` — input validation, row serialization, default end-date,
  query parameter binding (start/end derived from ``days``).
- ``build_overview`` — payload composition for Starter / empty / HNW,
  duplicate rollup behavior end-to-end.

Real Postgres isn't required — we monkeypatch ``net_worth_calculator``
and ``asset_service`` and stub ``db.execute`` for the trend SQL.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services import wealth_dashboard_service as svc
from backend.wealth.services import net_worth_calculator as nwc


def _asset(asset_type, name, current, initial=None, subtype=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        name=name,
        asset_type=asset_type,
        subtype=subtype,
        initial_value=Decimal(initial if initial is not None else current),
        current_value=Decimal(current),
        acquired_at=date(2026, 1, 1),
    )


class TestSerializeGroup:
    def test_single_member_known_type(self):
        a = _asset("cash", "VCB", 5_000_000, initial=4_000_000, subtype="bank_savings")
        out = svc._serialize_group([a])
        # YAML config drives icon + parent label.
        assert out["asset_type"] == "cash"
        assert out["subtype"] == "bank_savings"
        # Subtype label surfaces alongside the parent type so users can
        # distinguish products that share a name but differ in subtype.
        assert out["subtype_label"] == "Tiết kiệm"
        assert out["icon"] == "💵"
        assert out["type_label"] == "Tiền mặt & Tài khoản"
        assert out["current_value"] == 5_000_000.0
        assert out["initial_value"] == 4_000_000.0
        assert out["change"] == 1_000_000.0
        assert out["change_pct"] == 25.0
        assert out["acquired_at"] == "2026-01-01"
        assert out["count"] == 1
        assert out["member_ids"] == [str(a.id)]
        assert isinstance(out["id"], str)  # UUID stringified

    def test_unknown_type_falls_back_to_default_icon_and_label(self):
        a = _asset("widgets", "Magic Bean", 1_000_000)
        out = svc._serialize_group([a])
        # Unknown asset_type → 📌 default + raw type as label.
        assert out["icon"] == "📌"
        assert out["type_label"] == "widgets"
        assert out["subtype_label"] is None

    def test_zero_initial_value_does_not_divide_by_zero(self):
        a = _asset("other", "Gift", 5_000_000, initial=0)
        out = svc._serialize_group([a])
        # Initial 0 → percentage flat 0% rather than infinity.
        assert out["change"] == 5_000_000.0
        assert out["change_pct"] == 0.0

    def test_loss_renders_negative_change(self):
        a = _asset("crypto", "BTC", 80_000_000, initial=100_000_000)
        out = svc._serialize_group([a])
        assert out["change"] == -20_000_000.0
        assert out["change_pct"] == -20.0

    def test_missing_acquired_at_yields_none(self):
        a = _asset("cash", "VCB", 1_000_000)
        a.acquired_at = None
        out = svc._serialize_group([a])
        assert out["acquired_at"] is None


class TestGroupAssets:
    def test_same_name_and_subtype_merge(self):
        # User added "Tiền mặt" twice (10tr + 2tr) → one card 12tr.
        a1 = _asset("cash", "Tiền mặt", 10_000_000, subtype="cash")
        a2 = _asset("cash", "Tiền mặt", 2_000_000, subtype="cash")
        out = svc._group_assets([a1, a2])
        assert len(out) == 1
        assert out[0]["current_value"] == 12_000_000.0
        assert out[0]["count"] == 2
        assert set(out[0]["member_ids"]) == {str(a1.id), str(a2.id)}

    def test_same_name_different_subtypes_stay_separate(self):
        # Techcombank checking and Techcombank savings are different
        # products even though the bank name matches. The subtype label
        # makes the distinction visible to the user.
        a1 = _asset("cash", "Techcombank", 20_000_000, subtype="bank_checking")
        a2 = _asset("cash", "Techcombank", 15_000_000, subtype="bank_savings")
        out = svc._group_assets([a1, a2])
        assert len(out) == 2
        # Sorted desc by value: checking (20tr) first.
        assert out[0]["subtype"] == "bank_checking"
        assert out[0]["subtype_label"] == "Thanh toán"
        assert out[0]["current_value"] == 20_000_000.0
        assert out[1]["subtype"] == "bank_savings"
        assert out[1]["subtype_label"] == "Tiết kiệm"

    def test_name_match_is_case_and_whitespace_insensitive(self):
        # Trim + casefold names before grouping — "tiền mặt" and
        # "Tiền mặt " are obviously the same bucket to a user.
        a1 = _asset("cash", "Tiền mặt", 5_000_000, subtype="cash")
        a2 = _asset("cash", "tiền mặt ", 3_000_000, subtype="cash")
        out = svc._group_assets([a1, a2])
        assert len(out) == 1
        assert out[0]["current_value"] == 8_000_000.0
        assert out[0]["count"] == 2

    def test_sorts_largest_first(self):
        a1 = _asset("cash", "VCB", 5_000_000, subtype="bank_savings")
        a2 = _asset("crypto", "BTC", 100_000_000)
        a3 = _asset("real_estate", "Đất", 1_500_000_000)
        out = svc._group_assets([a1, a2, a3])
        assert [g["asset_type"] for g in out] == [
            "real_estate", "crypto", "cash"
        ]

    def test_change_pct_aggregated_across_members(self):
        # Combined initial 10tr (5+5), combined current 12tr (10+2)
        # → blended +20%.
        a1 = _asset("cash", "X", 10_000_000, initial=5_000_000, subtype="cash")
        a2 = _asset("cash", "X", 2_000_000, initial=5_000_000, subtype="cash")
        out = svc._group_assets([a1, a2])
        assert out[0]["initial_value"] == 10_000_000.0
        assert out[0]["current_value"] == 12_000_000.0
        assert out[0]["change"] == 2_000_000.0
        assert out[0]["change_pct"] == 20.0

    def test_acquired_at_is_earliest(self):
        a1 = _asset("cash", "X", 5_000_000, subtype="cash")
        a1.acquired_at = date(2026, 3, 1)
        a2 = _asset("cash", "X", 5_000_000, subtype="cash")
        a2.acquired_at = date(2026, 1, 15)
        out = svc._group_assets([a1, a2])
        # Earliest preserves the genuine "since when" the bucket existed.
        assert out[0]["acquired_at"] == "2026-01-15"

    def test_empty_returns_empty(self):
        assert svc._group_assets([]) == []

    def test_none_subtype_groups_with_other_none(self):
        # Crypto / real_estate sometimes have no subtype. Two no-subtype
        # rows with the same name should still merge.
        a1 = _asset("crypto", "BTC", 50_000_000)
        a2 = _asset("crypto", "BTC", 30_000_000)
        out = svc._group_assets([a1, a2])
        assert len(out) == 1
        assert out[0]["count"] == 2
        assert out[0]["current_value"] == 80_000_000.0


class TestBuildBreakdown:
    def test_sorts_by_value_desc_and_computes_pct(self):
        by_type = {
            "cash": Decimal("50_000_000"),
            "stock": Decimal("200_000_000"),
            "real_estate": Decimal("750_000_000"),
        }
        total = sum(by_type.values())
        out = svc._build_breakdown(by_type, total)

        assert [b["asset_type"] for b in out] == ["real_estate", "stock", "cash"]
        # Pct should sum to ~100, individually correct.
        assert sum(b["pct"] for b in out) == pytest.approx(100.0, abs=0.01)
        assert out[0]["pct"] == 75.0
        assert out[1]["pct"] == 20.0
        assert out[2]["pct"] == 5.0

    def test_zero_total_returns_zero_pct_no_divide_by_zero(self):
        # Edge: by_type empty/zero — total is 0, no division crash.
        out = svc._build_breakdown({}, Decimal(0))
        assert out == []

        out = svc._build_breakdown(
            {"cash": Decimal(0)}, Decimal(0)
        )
        # The single zero-valued bucket is preserved with pct=0.
        assert len(out) == 1
        assert out[0]["pct"] == 0.0
        assert out[0]["value"] == 0.0

    def test_unknown_type_uses_fallback_color(self):
        # Unknown types still render rather than crash — the dashboard
        # gracefully shows them under the gray default color.
        out = svc._build_breakdown(
            {"widgets": Decimal("1_000_000")}, Decimal("1_000_000")
        )
        assert out[0]["color"] == "#9CA3AF"
        assert out[0]["icon"] == "📌"
        assert out[0]["label"] == "widgets"

    def test_known_type_uses_yaml_color(self):
        out = svc._build_breakdown(
            {"stock": Decimal("100_000_000")}, Decimal("100_000_000")
        )
        # Color comes from content/asset_categories.yaml — pin it to
        # catch accidental edits to the palette.
        assert out[0]["color"] == "#3B82F6"


@pytest.mark.asyncio
class TestBuildOverview:
    async def test_starter_with_one_cash_asset(self, monkeypatch):
        user_id = uuid.uuid4()

        monkeypatch.setattr(
            "backend.wealth.services.asset_service.get_user_assets",
            AsyncMock(return_value=[_asset("cash", "VCB", 5_000_000)]),
        )

        async def fake_change(db, uid, period):
            return nwc.NetWorthChange(
                current=Decimal("5_000_000"),
                previous=Decimal("4_000_000"),
                change_absolute=Decimal("1_000_000"),
                change_percentage=25.0,
                period_label=nwc._PERIOD_LABELS[period],
            )

        monkeypatch.setattr(nwc, "calculate_change", fake_change)

        async def fake_trend(db, uid, *, days, end=None):
            return [{"date": "2026-04-01", "value": 5_000_000.0}]

        monkeypatch.setattr(svc, "get_trend", fake_trend)

        # ``calculate`` runs through nwc.calculate which already uses
        # the patched asset_service — leave it unmocked.
        db = MagicMock()

        result = await svc.build_overview(db, user_id, trend_days=90)

        assert result["net_worth"] == 5_000_000.0
        assert result["asset_count"] == 1
        assert result["level"] == "starter"
        assert result["level_label"] == "Khởi đầu"
        assert result["change_day"]["amount"] == 1_000_000.0
        assert result["change_month"]["amount"] == 1_000_000.0
        assert len(result["assets"]) == 1
        assert result["assets"][0]["asset_type"] == "cash"
        assert result["assets"][0]["icon"] == "💵"
        assert result["assets"][0]["change"] == 0.0  # initial == current
        # Breakdown labelled and percent-summed.
        assert result["breakdown"][0]["label"] == "Tiền mặt & Tài khoản"
        assert result["breakdown"][0]["pct"] == 100.0

        ms = result["next_milestone"]
        assert ms["target"] == 30_000_000.0
        assert ms["target_level"] == "young_prof"
        # 5tr / 30tr ≈ 16.67 → rounded to 2 dp.
        assert ms["pct_progress"] == pytest.approx(16.67, abs=0.01)
        assert ms["remaining"] == 25_000_000.0

    async def test_empty_user_zero_net_worth(self, monkeypatch):
        monkeypatch.setattr(
            "backend.wealth.services.asset_service.get_user_assets",
            AsyncMock(return_value=[]),
        )

        async def fake_change(db, uid, period):
            return nwc.NetWorthChange(
                current=Decimal(0),
                previous=Decimal(0),
                change_absolute=Decimal(0),
                change_percentage=0.0,
                period_label="",
            )

        monkeypatch.setattr(nwc, "calculate_change", fake_change)
        monkeypatch.setattr(
            svc, "get_trend",
            AsyncMock(return_value=[]),
        )

        result = await svc.build_overview(MagicMock(), uuid.uuid4(), trend_days=30)

        assert result["net_worth"] == 0.0
        assert result["asset_count"] == 0
        assert result["level"] == "starter"
        assert result["assets"] == []
        assert result["breakdown"] == []
        assert result["trend"] == []
        # User at 0₫ should still see the first milestone — Young Professional.
        assert result["next_milestone"]["target"] == 30_000_000.0
        assert result["next_milestone"]["pct_progress"] == 0.0

    async def test_duplicate_assets_collapse_in_payload(self, monkeypatch):
        # Mirrors a real user's data: two "Tiền mặt | cash" rows + two
        # Techcombank rows with different subtypes. Expect three cards:
        # one merged "Tiền mặt" 12tr + two distinct Techcombank cards.
        monkeypatch.setattr(
            "backend.wealth.services.asset_service.get_user_assets",
            AsyncMock(return_value=[
                _asset("cash", "Tiền mặt", 10_000_000, subtype="cash"),
                _asset("cash", "Tiền mặt", 2_000_000, subtype="cash"),
                _asset("cash", "Techcombank", 20_000_000, subtype="bank_checking"),
                _asset("cash", "Techcombank", 15_000_000, subtype="bank_savings"),
            ]),
        )

        async def fake_change(db, uid, period):
            return nwc.NetWorthChange(
                current=Decimal("47_000_000"),
                previous=Decimal("47_000_000"),
                change_absolute=Decimal(0),
                change_percentage=0.0,
                period_label="",
            )

        monkeypatch.setattr(nwc, "calculate_change", fake_change)
        monkeypatch.setattr(svc, "get_trend", AsyncMock(return_value=[]))

        result = await svc.build_overview(MagicMock(), uuid.uuid4())

        # Hero count reflects logical cards, not raw rows.
        assert result["asset_count"] == 3
        assert len(result["assets"]) == 3

        # Cards sorted largest-first.
        names = [(a["name"], a["subtype"]) for a in result["assets"]]
        assert names == [
            ("Techcombank", "bank_checking"),
            ("Techcombank", "bank_savings"),
            ("Tiền mặt", "cash"),
        ]
        # The merged Tiền mặt card sums values and tags count.
        merged = result["assets"][2]
        assert merged["current_value"] == 12_000_000.0
        assert merged["count"] == 2
        # Techcombank cards stay split (different subtypes).
        assert result["assets"][0]["count"] == 1
        assert result["assets"][1]["count"] == 1

    async def test_breakdown_sorted_desc(self, monkeypatch):
        monkeypatch.setattr(
            "backend.wealth.services.asset_service.get_user_assets",
            AsyncMock(return_value=[
                _asset("cash", "VCB", 50_000_000),
                _asset("stock", "VNM", 200_000_000),
                _asset("real_estate", "Nhà MD", 1_500_000_000),
            ]),
        )

        async def fake_change(db, uid, period):
            return nwc.NetWorthChange(
                current=Decimal("1_750_000_000"),
                previous=Decimal("1_750_000_000"),
                change_absolute=Decimal(0),
                change_percentage=0.0,
                period_label="",
            )

        monkeypatch.setattr(nwc, "calculate_change", fake_change)
        monkeypatch.setattr(svc, "get_trend", AsyncMock(return_value=[]))

        result = await svc.build_overview(MagicMock(), uuid.uuid4())

        types = [b["asset_type"] for b in result["breakdown"]]
        assert types == ["real_estate", "stock", "cash"]
        # Largest band is HNW → next_milestone goes to next billion.
        assert result["level"] == "hnw"
        assert result["next_milestone"]["target"] == 2_000_000_000.0


@pytest.mark.asyncio
class TestGetTrend:
    async def test_rejects_invalid_days(self):
        with pytest.raises(ValueError):
            await svc.get_trend(MagicMock(), uuid.uuid4(), days=7)

    @pytest.mark.parametrize("days", [30, 90, 365])
    async def test_accepts_allowed_windows(self, days):
        result = MagicMock()
        result.all.return_value = []
        db = MagicMock()
        db.execute = AsyncMock(return_value=result)

        out = await svc.get_trend(db, uuid.uuid4(), days=days)
        assert out == []
        # Confirm the query fired exactly once for valid windows.
        assert db.execute.await_count == 1

    async def test_returns_serialized_rows(self):
        rows = [
            SimpleNamespace(day=date(2026, 4, 1), total=Decimal("1_000_000")),
            SimpleNamespace(day=date(2026, 4, 2), total=Decimal("1_500_000")),
            SimpleNamespace(day=date(2026, 4, 3), total=None),
        ]
        result = MagicMock()
        result.all.return_value = rows
        db = MagicMock()
        db.execute = AsyncMock(return_value=result)

        out = await svc.get_trend(db, uuid.uuid4(), days=30)
        assert out == [
            {"date": "2026-04-01", "value": 1_000_000.0},
            {"date": "2026-04-02", "value": 1_500_000.0},
            # NULL aggregate is normalized to 0 — frontend never sees None.
            {"date": "2026-04-03", "value": 0.0},
        ]

    async def test_passes_correct_bind_params(self):
        """SQL bind params: start = end - (days-1), user_id passed through."""
        result = MagicMock()
        result.all.return_value = []
        db = MagicMock()
        db.execute = AsyncMock(return_value=result)

        user_id = uuid.uuid4()
        end = date(2026, 4, 30)
        await svc.get_trend(db, user_id, days=30, end=end)

        # Inspect the second positional arg — the params dict.
        _stmt, params = db.execute.await_args.args
        assert params["user_id"] == user_id
        assert params["end_date"] == end
        # 30-day window inclusive of the end date → 29 days back.
        assert params["start_date"] == end - timedelta(days=29)

    async def test_default_end_is_today(self):
        result = MagicMock()
        result.all.return_value = []
        db = MagicMock()
        db.execute = AsyncMock(return_value=result)

        await svc.get_trend(db, uuid.uuid4(), days=90)

        _stmt, params = db.execute.await_args.args
        assert params["end_date"] == date.today()
        assert params["start_date"] == date.today() - timedelta(days=89)
