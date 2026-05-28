"""Pagination guards for asset list keyboards.

Background: ``asset_dashboard_edit_keyboard`` (Tài sản → Báo cáo) and the
two ``asset_manage`` list keyboards used to render one row per asset with
no upper bound. Around ~46 assets the serialized ``reply_markup`` JSON
crossed Telegram's practical ~10 KB limit and the API silently rejected
the message with ``Bad Request: reply markup is too long``. These tests
lock in pagination so the regression cannot recur.
"""
from __future__ import annotations

import json
import uuid

from backend.bot.keyboards.asset_keyboard import (
    ASSET_LIST_PAGE_SIZE,
    asset_dashboard_edit_keyboard,
    asset_delete_list_keyboard,
    asset_edit_list_keyboard,
    clamp_page,
)


# Telegram's practical reply_markup limit is ~10 KB; we keep keyboards
# comfortably below half of that so headers + nav rows don't push us over.
_KEYBOARD_BUDGET_BYTES = 4 * 1024


def _serialize(markup: dict) -> int:
    return len(json.dumps(markup, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _rows(n: int) -> list[tuple[uuid.UUID, str]]:
    # Realistic worst case: emoji + ~30-char VN asset label.
    return [(uuid.uuid4(), f"🏦 Vinhomes Grand Park 2PN A{i:04d}") for i in range(n)]


class TestPageSlice:
    def test_clamp_negative_to_zero(self):
        assert clamp_page(-5, 100) == 0

    def test_clamp_overshoot_to_last_page(self):
        # 100 items, page_size 8 -> last index = 12
        assert clamp_page(999, 100, page_size=8) == 12

    def test_empty_list_returns_zero(self):
        assert clamp_page(7, 0) == 0

    def test_in_range_unchanged(self):
        assert clamp_page(3, 100, page_size=8) == 3


class TestDashboardKeyboardSize:
    def test_single_page_when_under_page_size(self):
        kb = asset_dashboard_edit_keyboard(_rows(5))
        # 1 sort row + 5 asset rows + back row = 7 rows (no pagination row)
        assert len(kb["inline_keyboard"]) == 7

    def test_paginates_at_page_size(self):
        kb = asset_dashboard_edit_keyboard(_rows(ASSET_LIST_PAGE_SIZE * 3))
        # sort row + N asset rows + pagination row + back row
        asset_rows = [
            row for row in kb["inline_keyboard"]
            if any(b.get("callback_data", "").startswith("asset:edit:") for b in row)
        ]
        assert len(asset_rows) == ASSET_LIST_PAGE_SIZE

    def test_pagination_nav_appears_only_when_multipage(self):
        single = asset_dashboard_edit_keyboard(_rows(3))
        multi = asset_dashboard_edit_keyboard(_rows(20))
        single_cbs = {b.get("callback_data") for row in single["inline_keyboard"] for b in row}
        multi_cbs = {b.get("callback_data") for row in multi["inline_keyboard"] for b in row}
        assert not any(cb and cb.startswith("asset:page:") for cb in single_cbs)
        assert any(cb and cb.startswith("asset:page:") for cb in multi_cbs)

    def test_200_assets_stays_under_budget(self):
        # Used to be ~43 KB without pagination -> Telegram rejected.
        kb = asset_dashboard_edit_keyboard(_rows(200))
        size = _serialize(kb)
        assert size < _KEYBOARD_BUDGET_BYTES, (
            f"Keyboard is {size} bytes — pagination should keep it under "
            f"{_KEYBOARD_BUDGET_BYTES} bytes regardless of asset count"
        )

    def test_last_page_partial(self):
        rows = _rows(ASSET_LIST_PAGE_SIZE * 2 + 3)
        kb = asset_dashboard_edit_keyboard(rows, page=2)
        asset_rows = [
            row for row in kb["inline_keyboard"]
            if any(b.get("callback_data", "").startswith("asset:edit:") for b in row)
        ]
        assert len(asset_rows) == 3

    def test_page_overflow_clamped_to_last(self):
        rows = _rows(10)  # 2 pages
        kb = asset_dashboard_edit_keyboard(rows, page=999)
        # Page 1 (0-indexed) has rows 8-9 → 2 asset rows
        asset_rows = [
            row for row in kb["inline_keyboard"]
            if any(b.get("callback_data", "").startswith("asset:edit:") for b in row)
        ]
        assert len(asset_rows) == 2

    def test_sort_buttons_persist_across_pages(self):
        rows = _rows(30)
        for page in (0, 1, 2, 3):
            kb = asset_dashboard_edit_keyboard(rows, page=page, current_sort="alpha")
            first_row = kb["inline_keyboard"][0]
            cbs = [b["callback_data"] for b in first_row]
            assert all(cb.startswith("asset:sort:") for cb in cbs)

    def test_delete_button_uses_compact_icon_for_more_edit_label_space(self):
        kb = asset_dashboard_edit_keyboard(_rows(1))
        delete_btn = kb["inline_keyboard"][1][1]
        assert delete_btn["text"] == "🗑"

    def test_returns_none_for_empty(self):
        assert asset_dashboard_edit_keyboard([]) is None


class TestManageListKeyboards:
    def test_edit_list_paginates_under_budget(self):
        candidates = _rows(150)
        kb = asset_edit_list_keyboard(candidates, asset_type="stock")
        assert _serialize(kb) < _KEYBOARD_BUDGET_BYTES

    def test_delete_list_paginates_under_budget(self):
        candidates = _rows(150)
        kb = asset_delete_list_keyboard(candidates, asset_type="real_estate")
        assert _serialize(kb) < _KEYBOARD_BUDGET_BYTES

    def test_edit_list_page_nav_callback_shape(self):
        candidates = _rows(20)
        kb = asset_edit_list_keyboard(candidates, asset_type="stock", page=0)
        nav_cbs = [
            b["callback_data"]
            for row in kb["inline_keyboard"]
            for b in row
            if b.get("callback_data", "").startswith("asset_manage:edit_page:")
        ]
        assert nav_cbs, "Multi-page edit list must include navigation buttons"
        # callback fits Telegram's 64-byte cap
        assert all(len(cb.encode("utf-8")) <= 64 for cb in nav_cbs)

    def test_delete_list_page_nav_callback_shape(self):
        candidates = _rows(20)
        kb = asset_delete_list_keyboard(candidates, asset_type="real_estate", page=1)
        nav_cbs = [
            b["callback_data"]
            for row in kb["inline_keyboard"]
            for b in row
            if b.get("callback_data", "").startswith("asset_manage:del_page:")
        ]
        assert nav_cbs
        assert all(len(cb.encode("utf-8")) <= 64 for cb in nav_cbs)

    def test_no_pagination_row_for_single_page(self):
        candidates = _rows(ASSET_LIST_PAGE_SIZE)
        kb = asset_edit_list_keyboard(candidates, asset_type="stock")
        page_cbs = [
            b["callback_data"]
            for row in kb["inline_keyboard"]
            for b in row
            if "edit_page" in b.get("callback_data", "")
        ]
        assert not page_cbs
