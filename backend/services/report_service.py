import logging
import re
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.money import format_money_full, format_money_short
from backend.intent.extractors._normalize import strip_diacritics
from backend.models.expense import Expense
from backend.models.goal import Goal
from backend.models.report import MonthlyReport
from backend.models.user import User
from backend.config.categories import get_category
from backend.services.dashboard_service import get_user_by_telegram_id
from backend.services.llm_service import call_llm
from backend.wealth import income_types as _income_types
from backend.wealth.asset_types import get_label
from backend.wealth.ladder import WealthLevel, detect_level
from backend.wealth.models.income_stream import IncomeStream
from backend.wealth.services import net_worth_calculator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Intent detection + month parsing (consumed by the bot handler layer)
# ---------------------------------------------------------------------------

_REPORT_KEYWORDS = frozenset(
    [
        "báo cáo",
        "bao cao",
        "tổng chi tiêu",
        "tong chi tieu",
        "chi tiêu tháng",
        "chi tieu thang",
        # Expense-style phrases are handled by the Phase 3.5 intent
        # pipeline (query_expenses + time_range), not this legacy
        # monthly financial report fast-path.
        "report",
        # Removed "tháng trước tôi" / "thang truoc toi": too greedy, swallowed
        # natural-language expense queries like "tháng trước tôi chi tiêu bao
        # nhiêu?" that the Phase 3.5 intent pipeline routes to query_expenses
        # with time_range=last_month.
    ]
)


def is_report_query(text: str) -> bool:
    """Return True for monthly report requests, not transaction listings.

    Phrases like "báo cáo giao dịch hôm qua" should go through the
    intent pipeline as ``query_expenses`` so the time range (including
    daily ranges) is respected instead of generating the monthly CFO
    report. Likewise dashboard / miniapp asks bypass this fast path —
    the NLU layer owns ``nav_expense_dashboard`` and the user expects
    the interactive miniapp, not a pre-rendered text report.
    """
    lower = text.lower()
    normalized = strip_diacritics(lower)

    if "giao dich" in normalized:
        return False
    # "báo cáo chi tiêu tháng này" should route to the Phase 3.5
    # query_expenses handler (time range aware), not the legacy monthly
    # financial report generator.
    if "chi tieu" in normalized or "chi phi" in normalized:
        return False
    if (
        "dashboard" in normalized
        or "bang dieu khien" in normalized
        or "mini app" in normalized
        or "miniapp" in normalized
    ):
        return False

    return any(kw in lower for kw in _REPORT_KEYWORDS)


def extract_month_key(text: str) -> str:
    """Best-effort month extraction from natural language. Defaults to current month."""
    today = date.today()
    lower = text.lower()

    if "tháng trước" in lower or "thang truoc" in lower:
        m = today.month - 1 or 12
        y = today.year if today.month > 1 else today.year - 1
        return f"{y}-{m:02d}"

    # "tháng 3" or "tháng 03"
    match = re.search(r"tháng\s+(\d{1,2})", lower)
    if match:
        month = int(match.group(1))
        if 1 <= month <= 12:
            year = today.year if month <= today.month else today.year - 1
            return f"{year}-{month:02d}"

    # Explicit "2026-03"
    match = re.search(r"(\d{4})-(\d{2})", text)
    if match:
        return f"{match.group(1)}-{match.group(2)}"

    return today.strftime("%Y-%m")


async def process_report_request(db: AsyncSession, telegram_id: int, text: str) -> str:
    """Full orchestration: user lookup → month parsing → report generation → text.

    Returns a ready-to-send Telegram message string in all cases (including
    errors and unregistered users), so callers never need to catch exceptions.
    """
    user = await get_user_by_telegram_id(db, telegram_id)
    if not user:
        return "Bạn chưa đăng ký. Gửi /start để bắt đầu."

    month_key = extract_month_key(text)
    try:
        report = await generate_monthly_report(db, user.id, month_key)
        return report.report_text or "Không có dữ liệu chi tiêu."
    except Exception:
        logger.exception(
            "Report generation failed for user %s month %s", user.id, month_key
        )
        return "❌ Không thể tổng hợp báo cáo. Thử lại sau nhé."


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _prev_month_key(month_key: str) -> str:
    year, month = int(month_key[:4]), int(month_key[5:7])
    if month == 1:
        return f"{year - 1}-12"
    return f"{year}-{month - 1:02d}"


