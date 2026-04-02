"""Tests for menu_service — single source of truth for menu data."""
from backend.services.menu_service import (
    FEATURES,
    BOT_COMMANDS,
    get_callback_response,
    get_features_json,
    get_menu_text,
    get_telegram_buttons,
    get_telegram_menu_text,
)


class TestFeatureDefinitions:
    def test_features_not_empty(self):
        assert len(FEATURES) > 0

    def test_each_feature_has_required_keys(self):
        required = {"key", "emoji", "label", "short_label", "trigger_examples", "description"}
        for f in FEATURES:
            missing = required - set(f.keys())
            assert not missing, f"Feature '{f.get('key', '?')}' missing keys: {missing}"

    def test_feature_keys_unique(self):
        keys = [f["key"] for f in FEATURES]
        assert len(keys) == len(set(keys)), "Duplicate feature keys found"

    def test_trigger_examples_not_empty(self):
        for f in FEATURES:
            assert len(f["trigger_examples"]) > 0, f"Feature '{f['key']}' has no trigger examples"


class TestGetMenuText:
    def test_returns_string(self):
        text = get_menu_text()
        assert isinstance(text, str)

    def test_contains_all_feature_labels(self):
        text = get_menu_text()
        for f in FEATURES:
            assert f["label"] in text, f"Menu text missing feature label: {f['label']}"

    def test_contains_header(self):
        text = get_menu_text()
        assert "Finance Assistant" in text


class TestGetTelegramMenuText:
    def test_returns_markdown(self):
        text = get_telegram_menu_text()
        assert "*" in text, "Expected Markdown bold formatting"

    def test_contains_header(self):
        text = get_telegram_menu_text()
        assert "Finance Assistant" in text


class TestGetTelegramButtons:
    def test_returns_list_of_rows(self):
        buttons = get_telegram_buttons()
        assert isinstance(buttons, list)
        assert len(buttons) > 0

    def test_each_button_has_text_and_callback(self):
        for row in get_telegram_buttons():
            for btn in row:
                assert "text" in btn
                assert "callback_data" in btn
                assert btn["callback_data"].startswith("menu:")

    def test_button_count_matches_features(self):
        buttons = get_telegram_buttons()
        total = sum(len(row) for row in buttons)
        assert total == len(FEATURES)


class TestGetCallbackResponse:
    def test_valid_callback_returns_response(self):
        for f in FEATURES:
            resp = get_callback_response(f"menu:{f['key']}")
            assert resp is not None, f"No callback response for menu:{f['key']}"
            assert f["label"] in resp

    def test_invalid_callback_returns_none(self):
        assert get_callback_response("menu:nonexistent") is None
        assert get_callback_response("invalid") is None

    def test_response_contains_trigger_examples(self):
        for f in FEATURES:
            resp = get_callback_response(f"menu:{f['key']}")
            for example in f["trigger_examples"]:
                assert example in resp, f"Callback response for {f['key']} missing example: {example}"


class TestGetFeaturesJson:
    def test_returns_list(self):
        features = get_features_json()
        assert isinstance(features, list)

    def test_matches_features_constant(self):
        assert get_features_json() is FEATURES


class TestBotCommands:
    def test_commands_not_empty(self):
        assert len(BOT_COMMANDS) > 0

    def test_each_command_has_required_keys(self):
        for cmd in BOT_COMMANDS:
            assert "command" in cmd
            assert "description" in cmd

    def test_menu_command_exists(self):
        commands = [c["command"] for c in BOT_COMMANDS]
        assert "menu" in commands
