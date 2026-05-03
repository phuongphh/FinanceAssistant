"""Extract a spending category code from Vietnamese text.

Maps user phrasing onto canonical category codes from
``backend.config.categories`` so handlers + analytics share one
vocabulary. The keyword list intentionally favours noun phrases over
verbs ("ăn uống" yes, "đã ăn" no) so the matcher doesn't fire on
unrelated narrative text like "đã ăn cơm xong rồi".

Word-boundary aware: keywords are matched as whole words after
diacritic stripping so "quà" doesn't fire on "không liên quan".
"""
from __future__ import annotations

import re
from functools import lru_cache

from backend.intent.extractors._normalize import strip_diacritics

# (canonical category code, ordered keyword list — accent-stripped form
# stored alongside the source so we don't recompute on every call).
_CATEGORY_KEYWORDS: list[tuple[str, list[str]]] = [
    (
        "food",
        [
            "an uong", "do an", "thuc an", "nha hang", "cafe", "ca phe",
            "tra sua", "pho", "com", "am thuc", "food",
        ],
    ),
    (
        "transport",
        [
            "di chuyen", "di lai", "xang", "grab", "taxi", "xe om",
            "xe bus", "transport", "transportation",
        ],
    ),
    (
        "housing",
        [
            "nha cua", "nha o", "tien nha", "thue nha", "tien dien",
            "tien nuoc", "wifi", "internet", "housing",
        ],
    ),
    (
        "shopping",
        [
            "mua sam", "mua do", "quan ao", "shopping", "do dung",
            "thoi trang",
        ],
    ),
    (
        "health",
        [
            "suc khoe", "y te", "bac si", "benh vien", "thuoc",
            "kham benh", "health", "medical", "phong kham",
        ],
    ),
    (
        "education",
        [
            "giao duc", "hoc phi", "sach", "khoa hoc", "education",
            "course", "lop hoc",
        ],
    ),
    (
        "entertainment",
        [
            "giai tri", "phim", "game", "du lich", "vui choi",
            "entertainment", "concert", "show",
        ],
    ),
    (
        "utility",
        [
            "tien ich", "dien thoai", "subscription", "netflix",
            "spotify", "utility", "hoa don",
        ],
    ),
    (
        "gift",
        ["qua", "tang", "bieu", "li xi", "mung", "gift", "cuoi"],
    ),
    (
        "investment",
        ["dau tu", "investment", "investing", "mua co phieu"],
    ),
]


@lru_cache(maxsize=1)
def _compiled_patterns() -> list[tuple[str, list[re.Pattern[str]]]]:
    """Pre-compile each keyword into a word-boundary regex once."""
    out: list[tuple[str, list[re.Pattern[str]]]] = []
    for code, keywords in _CATEGORY_KEYWORDS:
        compiled = [
            re.compile(rf"(?<![a-z]){re.escape(kw)}(?![a-z])")
            for kw in keywords
        ]
        out.append((code, compiled))
    return out


def extract(text: str) -> str | None:
    """Return the first matching canonical category code, else None.

    Order of ``_CATEGORY_KEYWORDS`` defines priority — categories with
    more discriminating noun phrases come first to avoid e.g. "đầu tư"
    being shadowed by a generic "tiền".
    """
    if not text:
        return None
    needle = strip_diacritics(text.lower())
    for code, patterns in _compiled_patterns():
        for pat in patterns:
            if pat.search(needle):
                return code
    return None


__all__ = ["extract"]
