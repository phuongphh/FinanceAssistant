#!/usr/bin/env python3
"""OpenClaw Skill CLI: finance-menu
Thin wrapper — fetch menu from backend API.
"""
import os
import sys

import requests

API_URL = os.environ.get("FINANCE_API_URL", "")
API_KEY = os.environ.get("FINANCE_API_KEY", "")


def _validate_env():
    missing = []
    if not API_URL:
        missing.append("FINANCE_API_URL")
    if not API_KEY:
        missing.append("FINANCE_API_KEY")
    if missing:
        print(f"Error: missing required env vars: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)


def _headers() -> dict:
    return {"X-API-Key": API_KEY}


def show_menu():
    resp = requests.get(
        f"{API_URL}/telegram/menu",
        headers=_headers(),
        timeout=10,
    )
    if resp.status_code == 200:
        data = resp.json()
        print(data["data"]["text"])
    else:
        print(f"Lỗi: {resp.status_code}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    _validate_env()
    show_menu()