# ---------------------------------------------------------------------------
# Wealth-aware context for LLM prompt
# ---------------------------------------------------------------------------
#
# Issue #153: prompt cũ generate insight/advice giống một finance app cho
# người chưa có tài sản — comment "20tr/tháng đầu tư là rất lớn" với HNW
# user có 120 tỷ tài sản là sai context hoàn toàn. Personal CFO product
# phải frame mọi advice theo ladder của user (Starter / Young Prof /
# Mass Affluent / HNW) và data thực tế (net worth, asset breakdown,
# income streams), không chỉ cashflow tháng đó.

# Vietnamese-first bilingual labels — same convention as
# ``advisory._level_to_vi``. The English half stays in the parenthetical
# so the LLM stays grounded in the standard finance tier names without
# echoing English at the user.
_LEVEL_LABEL_VI = {
    WealthLevel.STARTER: "Khởi Đầu (<30tr)",
    WealthLevel.YOUNG_PROFESSIONAL: "Trẻ Năng Động (30tr – 300tr)",
    WealthLevel.MASS_AFFLUENT: "Trung Lưu Vững (300tr – 3 tỷ)",
    WealthLevel.HIGH_NET_WORTH: "Tinh Hoa (3 tỷ – 30 tỷ)",
    WealthLevel.VIP: "Đỉnh Cao (>30 tỷ)",
}

