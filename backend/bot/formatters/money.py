"""Format tiền Việt — ngắn gọn (45k / 2tr350 / 1tỷ200) và đầy đủ (45,000đ).

Quy tắc làm tròn: số tiền hiển thị chỉ làm tròn đến đơn vị NGHÌN ĐỒNG, không bao giờ
mất chính xác ở mức triệu (ví dụ 2,350,000đ → "2tr350", KHÔNG phải "2.4tr").
Ở thang tỷ, làm tròn đến triệu để giữ chuỗi đủ ngắn cho UI mobile.
"""

from decimal import ROUND_HALF_UP, Decimal


def _round_half_up(value: float, divisor: int) -> int:
    """Round ``value / divisor`` half-away-from-zero to int.

    Python's built-in ``round`` uses banker's rounding (round-half-even), which
    would turn 2,350,500 into 2,350 (then "2tr350") instead of the user-expected
    2,351 ("2tr351"). Use Decimal ROUND_HALF_UP for predictable display.
    """
    quotient = Decimal(int(value)) / Decimal(divisor) if isinstance(value, int) else Decimal(repr(value)) / Decimal(divisor)
    return int(quotient.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def format_money_short(amount) -> str:
    """Format ngắn gọn kiểu Việt Nam, giữ chính xác đến nghìn đồng.

    Examples:
        >>> format_money_short(500)
        '500đ'
        >>> format_money_short(45_000)
        '45k'
        >>> format_money_short(45_500)
        '46k'
        >>> format_money_short(2_350_000)
        '2tr350'
        >>> format_money_short(2_350_400)
        '2tr350'
        >>> format_money_short(2_350_500)
        '2tr351'
        >>> format_money_short(25_000_000)
        '25tr'
        >>> format_money_short(1_500_000)
        '1tr500'
        >>> format_money_short(1_200_000_000)
        '1tỷ200'
        >>> format_money_short(2_000_000_000)
        '2 tỷ'
        >>> format_money_short(0)
        '0đ'
        >>> format_money_short(-2_350_000)
        '-2tr350'
    """
    value = float(amount) if not isinstance(amount, Decimal) else float(amount)
    sign = "-" if value < 0 else ""
    raw = abs(value)

    if raw < 1:
        return "0đ"
    if raw < 1_000:
        return f"{sign}{_round_half_up(raw, 1)}đ"

    # Round to nearest 1,000đ to preserve thousand precision everywhere.
    thousands_total = _round_half_up(raw, 1000)
    if thousands_total < 1_000:
        return f"{sign}{thousands_total}k"

    if thousands_total < 1_000_000:
        millions, thousands = divmod(thousands_total, 1000)
        if thousands == 0:
            return f"{sign}{millions}tr"
        return f"{sign}{millions}tr{thousands:03d}"

    # Tỷ range: round to nearest 1tr (sub-tr precision <0.001% — not useful).
    tr_total = _round_half_up(raw, 1_000_000)
    billions, millions = divmod(tr_total, 1000)
    if millions == 0:
        return f"{sign}{billions} tỷ"
    return f"{sign}{billions}tỷ{millions:03d}"


def format_money_full(amount) -> str:
    """Format đầy đủ với dấu phẩy ngăn cách hàng nghìn.

    Examples:
        >>> format_money_full(45000)
        '45,000đ'
        >>> format_money_full(1500000)
        '1,500,000đ'
    """
    return f"{int(round(float(amount))):,}đ"
