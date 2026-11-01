"""Test cli với GitHub giả (FakeGH) + git thật trong ``tmp_path``.

``.env`` chỉ được tạo bên trong repo git tạm dưới ``tmp_path``, không bao giờ
đụng ``.env`` thật của repo.
"""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_loop.cli import AUTO_FIX_MARKER, Ctx, main
from agent_loop.config import LoopConfig
from agent_loop.github_api import GHError

REPO_ROOT = Path(__file__).resolve().parents[2]

NOW = datetime(2026, 10, 21, 3, 0, tzinfo=timezone.utc)  # 10:00 giờ VN
DISPATCH = "actions/workflows/agent-worker.yml/dispatches"


class FakeGH:
    def __init__(self, routes: dict[Any, Any] | None = None,
                 issues: dict[int, dict[str, Any]] | None = None) -> None:
        self.routes: dict[Any, Any] = routes or {}
        self.issues: dict[int, dict[str, Any]] = issues or {}
        self.calls: list[tuple[str, str, Any]] = []

    def api(self, path: str, method: str = "GET", body: Any = None, paginate: bool = False) -> Any:
        for key in ((method, path), path):
            if key in self.routes:
                if method != "GET":
                    self.calls.append((method, path, body))
                value = self.routes[key]
                return value(body) if callable(value) else value
        if method != "GET":
            self.calls.append((method, path, body))
            return {}
        if "/runs" in path or path.startswith("compare/"):
            return {}
        if path.startswith(("pulls/", "issues/")) and "?" not in path:
            return {}
        return []

    def graphql(self, query: str, **variables: Any) -> Any:
        if "mutation" in query:
            return {}
        n = variables.get("n")
        node = {"number": n, "title": "t", "state": "OPEN", "body": "", "labels": {"nodes": []}}
        node.update(self.issues.get(n, {}))
        return {"repository": {"issue": node}}

    def run_log(self, run_id: str) -> str:
        return ""

    # tiện cho assert
    def dispatches(self) -> list[dict[str, str]]:
        return [b["inputs"] for m, p, b in self.calls if p == DISPATCH]


def make_ctx(tmp_path: Path, fake: FakeGH, event_name: str, payload: dict[str, Any] | None,
             msgs: list[str], workdir: Path | None = None) -> Ctx:
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(payload or {}), encoding="utf-8")
    return Ctx(
        gh=fake, cfg=LoopConfig(), repo="o/r",
        env={"GITHUB_EVENT_NAME": event_name, "GITHUB_EVENT_PATH": str(event_path)},
        notifier=msgs.append, now=NOW, workdir=workdir or tmp_path,
    )


# --------------------------------------------------------------------------- on-event


def _pr_closed(merged: bool) -> dict[str, Any]:
    return {"action": "closed",
            "pull_request": {"number": 5, "merged": merged, "head": {"ref": "agent/issue-12-x"}}}


def test_on_event_pr_merged_clears_wip(tmp_path: Path) -> None:
    fake, msgs = FakeGH(), []
    ctx = make_ctx(tmp_path, fake, "pull_request", _pr_closed(True), msgs)
    assert main(["on-event"], ctx=ctx) == 0
    assert ("DELETE", "issues/12/labels/agent%3Awip", None) in fake.calls
    assert any("✅" in m for m in msgs)


def test_on_event_pr_closed_marks_rejected(tmp_path: Path) -> None:
    fake, msgs = FakeGH(), []
    ctx = make_ctx(tmp_path, fake, "pull_request", _pr_closed(False), msgs)
    assert main(["on-event"], ctx=ctx) == 0
    assert ("POST", "issues/12/labels", {"labels": ["agent:rejected"]}) in fake.calls
    assert any("🚫" in m for m in msgs)


# --------------------------------------------------------------------------- select

READY_ROUTE = "issues?state=open&labels=agent%3Aready&per_page=100"
READY = [{"number": 12, "title": "t", "labels": [{"name": "agent:ready"}]}]
READY_NODE = {12: {"labels": {"nodes": [{"name": "agent:ready"}]}}}


