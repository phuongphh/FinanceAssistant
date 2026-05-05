"""Format Tier 2 tool results into Bé Tiền-flavored Vietnamese text.

Two design choices worth knowing:

1. **Wealth-level adaptive.** Reuse ``intent.wealth_adapt.resolve_style``
   so the agent's voice matches every other handler — Starter sees
   simple language + encouragement, HNW sees % allocation + minimal
   chrome. Reusing the existing module means we don't fork the tone
   logic.

2. **Empty results are first-class.** Every formatter has an explicit
   "no data" branch with a friendly Vietnamese message + suggested
   next action. Falling back to a stock "no results" string makes
   the bot feel broken.

These functions are pure: they take typed dicts (Pydantic dumps from
``DBAgentResult.result``) plus the user, and return a string. The
formatter never touches the DB — that's the agent's job.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.tier2.db_agent import DBAgentResult
from backend.bot.formatters.money import format_money_full, format_money_short
from backend.intent.wealth_adapt import LevelStyle, decorate, resolve_style
from backend.models.user import User
from backend.wealth.asset_types import get_label as asset_type_label

# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------


async def format_db_agent_response(
    result: DBAgentResult,
    user: User,
    db: AsyncSession,
    query: str,
) -> str:
    """Pick the right formatter for whichever tool the agent called.

    Falls back to ``fallback_text`` (the LLM's plain reply, when it
    declined to pick a tool) or a generic apology — never raises so
    the caller's error path is short."""
    if not result.success:
        if result.fallback_text:
            return result.fallback_text.strip()
        return _generic_apology(user)

    style = await resolve_style(db, user)
    payload = result.result or {}
    tool = result.tool_called

    if tool == "get_assets":
        body = format_assets_response(payload, user, query, style, result.tool_args or {})
    elif tool == "get_transactions":
        body = format_transactions_response(payload, user, query, style)
    elif tool == "compute_metric":
        body = format_metric_response(payload, user, style)
    elif tool == "compare_periods":
        body = format_comparison_response(payload, user, style)
    elif tool == "get_market_data":
        body = format_market_response(payload, user, style)
    else:
        body = _generic_apology(user)

    return decorate(body, style)


# ---------------------------------------------------------------------------
# get_assets
# ---------------------------------------------------------------------------


def format_assets_response(
    payload: dict[str, Any],
    user: User,
    query: str,
    style: LevelStyle,
    tool_args: dict[str, Any],
) -> str:
    """Render the asset list with gain indicators (🟢 / 🔴 / ⚪).

    Header adapts to the filter shape so the user immediately sees
    what was asked: "Mã đang lãi" vs "Top 3 mã lãi" vs the generic
    "Tài sản hiện tại"."""
    assets = payload.get("assets") or []
    count = payload.get("count", len(assets))
    name = user.display_name or "bạn"

    if count == 0:
        return _empty_assets_message(tool_args, name)

    header = _assets_header(tool_args, name, count)
    lines = [header, ""]

    for a in assets:
        lines.append(_format_asset_line(a, style))

    total = Decimal(str(payload.get("total_value", 0)))
    if total > 0 and len(assets) > 1:
        lines.append("")
        lines.append(f"Tổng giá trị: {format_money_short(float(total))}")

    return "\n".join(lines)


def _empty_assets_message(tool_args: dict[str, Any], name: str) -> str:
    """Friendlier than 'no results'.

    We try to mention what the filter asked for so the user knows
    we understood — bare "không có" makes the bot feel robotic."""
    filt = (tool_args.get("filter") or {}) if tool_args else {}
    gain_pct = filt.get("gain_pct") or {}
    asset_type = filt.get("asset_type")

    if gain_pct.get("gt") is not None and gain_pct.get("gt") >= 0:
        return f"{name} chưa có mã nào đang lãi 🤔\n\nMuốn xem tổng quan tài sản không?"
    if gain_pct.get("lt") is not None and gain_pct.get("lt") <= 0:
        return f"Tin vui {name}: không có mã nào đang lỗ 🟢"
    if asset_type:
        return (
            f"{name} chưa có {asset_type_label(asset_type)} nào cả 🤔\n\n"
            "Tap /themtaisan để thêm vào nhé."
        )
    return (
        f"{name} chưa có tài sản nào cả!\n\n"
        "Tap /themtaisan để Bé Tiền giúp theo dõi 💎"
    )


def _assets_header(tool_args: dict[str, Any], name: str, count: int) -> str:
    filt = (tool_args.get("filter") or {}) if tool_args else {}
    gain_pct = filt.get("gain_pct") or {}
    sort = (tool_args.get("sort") or "") if tool_args else ""
    limit = tool_args.get("limit") if tool_args else None
    asset_type = filt.get("asset_type")

    asset_word = (
        asset_type_label(asset_type) if asset_type else "tài sản"
    )

    if limit and "gain_pct" in sort:
        return f"🏆 Top {limit} {asset_word} lãi nhất của {name}:"
    if limit and "value" in sort:
        return f"💎 Top {limit} {asset_word} lớn nhất của {name}:"
    if gain_pct.get("gt") is not None and gain_pct.get("gt") >= 0:
        return f"🟢 {asset_word.capitalize()} đang lãi của {name}:"
    if gain_pct.get("lt") is not None and gain_pct.get("lt") <= 0:
        return f"🔴 {asset_word.capitalize()} đang lỗ của {name}:"
    if asset_type:
        return f"💎 {asset_word.capitalize()} của {name} ({count}):"
    return f"💎 Tài sản của {name} ({count}):"


