"""Verify Telegram Mini App initData.

Docs: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app

Flow:
    1. Mini App JS sends `tg.initData` as header `X-Telegram-Init-Data`.
    2. Parse querystring, pop `hash`, build data-check-string by joining the
       remaining key=value pairs sorted alphabetically with `\n`.
    3. secret_key = HMAC-SHA256(key="WebAppData", msg=bot_token)
    4. expected_hash = HMAC-SHA256(key=secret_key, msg=data_check_string)
    5. Constant-time compare with received hash.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException

from backend.config import get_settings

logger = logging.getLogger(__name__)

# Reject initData older than this — protects against replayed tokens.
INIT_DATA_MAX_AGE_SECONDS = 24 * 60 * 60


def verify_init_data(
    init_data: str,
    bot_token: str | None = None,
    max_age_seconds: int = INIT_DATA_MAX_AGE_SECONDS,
) -> dict | None:
    """Validate `initData` string from Telegram Mini App.

    Returns parsed user info dict on success; None on any failure.
    """
    if not init_data:
        return None

    token = bot_token if bot_token is not None else get_settings().telegram_bot_token
    if not token:
        logger.warning("verify_init_data called without telegram_bot_token")
        return None

    # parse_qsl preserves the original-encoded values, which is what we need
    # for the HMAC — Telegram signs the URL-encoded string, not the decoded one.
    try:
        pairs = parse_qsl(init_data, strict_parsing=True, keep_blank_values=True)
    except ValueError:
        return None

    fields = dict(pairs)
    received_hash = fields.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(fields.items(), key=lambda kv: kv[0])
    )

    secret_key = hmac.new(
        key=b"WebAppData",
        msg=token.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()

    expected_hash = hmac.new(
        key=secret_key,
        msg=data_check_string.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(received_hash, expected_hash):
        return None

    # Freshness check — auth_date is seconds since epoch, UTC.
    try:
        auth_date = int(fields.get("auth_date", "0"))
    except ValueError:
        return None

    if auth_date <= 0 or (time.time() - auth_date) > max_age_seconds:
        return None

    user_payload = fields.get("user")
    user: dict = {}
    if user_payload:
        try:
            user = json.loads(user_payload)
        except (TypeError, ValueError):
            user = {}

    return {
        "user_id": user.get("id"),
        "first_name": user.get("first_name"),
        "last_name": user.get("last_name"),
        "username": user.get("username"),
        "language_code": user.get("language_code"),
        "auth_date": auth_date,
    }


async def require_miniapp_auth(
    x_telegram_init_data: str = Header(
        ...,
        alias="X-Telegram-Init-Data",
        description="Telegram Mini App initData (querystring)",
    ),
) -> dict:
    """FastAPI dependency — return verified user info or raise 401."""
    verified = verify_init_data(x_telegram_init_data)
    if not verified or not verified.get("user_id"):
        raise HTTPException(status_code=401, detail="Invalid Telegram auth")
    return verified
