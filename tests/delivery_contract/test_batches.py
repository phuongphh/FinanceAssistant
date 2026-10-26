import copy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from delivery.batches import Delivery, CHECKS, RELEASE_CHECKS, ledger, notify_delivery  # noqa: E402
from delivery.controller import Denied  # noqa: E402
from delivery.pm_monitor import Monitor  # noqa: E402

REPO = "example/repo"
BASE, ONE, TWO, EXTRA = [c * 40 for c in "abcd"]


class Batches(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "state"
        self.config = {
            "destination": {"channel": "telegram", "account": "pm", "target": "123"},
            "repositories": [
                {
                    "name": REPO,
                    "batch_delivery": True,
                    "controller_checkout": "/unused",
                    "dev_paths": ["backend/**"],
                    "candidate_workflow": ".github/workflows/ci.yml",
                    "candidate_job": "pytest",
                }
            ],
        }
        self.prs = {
            n: {
                "number": n,
                "merged": True,
                "state": "closed",
                "base": {"ref": "main"},
                "head": {"repo": {"full_name": REPO}},
                "title": f"Feature {n}",
                "merge_commit_sha": sha,
            }
            for n, sha in [(1, ONE), (2, TWO)]
        }
        self.github = Mock(
            side_effect=lambda repo, path: copy.deepcopy(
                self.prs[int(path.split("/")[1])]
            )
        )
        self.sender = Mock(return_value="telegram-1")
        self.m = Monitor(
            self.root,
            self.config,
            github=self.github,
            send=self.sender,
            clock=lambda: 12345,
        )
        d = ledger(self.m.state)
        d["dev"][REPO] = {"sha": BASE, "batch_id": "prior"}
        for n, p in self.prs.items():
            d["queue"][f"{REPO}#{n}"] = {
                "repository": REPO,
                "pr_number": n,
                "merge_sha": p["merge_commit_sha"],
                "status": "queued",
            }
        self.m.save()

    def command(self, action, **kw):
        return self.m.batch_command({"action": action, "repository": REPO, **kw})

    def proposed(self):
        with patch("delivery.batches.Delivery.scope", return_value=(TWO, [TWO, ONE])):
            return self.command("propose", all=True, title="Phase one")

    def bound(self, b):
        return {"batch_id": b["batch_id"], "digest": b["digest"]}

    def test_deferred_changes_remain_in_all_batch_after_restart(self):
        self.command("defer", pr=1, reference="owner:later")
        b = self.proposed()
        self.assertEqual(b["prs"], [1, 2])
        self.assertEqual(b["baseline_sha"], BASE)
        restarted = Monitor(self.root, self.config)
        self.assertEqual(
            ledger(restarted.state)["batches"][b["batch_id"]]["digest"], b["digest"]
        )
        with self.assertRaises(Denied):
            self.proposed()

    def test_changed_digest_cannot_approve_and_second_approval_never_redispatches(self):
        b = self.proposed()
        with self.assertRaises(Denied):
            self.command(
                "approve", batch_id=b["batch_id"], digest="wrong", reference="owner"
            )
        self.command("approve", **self.bound(b), reference="owner")
        self.assertFalse(
            self.command("approve", **self.bound(b), reference="owner")["changed"]
        )
        self.assertEqual(
            ledger(self.m.state)["batches"][b["batch_id"]]["candidate_sha"], TWO
        )

    def test_no_deploy_before_integration_ci_and_no_accept_before_deployed(self):
        b = self.proposed()
        self.command("approve", **self.bound(b), reference="owner")
        for action in ("claim", "accept", "deployed"):
            with self.assertRaises(Denied):
                self.command(action, **self.bound(b), reference="owner", sha=TWO)

    def test_receipt_and_acceptance_are_separate_exact_version_gates(self):
        b = self.proposed()
        self.command("approve", **self.bound(b), reference="owner")
        with patch(
            "delivery.batches.Delivery.candidate_ci",
            return_value={"sha": TWO, "run_id": 9},
        ):
            self.command("ci-verify", **self.bound(b), run_id=9)
        self.command(
            "claim", **self.bound(b), reference="ops:run", observed_baseline_sha=BASE
        )
        with self.assertRaises(Denied):
            self.command(
                "deployed", **self.bound(b), sha=TWO, checks={}, reference="ops"
            )
        self.command(
            "deployed",
            **self.bound(b),
            sha=TWO,
            checks=dict.fromkeys(CHECKS, True),
            reference="ops:receipt",
        )
        self.assertEqual(ledger(self.m.state)["releases"], {})
        with self.assertRaises(Denied):
            self.command("accept", **self.bound(b), sha=ONE, reference="owner")
        self.command("accept", **self.bound(b), sha=TWO, reference="owner:accepted")
        release = next(iter(ledger(self.m.state)["releases"].values()))
        self.assertFalse(release["production_approved"])
        self.assertEqual(release["status"], "preparation_needed")
        self.m.previews = []
        self.assertEqual(notify_delivery(self.m), 1)
        self.assertEqual(
            notify_delivery(Monitor(self.root, self.config, send=self.sender)), 0
        )
        self.sender.assert_called_once()

    def test_failed_send_is_retried_and_dry_run_has_no_write(self):
        self.proposed()
        before = self.m.path.read_bytes()
        self.m.previews = []
        self.assertEqual(notify_delivery(self.m, dry_run=True), 1)
        self.assertEqual(self.m.path.read_bytes(), before)
        self.sender.side_effect = RuntimeError("network")
        with self.assertRaises(RuntimeError):
            notify_delivery(self.m)
        self.sender.side_effect = None
        self.assertEqual(
            notify_delivery(Monitor(self.root, self.config, send=self.sender)), 1
        )

    def test_ci_rejects_wrong_sha_branch_skipped_job_or_moved_branch(self):
        b = self.proposed()
        ref = "delivery/" + b["batch_id"]
        run = {
            "path": ".github/workflows/ci.yml",
            "event": "workflow_dispatch",
            "head_sha": TWO,
            "head_branch": ref,
            "status": "completed",
            "conclusion": "success",
            "html_url": "https://github.com/example/repo/actions/runs/9",
        }
        job = {"name": "pytest", "head_sha": TWO, "conclusion": "success"}
        branch = {"object": {"sha": TWO}}

        def api(repo, path):
            if path.startswith("git/ref/"):
                return branch
            if "/jobs?" in path:
                return {"jobs": [job]}
            return run

        self.m.github = api
        d = Delivery(self.m)
        self.assertEqual(d.candidate_ci(b, {"run_id": 9})["sha"], TWO)
        for field, value in [
            ("head_sha", ONE),
            ("head_branch", "main"),
            ("event", "pull_request"),
            ("conclusion", "skipped"),
        ]:
            old = run[field]
            run[field] = value
            with self.assertRaises(Denied):
                d.candidate_ci(b, {"run_id": 9})
            run[field] = old
        job["conclusion"] = "skipped"
        with self.assertRaises(Denied):
            d.candidate_ci(b, {"run_id": 9})
        job["conclusion"] = "success"
        branch["object"]["sha"] = ONE
        with self.assertRaises(Denied):
            d.candidate_ci(b, {"run_id": 9})

    def test_baseline_drift_prevents_claim(self):
        b = self.proposed()
        ledger(self.m.state)["batches"][b["batch_id"]]["status"] = "ci_passed"
        ledger(self.m.state)["dev"][REPO]["sha"] = EXTRA
        self.m.save()
        with self.assertRaises(Denied):
            self.command("claim", **self.bound(b), reference="ops")

    def test_historical_import_requires_evidence_and_cannot_run_twice(self):
        ledger(self.m.state)["dev"].clear()
        self.m.save()
        with (
            patch("delivery.batches.Delivery.repository", return_value="/unused"),
            patch("delivery.batches.git"),
        ):
            with self.assertRaises(Denied):
                self.command(
                    "import-accepted",
                    sha=TWO,
                    prs=[1, 2],
                    title="history",
                    reference="owner",
                )
            b = self.command(
                "import-accepted",
                sha=TWO,
                prs=[1, 2],
                title="history",
                reference="owner:confirmation",
                deployment_reference="ops:historical-receipt",
            )
            self.assertEqual(
                b["history_evidence"]["kind"], "historical-owner-confirmed"
            )
            with self.assertRaises(Denied):
                self.command(
                    "import-accepted",
                    sha=TWO,
                    prs=[1, 2],
                    title="history",
                    reference="owner",
                    deployment_reference="ops",
                )

    def test_uncertain_ci_start_is_not_automatically_repeated(self):
        b = self.proposed()
        self.command("approve", **self.bound(b), reference="owner")
        with patch("delivery.batches.call", side_effect=Denied("network")) as remote:
            with self.assertRaises(Denied):
                self.command("ci-start", **self.bound(b))
            with self.assertRaises(Denied):
                self.command("ci-start", **self.bound(b))
            self.assertEqual(remote.call_count, 1)

    def test_phase_suggestion_waits_for_all_members_and_is_created_once(self):
        self.config["repositories"][0]["release_groups"] = [
            {"id": "phase-one", "title": "Phase one", "prs": [1, 2]}
        ]
        d = Delivery(self.m)
        b = {
            "batch_id": "first",
            "repository": REPO,
            "candidate_sha": ONE,
            "prs": [1],
            "title": "First issue",
        }
        d.data["queue"][REPO + "#1"]["status"] = "accepted"
        d.release(b)
        self.assertEqual(d.data["releases"], {})
        d.data["queue"][REPO + "#2"]["status"] = "accepted"
        b.update(batch_id="second", candidate_sha=TWO, prs=[2])
        d.release(b)
        d.release(b)
        self.assertEqual(len(d.data["releases"]), 1)
        self.assertEqual(d.data["releases"]["release-phase-one"]["source_sha"], TWO)

    def test_withdrawn_batch_keeps_history_and_receives_a_new_id(self):
        old = self.proposed()
        self.command("supersede", **self.bound(old), reference="owner:later")
        new = self.proposed()
        self.assertNotEqual(old["batch_id"], new["batch_id"])
        self.assertEqual(old["digest"], new["digest"])
        self.assertEqual(len(ledger(self.m.state)["batches"]), 2)

    def test_rejected_content_is_carried_into_next_uat_scope(self):
        b = self.proposed()
        d = ledger(self.m.state)
        d["batches"][b["batch_id"]].update(
            status="rejected", rejection_reference="owner:bug"
        )
        d["dev"][REPO] = {"sha": TWO, "batch_id": b["batch_id"]}
        self.m.save()
        self.command("supersede", **self.bound(b), reference="owner:fix-next")
        d = ledger(self.m.state)
        self.assertEqual(d["queue"][REPO + "#1"]["status"], "deployed_rejected")
        self.prs[3] = {**self.prs[2], "number": 3, "merge_commit_sha": EXTRA}
        d["queue"][REPO + "#3"] = {
            "repository": REPO,
            "pr_number": 3,
            "merge_sha": EXTRA,
            "status": "queued",
        }
        self.m.save()
        with patch("delivery.batches.Delivery.scope", return_value=(EXTRA, [EXTRA])):
            new = self.command("propose", all=True, title="Fix and retest")
        self.assertEqual(new["selected_prs"], [3])
        self.assertEqual(new["retest_prs"], [1, 2])
        self.assertEqual(new["prs"], [1, 2, 3])

    def test_readiness_requires_all_evidence_and_does_not_approve_production(self):
        b = self.proposed()
        d = ledger(self.m.state)
        d["batches"][b["batch_id"]]["status"] = "accepted"
        d["dev"][REPO] = {"sha": TWO}
        Delivery(self.m).release(b)
        release = next(iter(d["releases"].values()))
        self.m.save()
        base = {
            "release_id": release["release_id"],
            "sha": TWO,
            "production_baseline_sha": BASE,
            "reference": "ops:verified",
        }
        with self.assertRaises(Denied):
            self.command("release-readiness", **base, evidence={})
        result = self.command(
            "release-readiness",
            **base,
            evidence=dict.fromkeys(RELEASE_CHECKS, "ops:durable-evidence"),
        )
        self.assertEqual(result["status"], "ready_for_release_pr")
        self.assertFalse(result["production_approved"])


class ScopeHistory(unittest.TestCase):
    def test_real_git_cumulative_scope_refuses_unselected_app_commit(self):
        with tempfile.TemporaryDirectory() as t:

            def g(*args):
                return subprocess.check_output(
                    ["git", "-C", t, *args], text=True
                ).strip()

            g("init", "-q")
            g("config", "user.email", "test@example.invalid")
            g("config", "user.name", "Test")
            Path(t, "backend").mkdir()
            Path(t, "backend/a.py").write_text("base")
            g("add", ".")
            g("commit", "-qm", "baseline")
            base = g("rev-parse", "HEAD")
            Path(t, "backend/a.py").write_text("feature A")
            g("commit", "-qam", "feature A")
            one = g("rev-parse", "HEAD")
            Path(t, "backend/a.py").write_text("feature A and B")
            g("commit", "-qam", "feature B")
            two = g("rev-parse", "HEAD")
            Path(t, "notes.md").write_text("later doc")
            g("add", ".")
            g("commit", "-qm", "later docs")
            g("update-ref", "refs/remotes/origin/main", "HEAD")
            m = Mock()
            d = Delivery(m)
            profile = {"dev_paths": ["backend/**"]}
            with patch.object(d, "repository", return_value=t):
                with self.assertRaisesRegex(Denied, one):
                    d.scope(profile, base, [{"merge_commit_sha": two}])
                candidate, commits = d.scope(
                    profile,
                    base,
                    [{"merge_commit_sha": one}, {"merge_commit_sha": two}],
                )
                self.assertEqual(candidate, two)
                self.assertEqual(commits, [two, one])


if __name__ == "__main__":
    unittest.main()