def test_select_dry_run_writes_nothing(tmp_path: Path) -> None:
    fake, msgs = FakeGH({READY_ROUTE: READY}, READY_NODE), []
    ctx = make_ctx(tmp_path, fake, "workflow_dispatch", {}, msgs)
    summary = tmp_path / "summary.md"
    ctx.env["GITHUB_STEP_SUMMARY"] = str(summary)
    assert main(["select", "--dry-run"], ctx=ctx) == 0
    assert fake.calls == []
    assert msgs == []
    assert "#12 | ▶️ (dry-run)" in summary.read_text(encoding="utf-8")


def test_select_marks_wip_and_dispatches(tmp_path: Path) -> None:
    fake, msgs = FakeGH({READY_ROUTE: READY}, READY_NODE), []
    ctx = make_ctx(tmp_path, fake, "workflow_dispatch", {}, msgs)
    assert main(["select"], ctx=ctx) == 0
    assert ("POST", "issues/12/labels", {"labels": ["agent:wip"]}) in fake.calls
    assert {"mode": "implement", "issue": "12"}.items() <= fake.dispatches()[0].items()
    assert any("▶️" in m for m in msgs)


def _raise_500(_body: Any) -> Any:
    raise GHError("boom", status=500)


def test_select_fails_closed_when_blocker_lookup_errors(tmp_path: Path) -> None:
    fake = FakeGH({READY_ROUTE: READY,
                   "issues/12/dependencies/blocked_by?per_page=100": _raise_500}, READY_NODE)
    msgs: list[str] = []
    ctx = make_ctx(tmp_path, fake, "workflow_dispatch", {}, msgs)
    assert main(["select"], ctx=ctx) == 0
    assert fake.dispatches() == []


def test_select_dry_run_respects_simulated_labels(tmp_path: Path) -> None:
    fake, msgs = FakeGH({READY_ROUTE: READY}, READY_NODE), []
    ctx = make_ctx(tmp_path, fake, "workflow_dispatch", {}, msgs)
    summary = tmp_path / "summary.md"
    ctx.env["GITHUB_STEP_SUMMARY"] = str(summary)
    ctx._sim_labels[12] = {"agent:wip"}  # như thể vòng dry-run trước đã gắn wip
    assert main(["select", "--dry-run"], ctx=ctx) == 0
    assert "#12 | ▶️" not in (summary.read_text(encoding="utf-8") if summary.exists() else "")


# --------------------------------------------------------------------------- on-ci-fail

CI_EVENT = {"workflow_run": {"conclusion": "failure", "name": "CI",
                             "head_branch": "agent/issue-12-x", "head_sha": "abc", "id": 777}}
PR_BY_HEAD = "pulls?head=o:agent/issue-12-x&state=open"


def test_ci_fail_dispatches_auto_fix(tmp_path: Path) -> None:
    fake, msgs = FakeGH({PR_BY_HEAD: [{"number": 5, "head": {"sha": "abc"}}]}), []
    ctx = make_ctx(tmp_path, fake, "workflow_run", CI_EVENT, msgs)
    assert main(["on-ci-fail"], ctx=ctx) == 0
    inputs = fake.dispatches()
    assert inputs and inputs[0]["mode"] == "fix"
    assert inputs[0]["ci_run"] == "777" and inputs[0]["pr"] == "5"


def test_ci_fail_out_of_auto_fix_budget_asks_human(tmp_path: Path) -> None:
    marker_comments = [{"body": f"{AUTO_FIX_MARKER} lần {i}"} for i in range(2)]
    fake = FakeGH({
        PR_BY_HEAD: [{"number": 5, "head": {"sha": "abc"}}],
        "issues/5/comments?per_page=100": marker_comments,
    })
    msgs: list[str] = []
    ctx = make_ctx(tmp_path, fake, "workflow_run", CI_EVENT, msgs)
    assert main(["on-ci-fail"], ctx=ctx) == 0
    assert fake.dispatches() == []
    for num in (5, 12):
        assert ("POST", f"issues/{num}/labels", {"labels": ["agent:needs-fix"]}) in fake.calls
    assert any("⚠️" in m for m in msgs)


