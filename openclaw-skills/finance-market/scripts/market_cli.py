#!/usr/bin/env python3
"""OpenClaw Skill CLI: finance-market"""
import os
import sys

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


def snapshot():
    resp = requests.get(f"{API_URL}/market/snapshot", headers=_headers(), timeout=30)
    if resp.status_code == 200:
        data = resp.json()
        if not data:
            print("Chưa có dữ liệu thị trường.")
            return
        for s in data:
            price_str = f"{s['price']:,.0f}" if s.get("price") else "N/A"
            change = f" ({s['change_1d_pct']:+.2f}%)" if s.get("change_1d_pct") else ""
            print(f"  {s['asset_code']}: {price_str}{change}")
    else:
        print(f"Lỗi: {resp.status_code}", file=sys.stderr)


def history(asset: str):
    resp = requests.get(
        f"{API_URL}/market/history",
        params={"asset": asset},
        headers=_headers(),
        timeout=30,
    )
    if resp.status_code == 200:
        data = resp.json()
        if not data:
            print(f"Chưa có dữ liệu cho {asset}")
            return
        print(f"Lịch sử {asset}:")
        for s in data[:10]:
            price_str = f"{s['price']:,.0f}" if s.get("price") else "N/A"
            print(f"  {s['snapshot_date']}: {price_str}")
    else:
        print(f"Lỗi: {resp.status_code}", file=sys.stderr)


def advice():
    resp = requests.post(
        f"{API_URL}/market/advice",
        params={"user_id": USER_ID},
        headers=_headers(),
        timeout=60,
    )
    if resp.status_code == 200:
        data = resp.json()
        print(data["data"]["advice"])
    else:
        print(f"Lỗi: {resp.status_code} — {resp.text}", file=sys.stderr)


if __name__ == "__main__":
    _validate_env()
    if len(sys.argv) < 2:
        print("Usage: market_cli.py <snapshot|history|advice> [args...]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "snapshot":
        snapshot()
    elif cmd == "history":
        asset = sys.argv[2] if len(sys.argv) > 2 else "VNINDEX"
        history(asset)
    elif cmd == "advice":
        advice()
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)
