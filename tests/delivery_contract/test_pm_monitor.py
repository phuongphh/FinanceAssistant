import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from delivery.pm_monitor import Monitor, classify, pages, message, affects_dev  # noqa: E402

from delivery.controller import Denied  # noqa: E402

REPO = "example/repo"
REQUIRED = {".github/workflows/ci.yml": "pytest"}


def sample():
    pr = {
        "number": 1,
        "state": "open",
        "draft": False,
        "merged": False,
        "mergeable": True,
        "mergeable_state": "clean",
        "head": {
            "sha": "a" * 40,
            "ref": "codex/local-issue-2-test",
            "repo": {"full_name": REPO},
        },
        "base": {"ref": "main"},
        "title": "Improve news",
        "html_url": "https://github.com/example/repo/pull/1",
        "created_at": "2026-10-26T00:00:00Z",
    }
    run = {
        "id": 10,
        "path": ".github/workflows/ci.yml",
        "head_sha": "a" * 40,
        "head_branch": pr["head"]["ref"],
        "event": "pull_request",
        "pull_requests": [{"number": 1}],
        "status": "completed",
        "conclusion": "success",
    }
    jobs = {10: [{"name": "pytest", "head_sha": "a" * 40, "conclusion": "success"}]}
    return pr, [run], jobs


