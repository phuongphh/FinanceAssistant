import logging
import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.money import format_money_full, format_money_short
from backend.config import get_settings
from backend.models.expense import Expense
from backend.models.goal import Goal
from backend.models.investment_log import InvestmentLog
from backend.models.market_snapshot import MarketSnapshot
from backend.models.user import User
from backend.services.llm_service import call_llm
from backend.wealth.asset_types import get_label
from backend.wealth.ladder import WealthLevel, detect_level
from backend.wealth.models.income_stream import IncomeStream
from backend.wealth.services import net_worth_calculator

logger = logging.getLogger(__name__)
settings = get_settings()

# Target fund codes to scrape from cafef.vn
TARGET_FUNDS = ["DCDS", "VESAF", "VFMVF1", "VCBF-BCF", "SSIBF"]

# VN30 constituents — populated daily so the VNIndex menu screen (issue
# #530) can rank Top-5 by trading value without a live HTTP fetch. Kept
# in sync with the same list in ``backend/bot/handlers/menu_handler.py``.
VN30_CONSTITUENTS = [
    "ACB", "BCM", "BID", "BVH", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG",
    "LPB", "MBB", "MSN", "MWG", "PLX", "SAB", "SHB", "SSB", "SSI", "STB",
    "TCB", "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE",
]


