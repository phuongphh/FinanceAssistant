import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from delivery.local_runner import LocalRunner, assess_ci, git, proposal, safe_file  # noqa: E402
from delivery.engines import EngineResult, command  # noqa: E402
from delivery.controller import Denied, digest  # noqa: E402


class LocalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        (self.repo / ".github").mkdir()
        (self.repo / "example").mkdir()
        (self.repo / ".github/delivery.json").write_text(
            (ROOT / ".github/delivery.json").read_text()
        )
        (self.repo / "example/code.txt").write_text("before\n")
        git(self.repo, "add", ".")
        git(
            self.repo,
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-qm",
            "base",
        )
        head = git(self.repo, "rev-parse", "HEAD")
        git(self.repo, "update-ref", "refs/remotes/origin/main", head)
        git(
            self.repo,
            "remote",
            "add",
            "origin",
            "https://github.com/phuongphh/FinanceAssistant.git",
        )
        task = json.loads((ROOT / "docs/contracts/examples/task.json").read_text())
        task.update(base_sha=head, branch="codex/local-issue-1-test", engine="codex")
        self.spec = {
            "task": task,
            "context_paths": ["example/code.txt"],
            "write_paths": ["example/code.txt", "example/new.txt"],
        }
        self.engine = Mock(
            return_value=EngineResult(
                "codex",
                "completed",
                session_id="session-123",
                final_text=json.dumps(
                    {"changes": [{"path": "example/code.txt", "content": "after\n"}]}
                ),
            )
        )
        self.api = Mock(return_value={"state": "open", "labels": []})
        self.runner = LocalRunner(
            self.root / "state", engine=self.engine, github=self.api
        )

    def tearDown(self):
        self.tmp.cleanup()

    def begin(self):
        return self.runner.begin(
            self.spec, self.repo, digest(self.spec), min_free_gib=0
        )

    def test_scoped_proposal_commits_in_separate_worktree(self):
        run = self.begin()
        self.runner.propose(run)
        state = self.runner.commit(run)
        self.assertEqual((self.repo / "example/code.txt").read_text(), "before\n")
        self.assertEqual(
            (Path(state["worktree"]) / "example/code.txt").read_text(), "after\n"
        )
        self.assertEqual(state["phase"], "committed")
        args = self.engine.call_args
        self.assertTrue(args.kwargs["proposal_only"])
        self.assertTrue(args.kwargs["read_only"])
        self.assertNotIn(Path(state["worktree"]), args.args)
        self.assertIn("before\\n", args.args[1])
        self.assertFalse((args.args[2] / "example/code.txt").exists())

    def test_approval_digest_and_single_global_slot(self):
        with self.assertRaises(Denied):
            self.runner.begin(self.spec, self.repo, "wrong", min_free_gib=0)
        self.begin()
        changed = copy.deepcopy(self.spec)
        changed["task"]["task_id"] = "second"
        with self.assertRaises(Denied):
            self.runner.begin(changed, self.repo, digest(changed), min_free_gib=0)

    def test_dirty_original_or_wrong_remote_blocks_before_checkout(self):
        (self.repo / "untracked").write_text("user data")
        with self.assertRaises(Denied):
            self.begin()
        (self.repo / "untracked").unlink()
        git(self.repo, "remote", "set-url", "origin", "https://example.com/other.git")
        with self.assertRaises(Denied):
            self.begin()

    def test_legacy_owned_issue_is_not_admitted(self):
        self.api.return_value = {"state": "open", "labels": [{"name": "agent:ready"}]}
        with self.assertRaises(Denied):
            self.begin()

    def test_space_preflight_preserves_slot(self):
        with self.assertRaises(Denied):
            self.runner.begin(
                self.spec, self.repo, digest(self.spec), min_free_gib=10**8
            )
        self.assertFalse((self.runner.root / "active.json").exists())

    def test_control_traversal_secret_symlink_and_hardlink_denied(self):
        (self.repo / "example/link").symlink_to(self.root)
        import os

        os.link(self.repo / "example/code.txt", self.repo / "example/hard")
        for path in [
            "../outside",
            "/tmp/escape",
            ".github/ci.yml",
            "example/.env",
            ".gitattributes",
            "example/link/other",
            "example/hard",
            "example/a\nb",
        ]:
            with self.subTest(path=path), self.assertRaises(Denied):
                safe_file(self.repo, path)

    def test_duplicate_or_out_of_scope_change_never_written(self):
        run = self.begin()
        state = self.runner.state(run)
        for changes in [
            [{"path": "other", "content": "bad"}],
            [
                {"path": "example/code.txt", "content": "first"},
                {"path": "example/code.txt", "content": "second"},
            ],
        ]:
            with self.assertRaises(Denied):
                proposal(
                    json.dumps({"changes": changes}), self.spec, Path(state["worktree"])
                )
        self.assertEqual(
            (Path(state["worktree"]) / "example/code.txt").read_text(), "before\n"
        )

    def test_change_after_proposal_is_not_committed(self):
        run = self.begin()
        self.runner.propose(run)
        state = self.runner.state(run)
        (Path(state["worktree"]) / "example/code.txt").write_text("external edit")
        with self.assertRaises(Denied):
            self.runner.commit(run)

    def test_unknown_file_is_not_committed(self):
        run = self.begin()
        self.runner.propose(run)
        state = self.runner.state(run)
        (Path(state["worktree"]) / "unknown.txt").write_text("not proposed")
        with self.assertRaises(Denied):
            self.runner.commit(run)

    def test_timeout_stops_without_apply(self):
        self.engine.return_value = EngineResult("codex", "timeout")
        run = self.begin()
        state = self.runner.propose(run)
        self.assertEqual(state["phase"], "blocked")
        self.assertEqual(
            (Path(state["worktree"]) / "example/code.txt").read_text(), "before\n"
        )

    def test_crash_remains_fenced_and_cannot_restart(self):
        self.engine.side_effect = RuntimeError("crash")
        run = self.begin()
        with self.assertRaises(RuntimeError):
            self.runner.propose(run)
        self.assertEqual(self.runner.state(run)["phase"], "model_running")
        with self.assertRaises(Denied):
            self.runner.propose(run)
        with self.assertRaises(Denied):
            self.runner.close(run)

    def test_attempt_and_total_runtime_limits(self):
        run = self.begin()
        state = self.runner.state(run)
        state["attempts"] = 3
        self.runner.save(state)
        with self.assertRaises(Denied):
            self.runner.propose(run)
        state["attempts"] = 0
        state["elapsed_seconds"] = 99999
        self.runner.save(state)
        with self.assertRaises(Denied):
            self.runner.propose(run)

    def test_claude_needs_explicit_reservation_and_keeps_it_on_failure(self):
        self.spec["task"].update(engine="claude", branch="claude/local-issue-1-test")
        run = self.begin()
        with self.assertRaises(Denied):
            self.runner.propose(run)
        self.engine.return_value = EngineResult("claude", "rate_limited")
        result = self.runner.propose(run, claude_reservation=".2")
        self.assertEqual(result["claude_reserved_usd"], "0.2")
        self.assertEqual(result["phase"], "blocked")

    def test_publish_rejects_different_remote_head(self):
        run = self.begin()
        self.runner.propose(run)
        self.runner.commit(run)
        original = git

        def fake(repo, *args, **kwargs):
            if args[0] == "ls-remote":
                return "b" * 40 + "\trefs/heads/" + self.spec["task"]["branch"]
            return original(repo, *args, **kwargs)

        with (
            patch("delivery.local_runner.git", side_effect=fake),
            self.assertRaises(Denied),
        ):
            self.runner.publish(run)
        self.assertEqual(self.runner.state(run)["phase"], "committed")

    def test_no_tools_profile_is_explicit(self):
        args = command("codex", self.repo, self.root / "output", proposal_only=True)
        for feature in (
            "shell_tool",
            "plugins",
            "apps",
            "hooks",
            "multi_agent",
            "computer_use",
        ):
            self.assertIn(feature, args)
        self.assertIn('web_search="disabled"', args)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", args)
        with self.assertRaises(ValueError):
            command(
                "codex",
                self.repo,
                self.root / "out",
                proposal_only=True,
                read_only=False,
            )


