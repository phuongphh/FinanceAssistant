"""Bounded local loop invoked from an authorized operator/PM session.

No public endpoint, queue-label admission, merge, deployment or outbound messages.
Task text/digests are not proof of human authorization: the invoking trusted session
must already have it. Models retain the proposal-only/no-execution profile.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from decimal import Decimal
import fcntl
import json
from pathlib import Path
import re
import time

from .controller import Denied, digest, micros
from .local_runner import LocalRunner, LIMIT, CHECKS, call
from .loop import atomic_json


def owner_report(state, status, reason=None):
    """Machine-readable PO handoff; never infer a deployed version from CI."""
    task = state["spec"]["task"]
    messages = {
        "review_ready": (
            "Đã qua kiểm thử tự động; chờ kiểm tra kỹ thuật trước khi chuẩn bị bản Dev.",
            "PM kiểm tra kết quả và điều phối bước chuẩn bị Dev.",
            "Chưa cần thử trên Telegram; chưa có bản Dev được xác nhận.",
        ),
        "running": (
            "Đang thực hiện và kiểm thử thay đổi.",
            "Hệ thống tiếp tục trong giới hạn đã duyệt.",
            "Chưa cần thao tác.",
        ),
        "waiting_ci": (
            "Đang chờ kiểm thử tự động.",
            "Hệ thống kiểm tra kết quả trên GitHub.",
            "Chưa cần thao tác.",
        ),
        "stopped": (
            "Đã dừng tại ranh giới bước; giữ lại công việc.",
            "PM xác nhận bước tiếp theo.",
            "Chỉ quyết định tiếp tục khi được PM nêu rõ phạm vi.",
        ),
        "blocked": (
            "Chưa hoàn tất trong phạm vi hoặc giới hạn hiện tại.",
            "PM và Ốp Dev kiểm tra nguyên nhân; không tự tăng ngân sách.",
            "Chưa cần thao tác kỹ thuật; PM sẽ nêu quyết định sản phẩm nếu cần.",
        ),
    }
    summary, next_action, po_action = messages[status]
    return {
        "repository": task["repository"],
        "issue_number": task["issue_number"],
        "engine": task["engine"],
        "status": status,
        "summary": summary,
        "next_action": next_action,
        "po_action": po_action,
        "pr_url": state.get("pr_url"),
        "tested_sha": state.get("head_sha") if status == "review_ready" else None,
        "deployment": "not_verified",
        "technical_reason": reason,
    }


def scrub(text):
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    text = re.sub(
        r"(?i)((?:token|password|secret|api[_-]?key)\s*[:=]\s*)\S+",
        r"\1[REDACTED]",
        text,
    )
    text = re.sub(
        r"(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]+)",
        "[REDACTED]",
        text,
    )
    return text.encode()[-24000:].decode(errors="ignore")


def ci_feedback(runner, state):
    """Only logs from failed required jobs on the current PR/head; untrusted text."""
    task = state["spec"]["task"]
    repo = task["repository"]
    prs = runner.github(
        repo,
        "pulls?state=open&head="
        + repo.split("/")[0]
        + ":"
        + task["branch"]
        + "&base=main&per_page=100",
    )
    if len(prs) != 1 or prs[0]["head"]["sha"] != state["head_sha"]:
        raise Denied("PR changed before feedback collection")
    pr = prs[0]
    runs = runner.github(
        repo,
        "actions/runs?event=pull_request&head_sha="
        + state["head_sha"]
        + "&per_page=100",
    )["workflow_runs"]
    feedback = []
    for path, name in CHECKS.items():
        matching = [
            r
            for r in runs
            if r.get("path") == path
            and r.get("head_sha") == state["head_sha"]
            and r.get("head_branch") == task["branch"]
            and r.get("event") == "pull_request"
            and any(p.get("number") == pr["number"] for p in r.get("pull_requests", []))
        ]
        if not matching:
            raise Denied("Required CI evidence disappeared")
        run = max(matching, key=lambda r: r["id"])
        if run["status"] != "completed":
            raise Denied("CI changed while collecting feedback")
        if run["conclusion"] == "success":
            continue
        jobs = runner.github(
            repo, f"actions/runs/{run['id']}/jobs?filter=latest&per_page=100"
        )["jobs"]
        selected = [
            j
            for j in jobs
            if j.get("name") == name and j.get("head_sha") == state["head_sha"]
        ]
        if len(selected) != 1 or selected[0].get("conclusion") != "failure":
            raise Denied("Cancelled/skipped/unknown CI requires infrastructure review")
        job_id = selected[0]["id"]
        if not isinstance(job_id, int):
            raise Denied("Invalid GitHub job id")
        log = call(
            [
                "gh",
                "run",
                "view",
                str(run["id"]),
                "--repo",
                repo,
                "--job",
                str(job_id),
                "--log-failed",
            ],
            network=True,
        )
        feedback.append(path + "\n" + scrub(log))
    if not feedback:
        raise Denied("No verified failed job feedback")
    return scrub("\n\n".join(feedback))


class LocalLoop:
    def __init__(
        self, runner, *, clock=time.time, sleep=time.sleep, feedback=ci_feedback
    ):
        self.runner, self.clock, self.sleep, self.feedback = (
            runner,
            clock,
            sleep,
            feedback,
        )

    @contextmanager
    def lock(self):
        with (self.runner.root / "loop.lock").open("a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise Denied("Another local loop owns execution") from None
            yield

    def report(self, run_id, status, reason=None):
        state = self.runner.state(run_id)
        report = owner_report(state, status, reason)
        atomic_json(self.runner.root / run_id / "po-report.json", report)
        return report

    def ownership(self, state):
        task = state["spec"]["task"]
        issue = self.runner.github(
            task["repository"], "issues/" + str(task["issue_number"])
        )
        names = {x["name"] for x in issue.get("labels", [])}
        if issue.get("state") != "open" or names & {"agent:ready", "agent:wip"}:
            raise Denied(
                "Issue is closed or assigned to the cloud loop; no duplicate execution"
            )

    def run(
        self,
        spec,
        repo,
        approved_digest,
        *,
        wall_minutes=45,
        poll_seconds=30,
        claude_per_attempt=None,
    ):
        if digest(spec) != approved_digest:
            raise Denied("Approved request digest does not match")
        if not 1 <= wall_minutes <= 120 or not 5 <= poll_seconds <= 60:
            raise Denied("Wall limit must be 1-120 minutes; poll interval 5-60 seconds")
        task = spec["task"]
        if task["engine"] == "claude":
            if claude_per_attempt is None:
                raise Denied("Explicit Claude per-attempt budget required")
            amount = micros(claude_per_attempt)
            if amount <= 0 or amount * (task["limits"]["max_fix_rounds"] + 1) > micros(
                task["limits"]["max_cost_usd"]
            ):
                raise Denied(
                    "All allowed Claude attempts must fit the approved task budget"
                )
        elif claude_per_attempt is not None:
            raise Denied("Claude budget supplied for a different engine")
        options = {
            "wall_minutes": wall_minutes,
            "poll_seconds": poll_seconds,
            "claude_per_attempt": str(Decimal(str(claude_per_attempt)))
            if claude_per_attempt is not None
            else None,
        }
        run_id = digest(spec)[:20]
        with self.lock():
            directory = self.runner.root / run_id
            if directory.exists():
                state = self.runner.state(run_id)
                if (
                    state["request_digest"] != approved_digest
                    or Path(state["repo"]).resolve() != Path(repo).resolve()
                ):
                    raise Denied("Existing run does not match this request/repository")
            else:
                self.runner.begin(spec, repo, approved_digest)
            checkpoint = directory / "loop.json"
            if checkpoint.exists():
                saved = json.loads(checkpoint.read_text())
                if saved["options"] != options:
                    raise Denied("Cannot change limits on resume")
            else:
                saved = {
                    "deadline": self.clock() + wall_minutes * 60,
                    "options": options,
                }
                atomic_json(checkpoint, saved)
            try:
                while True:
                    state = self.runner.state(run_id)
                    phase = state["phase"]
                    if phase == "review_ready" and state.get("slot_released"):
                        return self.report(run_id, "review_ready")
                    if self.clock() >= saved["deadline"]:
                        return self.report(run_id, "blocked", "wall_clock_limit")
                    if (directory / "stop.request").exists():
                        return self.report(run_id, "stopped", "stop_requested")
                    if phase in ("preparing", "model_running", "blocked"):
                        return self.report(
                            run_id, "blocked", "needs_reconciliation_" + phase
                        )
                    self.ownership(state)
                    if phase in ("prepared", "ci_failed"):
                        if state["attempts"] >= task["limits"]["max_fix_rounds"] + 1:
                            return self.report(run_id, "blocked", "attempt_limit")
                        feedback = (
                            self.feedback(self.runner, state)
                            if phase == "ci_failed"
                            else ""
                        )
                        # Stop/deadline rechecked after fetching feedback, before model spend.
                        if (
                            self.clock() >= saved["deadline"]
                            or (directory / "stop.request").exists()
                        ):
                            continue
                        self.report(run_id, "running")
                        self.runner.propose(
                            run_id,
                            claude_reservation=claude_per_attempt,
                            feedback=feedback,
                            max_seconds=max(0, saved["deadline"] - self.clock()),
                        )
                    elif phase == "proposal_ready":
                        self.runner.commit(run_id)
                    elif phase == "committed":
                        self.runner.publish(run_id)
                    elif phase in ("awaiting_ci", "review_ready"):
                        self.report(run_id, "waiting_ci")
                        checked = self.runner.check(run_id)
                        if checked["phase"] == "review_ready":
                            self.runner.close(run_id)
                            return self.report(run_id, "review_ready")
                        if checked["phase"] == "awaiting_ci":
                            self.sleep(
                                min(
                                    poll_seconds,
                                    max(0, saved["deadline"] - self.clock()),
                                )
                            )
                    else:
                        return self.report(run_id, "blocked", "unknown_phase")
            except Exception as error:
                # Never include native output / tokens in a PO receipt. Keep task fenced.
                reason = (
                    str(error)
                    if isinstance(error, Denied)
                    else "operation_failed_inspect_private_state"
                )
                return self.report(run_id, "blocked", reason)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    run = sub.add_parser("run")
    run.add_argument("request", type=Path)
    run.add_argument("--repo", type=Path, required=True)
    run.add_argument("--approved-digest", required=True)
    run.add_argument("--wall-minutes", type=int, default=45)
    run.add_argument("--poll-seconds", type=int, default=30)
    run.add_argument("--claude-per-attempt")
    for name in ("status", "stop"):
        p = sub.add_parser(name)
        p.add_argument("run_id")
    args = parser.parse_args()
    runner = LocalRunner(args.state)
    try:
        if args.action == "run":
            raw = args.request.read_bytes()
            if len(raw) > LIMIT:
                raise Denied("Request too large")
            result = LocalLoop(runner).run(
                json.loads(raw),
                args.repo,
                args.approved_digest,
                wall_minutes=args.wall_minutes,
                poll_seconds=args.poll_seconds,
                claude_per_attempt=args.claude_per_attempt,
            )
        else:
            state = runner.state(
                args.run_id
            )  # validates run ID; no arbitrary path writes
            directory = runner.root / args.run_id
            if args.action == "stop":
                atomic_json(directory / "stop.request", {"requested_at": time.time()})
                result = {
                    "status": "stop_requested",
                    "note": "Stops before the next step; current model call keeps its bounded timeout.",
                }
            else:
                path = directory / "po-report.json"
                result = (
                    json.loads(path.read_text())
                    if path.exists()
                    else owner_report(state, "running")
                )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result.get("status") == "blocked":
            raise SystemExit(2)
    except Denied as error:
        print(
            json.dumps({"status": "blocked", "reason": str(error)}, ensure_ascii=False)
        )
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
