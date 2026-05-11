"""Zalo Official Account HTTP transport.

Phase 4B Epic 4 (Story P4B-S21).

Wraps the public Zalo OA API. Story #438 specifies aiohttp, but the
codebase already standardises on ``httpx`` (singleton ``AsyncClient``
with HTTP/2, see ``telegram_service``); reusing it keeps connection
pooling, timeouts, and lifespan cleanup uniform across transports.

Failure policy (fail-open):
- 429 (rate limit) → exponential backoff 2s / 4s / 8s, max 3 retries.
- Other non-2xx / network errors → log WARNING and return False. The
  caller (``Notifier``) treats False as "delivery failed" and the
  multi-channel fan-out keeps Telegram alive.
- We never raise from public methods — Notifier port contract.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from backend.config import get_settings

logger = logging.getLogger(__name__)

# Public Zalo OA base. ``message/cs`` is the Customer Support endpoint
# used for outbound messages to users who have explicitly followed the
# OA (which is the only audience the linking flow grants us).
_BASE_URL = "https://openapi.zalo.me/v3.0/oa"

# Retry knobs — Story #438 spec: 2s / 4s / 8s, max 3 retries on 429.
_RETRY_BACKOFFS_SECONDS: tuple[float, ...] = (2.0, 4.0, 8.0)

# Shared httpx client so repeated alert fan-outs keep TCP keep-alive
# instead of re-establishing TLS for every send.
_client: httpx.AsyncClient | None = None
_client_lock = asyncio.Lock()


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        async with _client_lock:
            if _client is None:
                _client = httpx.AsyncClient(
                    http2=True,
                    timeout=httpx.Timeout(10.0, connect=5.0),
                    limits=httpx.Limits(
                        max_keepalive_connections=20,
                        max_connections=50,
                        keepalive_expiry=60.0,
                    ),
                )
    return _client


async def close_client() -> None:
    """Close the shared httpx client. Called from FastAPI lifespan on
    shutdown so the worker doesn't leak sockets across reloads."""
    global _client
    if _client is not None:
        try:
            await _client.aclose()
        finally:
            _client = None


class ZaloOAClient:
    """Thin HTTP wrapper around the Zalo OA message endpoints.

    Stateless besides the access token — safe to instantiate per
    notifier or cache a module-level singleton. We do the latter via
    :func:`get_zalo_oa_client` because the token is read once at
    process startup.
    """

    def __init__(self, access_token: str):
        self._access_token = access_token

    @property
    def is_configured(self) -> bool:
        """Return False when the access token is missing — lets callers
        short-circuit before opening a TCP connection."""
        return bool(self._access_token)

    async def send_message(self, recipient_id: str, text: str) -> bool:
        """Send a plain-text message to a Zalo user_id. Returns True on
        success, False on any failure (caller treats False as fail-open).
        """
        if not self.is_configured:
            logger.warning("ZaloOAClient: access token not configured — skipping send")
            return False
        if not recipient_id or not text:
            return False

        payload = {
            "recipient": {"user_id": recipient_id},
            "message": {"text": text},
        }
        return await self._post("/message/cs", payload)

    async def send_image_message(
        self,
        recipient_id: str,
        image_url: str,
        caption: str = "",
    ) -> bool:
        """Send an image attachment with optional caption.

        Zalo's CS endpoint accepts attachment payloads under
        ``message.attachment``. We pass ``image_url`` rather than raw
        bytes because the OA API expects a publicly-reachable URL; the
        caller is responsible for uploading or proxying the bytes.
        """
        if not self.is_configured:
            logger.warning("ZaloOAClient: access token not configured — skipping image send")
            return False
        if not recipient_id or not image_url:
            return False

        payload: dict[str, Any] = {
            "recipient": {"user_id": recipient_id},
            "message": {
                "text": caption,
                "attachment": {
                    "type": "template",
                    "payload": {
                        "template_type": "media",
                        "elements": [
                            {"media_type": "image", "url": image_url}
                        ],
                    },
                },
            },
        }
        return await self._post("/message/cs", payload)

    async def _post(self, path: str, payload: dict) -> bool:
        url = f"{_BASE_URL}{path}"
        headers = {"access_token": self._access_token}
        client = await _get_client()

        # Total attempts = 1 initial + len(backoffs) retries. The
        # backoff schedule is applied AFTER a 429; success or
        # non-retryable failures break out immediately.
        last_status: int | None = None
        for attempt in range(len(_RETRY_BACKOFFS_SECONDS) + 1):
            try:
                resp = await client.post(url, json=payload, headers=headers)
            except (httpx.RequestError, httpx.HTTPError) as exc:
                logger.warning(
                    "Zalo OA POST %s failed (network): %s — fail-open", path, exc
                )
                return False

            last_status = resp.status_code
            if resp.status_code == 200:
                # Zalo also signals app-level errors with HTTP 200 + an
                # ``error`` field. error == 0 means success.
                data = _parse_json_safe(resp)
                err_code = data.get("error", 0) if data else 0
                if err_code == 0:
                    return True
                # Rate-limit error codes (-32, -239 historically) are
                # reported as 200 + error≠0 in some Zalo flows; treat
                # them as retryable too.
                if err_code in (-32, -239) and attempt < len(_RETRY_BACKOFFS_SECONDS):
                    await asyncio.sleep(_RETRY_BACKOFFS_SECONDS[attempt])
                    continue
                logger.warning(
                    "Zalo OA app error on %s: code=%s msg=%s",
                    path,
                    err_code,
                    (data or {}).get("message"),
                )
                return False

            if resp.status_code == 429 and attempt < len(_RETRY_BACKOFFS_SECONDS):
                logger.info(
                    "Zalo OA 429 on %s — backing off %.1fs (attempt %d/%d)",
                    path,
                    _RETRY_BACKOFFS_SECONDS[attempt],
                    attempt + 1,
                    len(_RETRY_BACKOFFS_SECONDS),
                )
                await asyncio.sleep(_RETRY_BACKOFFS_SECONDS[attempt])
                continue

            # Non-retryable HTTP error.
            logger.warning(
                "Zalo OA HTTP %s on %s: %s",
                resp.status_code,
                path,
                resp.text[:200],
            )
            return False

        logger.warning(
            "Zalo OA gave up on %s after %d attempts (last status=%s)",
            path,
            len(_RETRY_BACKOFFS_SECONDS) + 1,
            last_status,
        )
        return False


def _parse_json_safe(resp: httpx.Response) -> dict | None:
    try:
        return resp.json()
    except ValueError:
        return None


_singleton: ZaloOAClient | None = None


def get_zalo_oa_client() -> ZaloOAClient:
    """Process-wide ZaloOAClient. Reads the access token from
    ``Settings`` on first call so tests can patch settings before the
    factory is invoked. Tests override transport by patching
    ``backend.adapters.zalo_oa.get_zalo_oa_client``.
    """
    global _singleton
    if _singleton is None:
        settings = get_settings()
        _singleton = ZaloOAClient(access_token=settings.zalo_oa_access_token)
    return _singleton


def _reset_for_tests() -> None:
    """Drop the cached client. Test teardown only."""
    global _singleton
    _singleton = None
