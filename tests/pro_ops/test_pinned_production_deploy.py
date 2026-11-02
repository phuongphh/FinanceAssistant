"""Exercise the real shell controller with local Git and synthetic services only."""

import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]


class PinnedProductionDeployTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.project = self.base / "project"
        self.project.mkdir()
        self.origin = self.base / "origin.git"
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.events = self.base / "events.jsonl"
        self.lock = self.base / "deploy.lock"
        self.git("init", "--bare", str(self.origin), cwd=self.base)
        self.git("init", "-b", "prod")
        self.git("config", "user.name", "Synthetic Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("remote", "add", "origin", str(self.origin))
        (self.project / ".gitignore").write_text(".env\n.backups/\n")
        (self.project / "deploy/production").mkdir(parents=True)
        (self.project / "deploy/production/docker-compose.yml").write_text(
            "# synthetic\n"
        )
        (self.project / "betien-admin").mkdir()
        (self.project / "betien-admin/package.json").write_text("{}")
        self.git("add", ".")
        self.git("commit", "-m", "baseline")
        self.baseline = self.git("rev-parse", "HEAD").strip()
        (self.project / "feature.txt").write_text("approved feature")
        (self.project / "feature").mkdir()
        (self.project / "feature/child.py").write_text("# approved source\n")
        self.git("add", ".")
        self.git("commit", "-m", "approved feature")
        self.candidate = self.git("rev-parse", "HEAD").strip()
        self.git("push", "origin", "prod")
        self.git("reset", "--hard", self.baseline)
        (self.project / ".env").write_text(
            "\n".join(
                key + "=synthetic"
                for key in [
                    "POSTGRES_PASSWORD",
                    "DEEPSEEK_API_KEY",
                    "ANTHROPIC_API_KEY",
                    "TELEGRAM_BOT_TOKEN",
                    "ADMIN_JWT_SECRET",
                    "VITE_API_BASE",
                ]
            )
            + "\n"
        )
        mock = (
            "#!"
            + sys.executable
            + "\n"
            + """import json, os, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ['TEST_EVENTS'], 'a') as f:
    f.write(json.dumps([Path(sys.argv[0]).name, *args]) + '\\n')
if Path(sys.argv[0]).name == 'curl':
    print('503' if os.environ.get('TEST_HEALTH_FAIL') == '1' else '200', end='')
elif args[-2:] == ['ps', 'postgres']:
    print('finance-postgres Up' if os.environ.get('TEST_DB_DOWN') != '1' else '')
elif 'pg_dump' in args:
    print('-- synthetic consistent SQL dump')
    sys.exit(1 if os.environ.get('TEST_DUMP_FAIL') == '1' else 0)
elif 'build' in args and os.environ.get('TEST_BUILD_FAIL') == '1':
    sys.exit(1)
elif 'redis-cli' in args:
    print('PONG')
elif 'alembic' in args:
    print('synthetic_revision')
"""
        )
        for name in ["docker", "curl"]:
            path = self.bin / name
            path.write_text(mock)
            path.chmod(0o755)
        self.script = self.base / "deploy.sh"
        source = (ROOT / "scripts/rebuild-finance-prod.sh").read_text()
        # Private test lock/logs; never touch a live deployment lock or log.
        source = source.replace("/tmp/rebuild-finance-prod.lock", str(self.lock))
        source = source.replace(
            "/tmp/rebuild-finance-", str(self.base / "rebuild-finance-")
        )
        self.script.write_text(source)
        self.env = {
            **os.environ,
            "PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
            "PROJECT_DIR": str(self.project),
            "BRANCH": "prod",
            "SKIP_PRUNE": "1",
            "APPROVED_SHA": self.candidate,
            "EXPECTED_CHECKOUT_SHA": self.baseline,
            "TEST_EVENTS": str(self.events),
            "HOME": str(self.base),
        }

    def git(self, *args, cwd=None):
        result = subprocess.run(
            ["git", *args],
            cwd=cwd or self.project,
            env={
                **os.environ,
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": "/dev/null",
            },
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout

    def run_deploy(self, **overrides):
        return subprocess.run(
            ["bash", str(self.script)],
            env={**self.env, **overrides},
            cwd=self.base,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def service_events(self):
        return (
            [json.loads(line) for line in self.events.read_text().splitlines()]
            if self.events.exists()
            else []
        )

    def assert_no_service_mutations(self):
        for event in self.service_events():
            self.assertFalse(
                set(event) & {"down", "build", "up", "pg_dump", "seed_admin"}
            )
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), self.baseline)

    def test_pinned_release_backs_up_before_shutdown_and_keeps_private_archive(self):
        config = self.project / ".git/config"
        config.chmod(0o600)
        result = self.run_deploy()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), self.candidate)
        self.assertEqual((self.project / "feature.txt").stat().st_mode & 0o777, 0o644)
        self.assertEqual((self.project / "feature").stat().st_mode & 0o777, 0o755)
        self.assertEqual(
            (self.project / "feature/child.py").stat().st_mode & 0o777, 0o644
        )
        self.assertEqual((self.project / ".git/index").stat().st_mode & 0o777, 0o644)
        self.assertEqual(
            (self.project / ".git/refs/heads/prod").stat().st_mode & 0o777, 0o644
        )
        self.assertEqual(config.stat().st_mode & 0o777, 0o600)
        events = self.service_events()
        dump = next(i for i, e in enumerate(events) if "pg_dump" in e)
        down = next(i for i, e in enumerate(events) if "down" in e)
        self.assertLess(dump, down)
        backups = list((self.project / ".backups").glob("*.sql.gz"))
        self.assertEqual(len(backups), 1)
        self.assertIn(
            b"synthetic consistent SQL dump", gzip.decompress(backups[0].read_bytes())
        )
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)
        self.assertFalse(self.lock.exists())
        self.assertFalse(any("prune" in e for e in events))

    def test_baseline_change_blocks_before_backup_or_shutdown(self):
        result = self.run_deploy(EXPECTED_CHECKOUT_SHA="f" * 40)
        self.assertNotEqual(result.returncode, 0)
        self.assert_no_service_mutations()
        self.assertFalse(self.lock.exists())

    def test_newer_remote_commit_does_not_expand_approved_release(self):
        self.git("reset", "--hard", self.candidate)
        (self.project / "extra.txt").write_text("not approved")
        self.git("add", ".")
        self.git("commit", "-m", "unapproved newer commit")
        self.git("push", "origin", "prod")
        self.git("reset", "--hard", self.baseline)
        result = self.run_deploy()
        self.assertNotEqual(result.returncode, 0)
        self.assert_no_service_mutations()

    def test_database_unavailable_or_failed_dump_leaves_checkout_and_services_unchanged(
        self,
    ):
        for override in [{"TEST_DB_DOWN": "1"}, {"TEST_DUMP_FAIL": "1"}]:
            with self.subTest(override=override):
                self.events.unlink(missing_ok=True)
                result = self.run_deploy(**override)
                self.assertNotEqual(result.returncode, 0)
                events = self.service_events()
                self.assertFalse(any(set(e) & {"down", "build", "up"} for e in events))
                self.assertEqual(self.git("rev-parse", "HEAD").strip(), self.baseline)
                self.assertFalse(self.lock.exists())

    def test_existing_lock_is_preserved_and_does_not_run_deployment(self):
        self.lock.write_text("999999")
        result = self.run_deploy()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.lock.read_text(), "999999")
        self.assert_no_service_mutations()

    def test_backup_bypass_or_missing_candidate_is_rejected(self):
        for override in [{"SKIP_BACKUP": "1"}, {"APPROVED_SHA": ""}]:
            result = self.run_deploy(**override)
            self.assertNotEqual(result.returncode, 0)
            self.assert_no_service_mutations()

    def test_build_failure_reports_attempted_rollback_without_claiming_success(self):
        result = self.run_deploy(TEST_BUILD_FAIL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), self.baseline)
        self.assertIn("Chưa xác minh runtime", result.stderr)
        self.assertNotIn("REBUILD HOÀN TẤT", result.stdout)
        self.assertFalse(self.lock.exists())

    def test_health_failure_also_attempts_rollback(self):
        result = self.run_deploy(TEST_HEALTH_FAIL="1", HEALTH_TIMEOUT="0")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), self.baseline)
        self.assertIn("Chưa xác minh runtime", result.stderr)
        self.assertNotIn("REBUILD HOÀN TẤT", result.stdout)
        self.assertFalse(self.lock.exists())

    def test_git_fetch_failure_does_not_disclose_private_remote(self):
        self.git("remote", "set-url", "origin", str(self.base / "private_credential"))
        result = self.run_deploy()
        self.assertNotEqual(result.returncode, 0)
        self.assert_no_service_mutations()
        self.assertNotIn("private_credential", result.stdout + result.stderr)


