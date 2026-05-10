"""Telegram Bot API transport layer.

All Telegram API interactions go through this service.
Routers should never call Telegram API directly.
"""
import asyncio
import logging

import httpx

from backend.config import get_settings
from backend.utils.markdown_sanitizer import sanitize_markdown

logger = logging.getLogger(__name__)
settings = get_settings()

# Telegram methods whose payload carries user-facing body text we may
# need to sanitize. ``sendMessage`` / ``editMessageText`` use ``text``;
# ``sendPhoto`` / ``editMessageCaption`` use ``caption``. Anything else
# (answerCallbackQuery, sendChatAction, getFile, setMyCommands…) is
# either structured or short enough that sanitization isn't relevant.
_MARKDOWN_TEXT_FIELDS = {
    "sendMessage": "text",
    "editMessageText": "text",
    "sendPhoto": "caption",
    "editMessageCaption": "caption",
}

# Singleton httpx client. Creating a fresh AsyncClient per request paid the
# full TCP+TLS handshake to api.telegram.org every time (~300-500ms per call
# over the WAN), which compounded badly because each callback handler issues
# at least two sequential requests (answerCallbackQuery + sendMessage).
# Holding one client lets keep-alive reuse the connection so subsequent
# calls land in the 50-150ms range. See the asset-wizard latency fix.
_client: httpx.AsyncClient | None = None
_client_lock = asyncio.Lock()


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        async with _client_lock:
            if _client is None:
                # HTTP/2 lets one TCP connection multiplex many concurrent
                # requests to api.telegram.org, which removes the 6-stream
                # head-of-line bottleneck under callback-storm load (each
                # callback handler fires answerCallbackQuery + sendMessage,
                # so 100 concurrent users = 200 in-flight requests).
                _client = httpx.AsyncClient(
                    http2=True,
                    timeout=httpx.Timeout(10.0, connect=5.0),
                    limits=httpx.Limits(
                        max_keepalive_connections=50,
                        max_connections=100,
                        keepalive_expiry=60.0,
                    ),
                )
    return _client


async def close_client() -> None:
    """Close the shared httpx client. Called from the FastAPI lifespan
    on shutdown so we don't leak sockets."""
    global _client
    if _client is not None:
        try:
            await _client.aclose()
        finally:
            _client = None


def _sanitize_payload(method: str, payload: dict) -> dict:
    """Pre-process Markdown bodies so Telegram's parser doesn't reject them.

    Only touches payloads where ``parse_mode == "Markdown"`` — HTML mode
    has its own escaping rules (handled at the formatter layer), and
    bodies without ``parse_mode`` are plain text already. Returns a
    shallow copy with the relevant text field replaced; the input dict
    is not mutated so callers can safely re-use it.
    """
    if payload.get("parse_mode") != "Markdown":
        return payload
    field = _MARKDOWN_TEXT_FIELDS.get(method)
    if not field:
        return payload
    body = payload.get(field)
    if not isinstance(body, str) or not body:
        return payload
    sanitized = sanitize_markdown(body)
    if sanitized == body:
        return payload
    return {**payload, field: sanitized}


async def send_telegram(method: str, payload: dict) -> dict | None:
    """Send a request to the Telegram Bot API.

    Two layers of protection against the "can't parse entities" failure
    where unbalanced LLM-generated markdown silently drops the message:

    1. **Sanitize on the way out.** When ``parse_mode`` is ``Markdown``,
       we run the body through :func:`sanitize_markdown` to escape any
       unbalanced ``*`` / ``_`` / ``[`` / ``\\``` so Telegram parses
       cleanly the first time. This is the root-cause fix.
    2. **Plain-text retry on 400.** If a malformed body slips past the
       sanitizer and Telegram still rejects it, retry once without
       ``parse_mode`` so the user sees the raw text instead of nothing.
       Other 400s (chat not found, etc.) still fail fast.
    """
    if not settings.telegram_bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN not configured")
        return None

    payload = _sanitize_payload(method, payload)

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/{method}"
    client = await _get_client()
    resp = await client.post(url, json=payload)
    if resp.status_code == 200:
        return resp.json()

    if (
        resp.status_code == 400
        and "can't parse entities" in resp.text
        and (payload.get("parse_mode") or payload.get("entities"))
    ):
        logger.warning(
            "Telegram parse_entities error on %s; retrying as plain text",
            method,
        )
        plain = {
            k: v
            for k, v in payload.items()
            if k not in {"parse_mode", "entities"}
        }
        retry = await client.post(url, json=plain)
        if retry.status_code == 200:
            return retry.json()
        logger.error(
            "Telegram API error (plain retry): %s %s",
            retry.status_code,
            retry.text,
        )
        return None

    logger.error("Telegram API error: %s %s", resp.status_code, resp.text)
    return None


