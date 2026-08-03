"""Phase 5.1 #3.2/#3.3 — button mapping and the send path that uses it.

The epic's P0 is that no button is lost *silently*. Most of what follows
is that one claim, checked from several directions: every input button
comes back as a Zalo button, as a text line, or as a log record — never
as nothing.

No database and no network here; the mapper is pure and the notifier
talks to a hand-written fake client that records what it was asked to
send.
"""

from __future__ import annotations

import logging

import pytest

from backend.adapters.zalo_button_mapper import (
    BUTTON_TYPE_OPEN_URL,
    BUTTON_TYPE_QUERY_SHOW,
    ZALO_BUTTON_TITLE_MAX_CHARS,
    ZALO_MAX_BUTTONS,
    ButtonCopy,
    load_button_copy,
    map_buttons,
)
from backend.adapters.zalo_notifier import ZaloNotifier
from backend.ports.content_renderer import Button


def _rows(*buttons: Button) -> tuple[tuple[Button, ...], ...]:
    """One button per row — the shape Telegram keyboards usually take."""
    return tuple((b,) for b in buttons)


# ---------------------------------------------------------------------------
# map_buttons — the mapping rules
# ---------------------------------------------------------------------------


def test_callback_button_becomes_query_show_saying_its_own_label():
    buttons, lines = map_buttons(_rows(Button(text="Xem Twin", callback_data="twin:open")))

    assert lines == []
    assert buttons == [
        {
            "title": "Xem Twin",
            "type": BUTTON_TYPE_QUERY_SHOW,
            # `callback_data` cannot cross channels; the user "says" the
            # label and E4's dispatcher routes the resulting text.
            "payload": {"content": "Xem Twin"},
        }
    ]


def test_web_app_button_becomes_open_url():
    buttons, lines = map_buttons(
        _rows(Button(text="Mở bảng điều khiển", web_app_url="https://x.test/twin?b=9"))
    )

    assert lines == []
    assert buttons == [
        {
            "title": "Mở bảng điều khiển",
            "type": BUTTON_TYPE_OPEN_URL,
            "payload": {"url": "https://x.test/twin?b=9"},
        }
    ]


def test_url_wins_when_a_button_carries_both():
    # Telegram renders web_app buttons as a link too — following it is
    # the closer match to what the user would have got.
    buttons, _ = map_buttons(
        _rows(Button(text="Mở", callback_data="twin:open", web_app_url="https://x.test/t"))
    )

    assert buttons[0]["type"] == BUTTON_TYPE_OPEN_URL


def test_rows_are_flattened_in_reading_order():
    rows = (
        (Button(text="Một", callback_data="a"), Button(text="Hai", callback_data="b")),
        (Button(text="Ba", callback_data="c"),),
    )

    buttons, lines = map_buttons(rows)

    assert [b["title"] for b in buttons] == ["Một", "Hai", "Ba"]
    assert lines == []


# ---------------------------------------------------------------------------
# The overflow contract — nothing is dropped, it degrades to text
# ---------------------------------------------------------------------------


def test_buttons_past_the_cap_become_text_lines():
    extras = ZALO_MAX_BUTTONS + 2
    rows = _rows(*(Button(text=f"Nút {i}", callback_data=f"c{i}") for i in range(extras)))

    buttons, lines = map_buttons(rows, copy=ButtonCopy(query_line="say:{title}"))

    assert len(buttons) == ZALO_MAX_BUTTONS
    assert lines == ["say:Nút 5", "say:Nút 6"]
    # The invariant: every input accounted for exactly once.
    assert len(buttons) + len(lines) == extras


def test_overflowing_url_button_keeps_its_link_in_the_text_line():
    rows = _rows(
        *(Button(text=f"Nút {i}", callback_data=f"c{i}") for i in range(ZALO_MAX_BUTTONS)),
        Button(text="Mở app", web_app_url="https://x.test/app"),
    )

    _, lines = map_buttons(rows, copy=ButtonCopy(url_line="{title} -> {url}"))

    assert lines == ["Mở app -> https://x.test/app"]


def test_max_buttons_is_overridable_for_a_narrower_template():
    rows = _rows(*(Button(text=f"N{i}", callback_data=f"c{i}") for i in range(4)))

    buttons, lines = map_buttons(rows, max_buttons=1)

    assert len(buttons) == 1
    assert len(lines) == 3


def test_titleless_url_button_degrades_to_a_line_rather_than_a_blank_button():
    # A Zalo button with an empty title renders as an unlabelled tap
    # target. The URL as text is strictly more useful.
    _, lines = map_buttons(
        _rows(Button(text="", web_app_url="https://x.test/a")),
        copy=ButtonCopy(url_line="{title} | {url}"),
    )

    assert lines == ["https://x.test/a | https://x.test/a"]


def test_button_with_neither_title_nor_url_is_dropped_but_logged(caplog):
    with caplog.at_level(logging.WARNING, logger="backend.adapters.zalo_button_mapper"):
        buttons, lines = map_buttons(_rows(Button(text="   ", callback_data="ghost")))

    assert (buttons, lines) == ([], [])
    # "Not silently" is the whole epic — this is the only drop path and
    # it must leave a trace naming the button.
    assert "ghost" in caplog.text


# ---------------------------------------------------------------------------
# Title sanitising
# ---------------------------------------------------------------------------


def test_title_is_stripped_of_markdown_and_button_spans():
    buttons, _ = map_buttons(_rows(Button(text="[*Xem* Twin]", callback_data="t")))

    assert buttons[0]["title"] == "Xem Twin"


