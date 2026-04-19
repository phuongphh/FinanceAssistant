"""Format tiền Việt — ngắn gọn (45k / 1.5tr / 1.2 tỷ) và đầy đủ (45,000đ)."""


def format_money_short(amount: float) -> str:
    """Format ngắn gọn kiểu Việt Nam.

    Dùng trong progress bar, báo cáo tóm tắt, chỗ không gian hẹp.

    Examples:
        >>> format_money_short(45000)
        '45k'
        >>> format_money_short(1500000)
        '1.5tr'
        >>> format_money_short(25000000)
        '25tr'
        >>> format_money_short(1200000000)
        '1.2 tỷ'
    """
    amount = float(amount)
    sign = "-" if amount < 0 else ""
    amount = abs(amount)

    if amount < 1000:
        return f"{sign}{int(amount)}đ"
    if amount < 1_000_000:
        value = amount / 1000
        formatted = f"{int(value)}" if value == int(value) else f"{value:.1f}"
        return f"{sign}{formatted}k"
    if amount < 1_000_000_000:
        value = amount / 1_000_000
        formatted = f"{int(value)}" if value == int(value) else f"{value:.1f}"
        return f"{sign}{formatted}tr"
    value = amount / 1_000_000_000
    formatted = f"{int(value)}" if value == int(value) else f"{value:.1f}"
    return f"{sign}{formatted} tỷ"


def format_money_full(amount: float) -> str:
    """Format đầy đủ với dấu phẩy ngăn cách hàng nghìn.

    Dùng trong tin nhắn xác nhận giao dịch, nơi cần chính xác tuyệt đối.

    Examples:
        >>> format_money_full(45000)
        '45,000đ'
        >>> format_money_full(1500000)
        '1,500,000đ'
    """
    return f"{int(round(amount)):,}đ"
