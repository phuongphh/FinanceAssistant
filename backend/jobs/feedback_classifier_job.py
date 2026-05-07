from __future__ import annotations

import logging

from backend.database import get_session_factory
from backend.feedback.services.classifier import classify_feedback_batch

logger = logging.getLogger(__name__)


async def run_feedback_classifier_batch(limit: int = 50) -> int:
    """Process unclassified feedback rows once.

    Intended for APScheduler/cron. Retries are represented by
    feedback.classification_attempts and capped in the service query.
    """
    session_factory = get_session_factory()
    async with session_factory() as db:
        try:
            processed = await classify_feedback_batch(db, limit=limit)
            await db.commit()
            return processed
        except Exception:
            await db.rollback()
            logger.exception("Feedback classifier batch failed")
            raise