async def send_message(
    chat_id: int,
    text: str,
    parse_mode: str | None = "Markdown",
    reply_markup: dict | None = None,
    entities: list[dict] | None = None,
) -> dict | None:
    payload: dict = {
        "chat_id": chat_id,
        "text": text,
    }
    if entities:
        # Telegram expects either parse_mode OR explicit entities. Custom
        # emoji needs entities, so callers that opt in get a plain-text body
        # with exact UTF-16 spans and no markdown parser risk.
        payload["entities"] = entities
    elif parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return await send_telegram("sendMessage", payload)


async def send_photo(
    chat_id: int,
    photo_bytes: bytes,
    caption: str = "",
    filename: str = "chart.png",
    parse_mode: str = "Markdown",
    reply_markup: dict | None = None,
) -> dict | None:
    """Send a photo via Telegram Bot API using multipart upload."""
    if not settings.telegram_bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN not configured")
        return None

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendPhoto"
    data: dict = {"chat_id": str(chat_id)}
    if caption:
        # Mirror send_telegram's sanitization for the multipart path so
        # captions with LLM-generated markdown (e.g. briefing photos)
        # don't silently fail with "can't parse entities".
        if parse_mode == "Markdown":
            caption = sanitize_markdown(caption)
        data["caption"] = caption
        data["parse_mode"] = parse_mode
    if reply_markup:
        import json
        data["reply_markup"] = json.dumps(reply_markup)

    files = {"photo": (filename, photo_bytes, "image/png")}

    client = await _get_client()
    resp = await client.post(url, data=data, files=files, timeout=30)
    if resp.status_code == 200:
        return resp.json()
    logger.error("Telegram sendPhoto error: %s %s", resp.status_code, resp.text)
    return None


async def answer_callback(
    callback_id: str,
    text: str | None = None,
    show_alert: bool = False,
) -> dict | None:
    payload: dict = {"callback_query_id": callback_id}
    if text:
        payload["text"] = text
        payload["show_alert"] = show_alert
    return await send_telegram("answerCallbackQuery", payload)


async def edit_message_text(
    chat_id: int,
    message_id: int,
    text: str,
    parse_mode: str | None = "Markdown",
    reply_markup: dict | None = None,
    entities: list[dict] | None = None,
) -> dict | None:
    payload: dict = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
    }
    if entities:
        payload["entities"] = entities
    elif parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    return await send_telegram("editMessageText", payload)


async def edit_message_reply_markup(
    chat_id: int,
    message_id: int,
    reply_markup: dict | None,
) -> dict | None:
    payload: dict = {"chat_id": chat_id, "message_id": message_id}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    return await send_telegram("editMessageReplyMarkup", payload)


async def send_chat_action(chat_id: int, action: str = "typing") -> dict | None:
    """Send a chat action (typing indicator, etc.).

    Telegram clears the action after 5 seconds, so for long-running
    operations the caller should either re-send periodically or
    follow up with an actual message before then. Used by the Tier 3
    streamer to give immediate feedback while Claude is reasoning.
    """
    return await send_telegram(
        "sendChatAction", {"chat_id": chat_id, "action": action}
    )


async def download_file(file_id: str) -> bytes | None:
    """Download a Telegram file (voice, photo, document) by file_id.

    Two-step API: ``getFile`` returns a relative ``file_path``, which
    we then fetch from the Telegram CDN. Returns ``None`` if the bot
    isn't configured or either step fails — callers should treat that
    as "audio unavailable" and fall back gracefully.
    """
    if not settings.telegram_bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN not configured")
        return None

    info = await send_telegram("getFile", {"file_id": file_id})
    if not info or not info.get("ok"):
        return None
    file_path = (info.get("result") or {}).get("file_path")
    if not file_path:
        return None

    url = f"https://api.telegram.org/file/bot{settings.telegram_bot_token}/{file_path}"
    client = await _get_client()
    resp = await client.get(url, timeout=30)
    if resp.status_code != 200:
        logger.error("Telegram file download error: %s", resp.status_code)
        return None
    return resp.content
