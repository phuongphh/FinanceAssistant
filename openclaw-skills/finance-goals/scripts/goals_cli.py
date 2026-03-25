#!/usr/bin/env python3
"""OpenClaw Skill CLI: finance-goals
Thin wrapper — parse args → call backend API → format response.
"""
import os
import sys
from datetime import date

import requests

API_URL = os.environ.get("FINANCE_API_URL", "http://localhost:8001/api/v1")
API_KEY = os.environ.get("FINANCE_API_KEY", "")
USER_ID = os.environ.get("FINANCE_USER_ID", "")


def _headers() -> dict:
    return {"X-API-Key": API_KEY, "Content-Type": "application/json"}


def _format_vnd(amount: float) -> str:
    return f"{amount:,.0f}₫"


def _progress_bar(current: float, target: float, width: int = 20) -> str:
    pct = min(current / target, 1.0) if target > 0 else 0
    filled = int(width * pct)
    bar = "█" * filled + "░" * (width - filled)
    return f"{bar} {pct:.0%}"


def create_goal(name: str, target: float, deadline: str | None = None):
    payload = {
        "goal_name": name,
        "target_amount": target,
    }
    if deadline:
        payload["deadline"] = deadline
    resp = requests.post(
        f"{API_URL}/goals",
        params={"user_id": USER_ID},
        headers=_headers(),
        json=payload,
        timeout=30,
    )
    if resp.status_code == 201:
        data = resp.json()
        print(f"Đã tạo mục tiêu: {data['goal_name']}")
        print(f"Target: {_format_vnd(data['target_amount'])}")
        if data.get("deadline"):
            print(f"Deadline: {data['deadline']}")
    else:
        print(f"Lỗi: {resp.status_code} — {resp.text}", file=sys.stderr)
        sys.exit(1)


def list_goals():
    resp = requests.get(
        f"{API_URL}/goals",
        params={"user_id": USER_ID},
        headers=_headers(),
        timeout=30,
    )
    if resp.status_code == 200:
        goals = resp.json()
        if not goals:
            print("Chưa có mục tiêu nào.")
            return
        for g in goals:
            pbar = _progress_bar(g["current_amount"], g["target_amount"])
            print(f"Mục tiêu: {g['goal_name']}")
            print(
                f"   Tiến độ: {_format_vnd(g['current_amount'])} / "
                f"{_format_vnd(g['target_amount'])}"
            )
            print(f"   {pbar}")
            if g.get("deadline"):
                print(f"   Deadline: {g['deadline']}")
            print()
    else:
        print(f"Lỗi: {resp.status_code}", file=sys.stderr)


def update_progress(goal_id: str, current_amount: float):
    resp = requests.put(
        f"{API_URL}/goals/{goal_id}/progress",
        params={"user_id": USER_ID},
        headers=_headers(),
        json={"current_amount": current_amount},
        timeout=30,
    )
    if resp.status_code == 200:
        data = resp.json()
        pbar = _progress_bar(data["current_amount"], data["target_amount"])
        print(f"Đã cập nhật: {data['goal_name']}")
        print(f"   {_format_vnd(data['current_amount'])} / {_format_vnd(data['target_amount'])}")
        print(f"   {pbar}")
    else:
        print(f"Lỗi: {resp.status_code} — {resp.text}", file=sys.stderr)
        sys.exit(1)


def set_income(amount: float):
    resp = requests.post(
        f"{API_URL}/users/income",
        params={"user_id": USER_ID},
        headers=_headers(),
        json={"monthly_income": amount},
        timeout=30,
    )
    if resp.status_code == 200:
        data = resp.json()
        print(f"Đã cập nhật thu nhập: {_format_vnd(data['data']['monthly_income'])}")
    else:
        print(f"Lỗi: {resp.status_code} — {resp.text}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: goals_cli.py <create|list|progress|income> [args...]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "create":
        name = sys.argv[2] if len(sys.argv) > 2 else "Unnamed goal"
        target = float(sys.argv[3]) if len(sys.argv) > 3 else 0
        deadline = sys.argv[4] if len(sys.argv) > 4 else None
        create_goal(name, target, deadline)
    elif cmd == "list":
        list_goals()
    elif cmd == "progress":
        goal_id = sys.argv[2] if len(sys.argv) > 2 else ""
        amount = float(sys.argv[3]) if len(sys.argv) > 3 else 0
        update_progress(goal_id, amount)
    elif cmd == "income":
        amount = float(sys.argv[2]) if len(sys.argv) > 2 else 0
        set_income(amount)
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)