# Per-level guidance for the LLM. Keyed on WealthLevel; controls the tone
# and analytical lens of "Điểm chính" + "Lời khuyên". HNW must NEVER get
# budget-control framing — strategic CFO frame only.
_LEVEL_GUIDANCE = {
    WealthLevel.STARTER: (
        "Tone: ấm áp, khuyến khích, giáo dục, không thuật ngữ chuyên ngành.\n"
        "Trọng tâm: xây thói quen tiết kiệm, tránh phán xét khắc nghiệt về chi tiêu.\n"
        "Tránh: dùng tỷ lệ % tài sản (chưa có ý nghĩa), gợi ý phức tạp.\n"
        "Kết bài: 1 hành động đơn giản cho tuần tới (vd: đặt mục tiêu nhỏ)."
    ),
    WealthLevel.YOUNG_PROFESSIONAL: (
        "Tone: thân thiện, định hướng tăng trưởng.\n"
        "Trọng tâm: tỷ lệ tiết kiệm, bắt đầu đầu tư, cân bằng chi tiêu và đầu tư.\n"
        "Tránh: phân tích danh mục nặng (chưa đủ tài sản để có ý nghĩa).\n"
        "Kết bài: 1 gợi ý hướng đến tăng trưởng (tăng tỷ lệ đầu tư, mở thêm nguồn thu)."
    ),
    WealthLevel.MASS_AFFLUENT: (
        "Tone: Trợ lý Tài sản, có dữ liệu, ít cảm xúc.\n"
        "Trọng tâm: phân bổ, đa dạng hoá, tối ưu dòng tiền, "
        "tỷ lệ tiết kiệm trong bối cảnh tổng tài sản.\n"
        "Khung chi tiêu theo % tổng tài sản (vd: 5tr ăn uống = 0.5% tổng tài sản), "
        "KHÔNG nhận xét tuyệt đối '5tr là nhiều/ít'.\n"
        "Kết bài: 1 hành động mang tính chiến lược (tái cân bằng, tăng "
        "thu nhập thụ động, bổ sung dữ liệu còn thiếu)."
        "\nNgôn ngữ: 100% tiếng Việt, không dùng thuật ngữ tiếng Anh."
    ),
    WealthLevel.HIGH_NET_WORTH: (
        "Tone: Trợ lý Tài sản chiến lược, không 'nhắc nhở' sinh viên.\n"
        "Trọng tâm: tỷ trọng phân bổ danh mục %, mức bao phủ của thu nhập "
        "thụ động, tỷ lệ chi tiêu / tổng tài sản, dữ liệu còn thiếu "
        "(thu nhập thụ động, cổ tức, lãi cho thuê BĐS chưa được ghi nhận).\n"
        "TUYỆT ĐỐI tránh: nhận xét tuyệt đối ('20tr là rất lớn'), "
        "câu nhắc cuối tháng kiểu 'để biết lời/lỗ', tone nhắc nhở "
        "sinh viên.\n"
        "Khung mọi con số theo % tổng tài sản. Mục tiêu nhỏ (vd: "
        "50tr mua xe) phải ghi nhận là không đáng kể so với tổng tài sản và "
        "hỏi user có muốn phân bổ từ tài sản hiện có không.\n"
        "Kết bài: 1 đề xuất hành động kiểu Trợ lý Tài sản (rà soát phân "
        "bổ, ghi nhận thu nhập thụ động, tái cân bằng), KHÔNG 'để mình "
        "nhắc cuối tháng'."
        "\nNgôn ngữ: 100% tiếng Việt, không dùng thuật ngữ tiếng Anh."
    ),
    WealthLevel.VIP: (
        "Tone: Trợ lý Tài sản cấp cao, chiến lược, ngắn gọn.\n"
        "Trọng tâm: bảo toàn tài sản đa thế hệ, hoạch định thừa kế, "
        "các kênh đầu tư thay thế, cấu trúc thuế/pháp lý, tư duy "
        "văn phòng quản lý tài sản gia đình, tầm nhìn 10+ năm.\n"
        "TUYỆT ĐỐI tránh: khung dòng tiền/ngân sách, nhận xét tuyệt "
        "đối về chi tiêu, tone nhắc nhở. Mục tiêu cá nhân nhỏ (xe, du "
        "lịch) phải ghi nhận là nhiễu — không xếp vào review hàng tuần.\n"
        "Khung mọi con số theo % danh mục và rủi ro với tài sản kế thừa.\n"
        "Kết bài: 1 đề xuất chiến lược (tái cân bằng, rà soát cấu trúc "
        "người được uỷ thác / gia đình, kiểm tra phân bổ kênh thay thế)."
        "\nNgôn ngữ: 100% tiếng Việt, không dùng thuật ngữ tiếng Anh."
    ),
}


async def _build_wealth_context(
    db: AsyncSession, user_id: uuid.UUID, total_expense: float
) -> dict:
    """Assemble wealth-level data injected into the report prompt.

    Each component degrades gracefully — a user with no assets sees
    ``net_worth=0`` and falls into Starter band; missing income streams
    just show ``"chưa khai báo"`` rather than fabricating numbers.
    """
    breakdown = await net_worth_calculator.calculate(db, user_id)
    net_worth = breakdown.total
    level = detect_level(net_worth)

    # Asset breakdown lines, sorted by value desc.
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
        "\n".join(breakdown_lines)
        if breakdown_lines
        else "  (chưa khai báo tài sản nào)"
    )

    # Income streams. Phase 3.8 Epic 2: read monthly_equivalent so
    # quarterly dividends / annual interest don't double-count.
    stmt = select(IncomeStream).where(
        IncomeStream.user_id == user_id,
        IncomeStream.is_active.is_(True),
    )
    streams = list((await db.execute(stmt)).scalars().all())
    income_total = sum((s.monthly_equivalent for s in streams), Decimal(0))
    if streams:
        income_lines = [
            f"  • {s.name} ({_income_types.get_label(s.stream_type)}): "
            f"{format_money_short(s.monthly_equivalent)}/tháng"
            for s in streams
        ]
        income_str = (
            f"{format_money_full(income_total)}/tháng từ "
            f"{len(streams)} nguồn:\n" + "\n".join(income_lines)
        )
    else:
        income_str = "  (chưa khai báo nguồn thu nhập — dữ liệu còn thiếu đáng chú ý)"

    # Expense vs net worth ratio — only meaningful for Mass Affluent+.
    expense_pct_of_nw = None
    if net_worth > 0:
        expense_pct_of_nw = float(Decimal(total_expense) / net_worth * 100)

    return {
        "level": level,
        "level_label_vi": _LEVEL_LABEL_VI[level],
        "guidance": _LEVEL_GUIDANCE[level],
        "net_worth": net_worth,
        "net_worth_str": (
            format_money_full(net_worth) if net_worth > 0 else "chưa có dữ liệu"
        ),
        "asset_count": breakdown.asset_count,
        "breakdown_str": breakdown_str,
        "income_total": income_total,
        "income_str": income_str,
        "expense_pct_of_nw": expense_pct_of_nw,
    }


