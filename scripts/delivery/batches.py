"""Trusted-session delivery ledger. Never executes application code or deploys.

The PM translates owner chat into commands; text in GitHub issues is not consent.
State shares the monitor's private file and lock. All version/scope approvals are
immutable. Production entries are preparation proposals, never release approvals.
"""

from __future__ import annotations

import hashlib
import json
import re

from .controller import Denied
from .local_runner import call, git

SHA = re.compile(r"[0-9a-f]{40}")
TERMINAL = {"accepted", "superseded"}
CHECKS = ("local_health", "public_health", "webhook", "menu", "services")
RELEASE_CHECKS = (
    "production_baseline",
    "cumulative_scope",
    "migration_data_access",
    "backup_rollback",
    "artifact_platform",
    "executor_ready",
)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def ledger(state):
    return state.setdefault(
        "delivery_v2", {"queue": {}, "batches": {}, "releases": {}, "dev": {}}
    )


def key(repo, number):
    return f"{repo}#{number}"


def enqueue(monitor, profile, pr):
    """Called only after the observer has verified merged application changes."""
    data = ledger(monitor.state)
    item_key = key(profile["name"], pr["number"])
    previous = data["queue"].get(item_key)
    if previous and previous["merge_sha"] != pr["merge_commit_sha"]:
        raise Denied("Queue version changed")
    if previous:
        return "dev_queued" if previous["status"] == "queued" else "dev_decided"
    # Never reinterpret an older explicit decision as a new approval.
    old = monitor.state.get("dev_requests", {}).get(item_key)
    data["queue"][item_key] = {
        "repository": profile["name"],
        "pr_number": pr["number"],
        "merge_sha": pr["merge_commit_sha"],
        "title": pr["title"],
        "url": pr["html_url"],
        "status": "deferred" if old else "queued",
        "created_at": monitor.clock(),
    }
    return "dev_decided" if old else "dev_queued"


