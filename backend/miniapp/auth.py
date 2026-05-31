"""Verify Telegram Mini App initData.

Docs: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app

Flow:
    1. Mini App JS sends `tg.initData` as header `X-Telegram-Init-Data`.
    2. Parse querystring, pop `hash`, build data-check-string by joining the
       remaining key=value pairs sorted alphabetically with `\n`. Because
       clients disagree on whether the Ed25519 `signature` field belongs in
       this string, we try both (excluded / included) and accept either.
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
        logger.warning("miniapp auth fail: empty initData")
        return None

    token = bot_token if bot_token is not None else get_settings().telegram_bot_token
    if not token:
        logger.warning("verify_init_data called without telegram_bot_token")
        return None

    # parse_qsl URL-decodes each value, which is exactly what the HMAC
    # check needs — Telegram builds its data-check-string from the decoded
    # field values, then URL-encodes the whole querystring for transport.
    try:
        pairs = parse_qsl(init_data, strict_parsing=True, keep_blank_values=True)
    except ValueError:
        logger.warning("miniapp auth fail: initData not a valid querystring")
        return None

    fields = dict(pairs)
    received_hash = fields.pop("hash", None)
    if not received_hash:
        logger.warning("miniapp auth fail: no hash field in initData")
        return None

    # The Ed25519 `signature` field (third-party validation) is sent by recent
    # clients. There is genuine ambiguity across Telegram clients/libraries over
    # whether `signature` belongs in the bot-token HMAC check string. Rather
    # than guess, accept whichever variant the client actually signed — both
    # require the real bot token to forge, so accepting either is exactly as
    # secure as accepting one. We log which variant won so the truth is visible.
    secret_key = hmac.new(
        key=b"WebAppData",
        msg=token.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()

    def _expected(keys: list[str]) -> str:
        data_check_string = "\n".join(f"{k}={fields[k]}" for k in keys)
        return hmac.new(
            key=secret_key,
            msg=data_check_string.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

    signature_present = "signature" in fields
    keys_excl = sorted(k for k in fields if k != "signature")
    keys_incl = sorted(fields.keys())

    expected_excl = _expected(keys_excl)
    expected_incl = _expected(keys_incl) if signature_present else expected_excl

    if hmac.compare_digest(received_hash, expected_excl):
        pass  # canonical: signature excluded
    elif signature_present and hmac.compare_digest(received_hash, expected_incl):
        logger.warning(
            "miniapp auth: initData verified only with `signature` INCLUDED in "
            "the HMAC check string — this client signs differently than #867 "
            "assumed."
        )
    else:
        # Neither variant matched → the bot token we hash with is not the token
        # that signed this initData (stale process or wrong bot). Log the PUBLIC
        # bot_id (digits before ':', not the secret) so the operator can confirm
        # bot identity, plus hash prefixes and field KEYS (never values/PII).
        logger.warning(
            "miniapp auth fail: HMAC mismatch on BOTH variants — token problem. "
            "bot_id=%s had_signature=%s recv=%s… expected_excl=%s… "
            "expected_incl=%s… keys=%s",
            token.split(":", 1)[0],
            signature_present,
            received_hash[:8],
            expected_excl[:8],
            expected_incl[:8] if signature_present else "n/a",
            keys_excl,
        )
        return None

    # Freshness check — auth_date is seconds since epoch, UTC.
    try:
        auth_date = int(fields.get("auth_date", "0"))
    except ValueError:
        logger.warning("miniapp auth fail: auth_date not an integer")
        return None

    if auth_date <= 0 or (time.time() - auth_date) > max_age_seconds:
        logger.warning(
            "miniapp auth fail: initData stale (auth_date age=%ss, max=%ss)",
            int(time.time() - auth_date),
            max_age_seconds,
        )
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
    x_telegram_init_data: str | None = Header(
        None,
        alias="X-Telegram-Init-Data",
        description="Telegram Mini App initData (querystring)",
    ),
) -> dict:
    """FastAPI dependency — return verified user info or raise 401.

    The header is declared Optional so a *missing* header yields a clean
    401 (auth required) instead of FastAPI's default 422 for a missing
    required header. The client treats 401/403 as "re-auth"; a 422 leaks
    as an opaque "không tải được dữ liệu" with no recovery path.
    """
    if not x_telegram_init_data:
        logger.warning("miniapp auth fail: missing X-Telegram-Init-Data header")
        raise HTTPException(status_code=401, detail="Invalid Telegram auth")
    verified = verify_init_data(x_telegram_init_data)
    if not verified:
        raise HTTPException(status_code=401, detail="Invalid Telegram auth")
    if not verified.get("user_id"):
        logger.warning("miniapp auth fail: HMAC valid but initData has no user.id")
        raise HTTPException(status_code=401, detail="Invalid Telegram auth")
    return verified
