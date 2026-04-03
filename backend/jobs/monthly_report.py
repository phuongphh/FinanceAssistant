import logging

from sqlalchemy import select

from backend.database import get_session_factory
from backend.models.user import User
from backend.services.notion_sync import sync_report_to_notion
from backend.services.report_service import generate_monthly_report

logger = logging.getLogger(__name__)


def _prev_month_key() -> str:
    from datetime import date
    today = date.today()
    if today.month == 1:
        return f"{today.year - 1}-12"
    return f"{today.year}-{today.month - 1:02d}"


async def generate_all_monthly_reports():
    """Generate monthly reports for all active users (previous month)."""
    month_key = _prev_month_key()

    async with get_session_factory()() as db:
        try:
            users = (await db.execute(
                select(User).where(User.is_active.is_(True), User.deleted_at.is_(None))
            )).scalars().all()

            for user in users:
                try:
                    report = await generate_monthly_report(db, user.id, month_key)
                    logger.info("Generated monthly report for user %s: %s", user.id, month_key)

                    # Sync to Notion
                    await sync_report_to_notion(report)

                    # TODO: Push report via Telegram notification
                except Exception as e:
                    logger.error("Monthly report failed for user %s: %s", user.id, e)

            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error("Monthly report job error: %s", e)
