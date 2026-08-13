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

Token handling (Phase 5.0 #1.4)
-------------------------------
Zalo access tokens live one hour, so a token captured at construction
time is wrong within the hour. The client therefore resolves a token
**per send** through an injected ``token_provider`` and, when Zalo
answers with a token-expired code, refreshes once through an injected
``token_refresher`` and replays the request.

Both are plain callables and this module never imports the token
service: the wiring lives in :func:`get_zalo_oa_client` (the composition
root) so the adapter stays pure transport and tests can inject fakes.
Constructing with a bare ``access_token=`` string still works and is
byte-identical to Phase 4B — that is the fallback used until an operator
seeds ``zalo_oa_credentials``.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

import httpx

from backend.config import Settings, get_settings

logger = logging.getLogger(__name__)

#: Returns a usable access token, or "" when none can be obtained.
TokenProvider = Callable[[], Awaitable[str]]
#: Takes the token that just failed, returns a fresh one (or "").
TokenRefresher = Callable[[str], Awaitable[str]]

# Public Zalo OA base. ``message/cs`` is the Customer Support endpoint
# used for outbound messages to users who have explicitly followed the
# OA (which is the only audience the linking flow grants us).
_BASE_URL = "https://openapi.zalo.me/v3.0/oa"

# Read-only quota endpoint used by the #3.3 reconciliation snapshot: how
# many messages Zalo itself thinks the OA has left. Diagnostics only — no
# delivery path touches it, so a wrong path degrades the snapshot to
# internal counts instead of breaking a send.
# Provenance: docs/conventions/zalo-operations.md §Platform facts —
# ASSUMED, needs staging confirmation like the error codes below.
_QUOTA_PATH = "/quota/message"

# Retry knobs — Story #438 spec: 2s / 4s / 8s, max 3 retries on 429.
_RETRY_BACKOFFS_SECONDS: tuple[float, ...] = (2.0, 4.0, 8.0)

# App-level error codes that mean "this token is no longer valid". Worth
# exactly one forced refresh + replay; a second failure is a real problem
# (revoked OA, wrong app) and retrying it would just hammer Zalo.
# Provenance: docs/conventions/zalo-operations.md §Message sending — still
# ASSUMED, needs staging confirmation.
_TOKEN_EXPIRED_CODES: frozenset[int] = frozenset({-216, -201})

# Transient app-level codes that ride the same backoff schedule as 429.
_TRANSIENT_CODES: frozenset[int] = frozenset({-32, -239})


class ZaloSendRejected(Exception):
    """Zalo refused a send it may already have charged us for.

    The distinction this carries is the only thing that lets the quota
    ledger stay honest. ``False`` from a send means *the request never
    reached Zalo* — no token, no TCP connection, an auth rejection — so
    the caller may safely give the reserved free-message slot back.
    This exception means the opposite: Zalo answered, and it answered no.

    Why that must not be refunded: Zalo enforces the same 48h window and
    8-message ceiling we count locally, and the two can drift (a clock
    skew, a window we opened on a message Zalo dropped, a manual replay).
    When they drift, every rejection would refund the slot, the local
    count would never advance, and the next send would try again —
    hammering ``/message/cs`` with a message the platform has already
    decided it will never deliver. Holding the slot converges instead:
    the local ledger catches up with the platform's and stops.

    Adapter-internal by construction. It crosses ``ZaloNotifier`` (also
    an adapter) and is caught by
    :class:`backend.adapters.zalo_window_notifier.WindowedZaloNotifier`,
    which is the only sanctioned way to build a Zalo notifier — so it
    never escapes into a handler and the ``Notifier`` port's
    "implementations do not raise" contract stays intact.
    """

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

    Holds no per-request state, so a module-level singleton is safe and
    :func:`get_zalo_oa_client` returns one. Tokens are *not* state: they
    are fetched per send from ``token_provider`` (see module docstring).

    Args:
        access_token: Static fallback token (Phase 4B). Used when no
            provider is wired, or when the provider yields nothing.
        token_provider: Async callable returning a usable token, or ""
            when none can be obtained. Never expected to raise; if it
            does we fall back rather than break the Notifier contract.
        token_refresher: Async callable taking the token that just
            failed and returning a fresh one (or ""). Called at most
            once per send.
    """

    def __init__(
        self,
        access_token: str = "",
        *,
        token_provider: TokenProvider | None = None,
        token_refresher: TokenRefresher | None = None,
    ):
        self._static_token = access_token
        self._token_provider = token_provider
        self._token_refresher = token_refresher

    @property
    def is_configured(self) -> bool:
        """Whether a token can plausibly be obtained.

        Deliberately synchronous and deliberately optimistic: callers use
        it to skip work before opening a TCP connection, and asking the
        provider for real would mean a DB round trip inside a property.
        A wired provider counts as configured; whether it can actually
        produce a token is settled at send time, where failure is already
        handled.
        """
        return bool(self._static_token or self._token_provider)

    @property
    def is_send_enabled(self) -> bool:
        """Whether outbound Zalo traffic is switched on for this process.

        Separate from :attr:`is_configured` on purpose. "Do we hold usable
        credentials?" and "may we send?" are different questions, and
        conflating them broke both directions: with the flag folded into
        credential resolution, ``ZALO_CHANNEL_ENABLED=false`` silently
        disabled the ``/admin/zalo-quota`` diagnostics the rollback
        runbook tells an operator to read, while a leftover static
        ``ZALO_OA_ACCESS_TOKEN`` kept proactive fan-outs sending after the
        same documented rollback.

        So: credentials resolve regardless of the flag, and the flag is
        enforced at the two edges that actually emit — the inbound webhook
        (mounted only when the flag is on, so no reactive reply exists to
        send) and proactive target resolution in ``notifier_resolver``.
        Read live rather than cached at construction so flipping the flag
        needs a restart, not a redeploy of the wiring.
        """
        return bool(get_settings().zalo_channel_enabled)

    async def _resolve_token(self) -> str:
        """Token for this send. Never raises — fail-open contract.

        A wired provider is authoritative: it already knows when the
        static fallback applies (see :func:`_make_token_callables`), so
        second-guessing an empty answer here would resurrect a token the
        provider deliberately declined to use.
        """
        if self._token_provider is None:
            return self._static_token
        try:
            return await self._token_provider()
        except Exception as exc:  # pragma: no cover - provider owns policy
            logger.warning(
                "Zalo OA token provider raised %s: %s — falling back to the "
                "static token",
                type(exc).__name__,
                exc,
            )
            return self._static_token

    async def _refresh_token(self, stale: str) -> str:
        """Fresh token after a token-expired error. Never raises."""
        if self._token_refresher is None:
            return ""
        try:
            return await self._token_refresher(stale)
        except Exception as exc:  # pragma: no cover - refresher owns policy
            logger.warning(
                "Zalo OA token refresh raised %s: %s — giving up on this send",
                type(exc).__name__,
                exc,
            )
            return ""

    async def send_message(self, recipient_id: str, text: str) -> bool:
        """Send a plain-text message to a Zalo user_id.

        Returns ``True`` on success and ``False`` when the request never
        left this process (no credentials, empty arguments, connection
        refused) — the caller treats ``False`` as fail-open and may hand
        back a reserved quota slot. Raises :class:`ZaloSendRejected` when
        Zalo answered no; see :meth:`_post`.
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

        Same return/raise contract as :meth:`send_message`.
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

    async def send_message_with_buttons(
        self,
        recipient_id: str,
        text: str,
        buttons: list[dict],
    ) -> bool:
        """Send a text message carrying a Zalo button template (#3.3).

        ``buttons`` is what
        :func:`backend.adapters.zalo_button_mapper.map_buttons` returned
        — already clipped, already capped, already Zalo-shaped. This
        method does not re-validate it; there is one place that knows the
        button rules and it is the mapper.

        An empty ``buttons`` list delegates to :meth:`send_message`, so a
        caller never has to branch on "did anything survive the mapping".

        Same return/raise contract as :meth:`send_message` — the send
        goes through :meth:`_post`, so retry, backoff, token refresh and
        fail-open behaviour are untouched.
        """
        if not buttons:
            return await self.send_message(recipient_id, text)
        if not self.is_configured:
            logger.warning("ZaloOAClient: access token not configured — skipping button send")
            return False
        if not recipient_id or not text:
            return False

        payload: dict[str, Any] = {
            "recipient": {"user_id": recipient_id},
            "message": {
                "attachment": {
                    "type": "template",
                    "payload": {
                        "template_type": "button",
                        "text": text,
                        "buttons": buttons,
                    },
                },
            },
        }
        return await self._post("/message/cs", payload)

    async def get_message_quota(self) -> dict[str, int] | None:
        """Read the OA's remaining message allowance from Zalo (#3.3).

        Returns ``{"remain": int, "total": int}``, or ``None`` when the
        figure could not be obtained for any reason — not configured, no
        token, network down, HTTP error, app-level error, or a response
        shaped differently from what we expect.

        ``None`` means *"unknown"*, never *"zero"*, and the caller must
        keep the distinction: a reconciliation that reads a failed quota
        call as 0 remaining would raise a drift alarm on every outage,
        which is the fastest way to teach an operator to ignore the
        alarm.

        Diagnostics, not delivery. One attempt plus the same single
        refresh-and-replay a send gets — but no backoff schedule: an
        operator refreshing a dashboard should not sit through 14 seconds
        of sleeps, and a quota figure that arrives late is worth nothing.

        Provenance: the endpoint is ``ASSUMED`` — see
        ``docs/conventions/zalo-operations.md`` §Platform facts. If Zalo
        moves or renames it, this returns ``None`` and the snapshot
        degrades to internal counts only, which is the intended failure
        mode.
        """
        if not self.is_configured:
            return None

        data = await self._get_json(_QUOTA_PATH)
        if not data:
            return None

        # The payload nests the figures under ``data`` on every OA
        # endpoint we've seen; tolerate a flat shape too rather than
        # return None over a wrapper key.
        body = data.get("data")
        if not isinstance(body, dict):
            body = data

        remain = _coerce_int(body.get("remain"))
        total = _coerce_int(body.get("total"))
        if remain is None or total is None:
            logger.warning(
                "Zalo OA quota response missing remain/total — keys=%s",
                sorted(body)[:10],
            )
            return None
        return {"remain": remain, "total": total}

    async def _get_json(self, path: str) -> dict | None:
        """One GET, one optional token-refresh replay, no backoff.

        Deliberately not a generalisation of :meth:`_post`: that method
        returns ``bool`` and owns a retry policy tuned for delivery, where
        a slow success beats a fast failure. Here the trade runs the other
        way round, and folding both policies into one method would leave
        every send carrying a branch it never takes.
        """
        token = await self._resolve_token()
        if not token:
            logger.warning("Zalo OA GET %s skipped: no usable access token", path)
            return None

        url = f"{_BASE_URL}{path}"
        client = await _get_client()

        for attempt in range(2):
            try:
                resp = await client.get(url, headers={"access_token": token})
            except (httpx.RequestError, httpx.HTTPError) as exc:
                logger.warning("Zalo OA GET %s failed (network): %s", path, exc)
                return None

            if resp.status_code != 200:
                logger.warning(
                    "Zalo OA HTTP %s on GET %s: %s",
                    resp.status_code,
                    path,
                    resp.text[:200],
                )
                return None

            data = _parse_json_safe(resp)
            err_code = data.get("error", 0) if data else 0
            if err_code == 0:
                return data

            if err_code in _TOKEN_EXPIRED_CODES and attempt == 0:
                fresh = await self._refresh_token(token)
                if not fresh or fresh == token:
                    return None
                token = fresh
                continue

            logger.warning(
                "Zalo OA app error on GET %s: code=%s msg=%s",
                path,
                err_code,
                (data or {}).get("message"),
            )
            return None

        return None

    async def _post(self, path: str, payload: dict) -> bool:
        """POST one CS message.

        Returns ``True`` when Zalo accepted it and ``False`` only when the
        request demonstrably never reached Zalo — no usable token, or the
        connection could not be established. Every other failure means
        Zalo answered and answered *no*, which may already have consumed a
        free-message slot, and is reported by raising
        :class:`ZaloSendRejected` so the quota ledger is not refunded.
        """
        token = await self._resolve_token()
        if not token:
            logger.warning(
                "Zalo OA POST %s skipped: no usable access token — fail-open", path
            )
            return False

        url = f"{_BASE_URL}{path}"
        client = await _get_client()

        # Two independent budgets, on purpose:
        #  * ``backoffs_used`` — 1 initial + len(backoffs) retries against
        #    congestion (429 and the transient app codes).
        #  * ``token_retried`` — one extra replay after a forced token
        #    refresh. A stale token is not congestion, so it must not eat
        #    a backoff slot: a send that races the hourly rotation would
        #    otherwise arrive with one fewer retry than a send that
        #    didn't, for no reason the caller can see.
        backoffs_used = 0
        token_retried = False

        while True:
            try:
                resp = await client.post(
                    url, json=payload, headers={"access_token": token}
                )
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                # The connection was never established, so the request
                # never reached Zalo and cannot have been charged. This is
                # the one transport failure whose outcome we actually know.
                logger.warning(
                    "Zalo OA POST %s failed to connect: %s — fail-open", path, exc
                )
                return False
            except (httpx.RequestError, httpx.HTTPError) as exc:
                # Anything else — read timeout, write error, broken pipe
                # mid-response — means the bytes may well have landed and
                # been processed. Unknown outcome is treated as *sent*:
                # over-counting one message is recoverable, exceeding the
                # 8-message ceiling is not.
                logger.warning(
                    "Zalo OA POST %s failed (network, outcome unknown): %s", path, exc
                )
                raise ZaloSendRejected(
                    f"transport failure with unknown outcome on {path}: {exc}"
                ) from exc

            if resp.status_code == 200:
                # Zalo also signals app-level errors with HTTP 200 + an
                # ``error`` field. error == 0 means success.
                data = _parse_json_safe(resp)
                err_code = data.get("error", 0) if data else 0
                if err_code == 0:
                    return True

                if err_code in _TOKEN_EXPIRED_CODES and not token_retried:
                    token_retried = True
                    # Our expiry bookkeeping and Zalo's disagree — Zalo
                    # wins. Pass the failed token along so a refresh that
                    # another coroutine already did is reused instead of
                    # burning a second single-use refresh_token.
                    fresh = await self._refresh_token(token)
                    if not fresh or fresh == token:
                        logger.warning(
                            "Zalo OA %s: token rejected (code=%s) and no fresh "
                            "token available — fail-open",
                            path,
                            err_code,
                        )
                        return False
                    logger.info(
                        "Zalo OA %s: token rejected (code=%s), refreshed and "
                        "replaying once",
                        path,
                        err_code,
                    )
                    token = fresh
                    continue

                if (
                    err_code in _TRANSIENT_CODES
                    and backoffs_used < len(_RETRY_BACKOFFS_SECONDS)
                ):
                    await asyncio.sleep(_RETRY_BACKOFFS_SECONDS[backoffs_used])
                    backoffs_used += 1
                    continue

                logger.warning(
                    "Zalo OA app error on %s: code=%s msg=%s",
                    path,
                    err_code,
                    (data or {}).get("message"),
                )
                raise ZaloSendRejected(
                    f"Zalo rejected {path} with app error code={err_code}"
                )

            if resp.status_code == 429:
                if backoffs_used < len(_RETRY_BACKOFFS_SECONDS):
                    logger.info(
                        "Zalo OA 429 on %s — backing off %.1fs (attempt %d/%d)",
                        path,
                        _RETRY_BACKOFFS_SECONDS[backoffs_used],
                        backoffs_used + 1,
                        len(_RETRY_BACKOFFS_SECONDS),
                    )
                    await asyncio.sleep(_RETRY_BACKOFFS_SECONDS[backoffs_used])
                    backoffs_used += 1
                    continue

                logger.warning(
                    "Zalo OA gave up on %s after %d attempts (last status=429)",
                    path,
                    len(_RETRY_BACKOFFS_SECONDS) + 1,
                )
                raise ZaloSendRejected(
                    f"Zalo rate-limited {path} for the whole retry budget"
                )

            # Non-retryable HTTP error.
            logger.warning(
                "Zalo OA HTTP %s on %s: %s",
                resp.status_code,
                path,
                resp.text[:200],
            )
            raise ZaloSendRejected(
                f"Zalo returned HTTP {resp.status_code} on {path}"
            )


def _parse_json_safe(resp: httpx.Response) -> dict | None:
    try:
        return resp.json()
    except ValueError:
        return None


def _coerce_int(value: Any) -> int | None:
    """Read an integer out of a JSON field we don't control.

    Zalo has been observed returning counters as both numbers and
    decimal strings, so both are accepted. Everything else — ``None``,
    floats, ``"12.5"``, garbage — returns ``None``, which the caller
    turns into *"quota unknown"*. Guessing a number here would feed a
    reconciliation that compares it against a real internal count, and a
    fabricated figure is worse than an absent one.

    ``bool`` is rejected explicitly: it is an ``int`` subclass in Python,
    and ``True`` silently becoming a remaining-quota of 1 is exactly the
    kind of drift alarm nobody can explain afterwards.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        try:
            return int(text)
        except ValueError:
            return None
    return None


def _make_token_callables(
    settings: Settings,
) -> tuple[TokenProvider | None, TokenRefresher | None]:
    """Wire the adapter to ``zalo_token_service`` (composition root).

    Returns ``(None, None)`` when no app id is configured, which leaves
    the client on the Phase 4B static-token path — identical behaviour to
    before 5.0.

    Deliberately **not** gated on ``ZALO_CHANNEL_ENABLED``. The flag
    governs sending, not credential resolution: the ``/admin/zalo-quota``
    router is mounted unconditionally precisely so an operator can read
    the OA's allowance before a rollout and after a rollback, and a
    provider that disappears with the flag makes those endpoints report
    "unavailable" exactly when the runbook says to use them. Sending is
    gated at the edges instead — see
    :attr:`ZaloOAClient.is_send_enabled`.

    The import is local so ``backend.adapters`` keeps no import-time
    dependency on ``backend.services``; the *policy* for what a token
    failure means lives here rather than in the transport:

    * :class:`ZaloTokenMissing` — nothing seeded yet ⇒ fall back to the
      static token (exactly the fallback documented in
      ``docs/conventions/zalo-operations.md`` §Configuration).
    * any other :class:`ZaloTokenError` — a refresh is in flight, stuck,
      or failed. The static token is from a different era and would only
      buy an opaque platform error, so yield "" and let the send
      fail-open with an actionable log line already written by the
      token service.
    """
    if not settings.zalo_app_id:
        return None, None

    from backend.services import zalo_token_service as token_service

    static_token = settings.zalo_oa_access_token

    async def provider() -> str:
        try:
            return await token_service.get_access_token()
        except token_service.ZaloTokenMissing:
            return static_token
        except token_service.ZaloTokenError as exc:
            logger.warning("Zalo OA token unavailable: %s", exc)
            return ""

    async def refresher(stale: str) -> str:
        try:
            return await token_service.force_refresh(stale_token=stale)
        except token_service.ZaloTokenError as exc:
            logger.warning("Zalo OA forced token refresh failed: %s", exc)
            return ""

    return provider, refresher


_singleton: ZaloOAClient | None = None


def get_zalo_oa_client() -> ZaloOAClient:
    """Process-wide ZaloOAClient.

    Reads ``Settings`` on first call so tests can patch settings before
    the factory is invoked. Tests override transport by patching
    ``backend.adapters.zalo_oa.get_zalo_oa_client``.
    """
    global _singleton
    if _singleton is None:
        settings = get_settings()
        provider, refresher = _make_token_callables(settings)
        _singleton = ZaloOAClient(
            access_token=settings.zalo_oa_access_token,
            token_provider=provider,
            token_refresher=refresher,
        )
    return _singleton


def _reset_for_tests() -> None:
    """Drop the cached client. Test teardown only."""
    global _singleton
    _singleton = None
