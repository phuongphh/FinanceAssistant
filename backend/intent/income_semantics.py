"""Single source of truth for income vs. expense semantics.

Vietnamese users log money-IN with the verb **"được"** far more often
than with the bare "+" sign the parser was originally built around:

    "được bố cho 500k"      → bố cho mình 500k  (gift)
    "được thưởng 200k"      → công ty thưởng    (bonus)
    "được lì xì 50k"        → lì xì Tết         (lucky money)
    "được mẹ cho 1tr"       → mẹ cho            (gift)
    "được biếu 2tr"         → ai đó biếu        (gift to elder, here received)
    "được mừng tuổi 100k"   → mừng tuổi         (lucky money)

The Chi tiêu menu *promises* these are recorded as money-in, so the
detection has to live in ONE place that the message-layer fast-path
(which records the transaction), the rule-based tier, and the expense
handler (defence-in-depth income guard) all agree on. Diverging copies
were the root cause of "được bố cho 500k" being silently mis-recorded
as an expense.

Design notes
------------
* All matching runs on the diacritic-stripped, lower-cased text so it
  survives users typing without tone marks ("duoc bo cho" == "được bố
  cho"). We reuse :func:`strip_diacritics` from the extractors package so
  the normalization is identical everywhere.
* "được" is also a *resultative particle* ("mua được áo" = managed to buy
  a shirt). Those are EXPENSES, so a leading action verb immediately
  before "được" vetoes the money-in reading.
* A mixed sentence that also carries a spend verb ("được thưởng 5tr rồi
  tiêu hết") lets the expense reading win — consistent with the existing
  keyword balancing in the handler.
"""

from __future__ import annotations

import re

from backend.intent.extractors._normalize import strip_diacritics

__all__ = [
    "INCOME_KEYWORDS",
    "EXPENSE_KEYWORDS",
    "has_leading_plus_sign",
    "looks_like_wallet_topup",
    "is_duoc_money_in",
    "looks_like_income",
]


# Verbs that, when they FOLLOW "được", mean the user *received* money.
# Kept as a regex fragment so the same alternation feeds both the
# Python detector here and the Tier-1 YAML pattern (keep them in sync).
_GIVING_VERBS = (
    "cho",  # bố cho, mẹ cho
    "tang",  # tặng
    "bieu",  # biếu
    "thuong",  # thưởng
    "li\\s*xi",  # lì xì
    "mung\\s*tuoi",  # mừng tuổi
    "mung",  # mừng (cưới/tân gia)
    "ho\\s*tro",  # hỗ trợ
    "hoan",  # hoàn (tiền)
    "tra",  # trả (lương/lại) — someone pays the user
)

# "được" + up to two filler words (the giver: bố / mẹ / sếp / công ty) +
# a giving verb. Anchored so it can appear anywhere in the clause.
_DUOC_INCOME_RE = re.compile(
    r"(?:^|(?<=\s))duoc\s+(?:\w+\s+){0,2}?(?:" + "|".join(_GIVING_VERBS) + r")\b",
)

# Resultative "được": a transactional action verb immediately before
# "được" turns it into "managed to <verb>", which is an EXPENSE
# ("mua được áo", "mua được cho con"). This vetoes the money-in reading.
# NOTE: "ban"/"kiem" (bán/kiếm được = sold/earned) ARE income and are
# intentionally excluded from this veto — they're covered by the keyword
# list below instead.
_RESULTATIVE_DUOC_RE = re.compile(
    r"\b(?:mua|tim|lam|an|choi|hoc|di|xem|dat|gianh)\s+duoc\b"
)

# Question-shaped inputs ("được thưởng bao nhiêu?") must never be treated
# as a recordable transaction.
_QUESTION_RE = re.compile(r"\?|\bbao nhieu\b|\bbao lau\b|\bkhi nao\b")


# Wallet top-up shape: "thêm/cộng/nạp/nhận X vào ví|tài khoản Y" — the
# user is explicitly moving money INTO a wallet/account, which is income
# from the cash-flow perspective regardless of which verb leads.
_WALLET_TOPUP_RE = re.compile(
    r"^\s*(?:them|cong|nap|nhan|cho|gui|bo|duoc|nop)\s+[+\-]?\s*[\d.,]+"
    r".*?\b(?:vao|into|toi|den)\s+"
    r"(?:vi|tai\s*khoan|cash|tien\s*mat|momo|zalopay|viettel|"
    r"vcb|acb|tcb|mb|tpb|techcom|sacombank|bidv|vietinbank)\b",
)


