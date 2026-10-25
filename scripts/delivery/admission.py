"""Trusted controller intake. GitHub GET evidence, never model claims, admits tasks.

No listener, dispatcher, credential provisioning or worker is started by this module.
"""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
from decimal import Decimal
import json
import math
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .controller import Denied, digest, micros
from .validate import ROOT, validate

MAX_BYTES = 256 * 1024
REPO = re.compile(r"[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+")


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise Denied("Duplicate JSON key")
        result[key] = value
    return result


def _nonfinite(_):
    raise Denied("Non-finite JSON")


def _finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise Denied("Non-finite JSON")
    return number


def decode(raw):
    if len(raw) > MAX_BYTES:
        raise Denied("JSON exceeds intake limit")
    try:
        return json.loads(
            raw,
            object_pairs_hook=_pairs,
            parse_constant=_nonfinite,
            parse_float=_finite_float,
        )
    except (ValueError, UnicodeError):
        raise Denied("Invalid JSON") from None


def load(path):
    with Path(path).open("rb") as source:
        return decode(source.read(MAX_BYTES + 1))


def approval_digest(task):
    # Bind scope_id too. Only GitHub-generated comment metadata is excluded to
    # avoid a circular digest before the operator has posted the approval.
    content = copy.deepcopy(task)
    content["approval"] = {"scope_id": task["approval"]["scope_id"]}
    return digest(content)


def approval_line(task):
    return "fleet-approve-v1 sha256:" + approval_digest(task)


def timestamp(value):
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            raise ValueError()
        return dt.timestamp()
    except (AttributeError, ValueError):
        raise Denied("Invalid approval timestamp") from None


def policy_check(policy):
    required = {
        "schema_version",
        "enabled",
        "repository",
        "repository_id",
        "approver_ids",
        "engines",
        "policy_id",
        "daily_budget_usd",
        "max_task_cost_usd",
        "approval_max_age_seconds",
    }
    if not isinstance(policy, dict) or set(policy) != required:
        raise Denied("Invalid admission policy fields")
    if policy["schema_version"] != 1 or type(policy["enabled"]) is not bool:
        raise Denied("Invalid admission policy version/flag")
    if not isinstance(policy["repository"], str) or not REPO.fullmatch(
        policy["repository"]
    ):
        raise Denied("Invalid policy repository")
    ids = policy["approver_ids"]
    if (
        type(policy["repository_id"]) is not int
        or policy["repository_id"] <= 0
        or not isinstance(ids, list)
        or not ids
        or any(type(x) is not int or x <= 0 for x in ids)
        or len(set(ids)) != len(ids)
    ):
        raise Denied("Positive immutable repository/approver IDs required")
    if (
        not isinstance(policy["engines"], list)
        or not policy["engines"]
        or any(x not in ("claude", "codex") for x in policy["engines"])
    ):
        raise Denied("Invalid engine policy")
    if (
        not isinstance(policy["policy_id"], str)
        or not policy["policy_id"]
        or type(policy["approval_max_age_seconds"]) is not int
        or not 1 <= policy["approval_max_age_seconds"] <= 86400
    ):
        raise Denied("Invalid policy identity/approval lifetime")
    for field in ("daily_budget_usd", "max_task_cost_usd"):
        try:
            value = Decimal(str(policy[field]))
            if not value.is_finite() or value < 0 or (policy["enabled"] and value <= 0):
                raise ValueError()
        except (ValueError, ArithmeticError):
            raise Denied("Explicit finite budget required before activation") from None
    if Decimal(str(policy["max_task_cost_usd"])) > Decimal(
        str(policy["daily_budget_usd"])
    ):
        raise Denied("Task cap exceeds daily policy")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise Denied("GitHub redirect refused; reverify repository identity")


