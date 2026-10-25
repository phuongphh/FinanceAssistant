"""Trusted post-execution assessment; model text is never a gate result."""

from __future__ import annotations
from fnmatch import fnmatchcase
from pathlib import PurePosixPath
import re

CONTROL = (
    ".git",
    ".git/**",
    ".github",
    ".github/**",
    ".codex",
    ".codex/**",
    ".claude",
    ".claude/**",
    "scripts/agent_loop",
    "scripts/agent_loop/**",
    "scripts/delivery",
    "scripts/delivery/**",
    "docs/contracts",
    "docs/contracts/**",
    "AGENTS.md",
    "CLAUDE.md",
)


def scope_check(paths, scope):
    violations = []
    for path in paths:
        p = PurePosixPath(path)
        if (
            not path
            or p.is_absolute()
            or ".." in p.parts
            or "\\" in path
            or str(p) != path
        ):
            violations.append(path)
            continue
        secret = p.name == ".env" or (
            p.name.startswith(".env.") and p.name != ".env.example"
        )
        if secret or any(
            fnmatchcase(path, x) for x in CONTROL + tuple(scope["excluded_paths"])
        ):
            violations.append(path)
            continue
        if not any(fnmatchcase(path, x) for x in scope["allowed_paths"]):
            violations.append(path)
    return violations


def worker_result(
    task, engine, *, run_id, checkpoint, changed_files, gates, tested_head_sha
):
    """gates/changed_files/tested_head_sha must come from the trusted executor adapter.
    Never deserialize these arguments from the model's final_text.
    """
    status = engine.status
    problems = scope_check(changed_files, task["scope"])
    if problems:
        status = "scope_violation"
    elif status == "completed":
        if gates["status"] == "failed":
            status = "test_failed"
        elif (
            gates["status"] == "passed"
            and gates["evidence"]
            and tested_head_sha
            and re.fullmatch("[0-9a-f]{40}", tested_head_sha)
        ):
            status = "review_ready"
        else:
            status = "blocked"
    return {
        "schema_version": 1,
        "repository": task["repository"],
        "task_id": task["task_id"],
        "run_id": run_id,
        "engine": engine.engine,
        "session_id": engine.session_id,
        "status": status,
        "base_sha": task["base_sha"],
        "head_sha": tested_head_sha,
        "changed_files": changed_files,
        "gates": gates,
        "checkpoint": checkpoint,
        "next_step": "Independent review before publish/release"
        if status == "review_ready"
        else "Resolve " + status + " using checkpoint; do not publish",
    }
