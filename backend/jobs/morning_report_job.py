"""Scheduled job: send morning portfolio report to all active users at 7:00 AM."""
import logging

from sqlalchemy import select

from backend.database import get_session_factory
from backend.models.user import User
from backend.services.morning_report_service import send_morning_report

logger = logging.getLogger(__name__)


async def send_all_morning_reports():
    """Send morning report to every active user with a telegram_id."""
    async with get_session_factory()() as db:
        try:
            result = await db.execute(
                select(User).where(
                    User.is_active.is_(True),
                    User.deleted_at.is_(None),
                    User.telegram_id.isnot(None),
                )
            )
            users = list(result.scalars().all())

            sent = 0
            for user in users:
                try:
                    await send_morning_report(db, user)
                    sent += 1
                except Exception as e:
                    logger.error(
                        "Morning report failed for user %s: %s", user.id, e
                    )

            logger.info(
                "Morning report job complete: %d/%d users", sent, len(users)
            )
        except Exception as e:
            logger.error("Morning report job error: %s", e)