class GitHubReadClient:
    """Fixed HTTPS origin, GET-only, no ambient proxies or redirect credential leak."""

    def __init__(self, token=None):
        self.token = token
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def get(self, path):
        route = r"/repos/[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+(?:/issues/(?:comments/)?[1-9][0-9]*|/compare/[0-9a-f]{40}\.\.\.main|/collaborators/[A-Za-z0-9_-]+/permission)?"
        if not re.fullmatch(route, path):
            raise Denied("Invalid GitHub API path")
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "fleet-admission-v1",
        }
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        request = Request(
            "https://api.github.com" + path, headers=headers, method="GET"
        )
        try:
            with self.opener.open(request, timeout=10) as response:
                return decode(response.read(MAX_BYTES + 1))
        except HTTPError as error:
            raise Denied(f"GitHub evidence unavailable (HTTP {error.code})") from None
        except (URLError, OSError, TimeoutError):
            raise Denied("GitHub evidence unavailable") from None


class Admission:
    def __init__(self, policy, config, github, *, clock=time.time):
        policy_check(policy)
        if policy["repository"] != config["repository"]:
            raise Denied("Trusted policy/config repository mismatch")
        self.policy = copy.deepcopy(policy)
        self.config = copy.deepcopy(config)
        self.github = github
        self.clock = clock

    def prepare(self, task):
        validate("task", task, self.config)
        if (
            not REPO.fullmatch(task["repository"])
            or task["engine"] not in self.policy["engines"]
        ):
            raise Denied("Repository/engine outside policy")
        if len(task["dependencies"]) > 20:
            raise Denied("At most 20 explicit dependencies")
        branch = task["branch"]
        if not re.fullmatch(
            rf"agent/issue-{task['issue_number']}-[A-Za-z0-9_-]+", branch
        ):
            raise Denied("One canonical agent issue branch required")
        if task["limits"]["daily_budget_reference"] != self.policy["policy_id"]:
            raise Denied("Task must reference the trusted daily budget policy")
        # All content below is data. No setup/test commands are executed.
        return {
            "approval_digest": approval_digest(task),
            "approval_line": approval_line(task),
            "content": {k: v for k, v in task.items() if k != "approval"},
            "scope_id": task["approval"]["scope_id"],
            "policy_enabled": self.policy["enabled"],
            "admitted": False,
        }

    def verify(self, task):
        self.prepare(task)
        prefix = "/repos/" + task["repository"]
        web_issue = (
            f"https://github.com/{task['repository']}/issues/{task['issue_number']}"
        )
        api_issue = f"https://api.github.com{prefix}/issues/{task['issue_number']}"
        match = re.fullmatch(
            re.escape(web_issue) + r"#issuecomment-([1-9][0-9]*)",
            task["approval"]["reference"],
        )
        if not match:
            raise Denied("Approval must reference a canonical comment on this issue")
        repo = self.github.get(prefix)
        if (
            repo.get("id") != self.policy["repository_id"]
            or repo.get("full_name") != task["repository"]
            or repo.get("archived")
            or repo.get("disabled")
            or repo.get("default_branch") != "main"
        ):
            raise Denied("Repository identity/state changed")
        issue = self.github.get(prefix + f"/issues/{task['issue_number']}")
        if (
            issue.get("number") != task["issue_number"]
            or issue.get("html_url") != web_issue
            or issue.get("state") != "open"
            or "pull_request" in issue
            or issue.get("locked")
        ):
            raise Denied("Task issue must remain open and unlocked")
        comparison = self.github.get(prefix + f"/compare/{task['base_sha']}...main")
        if comparison.get("merge_base_commit", {}).get("sha") != task[
            "base_sha"
        ] or comparison.get("status") not in ("ahead", "identical"):
            raise Denied("Task base must be an ancestor of trusted main")
        for url in task["dependencies"]:
            dep = re.fullmatch(
                re.escape(f"https://github.com/{task['repository']}/issues/")
                + r"([1-9][0-9]*)",
                url,
            )
            if not dep or int(dep[1]) == task["issue_number"]:
                raise Denied(
                    "Only explicit other issues in this repository are supported dependencies"
                )
            data = self.github.get(prefix + "/issues/" + dep[1])
            if (
                data.get("html_url") != url
                or "pull_request" in data
                or data.get("state") != "closed"
                or data.get("state_reason") != "completed"
            ):
                raise Denied("Dependency is not completed")
        comment = self.github.get(prefix + "/issues/comments/" + match[1])
        user = comment.get("user") or {}
        if (
            comment.get("id") != int(match[1])
            or comment.get("html_url") != task["approval"]["reference"]
            or comment.get("issue_url") != api_issue
        ):
            raise Denied("Approval comment identity mismatch")
        if (
            type(user.get("id")) is not int
            or user["id"] not in self.policy["approver_ids"]
            or user.get("type") != "User"
            or user.get("login") != task["approval"]["actor"]
        ):
            raise Denied("Approval author is not an allowed GitHub account")
        login = user["login"]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", login):
            raise Denied("Invalid GitHub login")
        permission = self.github.get(prefix + "/collaborators/" + login + "/permission")
        if permission.get("user", {}).get("id") != user["id"] or permission.get(
            "permission"
        ) not in ("write", "maintain", "admin"):
            raise Denied("Approver no longer has write/maintain/admin permission")
        if comment.get("body", "").strip() != approval_line(task):
            raise Denied("Approval does not match task content")
        if comment.get("created_at") != comment.get("updated_at") or timestamp(
            comment.get("created_at")
        ) != timestamp(task["approval"]["approved_at"]):
            raise Denied("Approval was edited or timestamp differs")
        age = self.clock() - timestamp(comment["created_at"])
        if not 0 <= age <= self.policy["approval_max_age_seconds"]:
            raise Denied("Approval expired or is future-dated")
        if micros(task["limits"]["max_cost_usd"]) > micros(
            self.policy["max_task_cost_usd"]
        ):
            raise Denied("Task exceeds approved spending policy")
        return {
            "source": "github_issue_comment_v1",
            "task_digest": digest(task),
            "approval_digest": approval_digest(task),
            "policy_digest": digest(self.policy),
            "repository_id": repo["id"],
            "actor": "github:" + str(user["id"]),
            "author_id": user["id"],
            "comment_id": comment["id"],
            "reference": comment["html_url"],
            "approved_at": comment["created_at"],
            "checked_at": datetime.fromtimestamp(
                self.clock(), timezone.utc
            ).isoformat(),
        }

    def admit(self, task, ledger):
        if not self.policy["enabled"]:
            raise Denied("Admission disabled; no product coding budget approved")
        if (
            ledger.daily != micros(self.policy["daily_budget_usd"])
            or ledger.approvers
            != frozenset("github:" + str(x) for x in self.policy["approver_ids"])
            or str(ledger.budget_timezone) != "Asia/Ho_Chi_Minh"
        ):
            raise Denied("Ledger differs from trusted admission policy")
        evidence = self.verify(task)
        ledger.approve(
            task,
            actor=evidence["actor"],
            verified_reference=evidence["reference"],
            evidence=evidence,
        )
        return evidence

    def execute(self, task, ledger, **kwargs):
        from .loop import execute

        self.admit(task, ledger)
        return execute(
            task,
            self.config,
            ledger,
            before_attempt=lambda: self.admit(task, ledger),
            before_accept=lambda: self.admit(task, ledger),
            **kwargs,
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "verify"))
    parser.add_argument("task", type=Path)
    parser.add_argument(
        "--policy", type=Path, default=ROOT / ".github/fleet-admission.json"
    )
    parser.add_argument("--config", type=Path, default=ROOT / ".github/delivery.json")
    args = parser.parse_args()
    try:
        intake = Admission(
            load(args.policy),
            load(args.config),
            GitHubReadClient(os.environ.get("FLEET_GITHUB_READ_TOKEN")),
        )
        result = getattr(intake, args.action)(load(args.task))
        print(
            json.dumps(
                {"action": args.action, "admitted": False, "result": result}, indent=2
            )
        )
    except Exception as error:
        # JSON schema messages may contain user-supplied text/secrets; don't echo them.
        reason = str(error) if isinstance(error, Denied) else "Invalid intake input"
        print(json.dumps({"admitted": False, "error": reason}))
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
