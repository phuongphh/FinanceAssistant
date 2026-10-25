import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))


def module(name):
    import importlib

    return importlib.import_module("delivery." + name)


engines = module("engines")
controller = module("controller")
assessment = module("assessment")
validator = module("validate")


def task(engine="claude", identifier="task1"):
    value = json.loads((ROOT / "docs/contracts/examples/task.json").read_text())
    value.update(engine=engine, task_id=identifier)
    value["limits"].update(max_cost_usd=1, max_minutes=2, max_fix_rounds=2)
    return value


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "controller"
        self.now = 1000000
        self.db = controller.Ledger(
            self.path, daily_usd=2, approvers=["owner"], clock=lambda: self.now
        )
        self.t = task()
        self.db.approve(
            self.t, actor="owner", verified_reference=self.t["approval"]["reference"]
        )

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def acquire(self, t=None, amount=".2"):
        return self.db.acquire(
            t or self.t, request_id=str(uuid.uuid4()), reservation_usd=amount, ttl=10
        )

    def finish(self, r, status="blocked", **kw):
        self.db.finish(
            r["run_id"],
            r["token"],
            status=status,
            evidence="controller://receipt",
            **kw,
        )

    def test_replayed_event_after_completion_does_not_execute(self):
        r = self.db.acquire(self.t, request_id="event-1", reservation_usd=".2")
        self.finish(r)
        with self.assertRaises(controller.DuplicateRequest) as ctx:
            self.db.acquire(self.t, request_id="event-1", reservation_usd=".2")
        self.assertEqual(ctx.exception.run_id, r["run_id"])

    def test_ready_task_not_reexecuted_under_new_event(self):
        r = self.acquire()
        self.finish(r, "review_ready", gate_passed=True, scope_passed=True)
        with self.assertRaises(controller.Denied):
            self.acquire()

    def test_task_content_drift_denied(self):
        t = copy.deepcopy(self.t)
        t["goal"] = "changed"
        with self.assertRaises(controller.Denied):
            self.acquire(t)

    def test_self_claimed_approval_denied(self):
        t = task(identifier="unapproved")
        t["approval"]["actor"] = "owner"
        with self.assertRaises(controller.Denied):
            self.acquire(t)

    def test_unknown_approver_denied(self):
        with self.assertRaises(controller.Denied):
            self.db.approve(
                task(identifier="other"),
                actor="model",
                verified_reference=self.t["approval"]["reference"],
            )

    def test_duplicate_task_and_different_repo_cannot_start_concurrently(self):
        self.acquire()
        t = task(identifier="other")
        t["repository"] = "other/product"
        self.db.approve(t, actor="owner", verified_reference=t["approval"]["reference"])
        for value in [self.t, t]:
            with self.assertRaises(controller.Denied):
                self.acquire(value)

    def test_expired_lease_does_not_allow_replacement(self):
        r = self.acquire()
        self.now += 11
        with self.assertRaises(controller.Denied):
            self.acquire()
        with self.assertRaises(controller.LeaseLost):
            self.db.heartbeat(r["run_id"], r["token"])

    def test_old_token_fenced_after_reconcile(self):
        old = self.acquire()
        self.now += 11
        self.db.reconcile_dead(
            old["run_id"],
            actor="owner",
            executor_death_receipt="executor://observed-exit",
        )
        fresh = self.acquire()
        with self.assertRaises(controller.LeaseLost):
            self.finish(old, "review_ready", gate_passed=True, scope_passed=True)
        self.finish(fresh)

    def test_reconcile_requires_operator_evidence(self):
        r = self.acquire()
        with self.assertRaises(controller.Denied):
            self.db.reconcile_dead(
                r["run_id"], actor="owner", executor_death_receipt=""
            )

    def test_unknown_cost_keeps_reservation_across_retry(self):
        r = self.acquire(amount=".6")
        self.finish(r)
        with self.assertRaises(controller.Denied):
            self.acquire(amount=".5")

    def test_daily_budget_across_tasks(self):
        self.db.daily = controller.micros(".3")
        r = self.acquire()
        self.finish(r)
        t = task(identifier="other")
        self.db.approve(t, actor="owner", verified_reference=t["approval"]["reference"])
        with self.assertRaises(controller.Denied):
            self.acquire(t)

    def test_daily_budget_resets_at_vietnam_midnight(self):
        from datetime import datetime, timezone

        self.now = datetime(2026, 10, 25, 16, 59, 59, tzinfo=timezone.utc).timestamp()
        self.db.daily = controller.micros(".2")
        first = self.acquire()
        self.finish(first)
        self.now += 2
        second = self.acquire()
        self.finish(second)
        self.assertEqual(
            [r["day"] for r in self.db.status()], ["2026-10-25", "2026-10-26"]
        )

    def test_total_task_time_across_attempts(self):
        r = self.acquire()
        self.now += 9
        self.finish(r)
        r = self.acquire()
        self.assertEqual(r["max_seconds"], 111)

    def test_time_exhausted_after_dead_worker_reconciliation(self):
        r = self.acquire()
        self.now += 121
        self.db.reconcile_dead(
            r["run_id"], actor="owner", executor_death_receipt="executor://stopped"
        )
        with self.assertRaises(controller.Denied):
            self.acquire()

    def test_expired_timeout_record_requires_confirmed_stop(self):
        r = self.acquire()
        self.now += 11
        with self.assertRaises(controller.LeaseLost):
            self.finish(r, "timeout")
        self.finish(r, "timeout", executor_stopped=True)

    def test_review_requires_independent_gates(self):
        r = self.acquire()
        with self.assertRaises(controller.Denied):
            self.finish(r, "review_ready", gate_passed=False, scope_passed=True)
        self.finish(r, "review_ready", gate_passed=True, scope_passed=True)

    def test_revocation_stops_heartbeat(self):
        r = self.acquire()
        self.db.revoke(self.t["task_id"], actor="owner")
        with self.assertRaises(controller.LeaseLost):
            self.db.heartbeat(r["run_id"], r["token"])

    def test_restart_preserves_active_run_and_checkpoint(self):
        r = self.acquire()
        self.db.heartbeat(
            r["run_id"],
            r["token"],
            session_id="session-123",
            checkpoint="controller://checkpoint",
        )
        self.db.close()
        self.db = controller.Ledger(
            self.path, daily_usd=2, approvers=["owner"], clock=lambda: self.now
        )
        self.assertEqual(self.db.status()[0]["session_id"], "session-123")
        self.assertNotIn("token", self.db.status()[0])
        with self.assertRaises(controller.Denied):
            self.acquire()

    def test_attempt_budget(self):
        for _ in range(3):
            r = self.acquire()
            self.finish(r)
        with self.assertRaises(controller.Denied):
            self.acquire()

    def test_concurrent_claims_only_one_winner(self):
        barrier = threading.Barrier(2)
        results = []

        def claim():
            db = controller.Ledger(
                self.path, daily_usd=2, approvers=["owner"], clock=lambda: self.now
            )
            barrier.wait()
            try:
                db.acquire(self.t, request_id=str(uuid.uuid4()), reservation_usd=".2")
                results.append("accepted")
            except controller.Denied:
                results.append("denied")
            finally:
                db.close()

        threads = [threading.Thread(target=claim) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        self.assertEqual(sorted(results), ["accepted", "denied"])


class AdapterTests(unittest.TestCase):
    def test_resume_is_explicit_and_no_bypass_flags(self):
        for engine in ["claude", "codex"]:
            args = engines.command(
                engine,
                Path("/tmp/w"),
                Path("/tmp/f"),
                session_id="session-123",
                max_cost_usd=".2",
            )
            self.assertIn("session-123", args)
            self.assertFalse(
                any(
                    x in args
                    for x in [
                        "--last",
                        "--continue",
                        "--dangerously-skip-permissions",
                        "--dangerously-bypass-approvals-and-sandbox",
                    ]
                )
            )

    def test_invalid_session_rejected(self):
        with self.assertRaises(ValueError):
            engines.command(
                "codex", Path("/tmp/w"), Path("/tmp/f"), session_id="--last"
            )

    def test_engine_env_never_inherits_publish_or_other_provider_credentials(self):
        source = {
            "HOME": "/tmp",
            "PATH": "/bin",
            "GH_TOKEN": "dummy",
            "OPENAI_API_KEY": "dummy",
            "ANTHROPIC_API_KEY": "dummy",
            "LOOP_TELEGRAM_BOT_TOKEN": "dummy",
        }
        for name in ["claude", "codex"]:
            env = engines.environment(name, source)
            self.assertNotIn("GH_TOKEN", env)
            self.assertNotIn("OPENAI_API_KEY", env)
            self.assertNotIn("LOOP_TELEGRAM_BOT_TOKEN", env)
            if name == "codex":
                self.assertNotIn("ANTHROPIC_API_KEY", env)

    def test_no_silent_claude_auth_fallback(self):
        with self.assertRaises(ValueError):
            engines.environment("claude", {"CLAUDE_CODE_OAUTH_TOKEN": "dummy"})

    def test_malformed_stream_cannot_be_completed(self):
        self.assertEqual(
            engines.parse("codex", "invalid\n{}", "", 0).status, "infra_failed"
        )

    def test_error_on_stdout_even_exit_zero(self):
        result = engines.parse(
            "claude",
            json.dumps(
                {
                    "type": "result",
                    "session_id": "session-123",
                    "subtype": "error_during_execution",
                    "is_error": True,
                    "result": "401 authentication failed",
                }
            ),
            "",
            0,
        )
        self.assertEqual(result.status, "auth_failed")

    def test_rate_limit_is_not_auth_failure(self):
        result = engines.parse(
            "codex",
            json.dumps({"type": "turn.failed", "error": {"message": "429 rate limit"}}),
            "",
            1,
        )
        self.assertEqual(result.status, "rate_limited")

    def test_codex_has_unknown_dollar_cost(self):
        events = "\n".join(
            json.dumps(x)
            for x in [
                {"type": "thread.started", "thread_id": "session-123"},
                {"type": "turn.completed", "usage": {"input_tokens": 10}},
            ]
        )
        result = engines.parse("codex", events, "", 0)
        self.assertEqual(result.status, "completed")
        self.assertIsNone(result.cost_usd)

    def fake(self, folder, body):
        path = folder / "fake"
        path.write_text("#!" + sys.executable + "\n" + body)
        path.chmod(0o700)
        return str(path)

    def test_timeout_stops_process_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = root / "w"
            work.mkdir()
            tick = root / "ticks"
            code = (
                "import sys,time,subprocess\nsys.stdin.read()\nsubprocess.Popen([sys.executable,'-c',"
                + repr(
                    "import time\nf=open("
                    + repr(str(tick))
                    + ",'a')\nwhile True:\n f.write('x');f.flush();time.sleep(.05)"
                )
                + "])\ntime.sleep(10)\n"
            )
            binary = self.fake(root, code)
            result = engines.run(
                "codex",
                "prompt",
                work,
                root / "out",
                timeout_seconds=1.5,
                executable=binary,
                check_version=False,
                source_env={"PATH": os.environ["PATH"], "HOME": tmp},
            )
            self.assertEqual(result.status, "timeout")
            size = tick.stat().st_size
            time.sleep(0.15)
            self.assertEqual(tick.stat().st_size, size)

    def test_lost_lease_stops_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = root / "w"
            work.mkdir()
            binary = self.fake(
                root, "import sys,time\nsys.stdin.read()\ntime.sleep(10)\n"
            )

            def lost():
                raise controller.LeaseLost("fenced")

            start = time.monotonic()
            with self.assertRaises(controller.LeaseLost):
                engines.run(
                    "codex",
                    "prompt",
                    work,
                    root / "out",
                    timeout_seconds=5,
                    executable=binary,
                    check_version=False,
                    heartbeat=lost,
                    source_env={"PATH": os.environ["PATH"], "HOME": tmp},
                )
            self.assertLess(time.monotonic() - start, 2)

    def test_cancellation_stops_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = root / "w"
            work.mkdir()
            binary = self.fake(
                root, "import sys,time\nsys.stdin.read()\ntime.sleep(10)\n"
            )

            def cancelled():
                raise KeyboardInterrupt()

            start = time.monotonic()
            with self.assertRaises(KeyboardInterrupt):
                engines.run(
                    "codex",
                    "prompt",
                    work,
                    root / "out",
                    timeout_seconds=5,
                    executable=binary,
                    check_version=False,
                    heartbeat=cancelled,
                    source_env={"PATH": os.environ["PATH"], "HOME": tmp},
                )
            self.assertLess(time.monotonic() - start, 2)

    def test_private_output_cannot_be_inside_workdir(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            with self.assertRaises(ValueError):
                engines.run("codex", "prompt", p, p / "out", timeout_seconds=1)


class AssessmentTests(unittest.TestCase):
    def setUp(self):
        self.task = task()
        self.engine = engines.EngineResult(
            "codex",
            "completed",
            session_id="session-123",
            final_text="All tests passed!",
        )
        self.kw = {
            "run_id": "run-1",
            "checkpoint": "controller://run-1",
            "changed_files": ["example/file.py"],
            "tested_head_sha": "b" * 40,
            "gates": {
                "status": "passed",
                "evidence": [
                    {
                        "url": "https://example.com/run/1",
                        "description": "independent test",
                    }
                ],
            },
        }

    def test_model_done_with_failed_gates_not_ready(self):
        self.kw["gates"]["status"] = "failed"
        self.assertEqual(
            assessment.worker_result(self.task, self.engine, **self.kw)["status"],
            "test_failed",
        )

    def test_scope_violation_even_with_passed_gates(self):
        self.kw["changed_files"] = [".github/workflows/ci.yml"]
        self.assertEqual(
            assessment.worker_result(self.task, self.engine, **self.kw)["status"],
            "scope_violation",
        )

    def test_path_traversal_and_secret_denied(self):
        paths = [
            "example/../outside.py",
            "/tmp/escape",
            "example/.env",
            "example//x.py",
        ]
        self.assertEqual(assessment.scope_check(paths, self.task["scope"]), paths)

    def test_control_roots_cannot_be_replaced_with_files_or_symlinks(self):
        paths = [
            ".codex",
            ".claude",
            "scripts/agent_loop",
            "scripts/delivery",
            "docs/contracts",
        ]
        self.assertEqual(
            assessment.scope_check(
                paths, {"allowed_paths": ["*"], "excluded_paths": []}
            ),
            paths,
        )

    def test_success_is_schema_valid(self):
        value = assessment.worker_result(self.task, self.engine, **self.kw)
        self.assertEqual(value["status"], "review_ready")
        validator.validate(
            "worker-result",
            value,
            json.loads((ROOT / ".github/delivery.json").read_text()),
        )

    def test_failed_start_has_no_fabricated_session(self):
        self.engine = engines.EngineResult("codex", "auth_failed")
        self.kw.update(
            tested_head_sha=None,
            changed_files=[],
            gates={"status": "not_run", "evidence": []},
        )
        value = assessment.worker_result(self.task, self.engine, **self.kw)
        self.assertIsNone(value["session_id"])
        validator.validate(
            "worker-result",
            value,
            json.loads((ROOT / ".github/delivery.json").read_text()),
        )

    def test_missing_independent_head_blocks_readiness(self):
        self.kw["tested_head_sha"] = None
        self.assertEqual(
            assessment.worker_result(self.task, self.engine, **self.kw)["status"],
            "blocked",
        )


loop = module("loop")


class LoopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = controller.Ledger(
            Path(self.tmp.name) / "state", daily_usd=2, approvers=["owner"]
        )
        self.task = task()
        self.config = json.loads((ROOT / ".github/delivery.json").read_text())
        self.calls = []
        self.gates = 0
        self.db.approve(
            self.task,
            actor="owner",
            verified_reference=self.task["approval"]["reference"],
        )

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def executor(self, t, session, feedback, heartbeat, seconds, directory):
        self.calls.append((session, feedback))
        heartbeat()
        return engines.EngineResult(t["engine"], "completed", session_id="session-123")

    def gate(self, t, heartbeat, seconds):
        self.gates += 1
        heartbeat()
        return {
            "changed_files": ["example/file.py"],
            "head_sha": "b" * 40,
            "patch_digest": "digest-" + str(self.gates),
            "gates": {
                "status": "failed" if self.gates == 1 else "passed",
                "evidence": [
                    {
                        "url": "https://example.com/run/1",
                        "description": "independent checks",
                    }
                ],
            },
        }

    def execute(self, **kw):
        args = dict(
            event_id="event-1",
            reservation_usd=".2",
            executor=self.executor,
            gate=self.gate,
            execution_enabled=True,
            sleeper=lambda s: None,
        )
        args.update(kw)
        return loop.execute(self.task, self.config, self.db, **args)

    def test_fail_fix_resume_then_independent_pass(self):
        result = self.execute()
        self.assertEqual(
            [r["status"] for r in result["receipts"]], ["test_failed", "review_ready"]
        )
        self.assertEqual(self.calls[1][0], "session-123")
        self.assertEqual(len(self.calls), 2)
        self.assertTrue(Path(result["checkpoint"]).is_file())

    def test_duplicate_event_returns_latest_checkpoint_no_new_worker(self):
        first = self.execute()
        again = self.execute()
        self.assertTrue(again["replayed"])
        self.assertEqual(again["checkpoint"], first["checkpoint"])
        self.assertEqual(len(self.calls), 2)

    def test_no_progress_stops_before_third_attempt(self):
        def fail(*args):
            return {
                "changed_files": ["example/file.py"],
                "head_sha": "b" * 40,
                "patch_digest": "same",
                "gates": {
                    "status": "failed",
                    "evidence": [
                        {
                            "url": "https://example.com/run/" + str(len(self.calls)),
                            "description": "fail",
                        }
                    ],
                },
            }

        result = self.execute(gate=fail)
        self.assertEqual(len(result["receipts"]), 2)
        self.assertEqual(result["receipts"][-1]["status"], "test_failed")

    def test_rate_limit_no_auto_retry(self):
        def limited(*args):
            return engines.EngineResult("claude", "rate_limited")

        result = self.execute(executor=limited)
        self.assertEqual(len(result["receipts"]), 1)
        self.assertEqual(self.gates, 0)

    def test_execution_disabled_by_default(self):
        with self.assertRaises(controller.Denied):
            self.execute(execution_enabled=False)
        self.assertEqual(self.calls, [])

    def test_resume_requires_verified_artifact_and_identity(self):
        def fail(*args):
            return engines.EngineResult("claude", "timeout", session_id="session-123")

        result = self.execute(executor=fail)
        with self.assertRaises(controller.Denied):
            self.execute(event_id="resume-1", resume_from=result["checkpoint"])

    def test_checkpoint_from_other_task_rejected(self):
        first = self.execute()
        self.task["task_id"] = "other"
        with self.assertRaises(controller.Denied):
            self.execute(
                event_id="resume-2",
                resume_from=first["checkpoint"],
                restore=lambda _: True,
            )


if __name__ == "__main__":
    unittest.main()
