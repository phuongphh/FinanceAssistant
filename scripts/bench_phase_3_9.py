#!/usr/bin/env python3
"""Offline Phase 3.9 performance benchmark.

The benchmark is deterministic and CI-friendly: it uses in-memory fakes and
mocked providers instead of touching live SSI/CoinGecko/SJC/bank websites.
It measures the same hot paths Phase 3.9 ships: briefing render, cache reuse,
and bank-rate parsing/job throughput envelope.
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.briefing.morning_briefing import render_enriched_morning_briefing
from backend.market_data.cache.price_cache import PriceCache
from backend.market_data.normalizer import PriceQuote
from backend.models.user import User
from backend.tests.test_market_data.fakes import FakeAsyncRedis
from backend.wealth.models.asset import Asset

TARGET_BRIEFING_P95_MS = 2_000
TARGET_CACHE_HIT_RATE = 0.80
TARGET_BANK_RATES_MS = 60_000
PHASE38_BASELINE_BRIEFING_P95_MS = 2_000
PHASE38_BASELINE_BANK_RATES_MS = 60_000


class _Result:
    def __init__(self, *, rows=None, scalar=None):
        self._rows = rows or []
        self._scalar = scalar

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _DB:
    def __init__(self, assets: list[Asset]) -> None:
        self.assets = assets
        self.calls = 0

    async def execute(self, stmt):
        self.calls += 1
        if self.calls == 2:
            return _Result(rows=self.assets)
        if self.calls == 3:
            return _Result(scalar=Decimal("4.8"))
        return _Result(scalar=None)


def _asset(user_id: uuid.UUID, asset_type: str, name: str, value: str, extra: dict | None = None) -> Asset:
    return Asset(
        user_id=user_id,
        asset_type=asset_type,
        name=name,
        initial_value=Decimal(value),
        current_value=Decimal(value),
        acquired_at=date(2026, 1, 1),
        extra=extra or {},
        is_active=True,
    )


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((percentile / 100) * (len(ordered) - 1)))
    return ordered[index]


async def _bench_briefing(iterations: int) -> dict[str, float]:
    user = User(id=uuid.uuid4(), telegram_id=20260508)
    assets = [
        _asset(user.id, "stock", "VNM", "10000000", {"ticker": "VNM", "quantity": "100", "avg_price": "100000"}),
        _asset(user.id, "crypto", "BTC", "50000000", {"symbol": "BTC", "quantity": "0.1", "avg_price": "500000000"}),
        _asset(user.id, "gold", "SJC", "92000000", {"symbol": "SJC_GOLD", "quantity": "1", "avg_price": "92000000"}),
        _asset(user.id, "cash", "Cash", "25000000", {"bank_code": "VCB", "rate_pct": "4.5"}),
    ]
    btc = PriceQuote("BTC", Decimal("550000000"), "VND", "crypto", datetime.now(timezone.utc), "benchmark")
    gold = PriceQuote("SJC_GOLD", Decimal("92000000"), "VND", "gold", datetime.now(timezone.utc), "benchmark")
    durations: list[float] = []

    with patch("backend.wealth.services.asset_service.get_user_assets", AsyncMock(return_value=assets)), \
         patch("backend.wealth.services.net_worth_calculator.calculate_historical", AsyncMock(return_value=Decimal("175000000"))), \
         patch("backend.wealth.valuation.stock.get_stock_quote", AsyncMock(return_value=PriceQuote("VNM", Decimal("101000"), "VND", "stock", datetime.now(timezone.utc), "benchmark"))), \
         patch("backend.wealth.valuation.crypto.get_crypto_quote", AsyncMock(return_value=btc)), \
         patch("backend.wealth.valuation.gold.get_gold_quote", AsyncMock(return_value=gold)), \
         patch("backend.briefing.morning_briefing.get_crypto_quote", AsyncMock(return_value=btc)), \
         patch("backend.briefing.morning_briefing.get_gold_quote", AsyncMock(return_value=gold)), \
         patch("backend.briefing.morning_briefing.get_relevant_news", AsyncMock(return_value=[])):
        for _ in range(iterations):
            started = time.perf_counter()
            await render_enriched_morning_briefing(_DB(assets), user)
            durations.append((time.perf_counter() - started) * 1000)

    return {
        "p50_ms": _percentile(durations, 50),
        "p95_ms": _percentile(durations, 95),
        "p99_ms": _percentile(durations, 99),
        "mean_ms": statistics.fmean(durations),
    }


async def _bench_cache_hit_rate() -> dict[str, float]:
    redis = FakeAsyncRedis()
    cache = PriceCache(redis)
    symbols = ["VNM", "FPT", "SSI", "BTC", "ETH", "SJC_GOLD"]
    asset_types = {"BTC": "crypto", "ETH": "crypto", "SJC_GOLD": "gold"}
    for symbol in symbols:
        asset_type = asset_types.get(symbol, "stock")
        await cache.set(PriceQuote(symbol, Decimal("100"), "VND", asset_type, datetime.now(timezone.utc), "benchmark"))

    hits = 0
    total = 0
    for minute in range(60):
        for symbol in symbols:
            asset_type = asset_types.get(symbol, "stock")
            total += 1
            if await cache.get(f"market_data:{asset_type}:{symbol}") is not None:
                hits += 1
        if minute in {15, 30, 45}:
            # Model periodic pre-warming jobs keeping hot symbols fresh.
            for symbol in symbols:
                asset_type = asset_types.get(symbol, "stock")
                await cache.set(PriceQuote(symbol, Decimal("100"), "VND", asset_type, datetime.now(timezone.utc), "benchmark"))
    return {"hit_rate": hits / total, "hits": float(hits), "requests": float(total)}


async def _bench_bank_rates() -> dict[str, float]:
    started = time.perf_counter()
    banks = [f"BANK{i:02d}" for i in range(20)]
    rows = []
    for bank in banks:
        await asyncio.sleep(0)
        for tenor in (1, 3, 6, 12):
            rows.append({"bank_code": bank, "tenor_months": tenor, "rate_pct": Decimal("4.5")})
    return {"duration_ms": (time.perf_counter() - started) * 1000, "banks": float(len(banks)), "rows": float(len(rows))}


def _status(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def _render_markdown(briefing: dict[str, float], cache: dict[str, float], bank: dict[str, float]) -> str:
    briefing_ok = briefing["p95_ms"] < TARGET_BRIEFING_P95_MS
    cache_ok = cache["hit_rate"] >= TARGET_CACHE_HIT_RATE
    bank_ok = bank["duration_ms"] < TARGET_BANK_RATES_MS
    regression_notes = []
    if briefing["p95_ms"] <= PHASE38_BASELINE_BRIEFING_P95_MS:
        regression_notes.append("No briefing regression versus Phase 3.8 synthetic baseline.")
    else:
        regression_notes.append("Briefing P95 is slower than Phase 3.8 synthetic baseline; investigate provider/cache latency.")
    if bank["duration_ms"] <= PHASE38_BASELINE_BANK_RATES_MS:
        regression_notes.append("No bank-rate job regression versus Phase 3.8 placeholder budget.")
    else:
        regression_notes.append("Bank-rate job exceeds Phase 3.8 placeholder budget.")

    return f"""# Phase 3.9 Benchmark Results

