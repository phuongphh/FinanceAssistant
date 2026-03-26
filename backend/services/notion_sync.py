import logging
from datetime import date

from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _get_client():
    if not settings.notion_api_key:
        raise ValueError("NOTION_API_KEY not configured")
    from notion_client import Client
    return Client(auth=settings.notion_api_key)


async def sync_expense_to_notion(expense) -> None:
    """Sync a single expense to Notion Expenses database."""
    if not settings.notion_expenses_db_id:
        logger.debug("Notion expenses DB not configured, skipping sync")
        return

    try:
        client = _get_client()
        client.pages.create(
            parent={"database_id": settings.notion_expenses_db_id},
            properties={
                "Date": {"date": {"start": expense.expense_date.isoformat()}},
                "Amount": {"number": float(expense.amount)},
                "Merchant": {"title": [{"text": {"content": expense.merchant or "N/A"}}]},
                "Category": {"select": {"name": expense.category}},
                "Source": {"select": {"name": expense.source}},
                "Month": {"rich_text": [{"text": {"content": expense.month_key}}]},
                "Note": {"rich_text": [{"text": {"content": expense.note or ""}}]},
                "Needs Review": {"checkbox": expense.needs_review or False},
            },
        )
        logger.info("Synced expense %s to Notion", expense.id)
    except Exception as e:
        logger.error("Failed to sync expense to Notion: %s", e)


async def sync_goal_to_notion(goal) -> None:
    """Sync a goal to Notion Goals database."""
    if not settings.notion_goals_db_id:
        logger.debug("Notion goals DB not configured, skipping sync")
        return

    try:
        client = _get_client()
        properties = {
            "Goal": {"title": [{"text": {"content": goal.goal_name}}]},
            "Target": {"number": float(goal.target_amount)},
            "Current": {"number": float(goal.current_amount)},
            "Priority": {"select": {"name": goal.priority}},
            "Active": {"checkbox": goal.is_active},
        }
        if goal.deadline:
            properties["Deadline"] = {"date": {"start": goal.deadline.isoformat()}}

        client.pages.create(
            parent={"database_id": settings.notion_goals_db_id},
            properties=properties,
        )
        logger.info("Synced goal %s to Notion", goal.id)
    except Exception as e:
        logger.error("Failed to sync goal to Notion: %s", e)


async def sync_report_to_notion(report) -> None:
    """Sync monthly report to Notion Reports database."""
    if not settings.notion_reports_db_id:
        logger.debug("Notion reports DB not configured, skipping sync")
        return

    try:
        client = _get_client()
        # Truncate report text for Notion's 2000 char limit on rich_text
        report_text = (report.report_text or "")[:2000]

        client.pages.create(
            parent={"database_id": settings.notion_reports_db_id},
            properties={
                "Month": {"title": [{"text": {"content": report.month_key}}]},
                "Total Expense": {"number": float(report.total_expense)},
                "Total Income": {"number": float(report.total_income)} if report.total_income else {"number": 0},
                "Savings Rate": {"number": float(report.savings_rate)} if report.savings_rate else {"number": 0},
            },
            children=[
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"text": {"content": report_text}}],
                    },
                }
            ] if report_text else [],
        )
        logger.info("Synced report %s to Notion", report.month_key)
    except Exception as e:
        logger.error("Failed to sync report to Notion: %s", e)


async def sync_market_snapshot_to_notion(snapshot) -> None:
    """Sync market snapshot to Notion Market database."""
    if not settings.notion_market_db_id:
        return

    try:
        client = _get_client()
        client.pages.create(
            parent={"database_id": settings.notion_market_db_id},
            properties={
                "Asset": {"title": [{"text": {"content": snapshot.asset_code}}]},
                "Date": {"date": {"start": snapshot.snapshot_date.isoformat()}},
                "Type": {"select": {"name": snapshot.asset_type}},
                "Price": {"number": float(snapshot.price)} if snapshot.price else {"number": 0},
                "Change 1D": {"number": float(snapshot.change_1d_pct)} if snapshot.change_1d_pct else {"number": 0},
            },
        )
    except Exception as e:
        logger.error("Failed to sync market snapshot to Notion: %s", e)