def _build_report_prompt(report_context: str, wealth_ctx: dict) -> str:
    """Compose the ladder-aware monthly-report LLM prompt.

    The prompt explicitly tells the LLM the user's wealth band and
    tone constraints — so an HNW user never gets "20tr/tháng là rất
    lớn" framing, and a Starter never gets portfolio-rebalance jargon.
    """
    expense_pct_str = (
        f"{wealth_ctx['expense_pct_of_nw']:.3f}% tổng tài sản"
        if wealth_ctx["expense_pct_of_nw"] is not None
        else "không tính được (chưa có tài sản khai báo)"
    )

    return (
        "Bạn là Trợ lý Tài sản — không phải ứng dụng quản lý chi tiêu "
        "cho người mới đi làm.\n"
        "Viết báo cáo tài chính tháng cho người dùng Telegram dưới đây.\n\n"
        "=== HỒ SƠ NGƯỜI DÙNG ===\n"
        f"Phân khúc tài sản: {wealth_ctx['level_label_vi']}\n"
        f"Tổng tài sản: {wealth_ctx['net_worth_str']}\n"
        f"Số tài sản đang theo dõi: {wealth_ctx['asset_count']}\n"
        f"Phân bổ tài sản:\n{wealth_ctx['breakdown_str']}\n"
        f"Nguồn thu nhập:\n{wealth_ctx['income_str']}\n"
        f"Chi tiêu tháng / tổng tài sản: {expense_pct_str}\n\n"
        "=== DỮ LIỆU THÁNG ===\n"
        f"{report_context}\n\n"
        "=== HƯỚNG DẪN VIẾT THEO PHÂN KHÚC ===\n"
        f"{wealth_ctx['guidance']}\n\n"
        "=== YÊU CẦU OUTPUT ===\n"
        "1. Dùng emoji phù hợp, định dạng thân thiện Telegram; viết đầy "
        "đủ ý, không cắt câu giữa chừng.\n"
        "2. Có 2 phần: '✅ Điểm chính' (3-4 gạch đầu dòng) + "
        "'💡 Lời khuyên' (2-3 gạch đầu dòng, hướng tới hành động).\n"
        "2b. Độ dài mục tiêu: khoảng 180-260 từ để đủ ngữ cảnh, không "
        "quá ngắn.\n"
        "3. Mọi nhận xét về số tiền PHẢI khung theo phân khúc: với "
        "Khá giả / Giàu, dùng % tổng tài sản thay vì nhận xét tuyệt đối. "
        "Với Khởi đầu / Trẻ đi làm, có thể nhận xét tuyệt đối nhưng "
        "giọng văn khuyến khích.\n"
        "4. Nếu dữ liệu còn thiếu (thu nhập, thu nhập thụ động, tài sản "
        "chưa khai), ghi nhận với giọng văn phù hợp phân khúc — KHÔNG "
        "dùng câu chung chung 'chưa khai báo'.\n"
        "5. Kết bài: 1 câu kêu gọi hành động phù hợp phân khúc (xem "
        "hướng dẫn). KHÔNG kết bằng 'để mình nhắc cuối tháng' với người "
        "dùng phân khúc Giàu trở lên.\n"
        "6. Nếu người dùng có mục tiêu đang theo dõi, khung số tiền mục "
        "tiêu theo % tổng tài sản (với phân khúc Giàu, 50tr là 0.04% "
        "tổng tài sản → không đáng kể, có thể trích từ tài sản hiện có).\n"
        "\n=== NGÔN NGỮ ===\n"
        "Toàn bộ báo cáo PHẢI 100% bằng tiếng Việt. Không dùng thuật "
        "ngữ tiếng Anh (net worth → tổng tài sản, passive income → "
        "thu nhập thụ động, cashflow → dòng tiền, allocate → phân bổ, "
        "rebalance → tái cân bằng, saving rate → tỷ lệ tiết kiệm)."
    )


