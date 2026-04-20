"""Common keyboard helpers.

Callback data convention:
    <prefix>:<resource_id>[:<extra>...]

Examples:
    edit_tx:<uuid>
    change_cat:<uuid>
    change_cat:<uuid>:food
    del_tx:<uuid>
    undo_tx:<uuid>
    confirm:delete:<uuid>
    cancel
"""
from typing import Final

TELEGRAM_CALLBACK_DATA_MAX_BYTES: Final[int] = 64


class CallbackPrefix:
    EDIT_TRANSACTION = "edit_tx"
    CHANGE_CATEGORY = "change_cat"
    DELETE_TRANSACTION = "del_tx"
    UNDO_TRANSACTION = "undo_tx"
    VIEW_REPORT = "view_report"
    SELECT_CATEGORY = "sel_cat"
    CONFIRM_ACTION = "confirm"
    CANCEL_ACTION = "cancel"


def parse_callback(data: str) -> tuple[str, list[str]]:
    """Parse `callback_data` thành `(prefix, args)`.

    Examples:
        >>> parse_callback("edit_tx:123")
        ('edit_tx', ['123'])
        >>> parse_callback("change_cat:abc:food")
        ('change_cat', ['abc', 'food'])
        >>> parse_callback("cancel")
        ('cancel', [])
    """
    parts = data.split(":")
    return parts[0], parts[1:]


def build_callback(prefix: str, *args: object) -> str:
    """Ghép callback string từ prefix + args với validation độ dài.

    Telegram giới hạn `callback_data` tối đa 64 bytes UTF-8.
    """
    if not prefix:
        raise ValueError("callback prefix must be non-empty")

    parts: list[str] = [prefix]
    for arg in args:
        piece = str(arg)
        if ":" in piece:
            raise ValueError(f"callback arg must not contain ':' — got {piece!r}")
        parts.append(piece)

    data = ":".join(parts)
    if len(data.encode("utf-8")) > TELEGRAM_CALLBACK_DATA_MAX_BYTES:
        raise ValueError(
            f"Callback data exceeds {TELEGRAM_CALLBACK_DATA_MAX_BYTES} bytes: {data!r}"
        )
    return data