# --------------------------------------------------------------------------- on-comment


def _comment(body: str, issue: dict[str, Any]) -> dict[str, Any]:
    return {"action": "created",
            "comment": {"id": 9, "body": body, "author_association": "OWNER",
                        "user": {"login": "u", "type": "User"}},
            "issue": issue}


def test_comment_fix_dispatches_on_pr(tmp_path: Path) -> None:
    fake = FakeGH({"pulls/5": {"state": "open", "head": {"ref": "agent/issue-12-x"}}})
    msgs: list[str] = []
    payload = _comment("/agent fix x", {"number": 5, "pull_request": {"url": "x"}})
    ctx = make_ctx(tmp_path, fake, "issue_comment", payload, msgs)
    assert main(["on-comment"], ctx=ctx) == 0
    inputs = fake.dispatches()
    assert inputs and inputs[0]["mode"] == "fix"
    assert (inputs[0]["comment_id"], inputs[0]["pr"], inputs[0]["issue"]) == ("9", "5", "12")
    assert ("POST", "issues/comments/9/reactions", {"content": "eyes"}) in fake.calls


def test_comment_from_untrusted_user_is_ignored(tmp_path: Path) -> None:
    fake, msgs = FakeGH({"pulls/5": {"state": "open", "head": {"ref": "agent/issue-12-x"}}}), []
    payload = _comment("/agent fix x", {"number": 5, "pull_request": {"url": "x"}})
    payload["comment"]["author_association"] = "NONE"
    ctx = make_ctx(tmp_path, fake, "issue_comment", payload, msgs)
    assert main(["on-comment"], ctx=ctx) == 0
    assert fake.calls == []


def test_comment_retry_requeues_blocked_issue(tmp_path: Path) -> None:
    fake, msgs = FakeGH(), []
    payload = _comment("/agent retry", {"number": 7, "labels": [{"name": "agent:blocked"}]})
    ctx = make_ctx(tmp_path, fake, "issue_comment", payload, msgs)
    assert main(["on-comment"], ctx=ctx) == 0
    delete = ("DELETE", "issues/7/labels/agent%3Ablocked", None)
    add = ("POST", "issues/7/labels", {"labels": ["agent:ready"]})
    assert delete in fake.calls and add in fake.calls
    assert fake.calls.index(delete) < fake.calls.index(add)


# --------------------------------------------------------------------------- publish (git thật)


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout


def _setup_repo(tmp_path: Path) -> tuple[Path, Path, str]:
    origin, work, out = tmp_path / "origin.git", tmp_path / "work", tmp_path / "out"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    _git(tmp_path, "clone", "-q", str(origin), str(work))
    _git(work, "config", "user.name", "t")
    _git(work, "config", "user.email", "t@example.com")
    _git(work, "checkout", "-q", "-b", "main")
    (work / "a.txt").write_text("one\n", encoding="utf-8")
    _git(work, "add", "a.txt")
    _git(work, "commit", "-q", "-m", "init")
    _git(work, "push", "-q", "origin", "main")
    _git(work, "fetch", "-q", "origin")
    base_sha = _git(work, "rev-parse", "HEAD").strip()
    out.mkdir()
    (out / "meta.json").write_text(json.dumps({
        "issue": 12, "base_sha": base_sha, "branch": "agent/issue-12-x", "title": "t",
        "merge_parent": "",
    }), encoding="utf-8")
    (out / "status").write_text("done", encoding="utf-8")
    (out / "gates_result").write_text("pass", encoding="utf-8")
    (out / "summary.md").write_text("Đã làm.\n\n## Cách test tay\n- bước 1\n", encoding="utf-8")
    return work, out, base_sha


