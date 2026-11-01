"""Opt-in integration test with disposable synthetic Docker resources only.

Run: python tests/pro_ops/smoke_docker.py --output /absolute/evidence.json
Requires cached postgres:16-alpine, redis:7-alpine and fleet-content-dev:local.
Never uses Finance container names, its volume, data, code or deploy lock.
"""

import argparse
import importlib.util
import json
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
from unittest.mock import patch


def run(*args, data=None):
    return subprocess.run(
        list(args), input=data, capture_output=True, check=True, timeout=90
    ).stdout


def main(output):
    ident = "fleet-pro-ops-smoke-" + secrets.token_hex(4)
    names = {s: ident + "-" + s for s in ["backend", "scheduler", "postgres", "redis"]}
    volume = ident + "-db"
    network = ident + "-net"
    spec = importlib.util.spec_from_file_location(
        "ops", Path(__file__).resolve().parents[2] / "ops/fleet/pro_tasks.py"
    )
    ops = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ops)
    started = []
    created_volume = False
    created_network = False
    try:
        with tempfile.TemporaryDirectory(prefix=ident) as temporary:
            root = Path(temporary).resolve()
            code = root / "code"
            backups = root / "backups"
            code.mkdir()
            backups.mkdir(mode=0o700)
            for name, content in [
                ("backend/main.py", "VALUE = 1\n"),
                ("alembic/versions/demo.py", "revision = 'synthetic_v1'\n"),
            ]:
                p = code / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content)
            run("git", "init", "-q", str(code))
            run("git", "-C", str(code), "add", "backend", "alembic")
            run(
                "git",
                "-C",
                str(code),
                "-c",
                "user.name=synthetic",
                "-c",
                "user.email=synthetic@localhost",
                "commit",
                "-qm",
                "Synthetic runtime fixture",
            )
            sha = run("git", "-C", str(code), "rev-parse", "HEAD").decode().strip()
            run("docker", "volume", "create", volume)
            created_volume = True
            run("docker", "network", "create", network)
            created_network = True
            for service in names:
                args = [
                    "docker",
                    "run",
                    "-d",
                    "--pull=never",
                    "--name",
                    names[service],
                    "--label",
                    "com.docker.compose.project=" + ident,
                    "--label",
                    "com.docker.compose.service=" + service,
                    "--network",
                    network,
                    "--memory",
                    "256m",
                    "--cpus",
                    "0.5",
                ]
                if service == "postgres":
                    args += [
                        "--env",
                        "POSTGRES_HOST_AUTH_METHOD=trust",
                        "--env",
                        "POSTGRES_USER=fixture",
                        "--env",
                        "POSTGRES_DB=fixture",
                        "--mount",
                        "type=volume,source="
                        + volume
                        + ",target=/var/lib/postgresql/data",
                        "postgres:16-alpine",
                    ]
                elif service == "redis":
                    args += ["redis:7-alpine"]
                else:
                    args += [
                        "--read-only",
                        "--mount",
                        "type=bind,source=" + str(code) + ",target=/app,readonly",
                    ]
                    if service == "backend":
                        server = "from http.server import BaseHTTPRequestHandler,HTTPServer\nclass H(BaseHTTPRequestHandler):\n def do_GET(self):\n  self.send_response(200);self.end_headers();self.wfile.write(b'{\"status\":\"healthy\"}')\nHTTPServer(('0.0.0.0',18092),H).serve_forever()"
                        args += [
                            "-p",
                            "127.0.0.1::18092",
                            "fleet-content-dev:local",
                            "python",
                            "-I",
                            "-c",
                            server,
                        ]
                    else:
                        args += [
                            "fleet-content-dev:local",
                            "python",
                            "-I",
                            "-c",
                            "import time;time.sleep(600)",
                        ]
                run(*args)
                started.append(names[service])
            deadline = time.monotonic() + 30
            while True:
                logs = subprocess.run(
                    ["docker", "logs", names["postgres"]],
                    capture_output=True,
                    timeout=10,
                )
                initialized = (
                    b"PostgreSQL init process complete" in logs.stdout + logs.stderr
                )
                ready = subprocess.run(
                    [
                        "docker",
                        "exec",
                        names["postgres"],
                        "psql",
                        "-At",
                        "-U",
                        "fixture",
                        "-d",
                        "fixture",
                        "-c",
                        "SELECT 1",
                    ],
                    capture_output=True,
                    timeout=10,
                )
                if initialized and ready.returncode == 0:
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError("Synthetic DB startup timed out")
                time.sleep(0.3)
            sql = b"CREATE TABLE alembic_version(version_num varchar(32)); INSERT INTO alembic_version VALUES ('synthetic_v1'); CREATE TABLE sample(id int); INSERT INTO sample VALUES (42);"
            run(
                "docker",
                "exec",
                "-i",
                names["postgres"],
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "fixture",
                "-d",
                "fixture",
                data=sql,
            )
            endpoint = (
                run("docker", "port", names["backend"], "18092/tcp").decode().strip()
            )
            policy = {
                "repository": ops.REPOSITORY,
                "project_dir": str(code),
                "compose_project": ident,
                "containers": names,
                "postgres_volume": volume,
                "backup_directory": str(backups),
                "health_url": "http://" + endpoint + "/health",
                "max_backup_bytes": 8 * 1024**2,
            }
            # Scope the deploy lock to this fixture. The real /tmp lock is untouched.
            ops.DEPLOY_LOCK = root / "fixture-deploy.lock"
            request = {
                "request_id": secrets.token_hex(16),
                "repository": ops.REPOSITORY,
                "operation": "inspect",
                "expected_checkout_sha": sha,
                "candidate_sha": sha,
            }
            inspected = ops.execute(request, policy, str(root))
            verified = ops.execute(dict(request, operation="verify"), policy, str(root))
            original_run = subprocess.run

            def fixture_run(argv, **kwargs):
                archive_check = argv[-2:] == ["pg_restore", "--list"]
                if archive_check:
                    kwargs["stderr"] = subprocess.PIPE
                result = original_run(argv, **kwargs)
                if archive_check and result.returncode:
                    raise AssertionError(
                        "Synthetic archive check failed: " + result.stderr.decode()
                    )
                return result

            with patch.object(ops.subprocess, "run", side_effect=fixture_run):
                backup = ops.execute(
                    dict(request, operation="backup"), policy, str(root)
                )
            # Independently restore this synthetic archive into a disposable DB.
            run(
                "docker",
                "exec",
                names["postgres"],
                "createdb",
                "-U",
                "fixture",
                "restored_fixture",
            )
            run(
                "docker",
                "exec",
                "-i",
                names["postgres"],
                "pg_restore",
                "--exit-on-error",
                "--no-owner",
                "-U",
                "fixture",
                "-d",
                "restored_fixture",
                data=Path(backup["private_path"]).read_bytes(),
            )
            restored = (
                run(
                    "docker",
                    "exec",
                    names["postgres"],
                    "psql",
                    "-At",
                    "-U",
                    "fixture",
                    "-d",
                    "restored_fixture",
                    "-c",
                    "SELECT id FROM sample",
                )
                .decode()
                .strip()
                == "42"
            )
            (code / "backend/main.py").write_text("VALUE = 999\n")
            # Compare runtime hashes directly after changing the synthetic bind.
            # This also dirties the fixture checkout, another verify blocker.
            drift = ops.inspect(policy)["runtime_code"]
            if all(v["matches"] for v in drift.values()):
                raise AssertionError("Runtime drift escaped detection")
            if (
                not restored
                or not verified["health"]
                or not all(v["matches"] for v in verified["runtime_code"].values())
            ):
                raise AssertionError("Integration verification failed")
            report = {
                "status": "passed",
                "synthetic_only": True,
                "repository": ops.REPOSITORY,
                "checkout_sha": sha,
                "inspect": inspected,
                "verify": verified,
                "backup": backup,
                "synthetic_restore_row_verified": restored,
                "runtime_drift_detected": True,
                "production_touched": False,
                "created_containers": started,
                "created_volume": volume,
            }
    finally:
        for name in reversed(started):
            subprocess.run(
                ["docker", "rm", "-f", name],
                capture_output=True,
                timeout=30,
                check=True,
            )
        if created_network:
            subprocess.run(
                ["docker", "network", "rm", network],
                capture_output=True,
                timeout=30,
                check=True,
            )
        if created_volume:
            subprocess.run(
                ["docker", "volume", "rm", volume],
                capture_output=True,
                timeout=30,
                check=True,
            )
    report["fixture_resources_removed"] = True
    output.write_text(json.dumps(report, indent=2))
    output.chmod(0o600)
    print(
        json.dumps(
            {
                "status": report["status"],
                "evidence": str(output),
                "synthetic_restore_row_verified": True,
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    main(parser.parse_args().output)
