"""Seed / rotate the Zalo OA credential row (Phase 5.0 #1.3).

Used in two situations:

1. **First install** — after authorising the OA in the Zalo dev console you
   hold a one-off ``access_token`` + ``refresh_token`` pair. Put it here and
   the app takes over the hourly refresh by itself.
2. **Runbook recovery** — a ``refresh_pending`` marker means a refresh died
   halfway and nobody can tell whether Zalo consumed the token, so
   ``zalo_token_service`` refuses to guess. Re-authorising the OA by hand
   and re-seeding is the documented way out; this script therefore *clears*
   ``refresh_pending`` as part of the upsert. See
   ``docs/conventions/zalo-operations.md`` §Runbook.

Usage::

    python -m scripts.seed_zalo_credentials \\
        --app-id 1234567890 \\
        --access-token "$ZALO_BOOTSTRAP_ACCESS_TOKEN" \\
        --refresh-token "$ZALO_BOOTSTRAP_REFRESH_TOKEN"

Tokens may also be passed via the environment
(``ZALO_BOOTSTRAP_ACCESS_TOKEN`` / ``ZALO_BOOTSTRAP_REFRESH_TOKEN``), which
is the preferred form on a shared machine: an argv token is visible to every
process in ``ps``. Nothing here ever prints token material.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

from backend.config import get_settings
from backend.database import get_session_factory
from backend.models.zalo_oa_credential import ZaloOACredential

# Zalo access tokens live one hour. Seeding right after authorising is the
# normal case, so assume a full hour unless the operator says otherwise.
DEFAULT_EXPIRES_IN = 3600


def _mask(token: str) -> str:
    """Enough to tell two tokens apart in a terminal, useless if leaked."""
    if not token:
        return "(none)"
    return f"…{token[-4:]} ({len(token)} chars)"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed or rotate the zalo_oa_credentials row."
    )
    parser.add_argument(
        "--app-id",
        default=os.getenv("ZALO_APP_ID", ""),
        help="Zalo app id (defaults to ZALO_APP_ID / settings).",
    )
    parser.add_argument(
        "--access-token",
        default=os.getenv("ZALO_BOOTSTRAP_ACCESS_TOKEN", ""),
        help="Fresh OA access token.",
    )
    parser.add_argument(
        "--refresh-token",
        default=os.getenv("ZALO_BOOTSTRAP_REFRESH_TOKEN", ""),
        help="Fresh OA refresh token (single-use; rotates on every refresh).",
    )
    parser.add_argument(
        "--expires-in",
        type=int,
        default=DEFAULT_EXPIRES_IN,
        help=f"Access-token lifetime in seconds (default {DEFAULT_EXPIRES_IN}).",
    )
    return parser.parse_args(argv)


async def seed(
    *,
    app_id: str,
    access_token: str,
    refresh_token: str,
    expires_in: int = DEFAULT_EXPIRES_IN,
) -> None:
    if expires_in <= 0:
        raise SystemExit("--expires-in must be positive")

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=expires_in)

    session_factory = get_session_factory()
    async with session_factory() as db:
        row = await db.get(ZaloOACredential, app_id)
        created = row is None
        if row is None:
            row = ZaloOACredential(app_id=app_id)
            db.add(row)

        had_pending = bool(row.refresh_pending_token)

        row.access_token = access_token
        row.refresh_token = refresh_token
        row.expires_at = expires_at
        # The whole point of re-seeding after a crash: the operator has just
        # re-authorised the OA, so the half-finished refresh is moot and the
        # marker that blocks the service must go.
        row.refresh_pending_token = None
        row.refresh_pending_at = None
        row.last_refreshed_at = now

        await db.commit()

    verb = "Seeded" if created else "Rotated"
    print(f"✓ {verb} zalo_oa_credentials for app_id={app_id}")
    print(f"  access_token  : {_mask(access_token)}")
    print(f"  refresh_token : {_mask(refresh_token)}")
    print(f"  expires_at    : {expires_at.isoformat()}")
    if had_pending:
        print("  refresh_pending: cleared (was set — recovery path)")


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)

    app_id = args.app_id or get_settings().zalo_app_id
    missing = [
        name
        for name, value in (
            ("--app-id", app_id),
            ("--access-token", args.access_token),
            ("--refresh-token", args.refresh_token),
        )
        if not value
    ]
    if missing:
        # Refuse a partial write: a row with an access token but no refresh
        # token works for one hour and then dies at 3am.
        print(f"✗ missing required value(s): {', '.join(missing)}", file=sys.stderr)
        raise SystemExit(2)

    asyncio.run(
        seed(
            app_id=app_id,
            access_token=args.access_token,
            refresh_token=args.refresh_token,
            expires_in=args.expires_in,
        )
    )


if __name__ == "__main__":
    main()
