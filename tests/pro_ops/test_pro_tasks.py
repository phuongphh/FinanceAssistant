import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "finance_pro_tasks", ROOT / "ops/fleet/pro_tasks.py"
)
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)


class ProductionOperationsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.policy = {
            "repository": ops.REPOSITORY,
            "backup_directory": str(self.root),
            "project_dir": str(self.root),
            "compose_project": "financeassistant",
            "postgres_volume": "financeassistant_postgres_data",
            "containers": {
                s: "finance-" + s for s in ["postgres", "backend", "scheduler", "redis"]
            },
            "max_backup_bytes": 1024**2,
        }
        self.request = {
            "repository": ops.REPOSITORY,
            "operation": "backup",
            "expected_checkout_sha": "a" * 40,
            "candidate_sha": None,
            "request_id": "b" * 32,
        }
        self.observation = {
            "checkout_sha": "a" * 40,
            "containers": {"postgres": {"running": True}},
        }
        self.lock = patch.object(ops, "DEPLOY_LOCK", self.root / "deploy.lock")
        self.lock.start()
        self.addCleanup(self.lock.stop)

    def test_wrong_repository_and_unregistered_commands_never_spawn(self):
        with patch.object(ops.subprocess, "run") as run:
            for request in [
                dict(self.request, repository="other/repo"),
                dict(self.request, operation="deploy"),
            ]:
                with self.assertRaises(ops.OpsError):
                    ops.execute(request, self.policy, str(self.root))
            run.assert_not_called()

    def test_container_label_or_volume_drift_rejects_database(self):
        values = [
            {
                "com.docker.compose.project": "financeassistant",
                "com.docker.compose.service": "postgres",
            },
            True,
            "sha256:example",
            [
                {
                    "Type": "volume",
                    "Name": "taxassistant_postgres_data",
                    "Destination": "/var/lib/postgresql/data",
                }
            ],
        ]
        with patch.object(
            ops, "command", return_value=("\n".join(map(json.dumps, values))).encode()
        ):
            with self.assertRaisesRegex(
                ops.OpsError, "database_volume_identity_mismatch"
            ):
                ops.container(self.policy, "postgres")

    def test_unavailable_database_cannot_be_skipped_as_a_first_deploy(self):
        self.observation["containers"]["postgres"]["running"] = False
        with (
            patch.object(ops, "inspect", return_value=self.observation),
            patch.object(ops.subprocess, "run") as run,
        ):
            with self.assertRaisesRegex(ops.OpsError, "database_not_running"):
                ops.execute(self.request, self.policy, str(self.root))
            run.assert_not_called()
            self.assertFalse(ops.DEPLOY_LOCK.exists())

    def test_busy_deploy_lock_is_preserved_and_no_dump_starts(self):
        ops.DEPLOY_LOCK.write_text("other-process")
        with (
            patch.object(ops, "inspect", return_value=self.observation),
            patch.object(ops.subprocess, "run") as run,
        ):
            with self.assertRaisesRegex(ops.OpsError, "lock_busy"):
                ops.execute(self.request, self.policy, str(self.root))
            run.assert_not_called()
        self.assertEqual(ops.DEPLOY_LOCK.read_text(), "other-process")

    def test_checkout_is_rechecked_after_the_deploy_lock_is_acquired(self):
        with (
            patch.object(ops, "inspect", return_value=self.observation),
            patch.object(ops, "git", return_value=("c" * 40).encode()),
            patch.object(ops.subprocess, "run") as run,
        ):
            with self.assertRaisesRegex(ops.OpsError, "checkout_changed"):
                ops.execute(self.request, self.policy, str(self.root))
            run.assert_not_called()
        self.assertFalse(ops.DEPLOY_LOCK.exists())

    def test_existing_backup_or_partial_is_not_overwritten(self):
        for suffix in [".dump", ".dump.partial"]:
            target = self.root / (self.request["request_id"] + suffix)
            target.write_bytes(b"preserve")
            with patch.object(ops, "inspect", return_value=self.observation):
                with self.assertRaisesRegex(ops.OpsError, "already_exists"):
                    ops.execute(self.request, self.policy, str(self.root))
            self.assertEqual(target.read_bytes(), b"preserve")
            target.unlink()
            self.assertFalse(ops.DEPLOY_LOCK.exists())

    def test_nonzero_dump_cannot_create_a_successful_backup_receipt(self):
        with (
            patch.object(ops, "inspect", return_value=self.observation),
            patch.object(ops, "git", return_value=("a" * 40).encode()),
            patch.object(ops, "container"),
            patch.object(ops.subprocess, "run", return_value=Mock(returncode=1)),
        ):
            with self.assertRaisesRegex(ops.OpsError, "backup_incomplete"):
                ops.execute(self.request, self.policy, str(self.root))
        self.assertFalse((self.root / (self.request["request_id"] + ".dump")).exists())
        self.assertFalse(ops.DEPLOY_LOCK.exists())

    def test_verify_requires_candidate_runtime_and_does_not_claim_user_path(self):
        observed = {
            "checkout_sha": "a" * 40,
            "dirty_tracked_files": 0,
            "health": True,
            "containers": {
                "backend": {"running": True},
                "scheduler": {"running": True},
            },
            "runtime_code": {
                "backend": {"matches": True},
                "scheduler": {"matches": False},
            },
            "user_path_verified": False,
        }
        request = dict(self.request, operation="verify", candidate_sha="a" * 40)
        with patch.object(ops, "inspect", return_value=observed):
            with self.assertRaisesRegex(ops.OpsError, "runtime_code_not_candidate"):
                ops.execute(request, self.policy, str(self.root))
            observed["runtime_code"]["scheduler"]["matches"] = True
            self.assertFalse(
                ops.execute(request, self.policy, str(self.root))["user_path_verified"]
            )

    def test_archive_check_receives_descriptor_at_start_after_magic_read(self):
        archive = b"PGDMP" + b"x" * 100

        def subprocess(argv, **kwargs):
            if argv[-2:] == ["pg_restore", "--list"]:
                self.assertEqual(os.read(kwargs["stdin"].fileno(), 5), b"PGDMP")
            else:
                kwargs["stdout"].write(archive)
            return Mock(returncode=0)

        with (
            patch.object(ops, "inspect", return_value=self.observation),
            patch.object(ops, "git", return_value=("a" * 40).encode()),
            patch.object(ops, "container"),
            patch.object(ops.subprocess, "run", side_effect=subprocess),
        ):
            result = ops.execute(self.request, self.policy, str(self.root))
        self.assertEqual(Path(result["private_path"]).read_bytes(), archive)
        self.assertTrue(result["archive_list_verified"])
        self.assertFalse(result["restore_test_performed"])

    def test_inspect_uses_finance_health_envelope_and_rejects_error_payload(self):
        self.policy["health_url"] = "http://127.0.0.1:8002/health"
        for body, expected in [
            ({"data": {"status": "healthy"}, "error": None}, True),
            ({"status": "healthy"}, False),
            ({"data": {"status": "healthy"}, "error": "backend error"}, False),
            ({"data": {"status": "degraded"}, "error": None}, False),
            (None, False),
        ]:
            with (
                self.subTest(body=body),
                patch.object(ops, "git", side_effect=[b"a" * 40, b"prod", b""]),
                patch.object(ops, "container", return_value={"running": False}),
                patch.object(ops.urllib.request, "build_opener") as opener,
            ):
                response = opener.return_value.open.return_value.__enter__.return_value
                response.status = 200
                response.read.return_value = json.dumps(body).encode()
                self.assertEqual(ops.inspect(self.policy)["health"], expected)
