"""Persistent engine preference for an authorized local PM/operator session.

Resolve preferences before request approval/digest, never while resuming a run.
This CLI is not an authenticated public endpoint or a provider spending grant.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import copy
import fcntl
import json
import os
from pathlib import Path
import re

from .controller import Denied, digest
from .local_runner import LIMIT
from .loop import atomic_json

ENGINES = ("claude", "codex")


def read_preferences(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise Denied("Missing/invalid preferences; set a default explicitly")
    value = json.loads(path.read_text())
    if (
        not isinstance(value, dict)
        or set(value) != {"schema_version", "default_engine"}
        or value["schema_version"] != 1
        or value["default_engine"] not in ENGINES
    ):
        raise Denied("Invalid local engine preferences")
    return value


@contextmanager
def preference_lock(path):
    path = Path(path)
    if path.is_symlink() or path.parent.is_symlink():
        raise Denied("Preferences cannot be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(path.suffix + ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def set_default(path, engine):
    if engine not in ENGINES:
        raise Denied("Engine must be claude or codex")
    path = Path(path)
    with preference_lock(path):
        old = read_preferences(path) if path.exists() else None
        new = {"schema_version": 1, "default_engine": engine}
        if old != new:
            if old is not None:
                atomic_json(path.with_suffix(path.suffix + ".previous"), old)
            atomic_json(path, new)
        if read_preferences(path) != new:
            raise Denied("Preference readback failed")
    return {
        "default_engine": engine,
        "changed": old != new,
        "applies_to": "new requests; existing tasks keep their approved engine",
    }


def prepare_request(spec, preferences):
    """Freeze engine/branch before approval; explicit task override is preserved."""
    result = copy.deepcopy(spec)
    task = result.get("task")
    if not isinstance(task, dict):
        raise Denied("Missing task")
    engine = task.get("engine")
    if engine is None or engine == "default":
        engine = preferences["default_engine"]
    if engine not in ENGINES:
        raise Denied("Invalid task engine")
    task["engine"] = engine
    branch = task.get("branch")
    issue = task.get("issue_number")
    if not isinstance(issue, int) or isinstance(issue, bool) or issue < 1:
        raise Denied("Positive issue number required")
    stem = r"local-issue-" + str(issue) + r"-[a-z0-9-]+"
    if isinstance(branch, str) and re.fullmatch(stem, branch):
        branch = engine + "/" + branch
    if not isinstance(branch, str) or not re.fullmatch(engine + "/" + stem, branch):
        raise Denied("Branch must match resolved engine and issue; no silent rewrite")
    task["branch"] = branch
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("show")
    change = sub.add_parser("set")
    change.add_argument("engine", choices=ENGINES)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("request", type=Path)
    prepare.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.action == "set":
            result = set_default(args.config, args.engine)
        elif args.action == "show":
            result = read_preferences(args.config)
        else:
            raw = args.request.read_bytes()
            if len(raw) > LIMIT:
                raise Denied("Request too large")
            if args.output.exists() or args.output.is_symlink():
                raise Denied("Do not overwrite an existing prepared request")
            prepared = prepare_request(json.loads(raw), read_preferences(args.config))
            encoded = json.dumps(prepared, ensure_ascii=False).encode()
            if len(encoded) > LIMIT:
                raise Denied("Prepared request too large")
            # Exclusive create: another preparer cannot overwrite this artifact.
            with os.fdopen(
                os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w"
            ) as output:
                output.write(json.dumps(prepared, ensure_ascii=False, indent=2) + "\n")
            args.output.chmod(0o600)
            result = {
                "engine": prepared["task"]["engine"],
                "branch": prepared["task"]["branch"],
                "request_digest": digest(prepared),
                "output": str(args.output),
                "note": "Preparation does not authorize or start coding",
            }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (Denied, ValueError, OSError, KeyError, TypeError):
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "reason": "Invalid preferences/request or inaccessible path; no coding started",
                }
            )
        )
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
