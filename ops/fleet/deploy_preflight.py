"""Read-only diagnostics using the actual GitHub Actions SSH identity.

No deploy, fetch/pull, permission change, credential output or application restart.
The optional sudo probe uses existing permission only and never installs a grant.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from urllib.parse import urlsplit

PROJECT = Path("/home/evg-user/FinanceAssistant")
COMPONENTS = {
    "project": ".",
    "git_dir": ".git",
    "git_config": ".git/config",
    "git_index": ".git/index",
    "git_fetch_head": ".git/FETCH_HEAD",
    "git_objects": ".git/objects",
    "git_pack": ".git/objects/pack",
    "git_prod_ref": ".git/refs/heads/prod",
    "environment": ".env",
    "backups": ".backups",
    "deploy_script": "scripts/rebuild-finance-prod.sh",
}


def command(argv: list[str]) -> subprocess.CompletedProcess:
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(Path.home()),
        "LC_ALL": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
    }
    # Preserve sudo's actual caller identity for Git's normal ownership check.
    if os.environ.get("SUDO_UID", "").isdigit():
        env["SUDO_UID"] = os.environ["SUDO_UID"]
    return subprocess.run(argv, capture_output=True, env=env, timeout=25)


def git(*args: str) -> subprocess.CompletedProcess:
    return command(
        [
            "git",
            "--no-replace-objects",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "core.fsmonitor=false",
            "-C",
            str(PROJECT),
            *args,
        ]
    )


def error_kind(data: bytes) -> str:
    data = data.lower()
    for pattern, kind in [
        (b"permission denied", "permission_denied"),
        (b"dubious ownership", "ownership_check"),
        (b"authentication failed", "authentication_failed"),
        (b"could not read username", "credential_unavailable"),
        (b"could not resolve", "network_name_resolution"),
        (b"not a git repository", "repository_unavailable"),
    ]:
        if pattern in data:
            return kind
    return "command_failed"


def metadata(path: Path) -> dict:
    try:
        info = path.lstat()
        return {
            "uid": info.st_uid,
            "gid": info.st_gid,
            "mode": oct(stat.S_IMODE(info.st_mode)),
            "type": "symlink"
            if stat.S_ISLNK(info.st_mode)
            else "directory"
            if stat.S_ISDIR(info.st_mode)
            else "file"
            if stat.S_ISREG(info.st_mode)
            else "other",
            "readable": os.access(path, os.R_OK),
            "writable": os.access(path, os.W_OK),
        }
    except OSError as error:
        return {"error_type": type(error).__name__}


def probe(*, root_probe: bool = False) -> dict:
    report = {
        "status": "diagnostic_complete",
        "uid": os.getuid(),
        "gid": os.getgid(),
        "root_probe": root_probe,
        "production_changed": False,
        "components": {
            key: metadata(PROJECT / value) for key, value in COMPONENTS.items()
        },
    }
    result = git("rev-parse", "HEAD")
    head = result.stdout.decode(errors="replace").strip()
    report.update(
        git_readable=result.returncode == 0
        and re.fullmatch(r"[0-9a-f]{40}", head) is not None,
        git_head=head
        if result.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", head)
        else None,
        git_error=None if result.returncode == 0 else error_kind(result.stderr),
    )
    result = command(
        ["docker", "inspect", "--format", "{{.State.Running}}", "finance-backend"]
    )
    report["docker_backend_visible"] = (
        result.returncode == 0 and result.stdout.strip() == b"true"
    )
    script = PROJECT / COMPONENTS["deploy_script"]
    if (
        script.resolve() == script
        and script.is_file()
        and os.access(script, os.R_OK)
        and script.stat().st_size <= 1024**2
    ):
        report["deploy_script_sha256"] = hashlib.sha256(script.read_bytes()).hexdigest()
    if root_probe and report["git_readable"]:
        result = git("remote", "get-url", "origin")
        if result.returncode:
            report["origin_identity_matches"] = False
            return report
        # URI is private, kept only in memory. No URL/credential enters the report.
        try:
            value = result.stdout.decode().strip()
            url = urlsplit(value)
            matched = (
                url.scheme == "https"
                and url.hostname == "github.com"
                and url.port is None
                and url.path == "/phuongphh/FinanceAssistant.git"
                and not url.query
                and not url.fragment
            )
            report["origin_identity_matches"] = matched
            embedded = matched and url.username is not None
        except ValueError:
            report["origin_identity_matches"] = False
            embedded = False
        if embedded:
            # Read the single prod ref without fetching or writing credentials.
            result = git(
                "-c",
                "credential.helper=",
                "-c",
                "http.sslVerify=true",
                "ls-remote",
                "--exit-code",
                "origin",
                "refs/heads/prod",
            )
            match = re.fullmatch(rb"([0-9a-f]{40})\s+refs/heads/prod\n?", result.stdout)
            report["git_remote_auth_ok"] = result.returncode == 0 and match is not None
            report["github_prod_sha"] = (
                match[1].decode() if result.returncode == 0 and match else None
            )
            report["git_remote_error"] = (
                None if result.returncode == 0 else error_kind(result.stderr)
            )
        else:
            report["git_remote_auth_ok"] = None
            report["git_remote_error"] = (
                "not_checked_no_embedded_finance_https_credential"
            )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root-probe", action="store_true")
    args = parser.parse_args()
    try:
        if PROJECT.resolve() != PROJECT or not PROJECT.is_dir():
            raise ValueError("Registered project unavailable")
        if (PROJECT / ".git").resolve() != PROJECT / ".git" or not (
            PROJECT / ".git"
        ).is_dir():
            raise ValueError("Registered Git directory differs")
        if args.root_probe and os.getuid() != 0:
            raise ValueError("Existing sudo permission required")
        report = probe(root_probe=args.root_probe)
        if not args.root_probe:
            if os.getuid() == 0:
                report["existing_root_context"] = probe(root_probe=True)
            else:
                result = command(
                    [
                        "sudo",
                        "-n",
                        "/usr/bin/python3",
                        str(Path(__file__).resolve()),
                        "--root-probe",
                    ]
                )
                report["existing_root_probe_available"] = result.returncode == 0
                if result.returncode == 0:
                    value = json.loads(result.stdout)
                    if (
                        value.get("status") == "diagnostic_complete"
                        and value.get("uid") == 0
                    ):
                        report["existing_root_context"] = value
                    else:
                        report["existing_root_probe_available"] = False
        print(json.dumps(report, indent=2))
    except Exception as error:
        print(
            json.dumps(
                {
                    "status": "diagnostic_failed",
                    "error_type": type(error).__name__,
                    "production_changed": False,
                }
            )
        )
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