class CITests(unittest.TestCase):
    def setUp(self):
        self.task = {"repository": "owner/repo", "branch": "codex/local-issue-1-task"}
        self.head = "a" * 40
        self.pr = {
            "number": 3,
            "state": "open",
            "base": {"ref": "main"},
            "head": {
                "sha": self.head,
                "ref": self.task["branch"],
                "repo": {"full_name": "owner/repo"},
            },
        }
        self.runs = []
        self.jobs = {}
        for i, (path, name) in enumerate(
            [
                (".github/workflows/ci.yml", "pytest"),
                (".github/workflows/delivery-contract.yml", "contract"),
            ],
            1,
        ):
            self.runs.append(
                {
                    "id": i,
                    "head_sha": self.head,
                    "head_branch": self.task["branch"],
                    "event": "pull_request",
                    "path": path,
                    "pull_requests": [{"number": 3}],
                    "status": "completed",
                    "conclusion": "success",
                    "html_url": f"https://github.com/owner/repo/actions/runs/{i}",
                }
            )
            self.jobs[i] = [
                {"name": name, "conclusion": "success", "head_sha": self.head}
            ]

    def check(self):
        return assess_ci(self.task, self.head, self.pr, self.runs, self.jobs)[0]

    def test_matching_actual_jobs_are_ready(self):
        self.assertEqual(self.check(), "review_ready")

    def test_changed_pr_head_or_closed_pr_blocks(self):
        self.pr["head"]["sha"] = "b" * 40
        self.assertEqual(self.check(), "blocked")
        self.pr["head"]["sha"] = self.head
        self.pr["state"] = "closed"
        self.assertEqual(self.check(), "blocked")

    def test_wrong_head_event_path_or_pr_cannot_satisfy_ci(self):
        original = copy.deepcopy(self.runs[0])
        for key, value in [
            ("head_sha", "b" * 40),
            ("event", "workflow_dispatch"),
            ("path", ".github/workflows/fake.yml"),
            ("pull_requests", [{"number": 9}]),
        ]:
            self.runs[0] = copy.deepcopy(original)
            self.runs[0][key] = value
            self.assertEqual(self.check(), "awaiting_ci")

    def test_pending_and_missing_ci_are_not_ready(self):
        self.runs[0]["status"] = "in_progress"
        self.assertEqual(self.check(), "awaiting_ci")
        self.runs = []
        self.assertEqual(self.check(), "awaiting_ci")

    def test_skipped_job_or_bad_job_head_fails(self):
        self.jobs[1][0]["conclusion"] = "skipped"
        self.assertEqual(self.check(), "ci_failed")
        self.jobs[1][0].update(conclusion="success", head_sha="b" * 40)
        self.assertEqual(self.check(), "ci_failed")

    def test_newer_failure_overrides_old_success(self):
        newest = {**self.runs[0], "id": 99, "conclusion": "failure"}
        self.runs.append(newest)
        self.assertEqual(self.check(), "ci_failed")


if __name__ == "__main__":
    unittest.main()
