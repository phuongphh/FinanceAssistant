import logging
import uuid
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.expense import Expense
from backend.models.goal import Goal
from backend.models.report import MonthlyReport
from backend.models.user import User
from backend.services.llm_service import call_llm

logger = logging.getLogger(__name__)


def _prev_month_key(month_key: str) -> str:
    year, month = int(month_key[:4]), int(month_key[5:7])
    if month == 1:
        return f"{year - 1}-12"
    return f"{year}-{month - 1:02d}"


async def _get_breakdown(db: AsyncSession, user_id: uuid.UUID, month_key: str) -> dict:
    stmt = (
        select(Expense.category, func.sum(Expense.amount).label("total"))
        .where(
            Expense.user_id == user_id,
            Expense.month_key == month_key,
            Expense.deleted_at.is_(None),
        )
        .group_by(Expense.category)
    )
    result = await db.execute(stmt)
    return {row.category: float(row.total) for row in result.all()}


async def generate_monthly_report(
    db: AsyncSession, user_id: uuid.UUID, month_key: str | None = None
) -> MonthlyReport:
    if not month_key:
        today = date.today()
        month_key = today.strftime("%Y-%m")

    # Get user info
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    monthly_income = float(user.monthly_income) if user and user.monthly_income else None

    # Current month breakdown
    breakdown = await _get_breakdown(db, user_id, month_key)
    total_expense = sum(breakdown.values())

    # Previous month for comparison
    prev_key = _prev_month_key(month_key)
    prev_breakdown = await _get_breakdown(db, user_id, prev_key)
    prev_total = sum(prev_breakdown.values())

    vs_previous = None
    if prev_total > 0:
        diff_pct = ((total_expense - prev_total) / prev_total) * 100
        vs_previous = {
            "prev_month_key": prev_key,
            "prev_total": prev_total,
            "total_diff_pct": round(diff_pct, 2),
            "prev_breakdown": prev_breakdown,
        }

    # Savings
    savings_amount = None
    savings_rate = None
    if monthly_income and monthly_income > 0:
        savings_amount = monthly_income - total_expense
        savings_rate = round((savings_amount / monthly_income) * 100, 2)

    # Goal progress snapshot
    goals_stmt = select(Goal).where(
        Goal.user_id == user_id,
        Goal.is_active.is_(True),
        Goal.deleted_at.is_(None),
    )
    goals = (await db.execute(goals_stmt)).scalars().all()
    goal_progress = [
        {
            "name": g.goal_name,
            "target": float(g.target_amount),
            "current": float(g.current_amount),
            "pct": round((float(g.current_amount) / float(g.target_amount)) * 100, 1) if g.target_amount else 0,
        }
        for g in goals
    ]

    # Generate report text via LLM
    report_context = f"""Tháng: {month_key}
Tổng chi tiêu: {total_expense:,.0f} VND
Thu nhập: {f'{monthly_income:,.0f} VND' if monthly_income else 'Chưa khai báo'}
Tiết kiệm: {f'{savings_amount:,.0f} VND ({savings_rate}%)' if savings_amount is not None else 'N/A'}

Chi tiết theo danh mục:
{chr(10).join(f'  • {cat}: {amt:,.0f} VND' for cat, amt in sorted(breakdown.items(), key=lambda x: -x[1]))}

{f'So với tháng trước ({prev_key}): tổng {prev_total:,.0f} VND, thay đổi {vs_previous["total_diff_pct"]:+.1f}%' if vs_previous else 'Không có dữ liệu tháng trước'}

Mục tiêu:
{chr(10).join(f'  • {g["name"]}: {g["current"]:,.0f}/{g["target"]:,.0f} VND ({g["pct"]}%)' for g in goal_progress) if goal_progress else '  Chưa có mục tiêu'}"""

    try:
        report_text = await call_llm(
            f"Viết báo cáo tài chính tháng ngắn gọn, thân thiện cho 1 người dùng Telegram. "
            f"Dùng emoji phù hợp. Tóm tắt điểm chính và đưa ra 1-2 lời khuyên.\n\n{report_context}",
            task_type="report_text",
            db=db,
            use_cache=False,
        )
    except Exception:
        report_text = report_context  # Fallback to raw data

    # Upsert report
    existing = (await db.execute(
        select(MonthlyReport).where(
            MonthlyReport.user_id == user_id,
            MonthlyReport.month_key == month_key,
        )
    )).scalar_one_or_none()

    if existing:
        existing.total_expense = total_expense
        existing.total_income = monthly_income
        existing.savings_amount = savings_amount
        existing.savings_rate = savings_rate
        existing.breakdown_by_category = breakdown
        existing.vs_previous_month = vs_previous
        existing.goal_progress = goal_progress
        existing.report_text = report_text
        existing.generated_at = datetime.utcnow()
        await db.flush()
        await db.refresh(existing)
        return existing

    report = MonthlyReport(
        user_id=user_id,
        month_key=month_key,
        total_expense=total_expense,
        total_income=monthly_income,
        savings_amount=savings_amount,
        savings_rate=savings_rate,
        breakdown_by_category=breakdown,
        vs_previous_month=vs_previous,
        goal_progress=goal_progress,
        report_text=report_text,
    )
    db.add(report)
    await db.flush()
    await db.refresh(report)
    return report
