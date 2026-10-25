import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from delivery.admission import (  # noqa: E402 - standalone unittest discovery
    Admission,
    GitHubReadClient,
    NoRedirect,
    approval_line,
    approval_digest,
    decode,
    timestamp,
)
from delivery.controller import Ledger, Denied  # noqa: E402
from delivery.engines import EngineResult  # noqa: E402


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.task = json.loads((ROOT / "docs/contracts/examples/task.json").read_text())
        self.task["limits"].update(max_cost_usd=1, daily_budget_reference="test-budget")
        self.task["approval"].update(
            reference="https://github.com/phuongphh/FinanceAssistant/issues/1#issuecomment-7",
            actor="owner",
            approved_at="2026-10-25T00:00:00Z",
        )
        self.config = json.loads((ROOT / ".github/delivery.json").read_text())
        self.policy = json.loads((ROOT / ".github/fleet-admission.json").read_text())
        self.policy.update(
            enabled=True,
            approver_ids=[123],
            policy_id="test-budget",
            daily_budget_usd=2,
            max_task_cost_usd=1,
        )
        self.now = timestamp(self.task["approval"]["approved_at"]) + 10
        self.prefix = "/repos/phuongphh/FinanceAssistant"
        self.comment_path = self.prefix + "/issues/comments/7"
        self.data = {
            self.prefix: {
                "id": 1189887539,
                "full_name": self.task["repository"],
                "default_branch": "main",
                "archived": False,
            },
            self.prefix + "/issues/1": {
                "number": 1,
                "state": "open",
                "html_url": "https://github.com/phuongphh/FinanceAssistant/issues/1",
            },
            self.prefix + "/compare/" + self.task["base_sha"] + "...main": {
                "status": "ahead",
                "merge_base_commit": {"sha": self.task["base_sha"]},
            },
            self.comment_path: {
                "id": 7,
                "html_url": self.task["approval"]["reference"],
                "issue_url": "https://api.github.com" + self.prefix + "/issues/1",
                "body": approval_line(self.task),
                "user": {"id": 123, "login": "owner", "type": "User"},
                "created_at": self.task["approval"]["approved_at"],
                "updated_at": self.task["approval"]["approved_at"],
            },
            self.prefix + "/collaborators/owner/permission": {
                "permission": "admin",
                "user": {"id": 123},
            },
        }
        self.github = Mock()
        self.github.get.side_effect = lambda path: copy.deepcopy(self.data[path])
        self.intake = self.make()
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Ledger(
            Path(self.tmp.name) / "state", daily_usd=2, approvers=["github:123"]
        )

    def make(self):
        return Admission(self.policy, self.config, self.github, clock=lambda: self.now)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_preparation_never_reads_github_or_grants(self):
        self.policy["enabled"] = False
        result = self.make().prepare(self.task)
        self.assertFalse(result["admitted"])
        self.assertEqual(result["approval_line"], approval_line(self.task))
        self.github.get.assert_not_called()
        self.assertEqual(self.db.status(), [])

    def test_digest_binds_all_task_content_except_generated_metadata(self):
        original = approval_digest(self.task)
        for field, value in [
            ("goal", "different"),
            ("engine", "claude"),
            ("base_sha", "b" * 40),
            ("acceptance_criteria", []),
            ("scope", {}),
            ("limits", {}),
            ("dependencies", ["https://example.com"]),
            ("branch", "agent/issue-1-other"),
            ("task_id", "other"),
        ]:
            with self.subTest(field=field):
                changed = copy.deepcopy(self.task)
                changed[field] = value
                self.assertNotEqual(original, approval_digest(changed))
        changed = copy.deepcopy(self.task)
        changed["approval"]["scope_id"] = "different"
        self.assertNotEqual(original, approval_digest(changed))
        for field in ("reference", "actor", "approved_at"):
            changed = copy.deepcopy(self.task)
            changed["approval"][field] = "generated"
            self.assertEqual(original, approval_digest(changed))

    def test_verified_grant_and_evidence_persist_atomically_and_replay(self):
        result = self.intake.admit(self.task, self.db)
        self.now += 1
        self.intake.admit(self.task, self.db)
        self.assertEqual(result["actor"], "github:123")
        self.assertEqual(
            self.db.db.execute("SELECT COUNT(*) FROM grants").fetchone()[0], 1
        )
        saved = json.loads(
            self.db.db.execute("SELECT record FROM approval_evidence").fetchone()[0]
        )
        self.assertEqual(saved, result)
        self.assertEqual(self.db.status(), [])

    def test_evidence_storage_failure_rolls_back_grant(self):
        evidence = self.intake.verify(self.task)
        evidence["not_serializable"] = object()
        with self.assertRaises(TypeError):
            self.db.approve(
                self.task,
                actor="github:123",
                verified_reference=evidence["reference"],
                evidence=evidence,
            )
        self.assertEqual(
            self.db.db.execute("SELECT COUNT(*) FROM grants").fetchone()[0], 0
        )

    def test_disabled_policy_does_not_read_or_admit(self):
        self.policy["enabled"] = False
        with self.assertRaises(Denied):
            self.make().admit(self.task, self.db)
        self.github.get.assert_not_called()

    def test_zero_or_mismatched_budget_is_not_authorized(self):
        self.policy["daily_budget_usd"] = 0
        with self.assertRaises(Denied):
            self.make()
        self.policy["daily_budget_usd"] = 3
        with self.assertRaises(Denied):
            self.make().admit(self.task, self.db)
        self.policy["daily_budget_usd"] = 2
        self.task["limits"]["max_cost_usd"] = 1.1
        self.data[self.comment_path]["body"] = approval_line(self.task)
        with self.assertRaises(Denied):
            self.make().admit(self.task, self.db)

    def test_foreign_approval_url_never_fetched(self):
        for url in [
            "https://evil.example/issues/1#issuecomment-7",
            "https://github.com/phuongphh/FinanceAssistant/issues/2#issuecomment-7",
            self.task["approval"]["reference"] + "?x=1",
        ]:
            with self.subTest(url=url), self.assertRaises(Denied):
                self.task["approval"]["reference"] = url
                self.intake.verify(self.task)
        self.github.get.assert_not_called()

    def test_spoofed_comment_metadata_denied(self):
        original = copy.deepcopy(self.data[self.comment_path])
        for field, value in [
            ("id", 8),
            ("issue_url", "https://api.github.com/repos/other/repo/issues/1"),
            ("html_url", "https://github.com/other/repo/issues/1#issuecomment-7"),
            ("user", {"id": 999, "login": "owner", "type": "User"}),
            ("user", {"id": 123, "login": "owner", "type": "Bot"}),
            ("user", {"id": 123, "login": "imposter", "type": "User"}),
            ("body", "Please approve " + approval_line(self.task)),
            ("updated_at", "2026-10-25T00:00:01Z"),
        ]:
            with self.subTest(field=field, value=value):
                self.data[self.comment_path] = copy.deepcopy(original)
                self.data[self.comment_path][field] = value
                with self.assertRaises(Denied):
                    self.intake.verify(self.task)

    def test_stale_future_or_wrong_timestamp_denied(self):
        for now in (
            timestamp("2026-10-26T00:00:01Z"),
            timestamp("2026-10-24T23:59:59Z"),
        ):
            self.now = now
            with self.assertRaises(Denied):
                self.intake.verify(self.task)
        self.now = timestamp("2026-10-25T00:00:10Z")
        self.task["approval"]["approved_at"] = "2026-10-25T00:00:02Z"
        with self.assertRaises(Denied):
            self.intake.verify(self.task)

    def test_changed_task_denied_without_new_approval(self):
        self.task["goal"] = "Run something else"
        with self.assertRaises(Denied):
            self.intake.admit(self.task, self.db)

    def test_closed_locked_pr_issue_and_wrong_repo_denied(self):
        for path, field, value in [
            (self.prefix, "id", 99),
            (self.prefix, "archived", True),
            (self.prefix, "default_branch", "prod"),
            (self.prefix + "/issues/1", "state", "closed"),
            (self.prefix + "/issues/1", "locked", True),
            (self.prefix + "/issues/1", "pull_request", {}),
        ]:
            old = copy.deepcopy(self.data[path])
            self.data[path][field] = value
            with self.subTest(field=field), self.assertRaises(Denied):
                self.intake.verify(self.task)
            self.data[path] = old

    def test_permission_removed_or_different_user_denied(self):
        path = self.prefix + "/collaborators/owner/permission"
        for value in [
            {"permission": "read", "user": {"id": 123}},
            {"permission": "admin", "user": {"id": 999}},
        ]:
            self.data[path] = value
            with self.assertRaises(Denied):
                self.intake.verify(self.task)

    def test_dependency_requires_completed_same_repo_issue(self):
        url = "https://github.com/phuongphh/FinanceAssistant/issues/2"
        self.task["dependencies"] = [url]
        self.data[self.comment_path]["body"] = approval_line(self.task)
        path = self.prefix + "/issues/2"
        for state, reason in [("open", None), ("closed", "not_planned")]:
            self.data[path] = {"state": state, "state_reason": reason, "html_url": url}
            with self.assertRaises(Denied):
                self.intake.verify(self.task)
        self.data[path] = {
            "state": "closed",
            "state_reason": "completed",
            "html_url": url,
        }
        self.intake.verify(self.task)
        self.task["dependencies"] = ["https://github.com/other/repo/issues/2"]
        with self.assertRaises(Denied):
            self.intake.verify(self.task)

    def test_unmerged_base_denied(self):
        self.data[self.prefix + "/compare/" + self.task["base_sha"] + "...main"][
            "merge_base_commit"
        ]["sha"] = "b" * 40
        with self.assertRaises(Denied):
            self.intake.verify(self.task)

    def test_no_api_error_fallback(self):
        self.github.get.side_effect = Denied("unavailable")
        with self.assertRaises(Denied):
            self.intake.admit(self.task, self.db)
        self.assertEqual(
            self.db.db.execute("SELECT COUNT(*) FROM grants").fetchone()[0], 0
        )

    def test_revoked_comment_stops_before_retry(self):
        calls = []

        def executor(*args):
            calls.append(1)
            self.data[self.comment_path]["body"] = "approval withdrawn"
            return EngineResult("codex", "infra_failed", session_id="session-123")

        with self.assertRaises(Denied):
            self.intake.execute(
                self.task,
                self.db,
                event_id="one",
                reservation_usd=".2",
                executor=executor,
                gate=Mock(),
                execution_enabled=True,
                sleeper=lambda _: None,
            )
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(self.db.status()), 1)

    def test_revocation_during_gates_cannot_publish_review_ready(self):
        executor = Mock(
            return_value=EngineResult("codex", "completed", session_id="session-123")
        )

        def gate(*args):
            self.data[self.comment_path]["body"] = "approval withdrawn"
            return {
                "changed_files": ["example/code.py"],
                "head_sha": "b" * 40,
                "gates": {
                    "status": "passed",
                    "evidence": [
                        {
                            "url": "https://example.com/gate",
                            "description": "Isolated test",
                        }
                    ],
                },
                "patch_digest": "patch-one",
            }

        with self.assertRaises(Denied):
            self.intake.execute(
                self.task,
                self.db,
                event_id="one",
                reservation_usd=".2",
                executor=executor,
                gate=gate,
                execution_enabled=True,
            )
        self.assertEqual(self.db.status()[0]["phase"], "running")
        self.assertFalse(
            list((self.db.directory / "runs").glob("*/worker-result.json"))
        )

    def test_successful_admitted_run_replays_without_second_executor(self):
        executor = Mock(
            return_value=EngineResult("codex", "completed", session_id="session-123")
        )
        gate = Mock(
            return_value={
                "changed_files": ["example/code.py"],
                "head_sha": "b" * 40,
                "gates": {
                    "status": "passed",
                    "evidence": [
                        {
                            "url": "https://example.com/gate",
                            "description": "Isolated test",
                        }
                    ],
                },
                "patch_digest": "patch-one",
            }
        )
        kwargs = dict(
            event_id="one",
            reservation_usd=".2",
            executor=executor,
            gate=gate,
            execution_enabled=True,
        )
        result = self.intake.execute(self.task, self.db, **kwargs)
        self.assertEqual(result["receipts"][0]["status"], "review_ready")
        self.assertTrue(self.intake.execute(self.task, self.db, **kwargs)["replayed"])
        self.assertEqual(executor.call_count, 1)

    def test_changed_policy_cannot_reuse_prior_grant(self):
        self.intake.admit(self.task, self.db)
        self.policy["approval_max_age_seconds"] = 3600
        with self.assertRaises(Denied):
            self.make().admit(self.task, self.db)