class Delivery:
    def __init__(self, monitor):
        self.m = monitor
        self.data = ledger(monitor.state)

    def profile(self, repo):
        found = [
            p
            for p in self.m.config["repositories"]
            if p["name"] == repo and p.get("batch_delivery") is True
        ]
        if len(found) != 1:
            raise Denied("Batch delivery not enabled for repository")
        return found[0]

    def reference(self, value):
        if not isinstance(value, str) or not value.strip() or len(value) > 2000:
            raise Denied(
                "Trusted owner/session or operations evidence reference required"
            )
        return value

    def sha(self, value):
        if not isinstance(value, str) or not SHA.fullmatch(value):
            raise Denied("Full immutable SHA required")
        return value

    def merged(self, repo, number):
        if not isinstance(number, int) or isinstance(number, bool) or number <= 0:
            raise Denied("Invalid PR number")
        pr = self.m.github(repo, f"pulls/{number}")
        if (
            not pr.get("merged")
            or pr.get("state") != "closed"
            or pr.get("base", {}).get("ref") != "main"
            or pr.get("head", {}).get("repo", {}).get("full_name") != repo
        ):
            raise Denied(
                "Only same-repository PRs actually merged into main are eligible"
            )
        self.sha(pr.get("merge_commit_sha"))
        return pr

    def repository(self, profile):
        path = profile["controller_checkout"]
        remote = git(path, "remote", "get-url", "origin")
        name = profile["name"]
        if remote not in (
            f"https://github.com/{name}.git",
            f"https://github.com/{name}",
            f"git@github.com:{name}.git",
        ):
            raise Denied("Controller checkout origin does not match profile")
        git(path, "fetch", "origin", "main", network=True)
        return path

    def scope(self, profile, baseline, prs):
        """Verify the cumulative main history, including nonselected app commits.

        A selected later PR cannot conceal an earlier feature. We intentionally
        require a first-parent main baseline; unusual history needs manual review.
        """
        from .pm_monitor import affects_dev

        checkout = self.repository(profile)
        history = git(
            checkout, "rev-list", "--first-parent", "origin/main"
        ).splitlines()
        positions = {sha: n for n, sha in enumerate(history)}
        if baseline not in positions:
            raise Denied("Dev baseline is not on main first-parent history")
        selected = {p["merge_commit_sha"] for p in prs}
        if any(
            s not in positions or positions[s] >= positions[baseline] for s in selected
        ):
            raise Denied("Selected version already deployed or outside main history")
        candidate = min(selected, key=positions.get)
        commits = history[positions[candidate] : positions[baseline]]
        uncovered = []
        for sha in commits:
            names = git(
                checkout, "diff", "--name-only", "--no-renames", sha + "^1", sha
            ).splitlines()
            if sha not in selected and affects_dev(
                [{"filename": n} for n in names], profile["dev_paths"]
            ):
                uncovered.append(sha)
        if uncovered:
            raise Denied(
                "Candidate contains unselected application commits: "
                + ",".join(uncovered)
            )
        return candidate, commits

    def batch(self, command):
        b = self.data["batches"].get(command.get("batch_id"))
        if not b or b["repository"] != command.get("repository"):
            raise Denied("Unknown delivery batch")
        if command.get("digest") != b["digest"]:
            raise Denied("Batch digest must match approved immutable scope")
        return b

    def active(self, repo):
        return [
            b
            for b in self.data["batches"].values()
            if b["repository"] == repo and b["status"] not in TERMINAL
        ]

    def propose(self, c, profile):
        repo = profile["name"]
        baseline = self.data["dev"].get(repo, {}).get("sha")
        self.sha(baseline)
        selected = c.get("prs")
        if c.get("all") is True:
            if selected:
                raise Denied("Choose explicit PRs or all queued/deferred PRs")
            selected = [
                q["pr_number"]
                for q in self.data["queue"].values()
                if q["repository"] == repo and q["status"] in ("queued", "deferred")
            ]
        if (
            not selected
            or not isinstance(selected, list)
            or len(set(selected)) != len(selected)
        ):
            raise Denied("Nonempty unique PR selection required")
        if self.active(repo):
            raise Denied("Finish or explicitly supersede the active Dev batch first")
        prs = [self.merged(repo, n) for n in selected]
        for p in prs:
            q = self.data["queue"].get(key(repo, p["number"]))
            if not q or q["status"] not in ("queued", "deferred"):
                raise Denied("PR is not queued/deferred")
            if q["merge_sha"] != p["merge_commit_sha"]:
                raise Denied("PR version changed")
        candidate, commits = self.scope(profile, baseline, prs)
        prior = self.data["batches"].get(self.data["dev"][repo].get("batch_id"), {})
        retest = (
            sorted(set(prior.get("prs", [])))
            if prior.get("rejection_reference")
            else []
        )
        manifest = {
            "repository": repo,
            "environment": "dev-macmini",
            "baseline_sha": baseline,
            "candidate_sha": candidate,
            "prs": sorted(set(selected) | set(retest)),
            "selected_prs": sorted(selected),
            "retest_prs": retest,
            "commits": commits,
            "title": self.reference(c.get("title")),
        }
        ident = (
            "dev-" + digest(manifest)[:10] + "-" + str(len(self.data["batches"]) + 1)
        )
        b = {
            **manifest,
            "batch_id": ident,
            "digest": digest(manifest),
            "status": "awaiting_approval",
            "created_at": self.m.clock(),
        }
        self.data["batches"][ident] = b
        for n in selected:
            self.data["queue"][key(repo, n)].update(status="in_batch", batch_id=ident)
        return b

    def candidate_ci(self, b, c):
        from .pm_monitor import pages

        run_id = c.get("run_id")
        if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id <= 0:
            raise Denied("GitHub Actions run ID required")
        repo = b["repository"]
        run = self.m.github(repo, f"actions/runs/{run_id}")
        ref = "delivery/" + b["batch_id"]
        expected_workflow = self.profile(repo)["candidate_workflow"]
        if (
            run.get("path") != expected_workflow
            or run.get("event") != "workflow_dispatch"
            or run.get("head_sha") != b["candidate_sha"]
            or run.get("head_branch") != ref
            or run.get("status") != "completed"
            or run.get("conclusion") != "success"
        ):
            raise Denied("Candidate CI must succeed on the exact batch branch and SHA")
        branch = self.m.github(repo, "git/ref/heads/" + ref)
        if branch.get("object", {}).get("sha") != b["candidate_sha"]:
            raise Denied("Candidate branch moved")
        jobs = pages(
            self.m.github, repo, f"actions/runs/{run_id}/jobs?filter=latest", "jobs"
        )
        required = self.profile(repo)["candidate_job"]
        good = [
            j
            for j in jobs
            if j.get("name") == required
            and j.get("head_sha") == b["candidate_sha"]
            and j.get("conclusion") == "success"
        ]
        if len(good) != 1:
            raise Denied("Exact candidate test job must pass, not skip")
        return {
            "run_id": run_id,
            "sha": b["candidate_sha"],
            "url": run["html_url"],
            "verified_at": self.m.clock(),
        }

    def apply(self, c):
        repo, action = c.get("repository"), c.get("action")
        profile = self.profile(repo)
        if action == "status":
            return self.data
        if action == "release-readiness":
            r = self.data["releases"].get(c.get("release_id"))
            if not r or r["repository"] != repo or c.get("sha") != r["source_sha"]:
                raise Denied("Release readiness must match proposed accepted version")
            b = self.data["batches"][r["batch_id"]]
            if (
                b["status"] != "accepted"
                or self.data["dev"].get(repo, {}).get("sha") != c["sha"]
            ):
                raise Denied(
                    "Revalidate a superseded Dev candidate before preparing release PR"
                )
            checks = c.get("evidence", {})
            if set(checks) != set(RELEASE_CHECKS):
                raise Denied(
                    "All Production readiness evidence categories are required"
                )
            for value in checks.values():
                self.reference(value)
            r.update(
                status="ready_for_release_pr",
                readiness_evidence=checks,
                production_baseline_sha=self.sha(c.get("production_baseline_sha")),
                readiness_reference=self.reference(c.get("reference")),
                verified_at=self.m.clock(),
            )
            return r
        if action == "defer":
            q = self.data["queue"].get(key(repo, c.get("pr")))
            if not q or q["status"] not in ("queued", "deferred"):
                raise Denied("Only queued changes may be deferred")
            q.update(
                status="deferred", decision_reference=self.reference(c.get("reference"))
            )
            return q
        if action == "propose":
            return self.propose(c, profile)
        if action == "import-accepted":
            # One-time recovery of genuine pre-ledger delivery; never synthesize
            # an approval or an independently verified deployment from chat text.
            if repo in self.data["dev"] or self.active(repo):
                raise Denied("Historical baseline already initialized")
            sha = self.sha(c.get("sha"))
            prs = [self.merged(repo, n) for n in c["prs"]]
            checkout = self.repository(profile)
            for p in prs:
                git(checkout, "merge-base", "--is-ancestor", p["merge_commit_sha"], sha)
            git(checkout, "merge-base", "--is-ancestor", sha, "origin/main")
            proof = {
                "operations": self.reference(c.get("deployment_reference")),
                "owner": self.reference(c.get("reference")),
                "kind": "historical-owner-confirmed",
            }
            ident = "dev-history-" + sha[:12]
            b = {
                "batch_id": ident,
                "repository": repo,
                "environment": "dev-macmini",
                "baseline_sha": None,
                "candidate_sha": sha,
                "prs": sorted(c["prs"]),
                "title": self.reference(c.get("title")),
                "history_evidence": proof,
            }
            b.update(digest=digest(b), status="accepted", accepted_at=self.m.clock())
            self.data["batches"][ident] = b
            self.data["dev"][repo] = {"sha": sha, "batch_id": ident}
            for p in prs:
                self.data["queue"][key(repo, p["number"])] = {
                    "repository": repo,
                    "pr_number": p["number"],
                    "merge_sha": p["merge_commit_sha"],
                    "title": p["title"],
                    "status": "accepted",
                    "batch_id": ident,
                }
            self.release(b)
            return b
        b = self.batch(c)
        if action == "approve":
            if b["status"] == "approved":
                return {"changed": False, "batch": b}
            if b["status"] != "awaiting_approval":
                raise Denied("Batch is not awaiting approval")
            b.update(
                status="approved",
                approval_reference=self.reference(c.get("reference")),
                approved_at=self.m.clock(),
            )
        elif action == "ci-start":
            if b["status"] != "approved":
                raise Denied("Only an approved batch can start integration CI")
            ref = "delivery/" + b["batch_id"]
            # Persist intent before remote mutations. On interruption inspect
            # Actions/refs; never automatically redispatch an uncertain start.
            b.update(status="ci_requested", ci_ref=ref, ci_requested_at=self.m.clock())
            self.m.save()
            call(
                [
                    "gh",
                    "api",
                    "--method",
                    "POST",
                    f"repos/{repo}/git/refs",
                    "-f",
                    "ref=refs/heads/" + ref,
                    "-f",
                    "sha=" + b["candidate_sha"],
                ],
                network=True,
            )
            workflow = profile["candidate_workflow"].split("/")[-1]
            call(
                ["gh", "workflow", "run", workflow, "--repo", repo, "--ref", ref],
                network=True,
            )
        elif action == "ci-verify":
            if b["status"] not in ("approved", "ci_requested", "ci_passed"):
                raise Denied("Batch is not awaiting integration CI")
            b.update(candidate_ci=self.candidate_ci(b, c), status="ci_passed")
        elif action == "claim":
            if b["status"] != "ci_passed":
                raise Denied(
                    "Verified integration CI required before deployment handoff"
                )
            if self.data["dev"].get(repo, {}).get("sha") != b["baseline_sha"]:
                raise Denied("Dev baseline drifted; prepare a new batch")
            if c.get("observed_baseline_sha") != b["baseline_sha"]:
                raise Denied(
                    "Ops must report the actual observed Dev baseline before handoff"
                )
            b.update(
                status="deploying",
                deployment_reference=self.reference(c.get("reference")),
                claimed_at=self.m.clock(),
            )
        elif action == "deployment-failed":
            if b["status"] != "deploying" or c.get("sha") not in (
                b["baseline_sha"],
                b["candidate_sha"],
            ):
                raise Denied(
                    "Reconcile the actual old or candidate runtime version first"
                )
            b.update(
                status="failed", failure_reference=self.reference(c.get("reference"))
            )
            if c["sha"] == b["candidate_sha"]:
                b.update(status="rejected", rejection_reference=c["reference"])
                self.data["dev"][repo] = {"sha": c["sha"], "batch_id": b["batch_id"]}
        elif action == "deployed":
            if b["status"] != "deploying" or c.get("sha") != b["candidate_sha"]:
                raise Denied("Deployment must match claimed batch SHA")
            checks = c.get("checks", {})
            if set(checks) != set(CHECKS) or not all(
                v is True for v in checks.values()
            ):
                raise Denied(
                    "Runtime, transport, menu and services checks must all pass"
                )
            b.update(
                status="awaiting_acceptance",
                deployment_receipt={
                    "sha": c["sha"],
                    "checks": checks,
                    "reference": self.reference(c.get("reference")),
                    "at": self.m.clock(),
                },
            )
            self.data["dev"][repo] = {"sha": c["sha"], "batch_id": b["batch_id"]}
        elif action == "accept":
            if b["status"] == "accepted":
                return {"changed": False, "batch": b}
            if (
                b["status"] != "awaiting_acceptance"
                or c.get("sha") != b["candidate_sha"]
                or self.data["dev"].get(repo, {}).get("sha") != c["sha"]
            ):
                raise Denied(
                    "Owner acceptance must identify the currently deployed batch"
                )
            b.update(
                status="accepted",
                acceptance_reference=self.reference(c.get("reference")),
                accepted_at=self.m.clock(),
            )
            for n in b["prs"]:
                self.data["queue"][key(repo, n)]["status"] = "accepted"
            self.release(b)
        elif action == "reject":
            if (
                b["status"] != "awaiting_acceptance"
                or c.get("sha") != b["candidate_sha"]
            ):
                raise Denied("Rejection must identify deployed batch")
            b.update(
                status="rejected",
                rejection_reference=self.reference(c.get("reference")),
            )
        elif action == "supersede":
            if b["status"] in (
                "deploying",
                "awaiting_acceptance",
                "accepted",
                "superseded",
            ):
                raise Denied("Reconcile in-flight deployment/acceptance first")
            b.update(
                status="superseded",
                superseded_reference=self.reference(c.get("reference")),
            )
            for n in b["prs"]:
                self.data["queue"][key(repo, n)].update(
                    status="deployed_rejected"
                    if b.get("rejection_reference") or n in b.get("retest_prs", [])
                    else "deferred",
                    batch_id=None,
                )
        else:
            raise Denied("Unknown batch action")
        return b

    def release(self, b):
        groups = self.profile(b["repository"]).get("release_groups", [])
        relevant = [g for g in groups if set(g["prs"]) & set(b["prs"])]
        if relevant:
            accepted = {
                q["pr_number"]
                for q in self.data["queue"].values()
                if q["repository"] == b["repository"] and q["status"] == "accepted"
            }
            # A partial phase does not create a premature Production suggestion.
            for group in relevant:
                if set(group["prs"]) <= accepted:
                    self.release_record(
                        b, "release-" + group["id"], group["title"], group["prs"]
                    )
        else:
            self.release_record(b, "release-" + b["batch_id"], b["title"], b["prs"])

    def release_record(self, b, ident, title, group_prs):
        self.data["releases"].setdefault(
            ident,
            {
                "release_id": ident,
                "repository": b["repository"],
                "batch_id": b["batch_id"],
                "source_sha": b["candidate_sha"],
                "prs": sorted(set(b["prs"]) | set(group_prs)),
                "title": title,
                "group_prs": group_prs,
                "status": "preparation_needed",
                "production_approved": False,
                "next_owner": "pm",
                "created_at": self.m.clock(),
                "required_evidence": [
                    "actual Production baseline and cumulative application scope",
                    "migration, data/tenant access and real content plan",
                    "backup and rollback",
                    "VPS artifact/platform and Pro/pipeline readiness",
                ],
            },
        )


