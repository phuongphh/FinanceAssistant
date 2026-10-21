"""Gửi tin Telegram cho bot OpenClaw (hoặc bất kỳ bot nào) qua Bot API.

Đọc ``LOOP_TELEGRAM_BOT_TOKEN`` + ``LOOP_TELEGRAM_CHAT_ID`` từ env. Thiếu một
trong hai → no-op (log warning), để loop vẫn chạy được khi chưa cấu hình.

Gửi plain text (không ``parse_mode``) để tiêu đề issue có ``_``/``*`` không
làm hỏng Markdown của Telegram.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from collections.abc import Mapping

log = logging.getLogger("agent_loop")

MAX_LEN = 4000  # Telegram giới hạn 4096 ký tự / tin


def send(text: str, env: Mapping[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    token = env.get("LOOP_TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("LOOP_TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        log.warning("notify: thiếu LOOP_TELEGRAM_BOT_TOKEN/CHAT_ID — bỏ qua")
        log.info("notify text:\n%s", text)
        return False
    if len(text) > MAX_LEN:
        text = text[: MAX_LEN - 20] + "\n…(đã cắt bớt)"
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps(
            {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
        ).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 — URL cố định
            return 200 <= resp.status < 300
    except (urllib.error.URLError, TimeoutError) as exc:
        # Không để lỗi Telegram làm fail cả workflow.
        log.warning("notify: gửi Telegram thất bại: %s", exc)
        return False
