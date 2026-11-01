import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "finance_git_ops", Path(__file__).resolve().parents[2] / "ops/fleet/pro_tasks.py"
)
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)


class ReadonlyGitMetadataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.project = self.root / "project"
        self.project.mkdir()
        self.scratch = self.root / "scratch"
        self.scratch.mkdir(mode=0o700)
        self.shell("init", "-q")
        (self.project / "backend").mkdir()
        (self.project / "backend/main.py").write_text("VALUE = 1\n")
        self.shell("add", "backend")
        self.shell(
            "-c",
            "user.name=fixture",
            "-c",
            "user.email=fixture@localhost",
            "commit",
            "-qm",
            "Initial synthetic runtime",
        )
        self.sha = self.shell("rev-parse", "HEAD").decode().strip()
        self.policy = {
            "project_dir": str(self.project),
            "git_scratch_directory": str(self.scratch),
            "git_metadata_mode": "isolated-readonly-v1",
        }
        self.config = self.project / ".git/config"
        self.original = (
            self.config.read_bytes()
            + b'\n[remote "origin"]\nurl = https://synthetic_private_credential@github.com/phuongphh/FinanceAssistant.git\n'
        )
        self.config.write_bytes(self.original)
        self.addCleanup(self.config.chmod, 0o600)

    def shell(self, *args):
        return subprocess.check_output(
            ["git", "-c", "core.hooksPath=/dev/null", "-C", str(self.project), *args],
            env=ops.environment(),
            stderr=subprocess.PIPE,
        )

    def test_protected_config_is_untouched_and_git_reads_real_head_index_and_blobs(
        self,
    ):
        self.config.chmod(0)
        if os.getuid() != 0:
            with self.assertRaises(subprocess.CalledProcessError):
                self.shell("remote", "get-url", "origin")
        self.assertEqual(
            ops.git(self.policy, "rev-parse", "HEAD").decode().strip(), self.sha
        )
        self.assertEqual(
            ops.git(self.policy, "status", "--porcelain", "--untracked-files=no"), b""
        )
        self.assertEqual(
            ops.expected_code(self.policy, self.sha),
            {"backend/main.py": hashlib.sha256(b"VALUE = 1\n").hexdigest()},
        )
        self.assertEqual(self.config.stat().st_mode & 0o777, 0)
        self.assertEqual(list(self.scratch.iterdir()), [])
        self.config.chmod(0o600)
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_live_metadata_updates_and_tracked_edits_are_not_hidden_by_snapshot(self):
        (self.project / "backend/main.py").write_text("VALUE = 2\n")
        self.shell("add", "backend")
        self.shell(
            "-c",
            "user.name=fixture",
            "-c",
            "user.email=fixture@localhost",
            "commit",
            "-qm",
            "Second synthetic runtime",
        )
        new_sha = self.shell("rev-parse", "HEAD").decode().strip()
        self.config.chmod(0)
        self.assertEqual(
            ops.git(self.policy, "rev-parse", "HEAD").decode().strip(), new_sha
        )
        (self.project / "backend/main.py").write_text("VALUE = 999\n")
        self.assertIn(
            b"backend/main.py",
            ops.git(self.policy, "status", "--porcelain", "--untracked-files=no"),
        )
        self.assertEqual(
            ops.expected_code(self.policy, new_sha)["backend/main.py"],
            hashlib.sha256(b"VALUE = 2\n").hexdigest(),
        )

    def test_config_content_and_hooks_are_excluded_and_writes_rejected(self):
        self.config.write_bytes(
            b"[invalid config syntax and private credential never read\n"
        )
        with ops.readonly_git_metadata(self.policy) as view:
            self.assertNotIn(
                "synthetic_private_credential", (view / "config").read_text()
            )
            self.assertFalse((view / "hooks").exists())
            self.assertFalse((view / "info").exists())
        self.assertEqual(
            ops.git(self.policy, "rev-parse", "HEAD").decode().strip(), self.sha
        )
        for args in [
            ("update-ref", "HEAD", "a" * 40),
            ("config", "remote.origin.url", "changed"),
            ("reset", "--hard"),
        ]:
            with self.assertRaisesRegex(ops.OpsError, "not_readonly"):
                ops.git(self.policy, *args)

    def test_unregistered_mode_public_scratch_and_symlink_git_directory_block(self):
        with self.assertRaisesRegex(ops.OpsError, "not_registered"):
            ops.git(dict(self.policy, git_metadata_mode="normal"), "rev-parse", "HEAD")
        self.scratch.chmod(0o755)
        with self.assertRaisesRegex(ops.OpsError, "private_git_scratch"):
            ops.git(self.policy, "rev-parse", "HEAD")
        self.scratch.chmod(0o700)
        metadata = self.project / ".git"
        metadata.rename(self.project / ".actual-git")
        metadata.symlink_to(self.project / ".actual-git")
        with self.assertRaisesRegex(ops.OpsError, "regular_registered_git"):
            ops.git(self.policy, "rev-parse", "HEAD")
