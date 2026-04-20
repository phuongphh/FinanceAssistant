import logging
import uuid
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.models.expense import Expense
from backend.models.goal import Goal
from backend.models.investment_log import InvestmentLog
from backend.models.market_snapshot import MarketSnapshot
from backend.models.user import User
from backend.services.llm_service import call_llm

logger = logging.getLogger(__name__)
settings = get_settings()

# Target fund codes to scrape from cafef.vn
TARGET_FUNDS = ["DCDS", "VESAF", "VFMVF1", "VCBF-BCF", "SSIBF"]


async def fetch_daily_snapshot() -> list[dict]:
    """Fetch market data from vnstock and cafef.vn."""
    snapshots = []
    today = date.today()

    # 1. VN-Index and other indices via vnstock
    try:
        from vnstock import Vnstock
        stock = Vnstock()
        for index_code in ["VNINDEX", "VN30", "HNXINDEX"]:
            try:
                df = stock.stock(symbol=index_code, source="VCI").quote.history(
                    start=(today - timedelta(days=30)).strftime("%Y-%m-%d"),
                    end=today.strftime("%Y-%m-%d"),
                )
                if df is not None and len(df) > 0:
                    latest = df.iloc[-1]
                    prev_1d = df.iloc[-2] if len(df) > 1 else None
                    prev_1w = df.iloc[-5] if len(df) > 5 else None
                    prev_1m = df.iloc[0] if len(df) > 20 else None

                    price = float(latest["close"])
                    snapshots.append({
                        "snapshot_date": today,
                        "asset_code": index_code,
                        "asset_type": "index",
                        "asset_name": index_code,
                        "price": price,
                        "change_1d_pct": round(((price - float(prev_1d["close"])) / float(prev_1d["close"])) * 100, 4) if prev_1d is not None else None,
                        "change_1w_pct": round(((price - float(prev_1w["close"])) / float(prev_1w["close"])) * 100, 4) if prev_1w is not None else None,
                        "change_1m_pct": round(((price - float(prev_1m["close"])) / float(prev_1m["close"])) * 100, 4) if prev_1m is not None else None,
                        "extra_data": {"volume": int(latest.get("volume", 0))},
                    })
            except Exception as e:
                logger.warning("Failed to fetch %s: %s", index_code, e)
    except ImportError:
        logger.warning("vnstock not installed, skipping index data")
    except Exception as e:
        logger.error("vnstock error: %s", e)

    # 2. Fund NAV from cafef.vn
    try:
        import requests
        from bs4 import BeautifulSoup

        for fund_code in TARGET_FUNDS:
            try:
                url = f"https://cafef.vn/quy-mo/{fund_code}.chn"
                resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "lxml")
                    # Try to extract NAV — structure varies
                    nav_elem = soup.select_one(".nav-value, .price, #nav-value")
                    if nav_elem:
                        nav_text = nav_elem.text.strip().replace(",", "").replace(".", "")
                        try:
                            nav = float(nav_text)
                            snapshots.append({
                                "snapshot_date": today,
                                "asset_code": fund_code,
                                "asset_type": "fund",
                                "asset_name": fund_code,
                                "price": nav,
                                "change_1d_pct": None,
                                "change_1w_pct": None,
                                "change_1m_pct": None,
                                "extra_data": {"source": "cafef.vn"},
                                "source_url": url,
                            })
                        except ValueError:
                            pass
            except Exception as e:
                logger.warning("Failed to scrape fund %s: %s", fund_code, e)
    except ImportError:
        logger.warning("beautifulsoup4/requests not installed")

    return snapshots


async def save_snapshots(db: AsyncSession, snapshots: list[dict]) -> list[MarketSnapshot]:
    """Save market snapshots to DB, skip duplicates."""
    saved = []
    for snap_data in snapshots:
        # Check for existing
        existing = (await db.execute(
            select(MarketSnapshot).where(
                MarketSnapshot.snapshot_date == snap_data["snapshot_date"],
                MarketSnapshot.asset_code == snap_data["asset_code"],
            )
        )).scalar_one_or_none()

        if existing:
            # Update
            for key, val in snap_data.items():
                if val is not None:
                    setattr(existing, key, val)
            saved.append(existing)
        else:
            snapshot = MarketSnapshot(**snap_data)
            db.add(snapshot)
            saved.append(snapshot)

    await db.flush()
    return saved


