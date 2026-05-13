"""Tests for the archived V1 menu_service helpers.

Phase 3.6 Epic 3 archived ``services/menu_service.py`` into
``services/_archived/menu_service_v1.py`` and dropped the V1 inline-keyboard
helpers, callback responder, and BOT_COMMANDS list (replaced by Epic 1/2
modules). What survives is the JSON description consumed by the OpenClaw
``finance-menu`` skill via ``GET /telegram/menu``. Tests below pin only
that surface so we don't accidentally break the OpenClaw contract while
the skill is still in use.

When OpenClaw is fully migrated off these helpers, this file (and the
archived module) can be deleted together.
"""
from backend.services._archived.menu_service_v1 import (
    FEATURES,
    get_features_json,
    get_menu_text,
)


class TestFeatureDefinitions:
    def test_features_not_empty(self):
        assert len(FEATURES) > 0

    def test_each_feature_has_required_keys(self):
        required = {
            "key", "emoji", "label", "short_label",
            "trigger_examples", "description",
        }
        for f in FEATURES:
            missing = required - set(f.keys())
            assert not missing, f"Feature '{f.get('key', '?')}' missing keys: {missing}"

    def test_feature_keys_unique(self):
        keys = [f["key"] for f in FEATURES]
        assert len(keys) == len(set(keys)), "Duplicate feature keys found"

    def test_trigger_examples_not_empty(self):
        for f in FEATURES:
            assert len(f["trigger_examples"]) > 0, (
                f"Feature '{f['key']}' has no trigger examples"
            )


class TestGetMenuText:
    def test_returns_string(self):
        text = get_menu_text()
        assert isinstance(text, str)

    def test_contains_all_feature_labels(self):
        text = get_menu_text()
        for f in FEATURES:
            assert f["label"] in text, (
                f"Menu text missing feature label: {f['label']}"
            )

    def test_contains_header(self):
        text = get_menu_text()
        assert "Finance Assistant" in text


class TestGetFeaturesJson:
    def test_returns_list(self):
        features = get_features_json()
        assert isinstance(features, list)

    def test_matches_features_constant(self):
        assert get_features_json() is FEATURES