def notify_delivery(monitor, *, dry_run=False):
    """Persistent notifications for new batch decisions and release preparation."""
    sent = 0
    for b in ledger(monitor.state)["batches"].values():
        if b["status"] == "awaiting_approval":
            text = (
                f"[{b['repository'].split('/')[-1]}] Đợt Dev {b['batch_id']}: {b['title']}\n"
                + "Gồm PR "
                + ", ".join("#" + str(n) for n in b["prs"])
                + ".\n"
                + f"Bạn chọn: ‘Duyệt Dev {b['batch_id']}’ hoặc ‘Để sau {b['batch_id']}’. "
                + "PM sẽ giao Ốp Dev kiểm thử bản gộp và triển khai sau khi bạn duyệt."
            )
            phase = "batch_approval"
        elif b["status"] == "awaiting_acceptance":
            text = (
                f"[{b['repository'].split('/')[-1]}] {b['title']} đã lên Dev và qua kiểm tra kết nối.\n"
                + f"Bạn cần: thử các yêu cầu trong đợt {b['batch_id']} trên bot Dev, "
                + "rồi báo ‘Nghiệm thu đạt’ hoặc nêu điểm cần sửa. Chưa phát hành Production."
            )
            phase = "batch_acceptance"
        else:
            continue
        sent += monitor.notify(
            "delivery:" + b["batch_id"],
            {"head": {"sha": b["digest"]}},
            phase,
            text,
            issue=True,
            dry_run=dry_run,
        )
    for r in ledger(monitor.state)["releases"].values():
        if r["status"] not in ("preparation_needed", "ready_for_release_pr"):
            continue
        ready = r["status"] == "ready_for_release_pr"
        text = (
            f"[{r['repository'].split('/')[-1]}] {r['title']} đã nghiệm thu trên Dev.\n"
            + "Đề xuất tiếp theo: chuẩn bị một đợt phát hành Production. PM cần đối chiếu bản đang chạy, "
            + "dữ liệu và phương án khôi phục với Ốp Pro trước khi trình bạn duyệt PR phát hành.\n"
            + "Bạn chưa cần triển khai hay duyệt Production lúc này; đây là đề xuất chuẩn bị, chưa phải bản sẵn sàng phát hành."
        )
        if ready:
            text = (
                f"[{r['repository'].split('/')[-1]}] {r['title']} đã đủ hồ sơ đề xuất phát hành.\n"
                + "PM cần trình PR phát hành lên Production kèm phạm vi và cách khôi phục. "
                + "Bạn duyệt bằng cách merge PR phát hành khi đồng ý. Chưa có phê duyệt Production từ thông báo này."
            )
        sent += monitor.notify(
            "delivery:" + r["release_id"],
            {"head": {"sha": r["source_sha"]}},
            "release_ready" if ready else "release_preparation",
            text,
            issue=True,
            dry_run=dry_run,
        )
    return sent