async def get_latest_snapshots(db: AsyncSession) -> list[MarketSnapshot]:
    """Get the most recent snapshots for all assets."""
    subq = (
        select(
            MarketSnapshot.asset_code,
            func.max(MarketSnapshot.snapshot_date).label("max_date"),
        )
        .group_by(MarketSnapshot.asset_code)
        .subquery()
    )
    stmt = select(MarketSnapshot).join(
        subq,
        (MarketSnapshot.asset_code == subq.c.asset_code)
        & (MarketSnapshot.snapshot_date == subq.c.max_date),
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_asset_history(
    db: AsyncSession, asset_code: str, days: int = 30
) -> list[MarketSnapshot]:
    since = date.today() - timedelta(days=days)
    stmt = (
        select(MarketSnapshot)
        .where(
            MarketSnapshot.asset_code == asset_code,
            MarketSnapshot.snapshot_date >= since,
        )
        .order_by(MarketSnapshot.snapshot_date.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def generate_investment_advice(
    db: AsyncSession, user_id: uuid.UUID
) -> str:
    """Generate investment advice based on market + user context."""
    # Get user info
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        return "Chưa thấy bạn trong danh sách — thử gõ /start để đăng ký nhé 🌱"

    # Market context
    snapshots = await get_latest_snapshots(db)
    market_data = []
    for s in snapshots:
        if s.change_1d_pct is not None and s.price is not None:
            market_data.append(f"  • {s.asset_code} ({s.asset_type}): {s.price:,.0f} "
                              f"[1d: {s.change_1d_pct:+.2f}%]")
        elif s.price is not None:
            market_data.append(f"  • {s.asset_code} ({s.asset_type}): {s.price:,.0f}")
        else:
            market_data.append(f"  • {s.asset_code}: N/A")

    # User financial context
    today = date.today()
    month_key = today.strftime("%Y-%m")

    # Current month expenses
    expense_stmt = select(func.sum(Expense.amount)).where(
        Expense.user_id == user_id,
        Expense.month_key == month_key,
        Expense.deleted_at.is_(None),
    )
    total_expense = (await db.execute(expense_stmt)).scalar() or 0

    # Active goals
    goals = (await db.execute(
        select(Goal).where(Goal.user_id == user_id, Goal.is_active.is_(True), Goal.deleted_at.is_(None))
    )).scalars().all()

    monthly_income = float(user.monthly_income) if user.monthly_income else 0
    cash_available = monthly_income - float(total_expense) if monthly_income else 0

    context = f"""Thị trường hiện tại:
{chr(10).join(market_data) if market_data else '  Chưa có dữ liệu'}

Tài chính người dùng:
  • Thu nhập tháng: {monthly_income:,.0f} VND
  • Chi tiêu tháng này: {float(total_expense):,.0f} VND
  • Tiền còn lại: {cash_available:,.0f} VND
  • Mục tiêu: {', '.join(f'{g.goal_name} ({float(g.current_amount):,.0f}/{float(g.target_amount):,.0f})' for g in goals) if goals else 'Chưa có'}"""

    prompt = f"""Dựa trên context dưới đây, đưa ra gợi ý đầu tư ngắn gọn cho người dùng cá nhân tại Việt Nam.

{context}

Yêu cầu output:
1. Nhận định ngắn thị trường (2-3 câu)
2. 1-2 gợi ý cụ thể có lý do
3. Disclaimer: "Đây chỉ là gợi ý tham khảo, không phải lời khuyên đầu tư chuyên nghiệp."

Viết ngắn gọn, thân thiện, dùng emoji phù hợp."""

    advice = await call_llm(prompt, task_type="investment_advice", db=db, use_cache=False)

    # Log the advice
    log = InvestmentLog(
        user_id=user_id,
        log_date=today,
        market_context={"snapshots": [{
            "code": s.asset_code, "price": float(s.price) if s.price else None,
            "change_1d": float(s.change_1d_pct) if s.change_1d_pct else None,
        } for s in snapshots]},
        user_financial_context={
            "monthly_income": monthly_income,
            "total_expense": float(total_expense),
            "cash_available": cash_available,
            "goals": [{"name": g.goal_name, "current": float(g.current_amount), "target": float(g.target_amount)} for g in goals],
        },
        recommendation=advice,
    )
    db.add(log)
    await db.flush()

    return advice
