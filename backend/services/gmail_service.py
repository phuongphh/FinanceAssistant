import base64
import logging
import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.models.expense import Expense
from backend.schemas.expense import ExpenseCreate
from backend.services import expense_service
from backend.services.llm_service import call_llm

logger = logging.getLogger(__name__)
settings = get_settings()

RECEIPT_KEYWORDS = [
    # Senders (domain)
    "shopee.vn", "lazada.vn", "grab.com", "gojek.com",
    "tiki.vn", "momo.vn", "vnpay.vn", "zalopay.vn",
    # Subject keywords
    "hóa đơn", "receipt", "invoice", "order confirmation",
    "đơn hàng", "thanh toán thành công", "giao dịch thành công",
    "payment confirmation", "your order",
]

PARSE_EMAIL_PROMPT = """Trích xuất thông tin chi tiêu từ email receipt sau và trả về JSON:

---
{email_text}
---

Trả về JSON:
{{"amount": <số tiền (chỉ số, không đơn vị)>, "currency": "VND", "merchant": "<tên merchant>", "category": "<food_drink|transport|shopping|health|entertainment|utilities|other>", "date": "<YYYY-MM-DD>", "note": "<mô tả ngắn>"}}

Chỉ trả về JSON, không giải thích."""


def _matches_receipt(subject: str, sender: str) -> bool:
    text = f"{subject} {sender}".lower()
    return any(kw.lower() in text for kw in RECEIPT_KEYWORDS)


async def _get_gmail_service(user_id):
    """Build Gmail API service for a user. Requires stored OAuth credentials."""
    # Phase 0: use owner's credentials from env
    # Phase 1+: per-user OAuth tokens from DB
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials(
            token=None,
            refresh_token=settings.gmail_refresh_token if hasattr(settings, 'gmail_refresh_token') else "",
            client_id=settings.gmail_client_id,
            client_secret=settings.gmail_client_secret,
            token_uri="https://oauth2.googleapis.com/token",
        )
        service = build("gmail", "v1", credentials=creds)
        return service
    except Exception as e:
        logger.error("Failed to build Gmail service: %s", e)
        raise


async def _dedup_check(db: AsyncSession, gmail_message_id: str) -> bool:
    stmt = select(Expense).where(Expense.gmail_message_id == gmail_message_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None


def _extract_body(payload: dict) -> str:
    """Extract plain text body from Gmail message payload."""
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

    parts = payload.get("parts", [])
    for part in parts:
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
        # Recurse into nested parts
        if part.get("parts"):
            result = _extract_body(part)
            if result:
                return result

    # Fallback: try HTML
    for part in parts:
        if part.get("mimeType") == "text/html" and part.get("body", {}).get("data"):
            html = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
            # Strip HTML tags
            return re.sub(r"<[^>]+>", " ", html)

    return ""


async def sync_new_receipts(db: AsyncSession, user_id) -> list[Expense]:
    service = await _get_gmail_service(user_id)

    # Query recent emails
    results = service.users().messages().list(
        userId="me",
        q="newer_than:30m label:inbox",
        maxResults=20,
    ).execute()

    messages = results.get("messages", [])
    if not messages:
        logger.info("No new messages found")
        return []

    new_expenses = []

    for msg_ref in messages:
        msg_id = msg_ref["id"]

        # Dedup check
        if await _dedup_check(db, msg_id):
            logger.debug("Skipping duplicate: %s", msg_id)
            continue

        # Fetch full message
        msg = service.users().messages().get(
            userId="me", id=msg_id, format="full"
        ).execute()

        headers = {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}
        subject = headers.get("subject", "")
        sender = headers.get("from", "")

        if not _matches_receipt(subject, sender):
            continue

        # Extract body
        body = _extract_body(msg["payload"])
        if not body or len(body) < 20:
            continue

        # Parse with LLM
        try:
            prompt = PARSE_EMAIL_PROMPT.format(email_text=body[:3000])
            result_text = await call_llm(prompt, task_type="parse_email", db=db, use_cache=False)

            import json
            if result_text.startswith("```"):
                lines = result_text.split("\n")
                lines = [l for l in lines if not l.startswith("```")]
                result_text = "\n".join(lines)
            parsed = json.loads(result_text)
        except Exception as e:
            logger.warning("Failed to parse email %s: %s", msg_id, e)
            continue

        # Create expense
        expense_data = ExpenseCreate(
            amount=float(parsed.get("amount", 0)),
            merchant=parsed.get("merchant"),
            category=parsed.get("category", "needs_review"),
            source="gmail",
            expense_date=date.fromisoformat(parsed["date"]) if parsed.get("date") else date.today(),
            note=parsed.get("note"),
            gmail_message_id=msg_id,
            raw_data={"subject": subject, "from": sender, "parsed": parsed},
        )

        expense = await expense_service.create_expense(db, user_id, expense_data)
        new_expenses.append(expense)

        # Label as processed (best effort)
        try:
            service.users().messages().modify(
                userId="me",
                id=msg_id,
                body={"addLabelIds": [], "removeLabelIds": []},
            ).execute()
        except Exception:
            pass

        logger.info("Created expense from email: %s — %s", expense.merchant, expense.amount)

    return new_expenses
