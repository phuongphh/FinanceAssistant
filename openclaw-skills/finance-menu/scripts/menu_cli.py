#!/usr/bin/env python3
"""OpenClaw Skill CLI: finance-menu
Thin wrapper — fetch menu from backend API.
"""
import os
import sys

import requests

API_URL = os.environ.get("FINANCE_API_URL", "http://localhost:8001/api/v1")
API_KEY = os.environ.get("FINANCE_API_KEY", "")


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
    show_menu()
