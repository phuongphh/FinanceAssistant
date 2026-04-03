import logging

from backend.database import get_session_factory
from backend.models.user import User
from sqlalchemy import select

logger = logging.getLogger(__name__)


async def poll_gmail():
    """Poll Gmail for new receipts for all active users."""
    from backend.services.gmail_service import sync_new_receipts

    async with get_session_factory()() as db:
        try:
            users = (await db.execute(
                select(User).where(User.is_active.is_(True), User.deleted_at.is_(None))
            )).scalars().all()

            for user in users:
                try:
                    expenses = await sync_new_receipts(db, user.id)
                    if expenses:
                        logger.info("Gmail sync for user %s: %d new expenses", user.id, len(expenses))
                except Exception as e:
                    logger.error("Gmail sync failed for user %s: %s", user.id, e)

            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error("Gmail poller error: %s", e)
