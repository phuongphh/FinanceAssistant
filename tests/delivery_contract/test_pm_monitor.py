import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from delivery.pm_monitor import Monitor, classify, pages, message  # noqa: E402

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

    def test_pagination_reads_all_pages(self):
        fake = Mock(side_effect=[[{}] * 100, [{}]])
        self.assertEqual(len(pages(fake, REPO, "pulls?state=open")), 101)
        self.assertIn("page=2", fake.call_args.args[1])