class ReviewedControllerWorkflowTests(unittest.TestCase):
    def test_workflow_uses_main_controller_and_validates_release_before_ssh(self):
        workflow = yaml.load(
            (ROOT / ".github/workflows/deploy.yml").read_text(), Loader=yaml.BaseLoader
        )
        job = workflow["jobs"]["deploy"]
        self.assertEqual(
            job["steps"][0]["with"], {"ref": "main", "persist-credentials": "false"}
        )
        prepare = job["steps"][1]["run"]
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "github-env"
            env = {
                **os.environ,
                "EVENT_NAME": "workflow_dispatch",
                "EVENT_REF": "refs/heads/main",
                "INPUT_SHA": "a" * 40,
                "INPUT_BASELINE": "b" * 40,
                "REGISTERED_PROJECT_DIR": "",
                "GITHUB_ENV": str(output),
            }
            result = subprocess.run(
                ["bash", "-e", "-c", prepare], env=env, cwd=ROOT, capture_output=True
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            values = dict(
                line.split("=", 1) for line in output.read_text().splitlines()
            )
            payload = base64.b64decode(values["FLEET_DEPLOY_B64"], validate=True)
            self.assertEqual(
                payload, (ROOT / "scripts/rebuild-finance-prod.sh").read_bytes()
            )
            self.assertEqual(
                hashlib.sha256(payload).hexdigest(), values["FLEET_DEPLOY_SHA"]
            )
            for override in [
                {"INPUT_SHA": ""},
                {"EVENT_REF": "refs/heads/unreviewed"},
                {"REGISTERED_PROJECT_DIR": "/other"},
            ]:
                output.unlink(missing_ok=True)
                invalid = subprocess.run(
                    ["bash", "-e", "-c", prepare],
                    env={**env, **override},
                    cwd=ROOT,
                    capture_output=True,
                )
                self.assertNotEqual(invalid.returncode, 0)
                self.assertFalse(output.exists())
        remote = job["steps"][2]["with"]["script"]
        result = subprocess.run(
            ["bash", "-n"], input=remote.encode(), capture_output=True
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertIn("sudo -n /usr/bin/env -i", remote)
        self.assertNotIn("chown", remote)
        self.assertNotIn("chmod", remote)
