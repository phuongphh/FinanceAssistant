"""Schema regression tests.

These run without a DB or LLM — they only verify that the Pydantic
models serialise to JSON Schema and validate the way the LLM will
produce inputs. Catching schema regressions here is dramatically
cheaper than catching them in a tier-2 LLM eval run."""
from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.agent.tools.schemas import (
    AssetFilter,
    AssetItem,
    AssetType,
    ComparePeriod,
    ComparePeriodsInput,
    CompareMetric,
    ComputeMetricInput,
    GetAssetsInput,
    GetAssetsOutput,
    GetMarketDataInput,
    GetTransactionsInput,
    MetricName,
    NumericFilter,
    SortOrder,
    TransactionCategory,
    TransactionFilter,
)


class TestSchemasSerialise:
    def test_get_assets_input_json_schema(self):
        schema = GetAssetsInput.model_json_schema()
        assert "filter" in schema["properties"]
        assert "sort" in schema["properties"]
        assert "limit" in schema["properties"]

    def test_all_inputs_have_json_schema(self):
        for cls in (
            GetAssetsInput,
            GetTransactionsInput,
            ComputeMetricInput,
            ComparePeriodsInput,
            GetMarketDataInput,
        ):
            schema = cls.model_json_schema()
            assert isinstance(schema, dict)
            assert "properties" in schema


class TestNumericFilter:
    def test_partial_filter(self):
        f = NumericFilter(gt=0)
        assert f.gt == 0 and f.lt is None

    def test_combined_range(self):
        f = NumericFilter(gt=10, lt=100)
        assert f.gt == 10 and f.lt == 100


class TestExtraFieldsRejected:
    def test_unknown_field_raises(self):
        # LLM hallucinations are caught at validation time.
        with pytest.raises(ValidationError):
            AssetFilter(asset_type="stock", weird_field=True)

    def test_unknown_root_field_raises(self):
        with pytest.raises(ValidationError):
            GetAssetsInput(filter={}, foo="bar")


class TestEnumCoercion:
    def test_asset_type_string_to_enum(self):
        f = AssetFilter(asset_type="stock")
        assert f.asset_type is AssetType.STOCK

    def test_sort_order_string_to_enum(self):
        i = GetAssetsInput(sort="gain_pct_desc")
        assert i.sort is SortOrder.GAIN_PCT_DESC

    def test_invalid_enum_rejected(self):
        with pytest.raises(ValidationError):
            GetAssetsInput(sort="hot_stocks")

    def test_compare_metric_enum(self):
        i = ComparePeriodsInput(
            metric="expenses", period_a="this_month", period_b="last_month"
        )
        assert i.metric is CompareMetric.EXPENSES
        assert i.period_a is ComparePeriod.THIS_MONTH


class TestTransactionFilter:
    def test_category(self):
        f = TransactionFilter(category="food")
        assert f.category is TransactionCategory.FOOD


class TestComputeMetric:
    def test_metric_name(self):
        i = ComputeMetricInput(metric_name="saving_rate")
        assert i.metric_name is MetricName.SAVING_RATE

    def test_period_months_bounds(self):
        with pytest.raises(ValidationError):
            ComputeMetricInput(metric_name="saving_rate", period_months=0)
        with pytest.raises(ValidationError):
            ComputeMetricInput(metric_name="saving_rate", period_months=61)


class TestMoneyDecimal:
    def test_decimal_for_money(self):
        item = AssetItem(
            name="VNM",
            asset_type="stock",
            current_value=Decimal("1000000"),
        )
        assert isinstance(item.current_value, Decimal)

    def test_total_value_decimal(self):
        out = GetAssetsOutput(assets=[], total_value=Decimal("0"), count=0)
        assert isinstance(out.total_value, Decimal)


class TestLimitBounds:
    def test_get_assets_limit(self):
        with pytest.raises(ValidationError):
            GetAssetsInput(limit=0)
        with pytest.raises(ValidationError):
            GetAssetsInput(limit=101)
        # 1 and 100 are accepted
        GetAssetsInput(limit=1)
        GetAssetsInput(limit=100)

    def test_get_transactions_limit(self):
        with pytest.raises(ValidationError):
            GetTransactionsInput(limit=201)


class TestMarketTickerNormalization:
    def test_required(self):
        with pytest.raises(ValidationError):
            GetMarketDataInput(ticker="")
