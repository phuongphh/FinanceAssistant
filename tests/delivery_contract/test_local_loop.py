import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from delivery.controller import Denied, digest  # noqa: E402
from delivery.local_loop import LocalLoop, ci_feedback, scrub  # noqa: E402
from agent_loop.cli import po_publish_notice  # noqa: E402


class FakeRunner:
    def __init__(self, root):
        self.root = root
        self.root.mkdir(mode=0o700)
        self.github = Mock(return_value={"state": "open", "labels": []})
        self.ci = ["review_ready"]
        self.proposals = []
        self.actions = []

    def begin(self, spec, repo, approved_digest):
        run = digest(spec)[:20]
        (self.root / run).mkdir()
        self.s = {
            "run_id": run,
            "request_digest": approved_digest,
            "repo": str(repo),
            "spec": copy.deepcopy(spec),
            "phase": "prepared",
            "attempts": 0,
            "head_sha": "a" * 40,
            "session_id": None,
        }
        return run

    def state(self, run):
        return copy.deepcopy(self.s)

    def propose(self, run, **kwargs):
        self.proposals.append(kwargs)
        self.s.update(
            phase="proposal_ready",
            attempts=self.s["attempts"] + 1,
            session_id="same-session",
        )

    def commit(self, run):
        self.actions.append("commit")
        self.s["phase"] = "committed"

    def publish(self, run):
        self.actions.append("publish")
        self.s["phase"] = "awaiting_ci"

    def check(self, run):
        self.s["phase"] = self.ci.pop(0) if len(self.ci) > 1 else self.ci[0]
        self.s["pr_url"] = "https://github.com/example/repo/pull/2"
        return self.state(run)

    def close(self, run):
        self.s["slot_released"] = True


class LoopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runner = FakeRunner(self.root / "state")
        self.spec = {
            "task": {
                "repository": "example/repo",
                "issue_number": 1,
                "engine": "codex",
                "limits": {"max_fix_rounds": 1, "max_cost_usd": 1},
            },
            "write_paths": ["a.txt"],
        }
        self.now = 100
        self.feedback = Mock(return_value="verified failed test")
        self.loop = LocalLoop(
            self.runner,
            clock=lambda: self.now,
            sleep=self.sleep,
            feedback=self.feedback,
        )

    def sleep(self, seconds):
        self.now += seconds

    def run_loop(self, **options):
        return self.loop.run(self.spec, self.root, digest(self.spec), **options)

    def test_full_cycle_and_duplicate_resume_do_not_spend_twice(self):
        result = self.run_loop()
        self.assertEqual(result["status"], "review_ready")
        self.assertEqual(result["deployment"], "not_verified")
        self.assertTrue(self.runner.s["slot_released"])
        self.assertEqual(self.run_loop(), result)
        self.assertEqual(len(self.runner.proposals), 1)

    def test_ci_failure_resumes_same_task_then_passes(self):
        self.runner.ci = ["ci_failed", "review_ready"]
        self.assertEqual(self.run_loop()["status"], "review_ready")
        self.assertEqual(len(self.runner.proposals), 2)
        self.assertEqual(self.runner.proposals[1]["feedback"], "verified failed test")
        self.assertEqual(
            self.runner.actions, ["commit", "publish", "commit", "publish"]
        )

    def test_retry_exhaustion_preserves_task(self):
        self.runner.ci = ["ci_failed"]
        self.assertEqual(self.run_loop()["technical_reason"], "attempt_limit")
        self.assertNotIn("slot_released", self.runner.s)
        self.assertEqual(len(self.runner.proposals), 2)

    def test_wall_timeout_survives_resume(self):
        self.runner.ci = ["awaiting_ci"]
        self.assertEqual(
            self.run_loop(wall_minutes=1)["technical_reason"], "wall_clock_limit"
        )
        before = len(self.runner.proposals)
        self.assertEqual(self.run_loop(wall_minutes=1)["status"], "blocked")
        self.assertEqual(len(self.runner.proposals), before)
        with self.assertRaises(Denied):
            self.run_loop(wall_minutes=2)

    def test_issue_claimed_by_cloud_blocks_before_model(self):
        self.runner.github.return_value = {
            "state": "open",
            "labels": [{"name": "agent:wip"}],
        }
        self.assertEqual(self.run_loop()["status"], "blocked")
        self.assertEqual(self.runner.proposals, [])

    def test_issue_closed_between_generation_and_publication_stops(self):
        self.runner.github.side_effect = [
            {"state": "open", "labels": []},
            {"state": "closed", "labels": []},
        ]
        self.assertEqual(self.run_loop()["status"], "blocked")
        self.assertNotIn("publish", self.runner.actions)

    def test_crashed_model_is_not_automatically_restarted(self):
        self.runner.begin(self.spec, self.root, digest(self.spec))
        self.runner.s["phase"] = "model_running"
        self.assertEqual(
            self.run_loop()["technical_reason"], "needs_reconciliation_model_running"
        )
        self.assertEqual(self.runner.proposals, [])

    def test_stop_marker_does_not_discard_work(self):
        run = self.runner.begin(self.spec, self.root, digest(self.spec))
        (self.runner.root / run / "stop.request").write_text("{}")
        self.assertEqual(self.run_loop()["status"], "stopped")
        self.assertEqual(self.runner.proposals, [])

    def test_claude_all_attempts_must_fit_explicit_budget(self):
        self.spec["task"]["engine"] = "claude"
        for value in (None, "0.6", "0"):
            with self.assertRaises(Denied):
                self.run_loop(claude_per_attempt=value)
        self.assertEqual(
            self.run_loop(claude_per_attempt="0.5")["status"], "review_ready"
        )
        self.assertEqual(self.runner.proposals[0]["claude_reservation"], "0.5")

    def test_wrong_digest_and_second_supervisor_refused(self):
        with self.assertRaises(Denied):
            self.loop.run(self.spec, self.root, "wrong")
        with self.loop.lock(), self.assertRaises(Denied):
            self.run_loop()

    def test_private_errors_do_not_leak_to_po_report(self):
        self.runner.publish = Mock(side_effect=RuntimeError("token=secret"))
        result = self.run_loop()
        self.assertEqual(
            result["technical_reason"], "operation_failed_inspect_private_state"
        )
        self.assertNotIn("secret", json.dumps(result))

    def test_po_notice_has_next_step_and_does_not_request_testing(self):
        text = po_publish_notice(
            1, 2, "Better news", True, "https://github.com/example/repo/pull/2"
        )
        self.assertIn("Bạn chưa cần", text)
        self.assertIn("Chưa có bản Dev", text)
        self.assertNotIn("Markdown", text)
        self.assertLess(len(text.split()), 120)
        self.assertIn("chưa đạt", po_publish_notice(1, 2, "Better news", False))


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.state = {
            "spec": {
                "task": {
                    "repository": "example/repo",
                    "branch": "codex/local-issue-1-test",
                }
            },
            "head_sha": "a" * 40,
        }
        self.pr = {"number": 2, "head": {"sha": "a" * 40}}
        self.runs = [
            {
                "id": i,
                "path": p,
                "head_sha": "a" * 40,
                "head_branch": "codex/local-issue-1-test",
                "event": "pull_request",
                "pull_requests": [{"number": 2}],
                "status": "completed",
                "conclusion": c,
            }
            for i, p, c in [
                (1, ".github/workflows/ci.yml", "failure"),
                (2, ".github/workflows/delivery-contract.yml", "success"),
            ]
        ]
        self.jobs = {
            "jobs": [
                {
                    "id": 10,
                    "name": "pytest",
                    "head_sha": "a" * 40,
                    "conclusion": "failure",
                }
            ]
        }

    def runner(self):
        return Mock(
            github=Mock(
                side_effect=[[self.pr], {"workflow_runs": self.runs}, self.jobs]
            )
        )

    def test_reads_only_failed_verified_job_and_scrubs_common_tokens(self):
        with patch(
            "delivery.local_loop.call",
            return_value="test failed token=hidden ghp_secret",
        ) as call:
            result = ci_feedback(self.runner(), self.state)
        self.assertNotIn("hidden", result)
        self.assertNotIn("ghp_secret", result)
        self.assertIn("10", call.call_args.args[0])

    def test_wrong_pr_head_never_reads_logs(self):
        self.pr["head"]["sha"] = "b" * 40
        with patch("delivery.local_loop.call") as call, self.assertRaises(Denied):
            ci_feedback(self.runner(), self.state)
        call.assert_not_called()

    def test_latest_foreign_and_cancelled_jobs_do_not_trigger_fix(self):
        self.jobs["jobs"][0]["conclusion"] = "cancelled"
        with self.assertRaises(Denied):
            ci_feedback(self.runner(), self.state)
        self.jobs["jobs"][0]["conclusion"] = "failure"
        self.runs[0]["pull_requests"] = [{"number": 99}]
        with self.assertRaises(Denied):
            ci_feedback(self.runner(), self.state)

    def test_newer_success_supersedes_stale_failure(self):
        newer = {**self.runs[0], "id": 3, "conclusion": "success"}
        self.runs.append(newer)
        with patch("delivery.local_loop.call") as call, self.assertRaises(Denied):
            ci_feedback(self.runner(), self.state)
        call.assert_not_called()

    def test_feedback_is_bounded(self):
        self.assertLessEqual(len(scrub("a" * 50000)), 24000)