async def _fetch_vn30_snapshots(today: date) -> list[dict]:
    """Fetch VN30 constituents via vnstock ``price_board`` in one batch.

    vnstock is synchronous + pandas-backed, so we offload to a thread.
    Column names differ across vnstock versions (``match_price`` vs
    ``Giá khớp``, etc.), so we probe candidates rather than assume a
    schema. A missing column falls through to ``None`` and is filtered
    out by the caller's row construction.
    """
    import asyncio

    def _sync() -> list[dict]:
        from vnstock import Vnstock

        vs = Vnstock().stock(symbol=VN30_CONSTITUENTS[0], source="VCI")
        df = vs.trading.price_board(VN30_CONSTITUENTS)
        if df is None or len(df) == 0:
            return []

        # vnstock returns either flat columns or a MultiIndex; flatten if
        # needed so ``record[k]`` lookup works uniformly.
        if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
            df.columns = ["_".join(str(c) for c in col if c).strip("_") for col in df.columns]

        rows: list[dict] = []
        for _, r in df.iterrows():
            record = {k: r[k] for k in df.columns}

            def pick(*names: str):
                for n in names:
                    for key in (n, n.lower(), n.upper()):
                        if key in record and record[key] not in (None, ""):
                            try:
                                if isinstance(record[key], float) and (record[key] != record[key]):  # NaN
                                    continue
                            except Exception:
                                pass
                            return record[key]
                return None

            sym = pick("symbol", "Mã CP", "ticker", "code", "listing_symbol")
            if not sym:
                continue
            sym = str(sym).upper().strip()
            price = pick("match_price", "Giá khớp", "matchPrice", "close", "match_match_price")
            if price is None:
                continue
            try:
                price = float(price)
                # vnstock VCI returns prices in thousands of VND (matches SSI iBoard).
                if price < 1000:
                    price *= 1000.0
            except (TypeError, ValueError):
                continue
            volume = pick("accumulated_volume", "Tổng KL", "total_volume", "match_accumulated_volume")
            trading_value = pick("accumulated_value", "Tổng GT", "total_value", "match_accumulated_value")
            change_pct = pick("change_pct", "%", "pct_change", "match_change_pct")
            change_abs = pick("change", "Thay đổi", "price_change")
            try:
                vol_f = float(volume) if volume is not None else 0.0
            except (TypeError, ValueError):
                vol_f = 0.0
            try:
                tv_f = float(trading_value) if trading_value is not None else 0.0
                # ``accumulated_value`` from VCI is in VND already; some sources return
                # value in thousands — heuristic: if tv looks too small to be VND, scale up.
                if tv_f and tv_f < vol_f * (price / 1000):
                    tv_f *= 1000.0
            except (TypeError, ValueError):
                tv_f = 0.0
            try:
                pct_f = float(change_pct) if change_pct is not None else None
            except (TypeError, ValueError):
                pct_f = None
            try:
                chg_f = float(change_abs) if change_abs is not None else None
            except (TypeError, ValueError):
                chg_f = None

            rows.append(
                {
                    "snapshot_date": today,
                    "asset_code": sym,
                    "asset_type": "stock",
                    "asset_name": sym,
                    "price": price,
                    "change_1d_pct": pct_f,
                    "change_1w_pct": None,
                    "change_1m_pct": None,
                    "extra_data": {
                        "volume": vol_f,
                        "trading_value": tv_f,
                        "change": chg_f,
                        "group": "VN30",
                    },
                }
            )
        return rows

    try:
        return await asyncio.to_thread(_sync)
    except ImportError:
        logger.warning("vnstock not installed, skipping VN30 board snapshot")
        return []


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
                    snapshots.append(
                        {
                            "snapshot_date": today,
                            "asset_code": index_code,
                            "asset_type": "index",
                            "asset_name": index_code,
                            "price": price,
                            "change_1d_pct": (
                                round(
                                    (
                                        (price - float(prev_1d["close"]))
                                        / float(prev_1d["close"])
                                    )
                                    * 100,
                                    4,
                                )
                                if prev_1d is not None
                                else None
                            ),
                            "change_1w_pct": (
                                round(
                                    (
                                        (price - float(prev_1w["close"]))
                                        / float(prev_1w["close"])
                                    )
                                    * 100,
                                    4,
                                )
                                if prev_1w is not None
                                else None
                            ),
                            "change_1m_pct": (
                                round(
                                    (
                                        (price - float(prev_1m["close"]))
                                        / float(prev_1m["close"])
                                    )
                                    * 100,
                                    4,
                                )
                                if prev_1m is not None
                                else None
                            ),
                            "extra_data": {"volume": int(latest.get("volume", 0))},
                        }
                    )
            except Exception as e:
                logger.warning("Failed to fetch %s: %s", index_code, e)
    except ImportError:
        logger.warning("vnstock not installed, skipping index data")
    except Exception as e:
        logger.error("vnstock error: %s", e)

    # 1b. VN30 individual stocks via vnstock ``price_board`` — used by
    # the VNIndex menu screen to rank Top-5 by trading value and to show
    # gainers/losers without a per-request HTTP roundtrip.
    try:
        snapshots.extend(await _fetch_vn30_snapshots(today))
    except Exception as e:
        logger.error("vnstock VN30 error: %s", e)

    # 2. Fund NAV from cafef.vn
    try:
        import requests
        from bs4 import BeautifulSoup

        for fund_code in TARGET_FUNDS:
            try:
                url = f"https://cafef.vn/quy-mo/{fund_code}.chn"
                resp = requests.get(
                    url, timeout=15, headers={"User-Agent": "Mozilla/5.0"}
                )
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "lxml")
                    # Try to extract NAV — structure varies
                    nav_elem = soup.select_one(".nav-value, .price, #nav-value")
                    if nav_elem:
                        nav_text = (
                            nav_elem.text.strip().replace(",", "").replace(".", "")
                        )
                        try:
                            nav = float(nav_text)
                            snapshots.append(
                                {
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
                                }
                            )
                        except ValueError:
                            pass
            except Exception as e:
                logger.warning("Failed to scrape fund %s: %s", fund_code, e)
    except ImportError:
        logger.warning("beautifulsoup4/requests not installed")

    return snapshots


async def save_snapshots(
    db: AsyncSession, snapshots: list[dict]
) -> list[MarketSnapshot]:
    """Save market snapshots to DB, skip duplicates."""
    saved = []
    for snap_data in snapshots:
        # Check for existing
        existing = (
            await db.execute(
                select(MarketSnapshot).where(
                    MarketSnapshot.snapshot_date == snap_data["snapshot_date"],
                    MarketSnapshot.asset_code == snap_data["asset_code"],
                )
            )
        ).scalar_one_or_none()

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


