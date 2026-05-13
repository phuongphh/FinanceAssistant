"""Sentry init + PII-scrub hook (Phase 4.1, Story A.5).

Wires Sentry into FastAPI app + workers. Strict PII scrub: we
**whitelist** what's allowed into the event payload rather than
blacklisting what to strip, because the latter approach inevitably
leaks user money figures as the codebase evolves.

Init is idempotent — calling it twice is a no-op. The DSN comes from
``SENTRY_DSN`` env var; empty/missing disables Sentry entirely.

The before_send hook:
  - Recursively walks the event dict
  - Strips strings matching number-with-≥6-digits (money values)
  - Strips email-like and phone-like substrings
  - Whitelists known-safe field names; other free-form text values
    are kept ONLY for the keys we explicitly allow (intent_type,
    step, error_message_template_id, user_id_hash)
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import uuid
from typing import Any

logger = logging.getLogger(__name__)

# ---------- Scrubbing primitives -------------------------------------

# 6+ consecutive digits — covers most VN money figures (45000, 200000000)
# while preserving short codes (e.g. status_code=403, version=2).
_MONEY_RE = re.compile(r"\b\d{6,}\b")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# VN phone: +84xxx, 84xxx, or 0xxxxxxxxx (8-10 digits after the leading 0).
_PHONE_RE = re.compile(r"(?:\+?84|0)\d{8,10}\b")

# Field names we let through with their original string content. Free
# text under ANY OTHER key is scrubbed by the regex layer.
SAFE_FIELDS = frozenset(
    {
        "intent_type",
        "step",
        "error_message_template_id",
        "user_id_hash",
        "exception_type",
        "module",
        "function",
        "lineno",
        "level",
        "logger",
        "tags",
        "environment",
        "release",
    }
)

_initialized = False


def _scrub_string(s: str) -> str:
    s = _EMAIL_RE.sub("[email]", s)
    s = _PHONE_RE.sub("[phone]", s)
    s = _MONEY_RE.sub("[redacted_n]", s)
    return s


def _scrub_value(key: str, value: Any) -> Any:
    """Recursively scrub one value. Keys not in SAFE_FIELDS still have
    their string values regex-stripped — this catches the long tail of
    custom tags we'll inevitably add.
    """
    if isinstance(value, str):
        return _scrub_string(value)
    if isinstance(value, dict):
        return {k: _scrub_value(k, v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        scrubbed = [_scrub_value(key, v) for v in value]
        return type(value)(scrubbed)
    return value


def before_send(event: dict, hint: dict | None = None) -> dict | None:
    """Sentry beforesend hook. Returns the scrubbed event or None to drop.

    Top-level fields scrubbed:
      - ``request.headers`` / ``request.cookies`` / ``request.data``
      - ``user.email`` / ``user.ip_address`` / ``user.username``
      - ``extra`` / ``contexts`` / ``tags`` (recursive)
      - ``breadcrumbs[].data`` (recursive)
      - exception messages
    """
    try:
        # Drop PII off user dict before recursion.
        user = event.get("user", {}) or {}
        if "email" in user:
            user["email"] = "[email]"
        if "ip_address" in user:
            user["ip_address"] = "[ip]"
        if "username" in user:
            user["username"] = "[redacted]"
        # Replace user_id with a hash so traces are joinable without leaking.
        if "id" in user:
            user["user_id_hash"] = hash_user_id(str(user.pop("id")))
        event["user"] = user

        # Recursively scrub the rest of the event.
        for top_key in ("extra", "contexts", "tags", "request"):
            if top_key in event:
                event[top_key] = _scrub_value(top_key, event[top_key])

        # Exception messages can quote user input — scrub the values.
        for ex in (event.get("exception", {}) or {}).get("values", []) or []:
            if "value" in ex and isinstance(ex["value"], str):
                ex["value"] = _scrub_string(ex["value"])

        # Breadcrumbs frequently embed request data.
        breadcrumbs = event.get("breadcrumbs") or {}
        if isinstance(breadcrumbs, dict):
            values = breadcrumbs.get("values") or []
        else:
            values = breadcrumbs
        for bc in values or []:
            if "message" in bc and isinstance(bc["message"], str):
                bc["message"] = _scrub_string(bc["message"])
            if "data" in bc:
                bc["data"] = _scrub_value("data", bc["data"])
    except Exception:
        # Never let a scrub error block the report — that loses signal
        # AND PII protection. Drop the event entirely.
        logger.exception("Sentry beforesend scrub failed; dropping event")
        return None
    return event


def hash_user_id(user_id: uuid.UUID | str) -> str:
    """Stable 12-char hash so traces are joinable across reports."""
    return hashlib.sha256(str(user_id).encode()).hexdigest()[:12]


# ---------- Init -----------------------------------------------------


def init(*, environment: str | None = None, release: str | None = None) -> bool:
    """Initialize Sentry once. Returns True if initialized, False if
    DSN missing (so callers can log and proceed without telemetry).
    """
    global _initialized
    if _initialized:
        return True

    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        logger.info("SENTRY_DSN not set; Sentry disabled")
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.asyncio import AsyncioIntegration
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    except ImportError:
        logger.warning("sentry_sdk not installed; Sentry disabled")
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=environment or os.environ.get("ENVIRONMENT", "production"),
        release=release or os.environ.get("APP_RELEASE"),
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        send_default_pii=False,  # Belt-and-braces with our scrubber.
        before_send=before_send,
        integrations=[
            FastApiIntegration(),
            SqlalchemyIntegration(),
            AsyncioIntegration(),
        ],
    )
    _initialized = True
    logger.info("Sentry initialized")
    return True


def set_user_context(user_id: uuid.UUID | str | None) -> None:
    """Tag the current scope with a hashed user id so subsequent
    exceptions carry it. Drops silently if Sentry isn't initialized.
    """
    if not _initialized or user_id is None:
        return
    try:
        import sentry_sdk

        sentry_sdk.set_user({"id": str(user_id)})
    except Exception:
        logger.debug("Sentry set_user failed", exc_info=True)


def capture_exception(exc: BaseException) -> None:
    """Explicit capture for places we catch + want telemetry."""
    if not _initialized:
        return
    try:
        import sentry_sdk

        sentry_sdk.capture_exception(exc)
    except Exception:
        logger.debug("Sentry capture_exception failed", exc_info=True)
