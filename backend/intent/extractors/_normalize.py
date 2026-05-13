"""Internal normalization helpers shared by the extractors.

Diacritic stripping makes patterns survive users typing without tone
marks ("tai san" vs "tài sản") which is common on desktop and in speed-
typed Telegram messages.
"""
from __future__ import annotations

import unicodedata


def strip_diacritics(text: str) -> str:
    """NFD-decompose then drop combining marks. ``đ``/``Đ`` is handled
    explicitly because Unicode normalization doesn't decompose it."""
    if not text:
        return text
    nfkd = unicodedata.normalize("NFD", text)
    no_marks = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    return no_marks.replace("đ", "d").replace("Đ", "D")
