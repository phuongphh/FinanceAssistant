"""Unicode progress bars cho tin nhắn Telegram.

Dùng ký tự block để nhìn đẹp và render nhất quán trên cả iOS và Android.
"""


def make_progress_bar(
    current: float,
    total: float,
    width: int = 10,
    filled_char: str = "█",
    empty_char: str = "░",
) -> str:
    """Tạo progress bar kèm label phần trăm.

    Examples:
        >>> make_progress_bar(50, 100)
        '█████░░░░░ 50%'
        >>> make_progress_bar(150, 100)
        '██████████ 150%'
        >>> make_progress_bar(0, 0)
        '░░░░░░░░░░ 0%'
    """
    if total <= 0:
        return f"{empty_char * width} 0%"

    ratio = current / total
    percentage = ratio * 100
    filled_count = max(0, min(width, int(ratio * width)))
    empty_count = width - filled_count
    bar = filled_char * filled_count + empty_char * empty_count
    return f"{bar} {percentage:.0f}%"


def make_category_bar(
    amount: float,
    max_amount: float,
    width: int = 10,
    filled_char: str = "█",
    empty_char: str = "░",
) -> str:
    """Progress bar cho category breakdown — không hiển thị label %."""
    if max_amount <= 0:
        return empty_char * width

    ratio = amount / max_amount
    filled_count = max(0, min(width, int(ratio * width)))
    empty_count = width - filled_count
    return filled_char * filled_count + empty_char * empty_count