def _remote_has_branch(work: Path) -> bool:
    return "refs/heads/agent/issue-12-x" in _git(work, "ls-remote", "origin")


def test_publish_pushes_branch_and_opens_pr(tmp_path: Path) -> None:
    work, out, _ = _setup_repo(tmp_path)
    (work / "a.txt").write_text("two\n", encoding="utf-8")
    (out / "patch.diff").write_text(_git(work, "diff", "--binary"), encoding="utf-8")
    _git(work, "reset", "-q", "--hard")

    fake = FakeGH({("POST", "pulls"): {"number": 99, "html_url": "u"}})
    msgs: list[str] = []
    ctx = make_ctx(tmp_path, fake, "workflow_dispatch", {}, msgs, workdir=work)
    rc = main(["publish", "--out", str(out), "--mode", "implement", "--issue", "12"], ctx=ctx)
    assert rc == 0
    assert _remote_has_branch(work)
    pr_calls = [b for m, p, b in fake.calls if (m, p) == ("POST", "pulls")]
    assert pr_calls and pr_calls[0]["draft"] is False and "Closes #12" in pr_calls[0]["body"]
    assert ("POST", "issues/99/labels", {"labels": ["agent"]}) in fake.calls
    assert any("Bạn chưa cần" in m and "Chưa có bản Dev" in m for m in msgs)
    assert all("Cách test tay" not in m and "bước 1" not in m for m in msgs)
    assert "bước 1" in pr_calls[0]["body"]  # keep technical instructions in PR


def test_publish_refuses_patch_touching_env(tmp_path: Path) -> None:
    work, out, _ = _setup_repo(tmp_path)
    tmp_env = work / ".env"  # chỉ trong repo tạm dưới tmp_path
    tmp_env.write_text("SECRET=fake\n", encoding="utf-8")
    _git(work, "add", "-N", ".env")
    (out / "patch.diff").write_text(_git(work, "diff", "--binary"), encoding="utf-8")
    _git(work, "reset", "-q", "--hard")
    tmp_env.unlink(missing_ok=True)

    fake, msgs = FakeGH({("POST", "pulls"): {"number": 99, "html_url": "u"}}), []
    ctx = make_ctx(tmp_path, fake, "workflow_dispatch", {}, msgs, workdir=work)
    rc = main(["publish", "--out", str(out), "--mode", "implement", "--issue", "12"], ctx=ctx)
    assert rc == 1
    assert not any((m, p) == ("POST", "pulls") for m, p, _ in fake.calls)
    assert not _remote_has_branch(work)
    assert ("POST", "issues/12/labels", {"labels": ["agent:blocked"]}) in fake.calls
    assert any("⛔" in m for m in msgs)


def test_publish_blocked_status_does_not_push(tmp_path: Path) -> None:
    work, out, _ = _setup_repo(tmp_path)
    (out / "status").write_text("blocked", encoding="utf-8")
    (out / "questions.md").write_text("Dùng bảng nào?", encoding="utf-8")
    fake, msgs = FakeGH(), []
    ctx = make_ctx(tmp_path, fake, "workflow_dispatch", {}, msgs, workdir=work)
    rc = main(["publish", "--out", str(out), "--mode", "implement", "--issue", "12"], ctx=ctx)
    assert rc == 0
    assert not _remote_has_branch(work)
    assert ("POST", "issues/12/labels", {"labels": ["agent:blocked"]}) in fake.calls


def _make_patch(work: Path, out: Path) -> None:
    (work / "a.txt").write_text("two\n", encoding="utf-8")
    (out / "patch.diff").write_text(_git(work, "diff", "--binary"), encoding="utf-8")
    _git(work, "reset", "-q", "--hard")


