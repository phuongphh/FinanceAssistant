#!/usr/bin/env python3
"""OpenClaw Skill CLI: finance-report"""
import os
import sys
from datetime import date

import requests

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


def monthly(month: str | None = None):
    if not month:
        month = date.today().strftime("%Y-%m")
    resp = requests.get(
        f"{API_URL}/reports/monthly",
        params={"user_id": USER_ID, "month": month},
        headers=_headers(),
        timeout=60,
    )
    if resp.status_code == 200:
        data = resp.json()
        print(data.get("report_text", "Không có dữ liệu"))
    else:
        print(f"Lỗi: {resp.status_code} — {resp.text}", file=sys.stderr)


def history():
    resp = requests.get(
        f"{API_URL}/reports/history",
        params={"user_id": USER_ID},
        headers=_headers(),
        timeout=30,
    )
    if resp.status_code == 200:
        reports = resp.json()
        if not reports:
            print("Chưa có báo cáo nào.")
            return
        for r in reports:
            print(f"• {r['month_key']}: tổng {r['total_expense']:,.0f}₫")
    else:
        print(f"Lỗi: {resp.status_code}", file=sys.stderr)


def generate(month: str | None = None):
    if not month:
        month = date.today().strftime("%Y-%m")
    resp = requests.post(
        f"{API_URL}/reports/generate",
        params={"user_id": USER_ID, "month": month},
        headers=_headers(),
        timeout=60,
    )
    if resp.status_code == 200:
        data = resp.json()
        print(data.get("report_text", "Không có dữ liệu"))
    else:
        print(f"Lỗi: {resp.status_code} — {resp.text}", file=sys.stderr)


if __name__ == "__main__":
    _validate_env()
    if len(sys.argv) < 2:
        print("Usage: report_cli.py <monthly|history|generate> [YYYY-MM]")
        sys.exit(1)

    cmd = sys.argv[1]
    month_arg = sys.argv[2] if len(sys.argv) > 2 else None

    if cmd == "monthly":
        monthly(month_arg)
    elif cmd == "history":
        history()
    elif cmd == "generate":
        generate(month_arg)
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)
