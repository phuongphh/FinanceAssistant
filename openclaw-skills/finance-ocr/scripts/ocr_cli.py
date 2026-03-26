#!/usr/bin/env python3
"""OpenClaw Skill CLI: finance-ocr
Upload receipt image → parse via Claude Vision → optionally save expense.
"""
import os
import sys

import requests

API_URL = os.environ.get("FINANCE_API_URL", "http://localhost:8001/api/v1")
API_KEY = os.environ.get("FINANCE_API_KEY", "")
USER_ID = os.environ.get("FINANCE_USER_ID", "")


def _headers() -> dict:
    return {"X-API-Key": API_KEY}


def _format_vnd(amount: float) -> str:
    return f"{amount:,.0f}₫"


def parse_receipt(image_path: str, save: bool = False):
    if not os.path.exists(image_path):
        print(f"File not found: {image_path}", file=sys.stderr)
        sys.exit(1)

    # Detect mime type
    ext = image_path.lower().rsplit(".", 1)[-1]
    mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                "webp": "image/webp", "gif": "image/gif"}
    mime_type = mime_map.get(ext, "image/jpeg")

    with open(image_path, "rb") as f:
        resp = requests.post(
            f"{API_URL}/ingestion/ocr",
            params={"user_id": USER_ID},
            headers=_headers(),
            files={"file": (os.path.basename(image_path), f, mime_type)},
            timeout=60,
        )

    if resp.status_code != 200:
        print(f"Lỗi OCR: {resp.status_code} — {resp.text}", file=sys.stderr)
        sys.exit(1)

    result = resp.json()
    if result.get("error"):
        print(f"Không phải hóa đơn: {result['error']['message']}")
        return

    data = result["data"]
    print(f"Nhận diện hóa đơn:")
    print(f"  Merchant: {data.get('merchant_name', 'N/A')}")
    print(f"  Số tiền: {_format_vnd(data.get('total_amount', 0))}")
    print(f"  Ngày: {data.get('date', 'N/A')}")
    print(f"  Danh mục: {data.get('category_suggestion', 'N/A')}")
    print(f"  Độ tin cậy: {data.get('confidence', 'N/A')}")

    if data.get("items"):
        print(f"\n  Chi tiết:")
        for item in data["items"]:
            print(f"    • {item.get('name', '?')}: {_format_vnd(item.get('price', 0))}")

    if save:
        save_expense(data)


def save_expense(ocr_data: dict):
    from datetime import date as date_mod

    payload = {
        "amount": ocr_data.get("total_amount", 0),
        "merchant": ocr_data.get("merchant_name"),
        "category": ocr_data.get("category_suggestion", "needs_review"),
        "source": "ocr",
        "expense_date": ocr_data.get("date") or date_mod.today().isoformat(),
        "needs_review": ocr_data.get("confidence") == "low",
        "raw_data": ocr_data,
    }

    resp = requests.post(
        f"{API_URL}/expenses",
        params={"user_id": USER_ID},
        headers={**_headers(), "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )

    if resp.status_code == 201:
        e = resp.json()
        print(f"\nĐã lưu: {_format_vnd(e['amount'])} — {e.get('merchant', 'N/A')} ({e['category']})")
    else:
        print(f"\nLỗi lưu expense: {resp.status_code} — {resp.text}", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: ocr_cli.py [--save] <image_path>")
        sys.exit(1)

    save = "--save" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--save"]
    image_path = args[0] if args else ""
    parse_receipt(image_path, save=save)