def _publish(tmp_path: Path, work: Path, out: Path) -> tuple[int, FakeGH, list[str]]:
    fake = FakeGH({("POST", "pulls"): {"number": 99, "html_url": "u"}})
    msgs: list[str] = []
    ctx = make_ctx(tmp_path, fake, "workflow_dispatch", {}, msgs, workdir=work)
    rc = main(["publish", "--out", str(out), "--mode", "implement", "--issue", "12"], ctx=ctx)
    return rc, fake, msgs


def _pr_opened(fake: FakeGH) -> bool:
    return any((m, p) == ("POST", "pulls") for m, p, _ in fake.calls)


def test_publish_missing_status_does_not_push(tmp_path: Path) -> None:
    work, out, _ = _setup_repo(tmp_path)
    _make_patch(work, out)
    (out / "status").unlink()
    rc, fake, _ = _publish(tmp_path, work, out)
    assert rc == 0
    assert not _remote_has_branch(work) and not _pr_opened(fake)
    assert ("POST", "issues/12/labels", {"labels": ["agent:blocked"]}) in fake.calls


def _rewrite_meta(out: Path, **changes: Any) -> None:
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    meta.update(changes)
    (out / "meta.json").write_text(json.dumps(meta), encoding="utf-8")


def test_publish_rejects_untrusted_branch(tmp_path: Path) -> None:
    for branch in ("main", "agent/issue-13-x"):
        sub = tmp_path / branch.replace("/", "_")
        sub.mkdir()
        work, out, _ = _setup_repo(sub)
        _make_patch(work, out)
        _rewrite_meta(out, branch=branch)
        remote_before = _git(work, "ls-remote", "origin")
        rc, fake, _ = _publish(sub, work, out)
        assert rc == 1, branch
        assert not _pr_opened(fake)
        assert _git(work, "ls-remote", "origin") == remote_before


def test_publish_rejects_meta_for_other_issue(tmp_path: Path) -> None:
    work, out, _ = _setup_repo(tmp_path)
    _make_patch(work, out)
    _rewrite_meta(out, issue=13)
    rc, fake, _ = _publish(tmp_path, work, out)
    assert rc == 1
    assert not _remote_has_branch(work) and not _pr_opened(fake)


def test_publish_rejects_base_sha_not_on_remote(tmp_path: Path) -> None:
    work, out, _ = _setup_repo(tmp_path)
    (work / "b.txt").write_text("local\n", encoding="utf-8")
    _git(work, "add", "b.txt")
    _git(work, "commit", "-q", "-m", "local only")
    _rewrite_meta(out, base_sha=_git(work, "rev-parse", "HEAD").strip())
    _make_patch(work, out)
    rc, fake, _ = _publish(tmp_path, work, out)
    assert rc == 1
    assert not _remote_has_branch(work) and not _pr_opened(fake)


# --------------------------------------------------------------------------- run-gates


def test_gate_that_changes_tree_fails_and_is_not_exported(tmp_path: Path) -> None:
    work, _, _ = _setup_repo(tmp_path)
    fake, msgs = FakeGH(), []
    ctx = make_ctx(tmp_path, fake, "workflow_dispatch", {}, msgs, workdir=work)
    ctx.cfg = dataclasses.replace(LoopConfig(), gates={"evil": "echo x > new.txt"})
    assert main(["run-gates", "--out", ".agent-out"], ctx=ctx) == 0
    out = work / ".agent-out"
    assert (out / "gates_result").read_text(encoding="utf-8") == "fail"
    assert "(working tree)" in (out / "gates.md").read_text(encoding="utf-8")
    assert "new.txt" not in _git(work, "diff", "--cached", "--name-only", "HEAD")


# --------------------------------------------------------------------------- sandbox-pytest


def test_sandbox_pytest_fails_closed_without_sudo(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    sudo = fake_bin / "sudo"
    sudo.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    sudo.chmod(0o755)
    proc = subprocess.run(
        ["bash", str(REPO_ROOT / "scripts/agent_loop/sandbox_pytest.sh"), "-q"],
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}"},
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 2
    assert "sandbox" in proc.stderr