def _format_asset_line(asset: dict[str, Any], style: LevelStyle) -> str:
    """One-line per asset.

    Format chosen so it fits Telegram mobile width:
      <indicator> <name> — <value> (<+pct%>)

    Drops the pct for STARTER level (where gain noise just confuses
    the user) — matches Phase 3.5 query_assets behavior."""
    name = asset.get("ticker") or asset.get("name")
    value = float(asset.get("current_value") or 0)
    gain_pct = asset.get("gain_pct")

    indicator = "⚪"
    if gain_pct is not None:
        if gain_pct > 0:
            indicator = "🟢"
        elif gain_pct < 0:
            indicator = "🔴"

    line = f"{indicator} {name} — {format_money_short(value)}"
    if gain_pct is not None and style.show_pnl_pct:
        sign = "+" if gain_pct >= 0 else ""
        line += f" ({sign}{gain_pct:.1f}%)"
    return line


# ---------------------------------------------------------------------------
# get_transactions
# ---------------------------------------------------------------------------


def format_transactions_response(
    payload: dict[str, Any],
    user: User,
    query: str,
    style: LevelStyle,
) -> str:
    txs = payload.get("transactions") or []
    name = user.display_name or "bạn"
    if not txs:
        return f"{name} chưa có giao dịch nào trong khoảng này."

    lines = [f"📒 Giao dịch ({len(txs)}):", ""]
    for t in txs:
        d = t.get("date")
        merchant = t.get("merchant") or t.get("category") or "—"
        amount = float(t.get("amount") or 0)
        lines.append(f"• {d}  {merchant}  {format_money_short(amount)}")

    total = float(payload.get("total_amount") or 0)
    if total > 0:
        lines.append("")
        lines.append(f"Tổng: {format_money_full(total)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# compute_metric
# ---------------------------------------------------------------------------


_METRIC_LABELS_VI = {
    "saving_rate": "Tỷ lệ tiết kiệm",
    "net_worth_growth": "Tăng trưởng net worth",
    "portfolio_total_gain": "Tổng lãi portfolio",
    "portfolio_total_gain_pct": "Tổng lãi portfolio (%)",
    "average_monthly_expense": "Chi tiêu trung bình/tháng",
    "expense_to_income_ratio": "Tỷ lệ chi/thu",
    "diversification_score": "Điểm đa dạng hoá",
}


def format_metric_response(
    payload: dict[str, Any],
    user: User,
    style: LevelStyle,
) -> str:
    metric = payload.get("metric_name", "metric")
    label = _METRIC_LABELS_VI.get(metric, metric)
    value = payload.get("value", 0)
    unit = payload.get("unit", "")
    context = payload.get("context")

    if unit == "vnd":
        rendered = format_money_full(float(value))
    elif unit == "percent":
        sign = "+" if value > 0 else ""
        rendered = f"{sign}{value:.2f}%"
    else:  # score
        rendered = f"{value:.1f}/100"

    body = f"📊 {label}: *{rendered}*"
    if context:
        body += f"\n_{context}_"
    return body


# ---------------------------------------------------------------------------
# compare_periods
# ---------------------------------------------------------------------------


def format_comparison_response(
    payload: dict[str, Any],
    user: User,
    style: LevelStyle,
) -> str:
    metric = payload.get("metric", "metric")
    label_a = payload.get("period_a_label", "A")
    label_b = payload.get("period_b_label", "B")
    a = float(payload.get("period_a_value") or 0)
    b = float(payload.get("period_b_value") or 0)
    diff = float(payload.get("diff_absolute") or 0)
    diff_pct = float(payload.get("diff_percent") or 0)

    sign = "+" if diff >= 0 else ""
    arrow = "📈" if diff > 0 else ("📉" if diff < 0 else "➡️")

    return (
        f"⚖️ So sánh {metric}:\n\n"
        f"• {label_a.capitalize()}: {format_money_short(a)}\n"
        f"• {label_b.capitalize()}: {format_money_short(b)}\n\n"
        f"{arrow} Chênh lệch: {sign}{format_money_short(diff)} "
        f"({sign}{diff_pct:.1f}%)"
    )


# ---------------------------------------------------------------------------
# get_market_data
# ---------------------------------------------------------------------------


def format_market_response(
    payload: dict[str, Any],
    user: User,
    style: LevelStyle,
) -> str:
    ticker = payload.get("ticker", "?")
    asset_name = payload.get("asset_name") or ticker
    price = float(payload.get("current_price") or 0)
    change_pct = payload.get("change_pct")
    period = payload.get("period", "1d")
    note = payload.get("note")

    if price <= 0:
        return f"⚠️ Chưa có dữ liệu thị trường cho {ticker}.\n_{note or ''}_".strip()

    arrow = "➡️"
    sign = ""
    if change_pct is not None:
        sign = "+" if change_pct >= 0 else ""
        arrow = "📈" if change_pct > 0 else ("📉" if change_pct < 0 else "➡️")

    lines = [
        f"📊 *{asset_name}* ({ticker})",
        f"Giá: {format_money_short(price)}",
    ]
    if change_pct is not None:
        lines.append(f"{arrow} {sign}{change_pct:.2f}% ({period})")
    if note:
        lines.append(f"_{note}_")

    if payload.get("user_owns"):
        qty = payload.get("user_quantity")
        holding = float(payload.get("user_holding_value") or 0)
        lines.append("")
        if qty:
            lines.append(
                f"Bạn đang nắm: {qty:g} đơn vị "
                f"(≈ {format_money_short(holding)})"
            )
        else:
            lines.append(f"Bạn đang nắm: ≈ {format_money_short(holding)}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _generic_apology(user: User) -> str:
    name = user.display_name or "bạn"
    return (
        f"Mình chưa hiểu rõ ý {name}, có thể hỏi lại cụ thể hơn được không? 🤔"
    )