def test_multiline_title_collapses_to_one_line():
    buttons, _ = map_buttons(_rows(Button(text="Xem\nTwin  ngay", callback_data="t")))

    assert buttons[0]["title"] == "Xem Twin ngay"


def test_long_title_is_clipped_by_us_rather_than_rejected_by_zalo():
    buttons, _ = map_buttons(_rows(Button(text="x" * 200, callback_data="t")))

    title = buttons[0]["title"]
    assert len(title) == ZALO_BUTTON_TITLE_MAX_CHARS
    assert title.endswith("…")
    # The query_show payload must be the clipped title too, otherwise the
    # sentence the user "says" no longer matches the button they tapped.
    assert buttons[0]["payload"]["content"] == title


def test_a_broken_copy_template_falls_back_to_the_title():
    rows = _rows(*(Button(text=f"N{i}", callback_data=f"c{i}") for i in range(ZALO_MAX_BUTTONS + 1)))

    _, lines = map_buttons(rows, copy=ButtonCopy(query_line="{nope}"))

    assert lines == [f"N{ZALO_MAX_BUTTONS}"]


def test_no_buttons_in_no_buttons_out():
    assert map_buttons(()) == ([], [])


def test_load_button_copy_reads_the_vietnamese_lines_from_yaml():
    # Copy lives in content/zalo.yaml, never in code (CLAUDE.md). This
    # asserts the section exists and is wired, not its exact wording.
    copy = load_button_copy()

    assert "{title}" in copy.query_line
    assert "{title}" in copy.url_line and "{url}" in copy.url_line


# ---------------------------------------------------------------------------
# ZaloNotifier.send_message — the join point (#3.3)
# ---------------------------------------------------------------------------


class _FakeClient:
    """Records sends instead of making them."""

    is_configured = True

    def __init__(self):
        self.plain: list[tuple[str, str]] = []
        self.with_buttons: list[tuple[str, str, list[dict]]] = []

    async def send_message(self, recipient_id: str, text: str) -> bool:
        self.plain.append((recipient_id, text))
        return True

    async def send_message_with_buttons(
        self, recipient_id: str, text: str, buttons: list[dict]
    ) -> bool:
        self.with_buttons.append((recipient_id, text, buttons))
        return True

    async def send_image_message(self, recipient_id: str, image_url: str, caption: str) -> bool:
        return True


@pytest.mark.asyncio
async def test_send_message_without_buttons_uses_the_plain_endpoint():
    client = _FakeClient()

    result = await ZaloNotifier(client, "u1").send_message(0, "Chào bạn")

    assert result == {"ok": True, "channel": "zalo"}
    assert client.plain == [("u1", "Chào bạn")]
    assert client.with_buttons == []


@pytest.mark.asyncio
async def test_send_message_with_buttons_uses_the_button_endpoint():
    client = _FakeClient()
    rows = _rows(Button(text="Xem Twin", callback_data="twin:open"))

    await ZaloNotifier(client, "u1").send_message(0, "Báo cáo tháng 8", buttons=rows)

    assert client.plain == []
    recipient, text, buttons = client.with_buttons[0]
    assert (recipient, text) == ("u1", "Báo cáo tháng 8")
    assert buttons[0]["type"] == BUTTON_TYPE_QUERY_SHOW


@pytest.mark.asyncio
async def test_suggestion_lines_are_appended_before_the_character_limit_applies():
    # #3.3 is explicit that the lines join the body *before* truncation,
    # so the 300-char ceiling is measured on what the user actually sees.
    client = _FakeClient()
    rows = _rows(*(Button(text=f"Nút {i}", callback_data=f"c{i}") for i in range(ZALO_MAX_BUTTONS + 1)))

    await ZaloNotifier(client, "u1").send_message(0, "x" * 295, buttons=rows)

    _, text, _ = client.with_buttons[0]
    assert len(text) == 300
    assert text.endswith("…")


@pytest.mark.asyncio
async def test_a_short_message_keeps_its_suggestion_lines_intact():
    client = _FakeClient()
    rows = _rows(*(Button(text=f"Nút {i}", callback_data=f"c{i}") for i in range(ZALO_MAX_BUTTONS + 1)))

    await ZaloNotifier(client, "u1").send_message(0, "Đầu tin", buttons=rows)

    _, text, _ = client.with_buttons[0]
    assert text.startswith("Đầu tin\n")
    assert f"Nút {ZALO_MAX_BUTTONS}" in text


@pytest.mark.asyncio
async def test_telegram_reply_markup_is_never_decoded_by_the_zalo_adapter():
    # Passing Telegram's wire format alone must not produce buttons: the
    # Zalo adapter reads the neutral `buttons` kwarg only. If this ever
    # starts failing, the channel coupling 5.1 forbids has crept back in.
    client = _FakeClient()
    markup = {"inline_keyboard": [[{"text": "Xem Twin", "callback_data": "twin:open"}]]}

    await ZaloNotifier(client, "u1").send_message(0, "Chào", reply_markup=markup)

    assert client.with_buttons == []
    assert client.plain == [("u1", "Chào")]


@pytest.mark.asyncio
async def test_send_photo_with_buttons_warns_because_zalo_cannot_carry_both(caplog):
    client = _FakeClient()
    rows = _rows(Button(text="Xem Twin", callback_data="twin:open"))

    with caplog.at_level(logging.WARNING, logger="backend.adapters.zalo_notifier"):
        await ZaloNotifier(client, "u1").send_photo(
            0, b"", caption="Twin", image_url="https://x.test/i.png", buttons=rows
        )

    assert "button" in caplog.text.lower()