class DecisionTests(unittest.TestCase):
    def setUp(self):
        self.pr, self.runs, self.jobs = sample()

    def decide(self, reviews=None):
        return classify(self.pr, self.runs, self.jobs, reviews or [], REQUIRED)

    def test_success_for_current_pr_is_ready(self):
        self.assertEqual(self.decide(), "ready")

    def test_wrong_head_foreign_pr_or_workflow_never_ready(self):
        for field, value in [
            ("head_sha", "b" * 40),
            ("path", ".github/workflows/other.yml"),
            ("pull_requests", [{"number": 99}]),
            ("event", "push"),
        ]:
            pr, runs, jobs = sample()
            runs[0][field] = value
            self.assertEqual(classify(pr, runs, jobs, [], REQUIRED), "pending")

    def test_latest_failure_supersedes_old_success_and_skips_fail(self):
        bad = {**self.runs[0], "id": 11, "conclusion": "failure"}
        self.runs.append(bad)
        self.assertEqual(self.decide(), "checks_failed")
        self.runs = [{**self.runs[0], "conclusion": "skipped"}]
        self.assertEqual(self.decide(), "checks_failed")

    def test_actual_job_must_succeed_on_current_head(self):
        self.jobs[10][0]["head_sha"] = "b" * 40
        self.assertEqual(self.decide(), "checks_failed")

    def test_draft_mergeability_or_pending_never_asks_merge(self):
        for field, value in [
            ("draft", True),
            ("mergeable", None),
            ("mergeable_state", "blocked"),
        ]:
            pr, runs, jobs = sample()
            pr[field] = value
            self.assertEqual(classify(pr, runs, jobs, [], REQUIRED), "pending")
        self.pr["mergeable"] = False
        self.assertEqual(self.decide(), "needs_revision")

    def test_commented_review_does_not_clear_changes_requested(self):
        reviews = [
            {"id": 1, "user": {"login": "reviewer"}, "state": "CHANGES_REQUESTED"},
            {"id": 2, "user": {"login": "reviewer"}, "state": "COMMENTED"},
        ]
        self.assertEqual(self.decide(reviews), "needs_revision")
        reviews.append({"id": 3, "user": {"login": "reviewer"}, "state": "APPROVED"})
        self.assertEqual(self.decide(reviews), "ready")

    def test_closed_or_merged_not_deployed(self):
        self.pr["state"] = "closed"
        self.assertEqual(self.decide(), "closed")
        self.pr["merged"] = True
        self.assertEqual(self.decide(), "merged")
        self.assertIn("chưa xác nhận triển khai Dev", message(REPO, self.pr, "merged"))


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "state"
        self.pr, self.runs, self.jobs = sample()
        self.opened = [copy.deepcopy(self.pr)]
        self.closed = []
        self.files = [{"filename": "backend/example.py"}]
        self.config = {
            "destination": {"channel": "telegram", "account": "pm", "target": "123"},
            "repositories": [
                {
                    "name": REPO,
                    "watch_prs": [],
                    "watch_issues": [],
                    "discover_after": "2026-10-25T00:00:00Z",
                    "required_workflows": REQUIRED,
                }
            ],
        }
        self.sent = Mock(return_value="message-1")
        self.queries = []
        self.now = 10000

    def api(self, repo, path):
        self.assertEqual(repo, REPO)
        self.queries.append(path)
        if path.startswith("pulls?state=closed"):
            return copy.deepcopy(self.closed)
        if path.startswith("pulls/1/files"):
            return copy.deepcopy(self.files)
        if path.startswith("pulls?"):
            return copy.deepcopy(self.opened)
        if path.startswith("pulls/1/reviews"):
            return []
        if path == "pulls/1":
            return copy.deepcopy(self.pr)
        if path.startswith("actions/runs?"):
            return {"workflow_runs": copy.deepcopy(self.runs)}
        if path.startswith("actions/runs/10/jobs"):
            return {"jobs": copy.deepcopy(self.jobs[10])}
        raise AssertionError(path)

    def monitor(self):
        return Monitor(
            self.root,
            self.config,
            github=self.api,
            send=self.sent,
            clock=lambda: self.now,
        )

    def test_confirmed_send_dedup_survives_restart(self):
        self.assertEqual(self.monitor().tick()["notifications"], 1)
        self.assertEqual(self.monitor().tick()["notifications"], 0)
        self.sent.assert_called_once()
        self.assertIn("Bạn cần:", self.sent.call_args.args[1])
        self.assertIn("Chưa cần thử", self.sent.call_args.args[1])
        self.assertLess(len(self.sent.call_args.args[1].split()), 120)
        self.assertTrue(all("POST" not in q for q in self.queries))

    def test_failure_not_acknowledged_retries_and_preserves_outbox(self):
        self.sent.side_effect = RuntimeError("network failure")
        with self.assertRaises(RuntimeError):
            self.monitor().tick()
        state = json.loads((self.root / "state.json").read_text())
        self.assertNotIn("delivered", state["prs"][REPO + "#1"])
        self.assertIn("pending", state["prs"][REPO + "#1"])
        self.sent.side_effect = None
        self.assertEqual(self.monitor().tick()["notifications"], 1)
        self.assertEqual(self.sent.call_count, 2)

    def test_new_head_and_recovery_are_meaningful_updates(self):
        self.monitor().tick()
        self.runs[0]["conclusion"] = "failure"
        self.monitor().tick()
        self.runs[0]["conclusion"] = "success"
        self.monitor().tick()
        self.assertEqual(self.sent.call_count, 3)
        self.pr["head"]["sha"] = "b" * 40
        self.runs[0]["head_sha"] = "b" * 40
        self.jobs[10][0]["head_sha"] = "b" * 40
        self.monitor().tick()
        self.assertEqual(self.sent.call_count, 4)

    def test_merged_pr_is_observed_after_disappearing_from_open_list(self):
        self.monitor().tick()
        self.opened = []
        self.pr.update(state="closed", merged=True)
        self.monitor().tick()
        self.monitor().tick()
        self.assertEqual(self.sent.call_count, 2)
        self.assertIn("Đã merge", self.sent.call_args.args[1])

    def test_dry_run_never_sends_or_writes_state(self):
        result = self.monitor().tick(dry_run=True)
        self.assertEqual(result["notifications"], 1)
        self.assertIn("Bạn cần:", result["messages"][0])
        self.sent.assert_not_called()
        self.assertFalse((self.root / "state.json").exists())

    def test_old_untracked_prs_are_not_announced(self):
        self.opened[0]["created_at"] = "2026-01-01T00:00:00Z"
        self.assertEqual(self.monitor().tick()["notifications"], 0)
        self.config["repositories"][0]["watch_prs"] = [1]
        self.assertEqual(self.monitor().tick()["notifications"], 1)

    def test_persistent_error_alert_is_rate_limited(self):
        def fail(repo, path):
            raise RuntimeError("GitHub outage")

        def poll():
            return Monitor(
                self.root,
                self.config,
                github=fail,
                send=self.sent,
                clock=lambda: self.now,
            ).tick()

        for _ in range(4):
            with self.assertRaises(RuntimeError):
                poll()
        self.sent.assert_called_once()
        self.assertIn("chưa cập nhật được", self.sent.call_args.args[1])

    def merged_dev(self):
        self.config["repositories"][0].update(
            dev_environment="dev-macmini", dev_paths=["backend/**"]
        )
        self.pr.update(
            state="closed",
            merged=True,
            merge_commit_sha="c" * 40,
            merged_at="2026-10-26T01:00:00Z",
            updated_at="2026-10-26T01:00:00Z",
        )
        self.opened = []
        self.closed = [copy.deepcopy(self.pr)]

    def test_merge_between_polls_creates_persistent_dev_approval_request(self):
        self.merged_dev()
        self.assertEqual(self.monitor().tick()["notifications"], 1)
        state = json.loads((self.root / "state.json").read_text())
        request = state["dev_requests"][REPO + "#1"]
        self.assertEqual(request["merge_sha"], "c" * 40)
        self.assertEqual(request["environment"], "dev-macmini")
        self.assertEqual(request["status"], "awaiting_approval")
        self.assertEqual(request["notification_status"], "delivered")
        self.assertIn("Duyệt Dev #1", self.sent.call_args.args[1])
        self.assertIn("Production", self.sent.call_args.args[1])
        self.assertEqual(self.monitor().tick()["notifications"], 0)

    def test_previous_merged_info_is_upgraded_to_approval_question_once(self):
        self.merged_dev()
        m = self.monitor()
        m.state["prs"][REPO + "#1"] = {
            "observed": {"phase": "merged", "head": "a" * 40},
            "delivered": {"phase": "merged", "head": "a" * 40},
        }
        m.save()
        self.assertEqual(self.monitor().tick()["notifications"], 1)
        self.assertEqual(self.monitor().tick()["notifications"], 0)

    def test_control_only_merge_does_not_request_application_dev(self):
        self.merged_dev()
        self.files = [{"filename": "scripts/delivery/pm_monitor.py"}]
        self.monitor().tick()
        state = json.loads((self.root / "state.json").read_text())
        self.assertFalse(state.get("dev_requests"))
        self.assertNotIn("Duyệt Dev", self.sent.call_args.args[1])
        self.assertFalse(affects_dev([{"filename": "docs/test.md"}], ["backend/**"]))
        self.assertTrue(
            affects_dev(
                [{"filename": "docs/moved.md", "previous_filename": "backend/old.py"}],
                ["backend/**"],
            )
        )

    def test_approval_is_recorded_idempotently_but_never_deploys(self):
        self.merged_dev()
        self.monitor().tick()
        first = self.monitor().decide_dev(
            REPO, 1, "c" * 40, "approved", "trusted-session:human-message"
        )
        self.assertTrue(first["changed"])
        self.assertFalse(first["deployment_started"])
        second = self.monitor().decide_dev(
            REPO, 1, "c" * 40, "approved", "trusted-session:human-message"
        )
        self.assertFalse(second["changed"])
        self.assertEqual(self.monitor().tick()["notifications"], 0)
        self.sent.assert_called_once()

    def test_decision_requires_matching_merge_version_and_explicit_reference(self):
        self.merged_dev()
        self.monitor().tick()
        for sha, ref in [("d" * 40, "trusted-session:human-message"), ("c" * 40, "")]:
            with self.assertRaises(Denied):
                self.monitor().decide_dev(REPO, 1, sha, "approved", ref)
        self.pr["merge_commit_sha"] = "d" * 40
        with self.assertRaises(Denied):
            self.monitor().decide_dev(
                REPO, 1, "c" * 40, "approved", "trusted-session:human-message"
            )

    def test_decline_does_not_prompt_again(self):
        self.merged_dev()
        self.monitor().tick()
        self.monitor().decide_dev(
            REPO, 1, "c" * 40, "declined", "trusted-session:human-message"
        )
        self.assertEqual(self.monitor().tick()["notifications"], 0)
        self.sent.assert_called_once()

    def test_later_explicit_approval_can_resume_a_deferred_request(self):
        self.merged_dev()
        self.monitor().tick()
        self.monitor().decide_dev(
            REPO, 1, "c" * 40, "declined", "trusted-session:defer-message"
        )
        result = self.monitor().decide_dev(
            REPO, 1, "c" * 40, "approved", "trusted-session:new-approve-message"
        )
        self.assertTrue(result["changed"])
        self.assertEqual(result["request"]["status"], "approved")
        self.assertFalse(result["deployment_started"])

    def test_unmerged_pr_with_predicted_merge_sha_cannot_request_dev(self):
        self.config["repositories"][0].update(
            dev_environment="dev-macmini", dev_paths=["backend/**"]
        )
        self.pr["merge_commit_sha"] = "c" * 40
        self.monitor().tick()
        self.assertFalse(
            json.loads((self.root / "state.json").read_text()).get("dev_requests")
        )

    def test_dev_request_dry_run_does_not_persist_or_send(self):
        self.merged_dev()
        result = self.monitor().tick(dry_run=True)
        self.assertIn("Duyệt Dev", result["messages"][0])
        self.assertFalse((self.root / "state.json").exists())
        self.sent.assert_not_called()

    def test_pagination_reads_all_pages(self):
        fake = Mock(side_effect=[[{}] * 100, [{}]])
        self.assertEqual(len(pages(fake, REPO, "pulls?state=open")), 101)
        self.assertIn("page=2", fake.call_args.args[1])

    def test_batch_profile_queues_manual_merge_once_and_blocks_legacy_approval(self):
        self.merged_dev()
        self.config["repositories"][0]["batch_delivery"] = True
        self.pr["head"]["ref"] = "feature/manual-change"
        self.closed = [copy.deepcopy(self.pr)]
        self.assertEqual(self.monitor().tick()["notifications"], 1)
        state = json.loads((self.root / "state.json").read_text())
        self.assertEqual(state["delivery_v2"]["queue"][REPO + "#1"]["status"], "queued")
        self.assertFalse(state.get("dev_requests"))
        self.assertIn("Để sau #1", self.sent.call_args.args[1])
        self.assertEqual(self.monitor().tick()["notifications"], 0)
        with self.assertRaises(Denied):
            self.monitor().decide_dev(REPO, 1, "c" * 40, "approved", "owner")

    def test_batch_discovery_does_not_backfill_maintenance_notifications(self):
        self.merged_dev()
        self.config["repositories"][0]["batch_delivery"] = True
        self.files = [{"filename": "scripts/delivery/pm_monitor.py"}]
        self.assertEqual(self.monitor().tick()["notifications"], 0)
        self.sent.assert_not_called()
