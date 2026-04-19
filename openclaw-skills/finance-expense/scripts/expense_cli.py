#!/usr/bin/env python3
"""OpenClaw Skill CLI: finance-expense
Thin wrapper — parse args → call backend API → format response.
"""
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

import requests

# Allow importing backend.* formatters from anywhere the script is launched.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.bot.formatters.money import format_money_full
from backend.bot.formatters.templates import format_transaction_confirmation
from backend.config.categories import get_category

API_URL = os.environ.get("FINANCE_API_URL", "")
API_KEY = os.environ.get("FINANCE_API_KEY", "")
USER_ID = os.environ.get("FINANCE_USER_ID", "")


def _validate_env():
    missing = []
    if not API_URL:
        missing.append("FINANCE_API_URL")
    if not API_KEY:
        missing.append("FINANCE_API_KEY")
    if not USER_ID:
        missing.append("FINANCE_USER_ID")
    if missing:
        print(f"Error: missing required env vars: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)


def _headers() -> dict:
    return {"X-API-Key": API_KEY, "Content-Type": "application/json"}


def _format_vnd(amount: float) -> str:
    return format_money_full(amount)


# Legacy backend category codes (food_drink) → new shared codes (food).
_CATEGORY_CODE_ALIASES = {
    "food_drink": "food",
    "utilities": "utility",
}


def _normalize_category(code: str | None) -> str:
    if not code:
        return "other"
    return _CATEGORY_CODE_ALIASES.get(code, code)


def add_expense(amount: float, note: str | None = None, merchant: str | None = None):
    payload = {
        "amount": amount,
        "source": "manual",
        "expense_date": date.today().isoformat(),
        "note": note,
        "merchant": merchant or note,
    }
    resp = requests.post(
        f"{API_URL}/expenses",
        params={"user_id": USER_ID},
        headers=_headers(),
        json=payload,
        timeout=30,
    )
    if resp.status_code == 201:
        data = resp.json()
        category_code = _normalize_category(data.get("category"))
        merchant_label = data.get("merchant") or data.get("note") or "Giao dịch"
        print(
            format_transaction_confirmation(
                merchant=merchant_label,
                amount=float(data["amount"]),
                category_code=category_code,
                time=datetime.now(),
            )
        )
    else:
        print(f"Lỗi: {resp.status_code} — {resp.text}", file=sys.stderr)
        sys.exit(1)


def list_expenses(month: str | None = None):
    params = {"user_id": USER_ID}
    if month:
        params["month"] = month
    resp = requests.get(
        f"{API_URL}/expenses",
        params=params,
        headers=_headers(),
        timeout=30,
    )
    if resp.status_code == 200:
        expenses = resp.json()
        if not expenses:
            print("Chưa có giao dịch nào 🌱")
            return
        for e in expenses:
            cat = get_category(_normalize_category(e.get("category")))
            merchant_label = e.get("merchant") or e.get("note") or "Giao dịch"
            print(
                f"{cat.emoji} {merchant_label} — {_format_vnd(e['amount'])}  "
                f"[{e['expense_date']}]"
            )
    else:
        print(f"Lỗi: {resp.status_code}", file=sys.stderr)


def get_summary(month: str | None = None):
    if not month:
        month = date.today().strftime("%Y-%m")
    resp = requests.get(
        f"{API_URL}/expenses/summary",
        params={"user_id": USER_ID, "month": month},
        headers=_headers(),
        timeout=30,
    )
    if resp.status_code == 200:
        data = resp.json()
        print(f"📊 Tổng chi tháng {data['month_key']}: {_format_vnd(data['total'])}")
        print(f"Số giao dịch: {data['count']}")
        if data["by_category"]:
            print("\nTheo danh mục:")
            for cat_code, amt in sorted(data["by_category"].items(), key=lambda x: -x[1]):
                cat = get_category(_normalize_category(cat_code))
                print(f"  {cat.emoji} {cat.name_vi}: {_format_vnd(amt)}")
    else:
        print(f"Lỗi: {resp.status_code}", file=sys.stderr)


if __name__ == "__main__":
    _validate_env()
    if len(sys.argv) < 2:
        print("Usage: expense_cli.py <add|list|summary> [args...]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "add":
        amount = float(sys.argv[2]) if len(sys.argv) > 2 else 0
        note = " ".join(sys.argv[3:]) if len(sys.argv) > 3 else None
        add_expense(amount, note=note, merchant=note)
    elif cmd == "list":
        month = sys.argv[2] if len(sys.argv) > 2 else None
        list_expenses(month)
    elif cmd == "summary":
        month = sys.argv[2] if len(sys.argv) > 2 else None
        get_summary(month)
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)
