"""Telegram Bot API transport layer.

All Telegram API interactions go through this service.
Routers should never call Telegram API directly.
"""
import asyncio
import logging

import httpx

from backend.config import get_settings
from backend.services.menu_service import (
    BOT_COMMANDS,
    get_callback_response,
    get_telegram_buttons,
    get_telegram_menu_text,
)

logger = logging.getLogger(__name__)
settings = get_settings()

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


async def send_telegram(method: str, payload: dict) -> dict | None:
    """Send a request to the Telegram Bot API."""
    if not settings.telegram_bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN not configured")
        return None

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/{method}"
    client = await _get_client()
    resp = await client.post(url, json=payload)
    if resp.status_code == 200:
        return resp.json()
    logger.error("Telegram API error: %s %s", resp.status_code, resp.text)
    return None


async def send_message(
    chat_id: int,
    text: str,
    parse_mode: str = "Markdown",
    reply_markup: dict | None = None,
) -> dict | None:
    payload: dict = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }
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


async def send_menu(chat_id: int) -> dict | None:
    """Send the interactive menu with inline keyboard."""
    return await send_telegram("sendMessage", {
        "chat_id": chat_id,
        "text": get_telegram_menu_text(),
        "parse_mode": "Markdown",
        "reply_markup": {"inline_keyboard": get_telegram_buttons()},
    })


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
    parse_mode: str = "Markdown",
    reply_markup: dict | None = None,
) -> dict | None:
    payload: dict = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": parse_mode,
    }
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


async def handle_menu_callback(chat_id: int, callback_data: str) -> dict | None:
    """Look up the callback response and send it."""
    response_text = get_callback_response(callback_data)
    if response_text:
        return await send_message(chat_id, response_text)
    return None


async def register_bot_commands() -> dict | None:
    return await send_telegram("setMyCommands", {"commands": BOT_COMMANDS})


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
