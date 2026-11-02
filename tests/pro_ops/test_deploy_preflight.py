import base64
from contextlib import redirect_stdout
import importlib.util
import io
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "deploy_preflight", ROOT / "ops/fleet/deploy_preflight.py"
)
diag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diag)


class DeployIdentityPreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name).resolve()
        (self.project / ".git").mkdir()
        (self.project / ".env").write_text("SECRET=synthetic_private_credential\n")
        (self.project / "scripts").mkdir()
        (self.project / "scripts/rebuild-finance-prod.sh").write_text(
            "synthetic reviewed deploy script"
        )
        self.project_patch = patch.object(diag, "PROJECT", self.project)
        self.project_patch.start()
        self.addCleanup(self.project_patch.stop)

    def result(self, args, code=0, output=b"", error=b""):
        return subprocess.CompletedProcess(args, code, output, error)

    def test_normal_user_reports_permission_failure_without_leaking_config_or_stderr(
        self,
    ):
        with (
            patch.object(
                diag,
                "git",
                return_value=self.result(
                    [],
                    128,
                    error=b"Permission denied https://synthetic_private_credential@github.com/",
                ),
            ) as git,
            patch.object(
                diag, "command", return_value=self.result([], output=b"true\n")
            ),
        ):
            report = diag.probe()
        self.assertFalse(report["git_readable"])
        self.assertEqual(report["git_error"], "permission_denied")
        self.assertTrue(report["docker_backend_visible"])
        self.assertFalse(report["production_changed"])
        self.assertNotIn("synthetic_private_credential", json.dumps(report))
        git.assert_called_once_with("rev-parse", "HEAD")
        self.assertEqual(
            (self.project / ".env").read_text(), "SECRET=synthetic_private_credential\n"
        )

    def test_existing_root_context_checks_only_exact_finance_https_prod_ref(self):
        calls = []

        def git(*args):
            calls.append(args)
            if args == ("rev-parse", "HEAD"):
                return self.result(args, output=b"a" * 40 + b"\n")
            if args == ("remote", "get-url", "origin"):
                return self.result(
                    args,
                    output=b"https://synthetic_private_credential@github.com/phuongphh/FinanceAssistant.git\n",
                )
            self.assertEqual(
                args,
                (
                    "-c",
                    "credential.helper=",
                    "-c",
                    "http.sslVerify=true",
                    "ls-remote",
                    "--exit-code",
                    "origin",
                    "refs/heads/prod",
                ),
            )
            return self.result(args, output=b"b" * 40 + b"\trefs/heads/prod\n")

        with (
            patch.object(diag, "git", side_effect=git),
            patch.object(diag, "command", return_value=self.result([], output=b"true")),
        ):
            report = diag.probe(root_probe=True)
        self.assertTrue(report["origin_identity_matches"])
        self.assertTrue(report["git_remote_auth_ok"])
        self.assertEqual(report["github_prod_sha"], "b" * 40)
        self.assertNotIn("synthetic_private_credential", json.dumps(report))
        self.assertFalse(any("fetch" in c or "pull" in c for c in calls))

    def test_other_repository_or_missing_embedded_credential_never_contacts_git_remote(
        self,
    ):
        for origin in [
            b"https://synthetic_private_credential@evil.test/phuongphh/FinanceAssistant.git",
            b"https://github.com/phuongphh/FinanceAssistant.git",
            b"git@github.com:other/FinanceAssistant.git",
        ]:
            with (
                patch.object(
                    diag,
                    "git",
                    side_effect=[
                        self.result([], output=b"a" * 40),
                        self.result([], output=origin),
                    ],
                ) as git,
                patch.object(
                    diag, "command", return_value=self.result([], output=b"true")
                ),
            ):
                report = diag.probe(root_probe=True)
            self.assertIsNone(report["git_remote_auth_ok"])
            self.assertEqual(git.call_count, 2)

    def test_unavailable_sudo_is_reported_without_prompting_or_secret_output(self):
        output = io.StringIO()
        with (
            patch("sys.argv", ["deploy_preflight.py"]),
            patch.object(diag.os, "getuid", return_value=1000),
            patch.object(
                diag,
                "probe",
                return_value={
                    "status": "diagnostic_complete",
                    "uid": 1000,
                    "production_changed": False,
                },
            ),
            patch.object(
                diag,
                "command",
                return_value=self.result(
                    [], 1, error=b"private credential should never be printed"
                ),
            ) as command,
            redirect_stdout(output),
        ):
            diag.main()
        report = json.loads(output.getvalue())
        self.assertFalse(report["existing_root_probe_available"])
        self.assertEqual(
            command.call_args.args[0][:3], ["sudo", "-n", "/usr/bin/python3"]
        )
        self.assertNotIn("credential", output.getvalue())

    def test_root_probe_cannot_grant_itself_root(self):
        output = io.StringIO()
        with (
            patch("sys.argv", ["deploy_preflight.py", "--root-probe"]),
            patch.object(diag.os, "getuid", return_value=1000),
            patch.object(diag, "probe") as probe,
            redirect_stdout(output),
            self.assertRaises(SystemExit),
        ):
            diag.main()
        probe.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())["status"], "diagnostic_failed")

    def test_runner_transfers_exact_reporter_and_rejects_another_project(self):
        workflow = yaml.load(
            (ROOT / ".github/workflows/deploy.yml").read_text(), Loader=yaml.BaseLoader
        )
        steps = workflow["jobs"]["diagnose"]["steps"]
        script = steps[1]["run"]
        env_file = self.project / "github-env"
        env = {**os.environ, "GITHUB_ENV": str(env_file), "REGISTERED_PROJECT_DIR": ""}
        result = subprocess.run(
            ["bash", "-e", "-c", script], cwd=ROOT, env=env, capture_output=True
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        lines = env_file.read_text().splitlines()
        self.assertEqual(len(lines), 2)
        values = dict(line.split("=", 1) for line in lines)
        payload = base64.b64decode(values["FLEET_DIAG_B64"], validate=True)
        self.assertEqual(payload, (ROOT / "ops/fleet/deploy_preflight.py").read_bytes())
        self.assertEqual(hashlib.sha256(payload).hexdigest(), values["FLEET_DIAG_SHA"])
        env_file.unlink()
        result = subprocess.run(
            ["bash", "-e", "-c", script],
            cwd=ROOT,
            env={**env, "REGISTERED_PROJECT_DIR": "/unregistered-project"},
            capture_output=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(env_file.exists())
        syntax = subprocess.run(
            ["bash", "-n"],
            input=steps[2]["with"]["script"].encode(),
            capture_output=True,
        )
        self.assertEqual(syntax.returncode, 0, syntax.stderr.decode())

    def test_workflow_keeps_diagnostics_separate_and_uses_trusted_main(self):
        workflow = yaml.load(
            (ROOT / ".github/workflows/deploy.yml").read_text(), Loader=yaml.BaseLoader
        )
        self.assertEqual(
            workflow["on"]["workflow_dispatch"]["inputs"]["diagnostics_only"][
                "default"
            ],
            "false",
        )
        diagnostic = workflow["jobs"]["diagnose"]
        deploy = workflow["jobs"]["deploy"]
        self.assertIn("inputs.diagnostics_only", diagnostic["if"])
        self.assertIn("!inputs.diagnostics_only", deploy["if"])
        checkout = diagnostic["steps"][0]
        self.assertEqual(checkout["with"]["ref"], "main")
        self.assertEqual(checkout["with"]["persist-credentials"], "false")
        self.assertEqual(diagnostic["permissions"], {"contents": "read"})
        scripts = "\n".join(
            s.get("script", s.get("run", s.get("with", {}).get("script", "")))
            for s in diagnostic["steps"]
        )
        self.assertNotIn("docker compose", scripts)
        self.assertNotIn("chown", scripts)
        self.assertNotIn(
            "chown -R", (ROOT / ".github/workflows/deploy.yml").read_text()
        )
