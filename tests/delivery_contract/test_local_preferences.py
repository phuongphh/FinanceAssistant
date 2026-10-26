import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from delivery.controller import Denied, digest  # noqa: E402
from delivery.local_preferences import prepare_request, read_preferences, set_default  # noqa: E402


class PreferencesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = self.root / "preferences.json"
        self.raw = {
            "task": {"issue_number": 7, "branch": "local-issue-7-example"},
            "context_paths": ["x.txt"],
        }

    def test_explicit_default_persists_and_readback(self):
        self.assertTrue(set_default(self.config, "claude")["changed"])
        self.assertEqual(read_preferences(self.config)["default_engine"], "claude")
        self.assertFalse(set_default(self.config, "claude")["changed"])
        set_default(self.config, "codex")
        self.assertEqual(read_preferences(self.config)["default_engine"], "codex")
        self.assertEqual(
            json.loads(self.config.with_suffix(".json.previous").read_text())[
                "default_engine"
            ],
            "claude",
        )

    def test_resolve_before_digest_and_keep_existing_task_after_switch(self):
        set_default(self.config, "claude")
        approved = prepare_request(self.raw, read_preferences(self.config))
        checkpoint = copy.deepcopy(approved)
        approved_digest = digest(approved)
        self.assertEqual(approved["task"]["engine"], "claude")
        self.assertEqual(approved["task"]["branch"], "claude/local-issue-7-example")
        self.assertNotIn("engine", self.raw["task"])
        set_default(self.config, "codex")
        self.assertEqual(approved, checkpoint)
        self.assertEqual(digest(approved), approved_digest)
        next_request = prepare_request(self.raw, read_preferences(self.config))
        self.assertEqual(next_request["task"]["engine"], "codex")

    def test_explicit_one_task_choice_does_not_change_default(self):
        set_default(self.config, "claude")
        self.raw["task"].update(engine="codex")
        result = prepare_request(self.raw, read_preferences(self.config))
        self.assertEqual(result["task"]["engine"], "codex")
        self.assertEqual(read_preferences(self.config)["default_engine"], "claude")

    def test_mismatched_branch_or_invalid_engine_not_silently_rewritten(self):
        set_default(self.config, "claude")
        self.raw["task"]["branch"] = "codex/local-issue-7-example"
        with self.assertRaises(Denied):
            prepare_request(self.raw, read_preferences(self.config))
        with self.assertRaises(Denied):
            set_default(self.config, "other-provider")
        self.assertEqual(read_preferences(self.config)["default_engine"], "claude")

    def test_missing_malformed_or_symlink_preferences_block(self):
        with self.assertRaises(Denied):
            read_preferences(self.config)
        self.config.write_text('{"schema_version":1,"default_engine":"invalid"}')
        with self.assertRaises(Denied):
            read_preferences(self.config)
        link = self.root / "link.json"
        link.symlink_to(self.config)
        with self.assertRaises(Denied):
            set_default(link, "claude")

    def test_default_marker_and_issue_validation(self):
        self.raw["task"]["engine"] = "default"
        self.assertEqual(
            prepare_request(self.raw, {"default_engine": "claude"})["task"]["engine"],
            "claude",
        )
        self.raw["task"]["issue_number"] = True
        with self.assertRaises(Denied):
            prepare_request(self.raw, {"default_engine": "claude"})
