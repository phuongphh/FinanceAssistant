"""Tests for Issue #28: callback convention + keyboards."""

import uuid

import pytest

from backend.bot.keyboards.common import (
    TELEGRAM_CALLBACK_DATA_MAX_BYTES,
    CallbackPrefix,
    build_callback,
    parse_callback,
)
from backend.bot.keyboards.transaction_keyboard import (
    category_picker_keyboard,
    confirm_delete_keyboard,
    source_picker_keyboard,
    transaction_actions_keyboard,
    transaction_actions_with_done_keyboard,
    transaction_batch_actions_keyboard,
)
from backend.config.categories import get_all_categories


class TestParseCallback:
    def test_simple(self):
        assert parse_callback("edit_tx:123") == ("edit_tx", ["123"])

    def test_multi_arg(self):
        assert parse_callback("change_cat:abc:food") == ("change_cat", ["abc", "food"])

    def test_no_args(self):
        assert parse_callback("cancel") == ("cancel", [])

    def test_uuid_arg(self):
        tx = str(uuid.uuid4())
        prefix, args = parse_callback(f"del_tx:{tx}")
        assert prefix == "del_tx"
        assert args == [tx]


class TestBuildCallback:
    def test_basic(self):
        assert build_callback("edit_tx", "123") == "edit_tx:123"

    def test_multi_args(self):
        assert build_callback("change_cat", "abc", "food") == "change_cat:abc:food"

    def test_no_args(self):
        assert build_callback("cancel") == "cancel"

    def test_coerces_non_string_args(self):
        assert build_callback("edit_tx", 42) == "edit_tx:42"

    def test_rejects_colon_in_arg(self):
        with pytest.raises(ValueError, match="must not contain"):
            build_callback("edit_tx", "bad:id")

    def test_rejects_empty_prefix(self):
        with pytest.raises(ValueError):
            build_callback("", "123")

    def test_rejects_too_long(self):
        with pytest.raises(ValueError, match="exceeds"):
            build_callback("change_cat", "x" * 80)

    def test_under_64_bytes_with_uuid(self):
        tx = str(uuid.uuid4())
        data = build_callback(CallbackPrefix.CHANGE_CATEGORY, tx, "entertainment")
        assert len(data.encode("utf-8")) <= TELEGRAM_CALLBACK_DATA_MAX_BYTES

    def test_roundtrip(self):
        tx = str(uuid.uuid4())
        data = build_callback(CallbackPrefix.CHANGE_CATEGORY, tx, "food")
        prefix, args = parse_callback(data)
        assert prefix == CallbackPrefix.CHANGE_CATEGORY
        assert args == [tx, "food"]


class TestTransactionActionsKeyboard:
    def test_structure(self):
        kb = transaction_actions_keyboard("abc")
        assert "inline_keyboard" in kb
        rows = kb["inline_keyboard"]
        assert len(rows) == 1
        assert len(rows[0]) == 4  # 🏷 / 💳 / 💵 / 🗑

    def test_button_labels_icon_only(self):
        kb = transaction_actions_keyboard("abc")
        labels = [btn["text"] for row in kb["inline_keyboard"] for btn in row]
        assert labels == ["🏷", "💳", "💵", "🗑"]

    def test_callback_prefixes(self):
        tx = str(uuid.uuid4())
        kb = transaction_actions_keyboard(tx)
        prefixes = [
            parse_callback(btn["callback_data"])[0]
            for row in kb["inline_keyboard"]
            for btn in row
        ]
        assert prefixes == [
            CallbackPrefix.CHANGE_CATEGORY,
            CallbackPrefix.CHANGE_SOURCE,
            CallbackPrefix.EDIT_AMOUNT,
            CallbackPrefix.DELETE_TRANSACTION,
        ]

    def test_callback_data_within_limit(self):
        tx = str(uuid.uuid4())
        kb = transaction_actions_keyboard(tx)
        for row in kb["inline_keyboard"]:
            for btn in row:
                assert (
                    len(btn["callback_data"].encode("utf-8"))
                    <= TELEGRAM_CALLBACK_DATA_MAX_BYTES
                )