_INVEST_LEVEL_GUIDANCE = {
    WealthLevel.STARTER: (
        "Tone: ấm áp, giáo dục. User chưa có tài sản đáng kể.\n"
        "Focus: gợi ý xây quỹ khẩn cấp (3-6 tháng chi tiêu) trước khi "
        "nghĩ đến đầu tư. Nếu khuyên đầu tư, chỉ gợi ý sản phẩm an toàn "
        "(quỹ index, tiết kiệm có kỳ hạn).\n"
        "Tránh: jargon (P/E, allocation %), khuyên cổ phiếu/crypto cụ thể."
    ),
    WealthLevel.YOUNG_PROFESSIONAL: (
        "Tone: thân thiện, growth-oriented.\n"
        "Focus: tăng saving rate, bắt đầu đầu tư định kỳ (DCA), "
        "diversify giữa cash / stock / fund.\n"
        "Có thể đề cập % allocation. KHÔNG khuyên cổ phiếu cụ thể."
    ),
    WealthLevel.MASS_AFFLUENT: (
        "Tone: CFO-style, dữ liệu, ít cảm xúc.\n"
        "Focus: rebalance portfolio, tỷ lệ cash / stock / real_estate, "
        "passive income coverage, tax-efficiency.\n"
        "Frame mọi gợi ý theo % net worth. KHÔNG dựa vào "
        "'thu nhập − chi tiêu = tiền dư' để quyết định invest size — "
        "với user này, investable wealth là cash position trong tài sản."
    ),
    WealthLevel.HIGH_NET_WORTH: (
        "Tone: Trợ lý Tài sản advisor strategic.\n"
        "Focus: portfolio allocation (% theo asset class), passive "
        "income / chi tiêu coverage, dòng tiền từ BĐS/cổ tức/lãi, "
        "rebalancing thresholds, tax planning.\n"
        "TUYỆT ĐỐI tránh: dùng monthly_income − expenses làm proxy "
        "cho 'tiền dư để đầu tư' (vô nghĩa với HNW). Frame mọi con "
        "số theo % tổng tài sản. Không khuyên cổ phiếu cụ thể."
    ),
}


def _level_label_vi(level: WealthLevel) -> str:
    return {
        WealthLevel.STARTER: "Khởi Đầu (<30tr)",
        WealthLevel.YOUNG_PROFESSIONAL: "Trẻ Năng Động (30tr – 200tr)",
        WealthLevel.MASS_AFFLUENT: "Trung Lưu Vững (200tr – 1 tỷ)",
        WealthLevel.HIGH_NET_WORTH: "Tinh Hoa (>1 tỷ)",
    }[level]


