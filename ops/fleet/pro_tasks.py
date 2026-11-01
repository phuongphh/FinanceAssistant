"""Reviewed Finance Production operations: inspect, consistent backup, verify.

Executed only by the signed fleet receiver using an owner-installed host binding.
No deploy, migrations, restore, restart, cleanup or arbitrary command interface.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import resource
import re
import subprocess
import time
import urllib.request

REPOSITORY = "phuongphh/FinanceAssistant"
DEPLOY_LOCK = Path("/tmp/rebuild-finance-prod.lock")


class OpsError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def environment() -> dict[str, str]:
    return {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(Path.home()),
        "LC_ALL": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
    }


def command(argv: list[str], *, data: bytes | None = None, timeout: int = 30) -> bytes:
    result = subprocess.run(
        argv, input=data, capture_output=True, env=environment(), timeout=timeout
    )
    if result.returncode:
        raise OpsError("registered_command_failed")
    return result.stdout


def git(policy: dict, *args: str) -> bytes:
    return command(
        [
            "git",
            "--no-replace-objects",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "core.fsmonitor=false",
            "-C",
            policy["project_dir"],
            *args,
        ]
    )


def container(policy: dict, service: str) -> dict:
    name = policy["containers"][service]
    template = "{{json .Config.Labels}}\n{{json .State.Running}}\n{{json .Image}}\n{{json .Mounts}}"
    rows = (
        command(["docker", "inspect", "--format", template, name]).decode().splitlines()
    )
    labels, running, image, mounts = map(json.loads, rows)
    if (
        labels.get("com.docker.compose.project") != policy["compose_project"]
        or labels.get("com.docker.compose.service") != service
    ):
        raise OpsError("container_identity_mismatch")
    if service == "postgres":
        volumes = [
            m.get("Name")
            for m in mounts
            if m.get("Type") == "volume"
            and m.get("Destination") == "/var/lib/postgresql/data"
        ]
        if volumes != [policy["postgres_volume"]]:
            raise OpsError("database_volume_identity_mismatch")
    return {"name": name, "running": running is True, "image_id": image}


def database_command(policy: dict, script: str, *, data: bytes | None = None) -> bytes:
    # script is always a literal in this reviewed module, never a task parameter.
    return command(
        [
            "docker",
            "exec",
            "-i",
            "--env",
            "PGOPTIONS=-c statement_timeout=120000 -c lock_timeout=5000",
            policy["containers"]["postgres"],
            "sh",
            "-ec",
            script,
        ],
        data=data,
        timeout=130,
    )


def expected_code(policy: dict, sha: str) -> dict[str, str]:
    names = (
        git(policy, "ls-tree", "-r", "--name-only", sha, "--", "backend/", "alembic/")
        .decode()
        .splitlines()
    )
    names = [
        n
        for n in names
        if n.endswith(".py") and "/tests/" not in n and "/fixtures/" not in n
    ]
    if (
        not names
        or len(names) > 2500
        or any(
            not n.startswith(("backend/", "alembic/")) or ".." in Path(n).parts
            for n in names
        )
    ):
        raise OpsError("source_tree_outside_runtime_contract")
    proc = subprocess.run(
        [
            "git",
            "--no-replace-objects",
            "-C",
            policy["project_dir"],
            "cat-file",
            "--batch",
        ],
        input=("\n".join(sha + ":" + name for name in names) + "\n").encode(),
        capture_output=True,
        env=environment(),
        timeout=30,
    )
    if proc.returncode or len(proc.stdout) > 24 * 1024**2:
        raise OpsError("runtime_source_inventory_failed")
    data = proc.stdout
    result = {}
    for name in names:
        header, separator, data = data.partition(b"\n")
        parts = header.split()
        if not separator or len(parts) != 3 or parts[1] != b"blob":
            raise OpsError("runtime_source_not_regular_blob")
        size = int(parts[2])
        content, data = data[:size], data[size + 1 :]
        if len(content) != size:
            raise OpsError("runtime_source_inventory_truncated")
        result[name] = hashlib.sha256(content).hexdigest()
    return result


RUNTIME_HASH_SCRIPT = r"""
import hashlib,json,pathlib,sys
expected=json.load(sys.stdin)
root=pathlib.Path('/app')
actual={}
for prefix in ['backend','alembic']:
 for p in (root/prefix).rglob('*.py'):
  relative=p.relative_to(root).as_posix()
  if '/tests/' in relative or '/fixtures/' in relative:continue
  if p.is_symlink():raise ValueError('runtime symlink')
  actual[relative]=hashlib.sha256(p.read_bytes()).hexdigest()
