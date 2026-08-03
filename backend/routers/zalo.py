"""Zalo Official Account webhook router.

Phase 4B Epic 4 (Story P4B-S23) → rewritten thin in Phase 5.0 #2.2.

Single endpoint: ``POST /api/v1/zalo/webhook``. The route does four
things and nothing else — verify the MAC, normalise the body, claim the
``msg_id``, hand off to a background task — so it answers in ≤100ms no
matter how slow the LLM behind it is. Zalo redelivers on any non-2xx,
and a webhook that blocks on classification turns one slow message into
a retry storm.

All dispatch logic lives in :mod:`backend.workers.zalo_worker`; all
business logic lives below that in the handler and services. Mirrors
:mod:`backend.routers.telegram` deliberately — two channels with the
same shape are far cheaper to reason about than two bespoke ones.

Security:
- ``X-ZEvent-Signature`` is verified by
  :mod:`backend.utils.zalo_signature`, the single implementation of the
  MAC. A failed verification returns 403 and logs the reason slug only —
  never the sender id, the token, or the body.
- ``ZALO_SIGNATURE_ENFORCE=false`` downgrades a failure to a log line
  (soak mode) so the MAC formula can be confirmed against live traffic
  before it starts rejecting real users. See
  docs/conventions/zalo-operations.md#signature-soak-rollout.
- Verification is skipped only when the secret is empty, which
  :func:`~backend.utils.zalo_signature.assert_startup_invariant` makes
  unreachable whenever the channel is enabled.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.database import get_db
from backend.models.zalo_update import ZaloUpdate
from backend.utils import zalo_signature
from backend.utils.zalo_events import ZaloEvent, parse_event
from backend.workers.zalo_worker import process_event_safely

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/zalo", tags=["zalo"])


def _verify_zalo_signature(body: bytes, signature_header: str | None) -> bool:
    """Verify ``X-ZEvent-Signature`` and decide whether to accept the request.

    The MAC itself is computed by :mod:`backend.utils.zalo_signature` —
    this function only turns a verdict into an accept/reject decision and
    emits the ``zalo.signature`` log record the soak procedure reads.

    Returns True when the request should be processed. Under
    ``ZALO_SIGNATURE_ENFORCE=false`` that is *always* true: the verdict is
    still computed and logged, but a mismatch does not reject.
    """
    current = get_settings()
    verdict = zalo_signature.verify(
        raw_body=body,
        signature_header=signature_header,
        app_id=current.zalo_app_id,
        oa_secret_key=current.zalo_oa_secret_key,
    )

    # Structured, PII-free: the soak counts valid=true over 24h before the
    # operator flips enforce on. Never log the body, the sender, or the MAC.
    # ``shape`` carries only the header's prefix/casing/length so the soak
    # can settle the "mac=<hex>" and "lowercase hex" rows of the facts
    # table, which a valid=true verdict alone cannot prove — the verifier
    # accepts a bare digest and lowercases before comparing.
    logger.info(
        "zalo.signature valid=%s reason=%s bypassed=%s enforced=%s shape=%s",
        verdict.valid,
        verdict.reason,
        verdict.bypassed,
        current.zalo_signature_enforce,
        zalo_signature.describe_header(signature_header),
    )

    if verdict.valid:
        return True
    if not current.zalo_signature_enforce:
        logger.warning(
            "zalo.signature soak mode — accepting request despite reason=%s. "
            "This is only safe pre-launch; see "
            "docs/conventions/zalo-operations.md#signature-soak-rollout",
            verdict.reason,
        )
        return True
    return False


async def _claim_update(db: AsyncSession, event: ZaloEvent) -> bool:
    """Atomically record ``msg_id``. True if we claimed it (first sight),
    False if it was already there (a Zalo redelivery).

    ``INSERT ... ON CONFLICT DO NOTHING`` makes the check one round trip
    and race-free across uvicorn workers — the alternative (SELECT then
    INSERT) double-books a transaction whenever Zalo retries fast.
    """
    stmt = (
        pg_insert(ZaloUpdate)
        .values(
            msg_id=event.msg_id,
            zalo_user_id=event.sender_id or None,
            payload=event.payload,
        )
        .on_conflict_do_nothing(index_elements=["msg_id"])
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount == 1


def _enqueue_event(msg_id: str, payload: dict) -> None:
    """Thin wrapper around ``asyncio.create_task`` so tests patch this
    rather than ``asyncio.create_task`` itself (which anyio also uses —
    patching it globally breaks the test client under Python 3.13).
    """
    asyncio.create_task(process_event_safely(msg_id, payload))


@router.post("/webhook")
async def zalo_webhook(
    request: Request,
    x_zevent_signature: str | None = Header(default=None, alias="X-ZEvent-Signature"),
    db: AsyncSession = Depends(get_db),
):
    """Accept one inbound Zalo OA event.

    Answers ``{"ok": True}`` for every authenticated request, including
    ones we do nothing with. Zalo retries on non-200, so returning an
    error for "user said hi" would have them redelivering it forever;
    the only rejection is a failed signature.
    """
    body = await request.body()
    if not _verify_zalo_signature(body, x_zevent_signature):
        logger.warning("Zalo webhook signature mismatch — rejecting")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="invalid signature",
        )

    try:
        payload = await request.json()
    except Exception:
        logger.warning("Zalo webhook: malformed JSON body")
        return {"ok": True}

    event = parse_event(payload, app_id=get_settings().zalo_app_id)
    if event is None:
        # Not a Zalo event object, or carries no identity we could dedup
        # on. Processing it twice would be unsafe and a retry wouldn't
        # change the outcome — ack and drop.
        logger.warning("Zalo webhook: unidentifiable payload — dropping")
        return {"ok": True}

    if not event.is_text:
        # follow / unfollow / delivery receipts. Nothing to process, so
        # nothing can be processed twice — no dedup row needed either,
        # which keeps zalo_updates proportional to real conversation.
        return {"ok": True}

    claimed = await _claim_update(db, event)
    if not claimed:
        logger.info("Duplicate Zalo msg_id — skipping (derived=%s)", event.derived_key)
        return {"ok": True}

    # Fire-and-forget: the task opens its own session, routes the event,
    # and marks the row done/failed. A crash here leaves the row in
    # 'processing', which orphan recovery picks up.
    _enqueue_event(event.msg_id, event.payload)
    return {"ok": True}