async def generate_investment_advice(db: AsyncSession, user_id: uuid.UUID) -> str:
    """Generate investment advice based on market + user wealth context.

    Personal CFO framing (issue #153): the prompt feeds the LLM the
    user's full wealth picture (net worth, asset allocation, income
    streams) and a level-specific guidance block — so HNW users never
    get cashflow-only advice ("thu nhập − chi tiêu = tiền dư") that's
    meaningless when they hold tỷ-class portfolios.
    """
    # Get user info
    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if not user:
        return "Chưa thấy bạn trong danh sách — thử gõ /start để đăng ký nhé 🌱"

    # Market context
    snapshots = await get_latest_snapshots(db)
    market_data = []
    for s in snapshots:
        if s.change_1d_pct is not None and s.price is not None:
            market_data.append(
                f"  • {s.asset_code} ({s.asset_type}): {s.price:,.0f} "
                f"[1d: {s.change_1d_pct:+.2f}%]"
            )
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

    # Active goals — Phase 3.8 Epic 5 promoted is_active → status enum.
    goals = (
        (
            await db.execute(
                select(Goal).where(
                    Goal.user_id == user_id,
                    Goal.status == "active",
                    Goal.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )

    monthly_income = float(user.monthly_income) if user.monthly_income else 0

    # Wealth-level context — the source-of-truth for "what advice frame
    # to use". We compute net worth from assets, not from monthly
    # cashflow, so HNW users with 120 tỷ NW don't get treated as
    # paycheck-to-paycheck just because their monthly_income field
    # is empty.
    breakdown = await net_worth_calculator.calculate(db, user_id)
    net_worth = breakdown.total
    level = detect_level(net_worth)

    breakdown_lines: list[str] = []
    if breakdown.by_type:
        for asset_type, value in sorted(
            breakdown.by_type.items(), key=lambda kv: kv[1], reverse=True
        ):
            label = get_label(asset_type)
            pct = float(value / net_worth * 100) if net_worth > 0 else 0.0
            breakdown_lines.append(
                f"  • {label}: {format_money_short(value)} ({pct:.1f}%)"
            )
    breakdown_str = (
        "\n".join(breakdown_lines) if breakdown_lines else "  (chưa khai báo tài sản)"
    )

    income_stmt = select(IncomeStream).where(
        IncomeStream.user_id == user_id,
        IncomeStream.is_active.is_(True),
    )
    income_streams = list((await db.execute(income_stmt)).scalars().all())
    # Phase 3.8 Epic 2: aggregate via monthly_equivalent so non-monthly
    # streams (annual dividend, quarterly interest) get the right
    # share of the headline income figure.
    income_total = sum((s.monthly_equivalent for s in income_streams), Decimal(0))
    if income_streams:
        income_str = (
            f"{format_money_full(income_total)}/tháng từ "
            f"{len(income_streams)} nguồn"
        )
    elif monthly_income > 0:
        income_str = f"{format_money_full(monthly_income)}/tháng (legacy field)"
    else:
        income_str = "chưa khai báo"

    context = f"""Thị trường hiện tại:
{chr(10).join(market_data) if market_data else '  Chưa có dữ liệu'}

Hồ sơ tài chính:
  • Wealth level: {_level_label_vi(level)}
  • Tổng tài sản (net worth): {format_money_full(net_worth) if net_worth > 0 else 'chưa có dữ liệu'}
  • Phân bổ tài sản:
{breakdown_str}
  • Income streams: {income_str}
  • Chi tiêu tháng này: {float(total_expense):,.0f} VND
  • Mục tiêu: {', '.join(f'{g.name} ({float(g.current_amount):,.0f}/{float(g.target_amount):,.0f})' for g in goals) if goals else 'Chưa có'}"""

    prompt = f"""Bạn là Trợ lý Tài sản advisor. Dựa trên context dưới đây, đưa ra gợi ý đầu tư cho user tại Việt Nam.

{context}

=== HƯỚNG DẪN THEO LEVEL ===
{_INVEST_LEVEL_GUIDANCE[level]}

=== YÊU CẦU OUTPUT ===
1. Nhận định ngắn thị trường (2-3 câu).
2. 1-2 gợi ý cụ thể có lý do, FRAMED theo wealth level (xem hướng dẫn).
3. KHÔNG khuyên cổ phiếu/coin cụ thể. KHÔNG hứa lợi nhuận.
4. Disclaimer cuối: "Đây chỉ là gợi ý tham khảo, không phải lời khuyên đầu tư chuyên nghiệp."

Viết ngắn gọn (max 200 từ), dùng emoji phù hợp."""

    advice = await call_llm(
        prompt,
        task_type="investment_advice",
        db=db,
        user_id=user_id,
        use_cache=False,
    )

    # Log the advice
    log = InvestmentLog(
        user_id=user_id,
        log_date=today,
        market_context={
            "snapshots": [
                {
                    "code": s.asset_code,
                    "price": float(s.price) if s.price else None,
                    "change_1d": float(s.change_1d_pct) if s.change_1d_pct else None,
                }
                for s in snapshots
            ]
        },
        user_financial_context={
            "monthly_income": monthly_income,
            "total_expense": float(total_expense),
            "wealth_level": level.value,
            "net_worth": float(net_worth),
            "asset_breakdown": {k: float(v) for k, v in breakdown.by_type.items()},
            "income_streams_total_monthly": float(income_total),
            "goals": [
                {
                    "name": g.name,
                    "current": float(g.current_amount),
                    "target": float(g.target_amount),
                }
                for g in goals
            ],
        },
        recommendation=advice,
    )
    db.add(log)
    await db.flush()

    return advice
