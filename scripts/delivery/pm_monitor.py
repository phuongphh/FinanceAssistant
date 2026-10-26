"""Read-only GitHub delivery observer with durable PM Telegram notifications.

No model calls, queue mutations, coding dispatch, merge or deploy. Invoked by the
native OpenClaw command scheduler. Delivery is confirmed before dedup is saved.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import time

from .controller import Denied
from .local_runner import api, call
from .loop import atomic_json

BRANCH = re.compile(
    r"^(?:agent/issue-[1-9][0-9]*-|(?:claude|codex)/local-issue-[1-9][0-9]*-)"
)


def pages(github, repo, suffix, key=None):
    found = []
    for page in range(1, 21):
        value = github(
            repo,
            suffix + ("&" if "?" in suffix else "?") + "per_page=100&page=" + str(page),
        )
        rows = value[key] if key else value
        found.extend(rows)
        if len(rows) < 100:
            return found
    raise Denied("Too many GitHub pages; narrow the monitoring profile")


def config_value(path):
    c = json.loads(Path(path).read_text())
    d = c["destination"]
    if (
        c["schema_version"] != 1
        or d.get("channel") != "telegram"
        or d.get("account") != "pm"
        or not re.fullmatch(r"[0-9]+", d.get("target", ""))
    ):
        raise Denied("Invalid monitor destination")
    if not c["repositories"]:
        raise Denied("No monitored repositories")
    for r in c["repositories"]:
        if not re.fullmatch(r"[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+", r["name"]):
            raise Denied("Invalid repository")
        datetime.fromisoformat(r["discover_after"].replace("Z", "+00:00"))
        if not r["required_workflows"]:
            raise Denied("Required CI workflows must be configured")
        for p, n in r["required_workflows"].items():
            if (
                not re.fullmatch(r"\.github/workflows/[A-Za-z0-9_-]+\.ya?ml", p)
                or not isinstance(n, str)
                or not n
            ):
                raise Denied("Invalid required workflow/job")
        if any(
            not isinstance(n, int) or isinstance(n, bool) or n <= 0
            for n in r.get("watch_prs", []) + r.get("watch_issues", [])
        ):
            raise Denied("Invalid watched number")
    return c


def classify(pr, runs, jobs, reviews, required):
    if pr.get("state") == "closed":
        return "merged" if pr.get("merged") else "closed"
    if pr.get("state") != "open":
        return "pending"
    sha, branch = pr["head"]["sha"], pr["head"]["ref"]
    pending, failed = False, False
    for path, name in required.items():
        candidates = [
            r
            for r in runs
            if r.get("path") == path
            and r.get("head_sha") == sha
            and r.get("event") == "pull_request"
            and r.get("head_branch") == branch
            and any(p.get("number") == pr["number"] for p in r.get("pull_requests", []))
        ]
        if not candidates:
            pending = True
            continue
        latest = max(candidates, key=lambda r: r["id"])
        if latest.get("status") != "completed":
            pending = True
            continue
        selected = [
            j
            for j in jobs.get(latest["id"], [])
            if j.get("name") == name and j.get("head_sha") == sha
        ]
        if (
            latest.get("conclusion") != "success"
            or len(selected) != 1
            or selected[0].get("conclusion") != "success"
        ):
            failed = True
    if failed:
        return "checks_failed"
    if pr.get("mergeable") is False or pr.get("mergeable_state") in ("dirty", "behind"):
        return "needs_revision"
    latest_reviews = {}
    for review in sorted(reviews, key=lambda r: r.get("id", 0)):
        if review.get("state") in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
            latest_reviews[review.get("user", {}).get("login", "")] = review.get(
                "state"
            )
    if "CHANGES_REQUESTED" in latest_reviews.values():
        return "needs_revision"
    if (
        pending
        or pr.get("draft")
        or pr.get("mergeable") is not True
        or pr.get("mergeable_state") in ("blocked", "unknown", "unstable")
    ):
        return "pending"
    return "ready"


def message(repo, pr, phase):
    title = " ".join(pr.get("title", "").split())[:150]
    title = re.sub(r"^\[agent\]\s*#[0-9]+\s*", "", title)
    texts = {
        "ready": (
            "Đã qua kiểm thử và review tự động; đang chờ bạn duyệt merge.",
            "Bạn cần: duyệt và merge nếu đúng yêu cầu để chuẩn bị bản Dev. Chưa cần thử trên bot đang chạy.",
        ),
        "merged": (
            "Đã merge vào bản tích hợp; chưa xác nhận triển khai Dev.",
            "Tiếp theo: PM phối hợp Ốp Dev chuẩn bị bản Dev để nghiệm thu. Bạn chưa cần thao tác.",
        ),
        "closed": (
            "PR đã đóng mà chưa merge.",
            "Tiếp theo: PM kiểm tra hướng xử lý; bạn chưa cần thao tác kỹ thuật.",
        ),
        "checks_failed": (
            "Kiểm thử tự động chưa đạt; chưa sẵn sàng merge.",
            "Tiếp theo: PM theo dõi coding agent xử lý lỗi. Bạn chưa cần thao tác.",
        ),
        "needs_revision": (
            "Cần xử lý yêu cầu sửa hoặc xung đột trước khi merge.",
            "Tiếp theo: PM phối hợp coding agent xử lý. Bạn chưa cần thao tác.",
        ),
    }
    status, action = texts[phase]
    return f"[{repo.split('/')[-1]}] PR #{pr['number']}: {title}\n{status}\n{action}\n{pr['html_url']}"


def telegram(destination, text):
    raw = call(
        [
            "openclaw",
            "message",
            "send",
            "--channel",
            "telegram",
            "--account",
            destination["account"],
            "--target",
            destination["target"],
            "--message",
            text,
            "--json",
        ],
        network=True,
    )
    value = json.loads(raw)
    # Native message send wraps Telegram result under payload or result.
    candidates = [value]
    for key in ("payload", "result"):
        if isinstance(value.get(key), dict):
            candidates.append(value[key])
    for item in candidates:
        if item.get("messageId") is not None:
            return str(item["messageId"])
    raise Denied("Telegram acknowledgement missing; notification not marked delivered")


class Monitor:
    def __init__(self, root, config, *, github=api, send=telegram, clock=time.time):
        self.root = Path(root).absolute()
        if self.root.is_symlink():
            raise Denied("Invalid monitor state")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.stat().st_mode & 0o077 or self.root.stat().st_uid != os.getuid():
            raise Denied("Private owner-only state required")
        self.config, self.github, self.send, self.clock = config, github, send, clock
        self.path = self.root / "state.json"
        self.state = (
            json.loads(self.path.read_text())
            if self.path.exists()
            else {"prs": {}, "issues": {}, "consecutive_errors": 0}
        )

    def save(self):
        atomic_json(self.path, self.state)

    def notify(self, key, item, phase, text, *, issue=False, dry_run=False):
        table = self.state["issues" if issue else "prs"]
        record = table.setdefault(key, {})
        fingerprint = {"phase": phase, "head": item.get("head", {}).get("sha")}
        record["observed"] = fingerprint
        if record.get("delivered") == fingerprint:
            return 0
        if dry_run:
            self.previews.append(text)
            return 1
        # Persist intent; on delivery failure retain an unsent record for retry.
        record["pending"] = fingerprint
        self.save()
        receipt = self.send(self.config["destination"], text)
        if not receipt:
            raise Denied("Delivery not confirmed")
        record.update(
            delivered=fingerprint, message_id=receipt, delivered_at=self.clock()
        )
        record.pop("pending", None)
        self.save()
        return 1

    def pull_requests(self, profile):
        repo = profile["name"]
        opened = pages(self.github, repo, "pulls?state=open&base=main")
        selected = {
            p["number"]: p
            for p in opened
            if p["number"] in profile.get("watch_prs", [])
            or (
                BRANCH.match(p["head"]["ref"])
                and p.get("created_at", "") >= profile["discover_after"]
            )
        }
        prefix = repo + "#"
        numbers = set(profile.get("watch_prs", [])) | {
            int(k[len(prefix) :])
            for k, v in self.state["prs"].items()
            if k.startswith(prefix)
            and v.get("observed", {}).get("phase") not in ("merged", "closed")
        }
        for number in numbers:
            if number not in selected:
                selected[number] = self.github(repo, "pulls/" + str(number))
        return list(selected.values())

    def tick(self, *, dry_run=False):
        with (self.root / "monitor.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return {"status": "already_running", "notifications": 0}
            self.previews = []
            if self.path.exists():
                self.state = json.loads(self.path.read_text())
            sent = 0
            try:
                for profile in self.config["repositories"]:
                    repo = profile["name"]
                    for pr in self.pull_requests(profile):
                        if (
                            pr.get("base", {}).get("ref") != "main"
                            or pr.get("head", {}).get("repo", {}).get("full_name")
                            != repo
                        ):
                            continue
                        # Full PR data supplies merged/mergeability; list responses do not.
                        pr = self.github(repo, "pulls/" + str(pr["number"]))
                        key = repo + "#" + str(pr["number"])
                        runs = []
                        jobs = {}
                        reviews = []
                        if pr["state"] == "open":
                            runs = pages(
                                self.github,
                                repo,
                                "actions/runs?event=pull_request&head_sha="
                                + pr["head"]["sha"],
                                "workflow_runs",
                            )
                            for path in profile["required_workflows"]:
                                eligible = [
                                    r
                                    for r in runs
                                    if r.get("path") == path
                                    and r.get("head_sha") == pr["head"]["sha"]
                                    and r.get("head_branch") == pr["head"]["ref"]
                                    and r.get("event") == "pull_request"
                                    and any(
                                        p.get("number") == pr["number"]
                                        for p in r.get("pull_requests", [])
                                    )
                                ]
                                if eligible:
                                    latest = max(eligible, key=lambda r: r["id"])
                                    if latest.get("status") == "completed":
                                        jobs[latest["id"]] = pages(
                                            self.github,
                                            repo,
                                            f"actions/runs/{latest['id']}/jobs?filter=latest",
                                            "jobs",
                                        )
                            reviews = pages(
                                self.github, repo, f"pulls/{pr['number']}/reviews"
                            )
                        phase = classify(
                            pr, runs, jobs, reviews, profile["required_workflows"]
                        )
                        if phase != "pending":
                            sent += self.notify(
                                key,
                                pr,
                                phase,
                                message(repo, pr, phase),
                                dry_run=dry_run,
                            )
                        else:
                            self.state["prs"].setdefault(key, {})["last_pending_at"] = (
                                self.clock()
                            )
                    for number in profile.get("watch_issues", []):
                        issue = self.github(repo, "issues/" + str(number))
                        names = {x["name"] for x in issue.get("labels", [])}
                        if issue.get("state") == "open" and "agent:blocked" in names:
                            title = " ".join(issue["title"].split())[:150]
                            text = f"[{repo.split('/')[-1]}] Công việc #{number} đang bị chặn: {title}\nPM cần kiểm tra nguyên nhân và đề xuất bước tiếp theo. Bạn chưa cần thao tác kỹ thuật.\n{issue['html_url']}"
                            sent += self.notify(
                                repo + "#" + str(number),
                                issue,
                                "blocked",
                                text,
                                issue=True,
                                dry_run=dry_run,
                            )
                        else:
                            # Clear the last blocked observation after recovery so recurrence can notify.
                            previous = self.state["issues"].get(
                                repo + "#" + str(number)
                            )
                            if previous:
                                previous["delivered"] = {
                                    "phase": "not_blocked",
                                    "head": None,
                                }
                self.state.update(last_poll_at=self.clock(), consecutive_errors=0)
                if not dry_run:
                    self.save()
                return {
                    "status": "ok",
                    "notifications": sent,
                    "dry_run": dry_run,
                    **({"messages": self.previews} if dry_run else {}),
                }
            except Exception:
                if not dry_run:
                    errors = self.state.get("consecutive_errors", 0) + 1
                    self.state.update(
                        consecutive_errors=errors, last_poll_at=self.clock()
                    )
                    if (
                        errors >= 2
                        and self.clock() - self.state.get("error_alert_at", 0) >= 3600
                    ):
                        try:
                            receipt = self.send(
                                self.config["destination"],
                                "Bé PM chưa cập nhật được tiến độ GitHub trong hai lần kiểm tra liên tiếp. Ốp Dev cần kiểm tra cơ chế theo dõi; bạn chưa cần xử lý kỹ thuật. Các trạng thái đã báo trước đó chưa được xác minh lại.",
                            )
                            if receipt:
                                self.state["error_alert_at"] = self.clock()
                        except Exception:
                            pass
                    self.save()
                raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        result = Monitor(args.state, config_value(args.config)).tick(
            dry_run=args.dry_run
        )
        print(json.dumps(result))
    except Exception:
        print(
            json.dumps(
                {
                    "status": "error",
                    "reason": "Monitor poll/delivery failed; inspect private state and scheduler run; notifications not acknowledged remain pending",
                }
            )
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