# Verbs/phrases that indicate the user is RECEIVING money (income), NOT
# spending. Matched on diacritic-stripped text. Phrasal forms only —
# bare "thuong"/"tra" collide with "thường" (usually) / "trả tiền"
# (spending) after stripping, so they're omitted on purpose.
INCOME_KEYWORDS: tuple[str, ...] = (
    "nhan luong",
    "nhan thuong",
    "nhan tien",
    "luong",
    "thuong tet",
    "tien thuong",
    "duoc thuong",
    "duoc tang",
    "duoc cho",
    "duoc bieu",
    "duoc li xi",
    "duoc mung tuoi",
    "duoc ho tro",
    # Lucky money needs a RECEIVING cue: bare "li xi" / "mung tuoi" also
    # cover the GIVING case ("lì xì cháu 500k", "mừng tuổi cho con 100k"),
    # which is an expense — so require "được"/"nhận" before counting it as
    # income. ("duoc li xi"/"duoc mung tuoi" above handle the "được" form.)
    "nhan li xi",
    "nhan mung tuoi",
    "thu nhap",
    "kiem duoc",
    "ban duoc",
    "hoan tien",
    "lai ngan hang",
    "co tuc",
    "freelance",
    "lam them",
)

# Verbs that explicitly mean "spend" — override the income check in mixed
# sentences ("lương tháng này tiêu hết 5tr" → expense wins). Bare "tra"
# is omitted (substring of "trả lương" = paying salary = income).
EXPENSE_KEYWORDS: tuple[str, ...] = (
    "tieu",
    "chi tieu",
    "tra tien",
    "mua",
    "thanh toan",
    "bo tien",
    "het",
)

# Spend verbs that still veto a *refund* inflow. "mua" is excluded because
# a refund sentence ("được hoàn 200k tiền mua vé") references the original
# purchase, not a new outflow — only an explicit re-spend ("tiêu", "hết")
# should flip a refund back to expense.
_REFUND_VETO_KEYWORDS: tuple[str, ...] = tuple(
    kw for kw in EXPENSE_KEYWORDS if kw != "mua"
)


def has_leading_plus_sign(text: str) -> bool:
    """True if the message starts with an explicit ``+`` before a number.

    A leading ``+`` is the user's most direct money-in signal.
    """
    return bool(re.match(r"^\s*\+\s*\d", text or ""))


def looks_like_wallet_topup(text: str) -> bool:
    """True when the message reads as a wallet/account top-up."""
    if not text:
        return False
    return bool(_WALLET_TOPUP_RE.search(strip_diacritics(text.lower())))


def is_duoc_money_in(text: str) -> bool:
    """True for the "được <giver> cho/tặng/lì xì/thưởng… <amount>" shape.

    This is the precise, high-confidence money-IN phrasing the Chi tiêu
    menu promises. Returns False for questions, resultative "được" (an
    expense, e.g. "mua được áo"), and mixed sentences where a spend verb
    is also present.
    """
    if not text:
        return False
    norm = strip_diacritics(text.lower())
    if _QUESTION_RE.search(norm):
        return False
    match = _DUOC_INCOME_RE.search(norm)
    if not match:
        return False
    if _RESULTATIVE_DUOC_RE.search(norm):
        return False
    # A spend verb elsewhere in the sentence means the money flowed back
    # OUT — let the expense reading win, mirroring looks_like_income.
    # Exception: a refund ("được hoàn ... tiền mua vé") inherently names the
    # original purchase, so a bare "mua" must NOT veto the refund inflow.
    # An explicit re-spend ("được hoàn 200k rồi tiêu hết") still wins.
    is_refund = "hoan" in match.group(0)
    veto_keywords = _REFUND_VETO_KEYWORDS if is_refund else EXPENSE_KEYWORDS
    if any(kw in norm for kw in veto_keywords):
        return False
    return True


def looks_like_income(text: str) -> bool:
    """True if the message reads as income rather than expense.

    Used as a pre-check in the expense handler to avoid mis-recording
    income ("nhận lương 20tr", "được bố cho 500k") as an expense. If the
    message carries BOTH income and expense verbs, expense wins — the
    user is describing what they did with the money, not the receipt.
    """
    if not text:
        return False
    if has_leading_plus_sign(text):
        return True
    if looks_like_wallet_topup(text):
        return True
    if is_duoc_money_in(text):
        return True
    norm = strip_diacritics(text.lower())
    has_income = any(kw in norm for kw in INCOME_KEYWORDS)
    if not has_income:
        return False
    has_expense = any(kw in norm for kw in EXPENSE_KEYWORDS)
    return not has_expense