async def _get_breakdown(db: AsyncSession, user_id: uuid.UUID, month_key: str) -> dict:
    stmt = (
        select(Expense.category, func.sum(Expense.amount).label("total"))
        .where(
            Expense.user_id == user_id,
            Expense.month_key == month_key,
            Expense.deleted_at.is_(None),
            Expense.transaction_type == "expense",
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
    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    monthly_income = (
        float(user.monthly_income) if user and user.monthly_income else None
    )

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

    # Goal progress snapshot — Phase 3.8 Epic 5: is_active → status,
    # goal_name → name.
    goals_stmt = select(Goal).where(
        Goal.user_id == user_id,
        Goal.status == "active",
        Goal.deleted_at.is_(None),
    )
    goals = (await db.execute(goals_stmt)).scalars().all()
    goal_progress = [
        {
            "name": g.name,
            "target": float(g.target_amount),
            "current": float(g.current_amount),
            "pct": (
                round((float(g.current_amount) / float(g.target_amount)) * 100, 1)
                if g.target_amount
                else 0
            ),
        }
        for g in goals
    ]

    # Generate report text via LLM
    report_context = f"""Tháng: {month_key}
Tổng chi tiêu: {total_expense:,.0f} VND
Thu nhập: {f'{monthly_income:,.0f} VND' if monthly_income else 'Chưa khai báo'}
Tiết kiệm: {f'{savings_amount:,.0f} VND ({savings_rate}%)' if savings_amount is not None else 'N/A'}

Chi tiết theo danh mục:
{chr(10).join(f'  • {get_category(cat).name_vi}: {amt:,.0f} VND' for cat, amt in sorted(breakdown.items(), key=lambda x: -x[1]))}

{f'So với tháng trước ({prev_key}): tổng {prev_total:,.0f} VND, thay đổi {vs_previous["total_diff_pct"]:+.1f}%' if vs_previous else 'Không có dữ liệu tháng trước'}

Mục tiêu:
{chr(10).join(f'  • {g["name"]}: {g["current"]:,.0f}/{g["target"]:,.0f} VND ({g["pct"]}%)' for g in goal_progress) if goal_progress else '  Chưa có mục tiêu'}"""

    # Inject wealth-level context so the LLM frames advice for the
    # user's actual ladder rung — not a one-size-fits-all "finance app"
    # tone (issue #153).
    try:
        wealth_ctx = await _build_wealth_context(db, user_id, total_expense)
    except Exception:
        logger.exception(
            "Failed to build wealth context for report prompt; falling back"
        )
        wealth_ctx = None

    try:
        if wealth_ctx is not None:
            prompt = _build_report_prompt(report_context, wealth_ctx)
        else:
            # Defensive fallback — keep the report functional even if
            # the wealth subsystem is unhealthy.
            prompt = (
                "Viết báo cáo tài chính tháng ngắn gọn, thân thiện cho 1 "
                "người dùng Telegram. Dùng emoji phù hợp. Tóm tắt điểm "
                f"chính và đưa ra 1-2 lời khuyên.\n\n{report_context}"
            )
        report_text = await call_llm(
            prompt,
            task_type="report_text",
            db=db,
            user_id=user_id,
            use_cache=False,
        )
    except Exception:
        report_text = report_context  # Fallback to raw data

    # Upsert report
    existing = (
        await db.execute(
            select(MonthlyReport).where(
                MonthlyReport.user_id == user_id,
                MonthlyReport.month_key == month_key,
            )
        )
    ).scalar_one_or_none()

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