print(json.dumps({'matches':actual==expected,'expected_files':len(expected),'actual_files':len(actual),'mismatches':sum(actual.get(k)!=v for k,v in expected.items())}))
"""


def inspect(policy: dict) -> dict:
    checkout = Path(policy["project_dir"])
    if checkout.resolve() != checkout or not checkout.is_dir():
        raise OpsError("registered_checkout_missing_or_symlinked")
    sha = git(policy, "rev-parse", "HEAD").decode().strip()
    if len(sha) != 40:
        raise OpsError("invalid_checkout_revision")
    branch = git(policy, "rev-parse", "--abbrev-ref", "HEAD").decode().strip()
    dirty = len(
        git(policy, "status", "--porcelain", "--untracked-files=no").splitlines()
    )
    containers = {
        s: container(policy, s) for s in ("backend", "scheduler", "postgres", "redis")
    }
    migrations = []
    if containers["postgres"]["running"]:
        rows = (
            database_command(
                policy,
                'test -n "$POSTGRES_USER"; test -n "$POSTGRES_DB"; exec psql -v ON_ERROR_STOP=1 -At -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT version_num FROM alembic_version ORDER BY version_num"',
            )
            .decode()
            .splitlines()
        )
        if len(rows) > 20 or any(
            not row.replace("_", "").isalnum() or len(row) > 100 for row in rows
        ):
            raise OpsError("migration_metadata_invalid")
        migrations = rows
    health = False
    try:
        url = policy["health_url"]
        if not re.fullmatch(r"http://127\.0\.0\.1:[0-9]{1,5}/health", url):
            raise OpsError("unregistered_health_endpoint")
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
            url, timeout=5
        ) as response:
            body = json.loads(response.read(65537))
            health = response.status == 200 and body.get("status") in ("ok", "healthy")
    except (OSError, ValueError):
        health = False
    runtime = {}
    if containers["backend"]["running"]:
        expected = expected_code(policy, sha)
        for service in ("backend", "scheduler"):
            if containers[service]["running"]:
                runtime[service] = json.loads(
                    command(
                        [
                            "docker",
                            "exec",
                            "-i",
                            containers[service]["name"],
                            "python",
                            "-I",
                            "-c",
                            RUNTIME_HASH_SCRIPT,
                        ],
                        data=json.dumps(expected).encode(),
                        timeout=45,
                    )
                )
    return {
        "checkout_sha": sha,
        "branch": branch,
        "dirty_tracked_files": dirty,
        "containers": containers,
        "migrations": migrations,
        "health": health,
        "runtime_code": runtime,
        "runtime_version_basis": "running-container Python source hashes; checkout alone is not runtime proof",
        "user_path_verified": False,
    }


def backup(request: dict, policy: dict, state: str) -> dict:
    observed = inspect(policy)
    if observed["checkout_sha"] != request["expected_checkout_sha"]:
        raise OpsError("production_checkout_changed")
    if not observed["containers"]["postgres"]["running"]:
        raise OpsError("production_database_not_running")
    destination = Path(policy["backup_directory"])
    if (
        destination.resolve() != destination
        or not destination.is_dir()
        or destination.stat().st_uid != os.getuid()
        or destination.stat().st_mode & 0o077
    ):
        raise OpsError("private_owned_backup_directory_required")
    lock_path = DEPLOY_LOCK
    try:
        fd = os.open(
            lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600
        )
    except FileExistsError:
        raise OpsError("finance_deploy_or_backup_lock_busy") from None
    own_stat = os.fstat(fd)
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    target = destination / (request["request_id"] + ".dump")
    partial = target.with_suffix(".dump.partial")
    if target.exists() or partial.exists():
        # Never overwrite or replay a prior side effect.
        release_lock(lock_path, own_stat)
        raise OpsError("backup_artifact_already_exists_reconcile")
    try:
        if (
            git(policy, "rev-parse", "HEAD").decode().strip()
            != request["expected_checkout_sha"]
        ):
            raise OpsError("production_checkout_changed")
        container(policy, "postgres")
        limit = policy["max_backup_bytes"]
        if type(limit) is not int or not 1024**2 <= limit <= 512 * 1024**2:
            raise OpsError("invalid_backup_limit")

        def bound_output() -> None:
            resource.setrlimit(resource.RLIMIT_FSIZE, (limit, limit))

        script = 'test -n "$POSTGRES_USER"; test -n "$POSTGRES_DB"; exec pg_dump --format=custom --no-owner --no-acl -U "$POSTGRES_USER" "$POSTGRES_DB"'
        fd = os.open(
            partial, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600
        )
        with os.fdopen(fd, "wb") as output:
            proc = subprocess.run(
                [
                    "docker",
                    "exec",
                    "--env",
                    "PGOPTIONS=-c statement_timeout=120000 -c lock_timeout=5000",
                    policy["containers"]["postgres"],
                    "sh",
                    "-ec",
                    script,
                ],
                stdout=output,
                stderr=subprocess.DEVNULL,
                env=environment(),
                timeout=130,
                preexec_fn=bound_output,
            )
            output.flush()
            os.fsync(output.fileno())
        if proc.returncode or not 5 < partial.stat().st_size < limit:
            raise OpsError("database_backup_incomplete")
        # pg_restore consumes this descriptor directly. Buffered read/seek may
        # rewind only Python's buffer while leaving the OS descriptor at EOF.
        with partial.open("rb", buffering=0) as handle:
            if handle.read(5) != b"PGDMP":
                raise OpsError("backup_archive_invalid")
            handle.seek(0)
            check = subprocess.run(
                [
                    "docker",
                    "exec",
                    "-i",
                    policy["containers"]["postgres"],
                    "pg_restore",
                    "--list",
                ],
                stdin=handle,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=environment(),
                timeout=45,
            )
        if check.returncode:
            raise OpsError("backup_archive_unreadable")
        checksum_state = hashlib.sha256()
        with partial.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                checksum_state.update(block)
        checksum = checksum_state.hexdigest()
        os.link(partial, target, follow_symlinks=False)
        partial.unlink()
        directory_fd = os.open(destination, os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return {
            "backup_id": request["request_id"],
            "private_path": str(target),
            "sha256": checksum,
            "bytes": target.stat().st_size,
            "created_at": int(time.time()),
            "checkout_sha": observed["checkout_sha"],
            "consistent_pg_dump": True,
            "archive_list_verified": True,
            "restore_test_performed": False,
            "data_exported_to_mailbox": False,
        }
    finally:
        release_lock(lock_path, own_stat)


def release_lock(path: Path, owned: os.stat_result) -> None:
    if (
        path.is_file()
        and not path.is_symlink()
        and path.stat().st_ino == owned.st_ino
        and path.read_text() == str(os.getpid())
    ):
        path.unlink()


def execute(request: dict, policy: dict, state: str) -> dict:
    if policy.get("repository") != REPOSITORY or request["repository"] != REPOSITORY:
        raise OpsError("repository_not_registered")
    if request["operation"] == "backup":
        return backup(request, policy, state)
    if request["operation"] not in ("inspect", "verify"):
        raise OpsError("operation_not_registered")
    observed = inspect(policy)
    if (
        request["expected_checkout_sha"]
        and observed["checkout_sha"] != request["expected_checkout_sha"]
    ):
        raise OpsError("production_checkout_changed")
    if request["operation"] == "verify":
        if (
            observed["checkout_sha"] != request["candidate_sha"]
            or observed["dirty_tracked_files"]
        ):
            raise OpsError("deployed_checkout_not_candidate")
        if not observed["health"] or not all(
            c["running"] for c in observed["containers"].values()
        ):
            raise OpsError("production_services_unhealthy")
        if set(observed["runtime_code"]) != {"backend", "scheduler"} or not all(
            v["matches"] for v in observed["runtime_code"].values()
        ):
            raise OpsError("runtime_code_not_candidate")
    return observed