class TestTransactionActionsWithDoneKeyboard:
    def test_adds_done_row(self):
        tx = str(uuid.uuid4())
        kb = transaction_actions_with_done_keyboard(tx)
        rows = kb["inline_keyboard"]
        assert len(rows) == 2
        assert len(rows[0]) == 4
        assert len(rows[1]) == 1
        done_btn = rows[1][0]
        assert "Đồng ý" in done_btn["text"]
        prefix, args = parse_callback(done_btn["callback_data"])
        assert prefix == CallbackPrefix.CONFIRM_EDIT_DONE
        assert args == [tx]


class TestSourcePickerKeyboard:
    def test_has_all_source_types_and_cancel(self):
        tx = str(uuid.uuid4())
        kb = source_picker_keyboard(tx)
        labels = [btn["text"] for row in kb["inline_keyboard"] for btn in row]
        assert any("Tiền mặt" in label for label in labels)
        assert any("Tài khoản" in label for label in labels)
        assert any("Ví điện tử" in label for label in labels)
        assert any("Thẻ tín dụng" in label for label in labels)
        assert kb["inline_keyboard"][-1][0]["text"] == "❌ Hủy"

    def test_callbacks_within_limit(self):
        tx = str(uuid.uuid4())
        kb = source_picker_keyboard(tx)
        for row in kb["inline_keyboard"]:
            for btn in row:
                assert (
                    len(btn["callback_data"].encode("utf-8"))
                    <= TELEGRAM_CALLBACK_DATA_MAX_BYTES
                )


class TestTransactionBatchActionsKeyboard:
    def test_undo_batch_callback(self):
        batch_id = str(uuid.uuid4())
        kb = transaction_batch_actions_keyboard(batch_id)
        button = kb["inline_keyboard"][0][0]
        prefix, args = parse_callback(button["callback_data"])
        assert prefix == CallbackPrefix.UNDO_TRANSACTION_BATCH
        assert args == [batch_id]
        assert (
            len(button["callback_data"].encode("utf-8"))
            <= TELEGRAM_CALLBACK_DATA_MAX_BYTES
        )


class TestCategoryPickerKeyboard:
    def test_has_all_categories(self):
        tx = str(uuid.uuid4())
        kb = category_picker_keyboard(tx)
        labels = [btn["text"] for row in kb["inline_keyboard"] for btn in row]
        for cat in get_all_categories():
            assert any(cat.name_vi in label for label in labels)

    def test_two_columns(self):
        tx = str(uuid.uuid4())
        kb = category_picker_keyboard(tx)
        # Last row is cancel button; all others should have <= 2 columns
        for row in kb["inline_keyboard"][:-1]:
            assert len(row) <= 2

    def test_has_cancel(self):
        kb = category_picker_keyboard("abc")
        last_row = kb["inline_keyboard"][-1]
        assert last_row[0]["text"] == "❌ Hủy"

    def test_callback_encodes_category_code(self):
        tx = str(uuid.uuid4())
        kb = category_picker_keyboard(tx)
        food_button = next(
            btn
            for row in kb["inline_keyboard"]
            for btn in row
            if "Ăn uống" in btn["text"]
        )
        prefix, args = parse_callback(food_button["callback_data"])
        assert prefix == CallbackPrefix.CHANGE_CATEGORY
        assert args[-1] == "food"

    def test_all_callbacks_within_byte_limit(self):
        tx = str(uuid.uuid4())
        kb = category_picker_keyboard(tx)
        for row in kb["inline_keyboard"]:
            for btn in row:
                assert (
                    len(btn["callback_data"].encode("utf-8"))
                    <= TELEGRAM_CALLBACK_DATA_MAX_BYTES
                )


class TestConfirmDeleteKeyboard:
    def test_two_buttons(self):
        kb = confirm_delete_keyboard("abc")
        row = kb["inline_keyboard"][0]
        assert len(row) == 2
        assert "✅" in row[0]["text"]
        assert "❌" in row[1]["text"]

    def test_confirm_callback_format(self):
        tx = str(uuid.uuid4())
        kb = confirm_delete_keyboard(tx)
        confirm_btn = kb["inline_keyboard"][0][0]
        prefix, args = parse_callback(confirm_btn["callback_data"])
        assert prefix == CallbackPrefix.CONFIRM_ACTION
        assert args[0] == "delete"
        assert args[1] == tx