class IntakeTransportTests(unittest.TestCase):
    def test_duplicate_keys_nonfinite_and_oversize_denied(self):
        for raw in [b'{"a":1,"a":2}', b'{"x":NaN}', b" " * 262145]:
            with self.assertRaises(Denied):
                decode(raw)

    def test_fixed_get_origin_and_compare_path(self):
        client = GitHubReadClient("fake-token")
        context = Mock()
        context.__enter__ = Mock(return_value=io.BytesIO(b'{"ok":true}'))
        context.__exit__ = Mock(return_value=False)
        client.opener = Mock()
        client.opener.open.return_value = context
        self.assertTrue(
            client.get("/repos/example/repo/compare/" + "a" * 40 + "...main")["ok"]
        )
        request = client.opener.open.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertTrue(request.full_url.startswith("https://api.github.com/repos/"))
        for path in [
            "https://evil.example",
            "//evil.example",
            "/repos/x/y/../../evil",
            "/repos/x/y?token=x",
        ]:
            with self.assertRaises(Denied):
                client.get(path)

    def test_redirect_and_http_failure_do_not_echo_secret(self):
        with self.assertRaises(Denied):
            NoRedirect().redirect_request(None, None, None, None, None, None)
        client = GitHubReadClient("secret")
        client.opener = Mock()
        client.opener.open.side_effect = HTTPError(
            "https://api.github.com", 403, "secret", {}, None
        )
        with self.assertRaises(Denied) as error:
            client.get("/repos/example/repo")
        self.assertNotIn("secret", str(error.exception))


if __name__ == "__main__":
    unittest.main()