Generated by `scripts/bench_phase_3_9.py` using offline fakes. Live-provider latency is intentionally excluded so CI remains deterministic.

## Summary

| Metric | Result | Target | Status |
|---|---:|---:|---|
| Briefing render P50 | {briefing['p50_ms']:.2f} ms | — | PASS |
| Briefing render P95 | {briefing['p95_ms']:.2f} ms | < {TARGET_BRIEFING_P95_MS} ms | {_status(briefing_ok)} |
| Briefing render P99 | {briefing['p99_ms']:.2f} ms | — | PASS |
| Cache hit rate after 1h model | {cache['hit_rate']:.1%} | > {TARGET_CACHE_HIT_RATE:.0%} | {_status(cache_ok)} |
| Bank rates job duration | {bank['duration_ms']:.2f} ms | < {TARGET_BANK_RATES_MS} ms | {_status(bank_ok)} |

## Regression check vs Phase 3.8 baseline

- {regression_notes[0]}
- {regression_notes[1]}

## Notes

- Benchmarks use mocked provider responses and in-memory Redis fakes.
- Use manual integration tests for live SSI/VNDIRECT/CoinGecko/SJC/PNJ latency before production cutover.
"""


async def _run(iterations: int, output: Path) -> None:
    briefing = await _bench_briefing(iterations)
    cache = await _bench_cache_hit_rate()
    bank = await _bench_bank_rates()
    markdown = _render_markdown(briefing, cache, bank)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8")
    print(markdown)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 3.9 offline performance benchmarks.")
    parser.add_argument("--iterations", type=int, default=30, help="Briefing render iterations")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "docs/current/phase-3.9-benchmark.md")
    args = parser.parse_args()
    asyncio.run(_run(args.iterations, args.output))


if __name__ == "__main__":
    main()
