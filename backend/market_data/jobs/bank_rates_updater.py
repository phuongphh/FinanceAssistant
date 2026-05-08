"""Weekly bank-rate updater."""
from __future__ import annotations

import logging
import time
from datetime import date

from sqlalchemy.dialects.postgresql import insert

from backend.database import get_session_factory
from backend.market_data.providers.bank_rates_scraper import BankRatesScraper
from backend.models.bank_rate import BankRateSnapshot

logger = logging.getLogger(__name__)


async def update_bank_rates() -> dict[str, int]:
    started = time.perf_counter()
    rates = await BankRatesScraper().fetch_all()
    snapshot_date = date.today()
    async with get_session_factory()() as db:
        for rate in rates:
            stmt = insert(BankRateSnapshot).values(
                bank_code=rate.bank_code,
                bank_name=rate.bank_name,
                tenor_months=rate.tenor_months,
                rate_pct=rate.rate_pct,
                deposit_type=rate.deposit_type,
                notes=rate.notes,
                snapshot_date=snapshot_date,
                fetched_at=rate.fetched_at,
            ).on_conflict_do_update(
                constraint="uq_bank_rate_snapshot",
                set_={"rate_pct": rate.rate_pct, "notes": rate.notes, "fetched_at": rate.fetched_at},
            )
            await db.execute(stmt)
        await db.commit()
    metrics = {"rates_attempted": len(rates), "rates_succeeded": len(rates), "duration_ms": int((time.perf_counter() - started) * 1000)}
    logger.info("Bank rates updater complete: %s", metrics)
    return metrics
