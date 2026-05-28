"""Diagnostic — what URL is Telegram actually serving for a specific chat's menu button?

# Why this exists

PR #873 added ``&source=chat_menu_button`` to the bot-wide default menu button URL
and confirmed-fixed the blank-Mini-App problem for most users. One specific chat
(reported chat_id 1863547567) still sees Telegram's default 4-square loading
skeleton — i.e. the HTML never loads. Inline-keyboard buttons work fine for the
SAME user, so backend/auth/data are not the suspect.

The leading hypothesis: that chat has a **per-chat menu button override** that
was registered at some point in the past (manually via BotFather while testing,
or by a previous version of this codebase) and now takes precedence over the
bot-wide default we sync on every boot. ``setChatMenuButton`` without ``chat_id``
sets the global default but DOES NOT clear per-chat overrides — those persist
on Telegram's servers until explicitly overwritten or cleared.

# What this prints

Two ``getChatMenuButton`` responses side by side:
- ``scope=default`` (no chat_id) — the bot-wide button our startup hook syncs
- ``scope=chat(<chat_id>)`` — what Telegram actually serves when this chat taps

If the URLs differ → per-chat override confirmed → run the FIX block below.

# Usage

    PYTHONPATH=. python scripts/diag_menu_button.py 1863547567

Paste full output back. If you want the script to also OVERWRITE the per-chat
override with the current build URL (so the user gets the same fresh URL as
everyone else), pass ``--fix``:

    PYTHONPATH=. python scripts/diag_menu_button.py 1863547567 --fix

Or to CLEAR the per-chat override entirely so the chat falls back to the
bot-wide default we sync on every boot:

    PYTHONPATH=. python scripts/diag_menu_button.py 1863547567 --clear
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from backend.bot.setup_menu_button import _bumped_mini_app_url
from backend.config import get_settings
from backend.services.telegram_service import send_telegram


def _get_build_hash() -> str:
    """Best-effort: same source the lifespan hook uses. Falls back to ``diag``
    so the script still runs in environments without the asset bundle."""
    try:
        from backend.miniapp.routes import current_build_hash
        return current_build_hash()
    except Exception:
        return "diag"


async def _get_menu_button(chat_id: int | None) -> dict | None:
    payload = {} if chat_id is None else {"chat_id": chat_id}
    return await send_telegram("getChatMenuButton", payload)


async def _set_menu_button(chat_id: int, menu_button: dict) -> dict | None:
    return await send_telegram(
        "setChatMenuButton",
        {"chat_id": chat_id, "menu_button": menu_button},
    )


def _summarize(label: str, resp: dict | None) -> None:
    print(f"\n=== {label} ===")
    if resp is None:
        print("  send_telegram returned None — see preceding 'Telegram API error' log line.")
        return
    print(json.dumps(resp, ensure_ascii=False, indent=2))
    result = resp.get("result") if isinstance(resp, dict) else None
    if isinstance(result, dict) and result.get("type") == "web_app":
        url = (result.get("web_app") or {}).get("url")
        print(f"  -> URL Telegram serves: {url}")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("chat_id", type=int, help="Affected user's chat_id")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--fix", action="store_true",
        help="Overwrite the per-chat override with the current build URL",
    )
    group.add_argument(
        "--clear", action="store_true",
        help="Clear the per-chat override so this chat falls back to the bot-wide default",
    )
    args = parser.parse_args()

    settings = get_settings()
    if not settings.telegram_bot_token:
        print("TELEGRAM_BOT_TOKEN not configured — set it in .env and retry.")
        return 2

    print(f"miniapp_base_url     = {settings.miniapp_base_url}")
    print(f"miniapp_menu_label   = {settings.miniapp_menu_label!r}")
    print(f"target chat_id       = {args.chat_id}")

    default_resp = await _get_menu_button(None)
    chat_resp = await _get_menu_button(args.chat_id)
    _summarize("scope=default (bot-wide)", default_resp)
    _summarize(f"scope=chat({args.chat_id})", chat_resp)

    def _button_of(resp: dict | None) -> dict | None:
        """Return the ``result`` dict if the API call succeeded, else None.
        Telegram's response shape: ``{"ok": true, "result": {"type": "...", ...}}``.
        We distinguish ``None`` (API failure) from ``{"type": "default"}``
        (chat inherits the bot-wide button) — collapsing both into ``None``
        was the bug that made the previous diagnosis logic misleading."""
        if not isinstance(resp, dict) or not resp.get("ok"):
            return None
        r = resp.get("result")
        return r if isinstance(r, dict) else None

    default_button = _button_of(default_resp)
    chat_button = _button_of(chat_resp)
    print("\n=== diagnosis ===")

    if default_button is None or chat_button is None:
        # Either API call failed — comparing URLs would be meaningless
        # (None == None would falsely report "NO per-chat override").
        print(
            "  *** INCONCLUSIVE *** — one or both getChatMenuButton calls returned\n"
            f"  no usable result (default_button={default_button!r},\n"
            f"  chat_button={chat_button!r}). Check the preceding 'Telegram API error'\n"
            "  log line; common causes: wrong/expired bot token, network blocked,\n"
            "  Telegram 5xx. Do NOT run --fix or --clear until both calls succeed."
        )
    elif chat_button.get("type") == "default":
        # Per Bot API: ``MenuButtonDefault`` means the chat inherits whatever
        # the bot-wide default is — i.e. NO per-chat override exists. Reporting
        # this as an override would push the operator to run --fix, which
        # CREATES a real per-chat web_app override that future bot-wide
        # syncs would never update — the exact stale-menu class we're hunting.
        print(
            "  Chat menu button type = 'default' → chat INHERITS the bot-wide button.\n"
            "  NO per-chat override exists.\n"
            "  → Telegram is serving the bot-wide default URL to this chat:\n"
            f"    {(default_button.get('web_app') or {}).get('url')}\n"
            "  → Root cause is NOT a stale override. Do NOT run --fix (it would\n"
            "    CREATE the very override class we're trying to avoid). Next\n"
            "    suspects: WebView per-user cookie/cache that survived all\n"
            "    client-side clears (try a different Telegram account on the\n"
            "    same device to confirm), or a network-layer rewrite on this\n"
            "    user's connection."
        )
    else:
        default_url = (default_button.get("web_app") or {}).get("url")
        chat_url = (chat_button.get("web_app") or {}).get("url")
        if default_url == chat_url and chat_button.get("type") == default_button.get("type"):
            print(
                "  Per-chat URL == default URL (both web_app, same href).\n"
                "  Telegram registered an explicit per-chat copy but it happens to\n"
                "  match the bot-wide default — functionally no override.\n"
                "  → Root cause is NOT a stale URL. Next suspects: WebView per-user\n"
                "    cookie/cache that survived all client-side clears, or a\n"
                "    network-layer rewrite on this user's connection."
            )
        else:
            print(
                f"  *** PER-CHAT OVERRIDE FOUND ***\n"
                f"  default ({default_button.get('type')}): {default_url}\n"
                f"  chat    ({chat_button.get('type')}): {chat_url}\n"
                f"  → This chat has been pinned to a different button — Telegram is\n"
                f"    opening THIS on every menu-button tap, ignoring the bot-wide\n"
                f"    default that the lifespan hook re-syncs each boot."
            )
            if not (args.fix or args.clear):
                print(
                    "  → Re-run with --clear (drop the override, fall back to default)\n"
                    "    or --fix (overwrite with current build URL)."
                )

    if args.fix:
        build_hash = _get_build_hash()
        url = _bumped_mini_app_url(settings.miniapp_base_url, build_hash)
        menu_button = {
            "type": "web_app",
            "text": settings.miniapp_menu_label,
            "web_app": {"url": url},
        }
        print(f"\n=== --fix: overwriting per-chat button with url={url} ===")
        resp = await _set_menu_button(args.chat_id, menu_button)
        _summarize("setChatMenuButton(chat_id=..., menu_button=web_app)", resp)

    if args.clear:
        print("\n=== --clear: dropping per-chat override (type=default) ===")
        resp = await _set_menu_button(args.chat_id, {"type": "default"})
        _summarize("setChatMenuButton(chat_id=..., menu_button=default)", resp)
        print(
            "  After this, the chat should pick up whatever the bot-wide default\n"
            "  is (i.e. whatever the lifespan hook synced on last boot)."
        )

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
