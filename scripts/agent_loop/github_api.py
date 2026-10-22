"""Bọc ``gh api`` (REST + GraphQL) thành 1 class nhỏ để cli dễ test bằng fake.

Token lấy từ env ``GH_TOKEN`` như mọi lệnh ``gh`` khác — dispatcher/publish
dùng PAT, job ``agent`` dùng GITHUB_TOKEN read-only.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from typing import Any

log = logging.getLogger("agent_loop")

_HTTP_STATUS_RE = re.compile(r"HTTP (\d{3})")


class GHError(RuntimeError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class GH:
    """``api()`` cho REST, ``graphql()`` cho GraphQL. Lỗi → ``GHError``."""

    def __init__(self, repo: str) -> None:
        self.repo = repo  # "owner/name"

    def _run(self, args: list[str], stdin: str | None = None) -> str:
        proc = subprocess.run(
            ["gh", *args],
            input=stdin,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            match = _HTTP_STATUS_RE.search(proc.stderr)
            raise GHError(
                f"gh {' '.join(args[:3])}: {proc.stderr.strip()[:500]}",
                int(match.group(1)) if match else None,
            )
        return proc.stdout

    def api(
        self,
        path: str,
        method: str = "GET",
        body: dict[str, Any] | None = None,
        paginate: bool = False,
    ) -> Any:
        """``path`` tương đối với ``repos/{repo}/`` trừ khi bắt đầu bằng ``/``."""
        full = path[1:] if path.startswith("/") else f"repos/{self.repo}/{path}"
        args = ["api", "-X", method, full, "-H", "Accept: application/vnd.github+json"]
        if paginate:
            args += ["--paginate", "--slurp"]
        stdin = None
        if body is not None:
            args += ["--input", "-"]
            stdin = json.dumps(body)
        out = self._run(args, stdin)
        if not out.strip():
            return None
        data = json.loads(out)
        if paginate and isinstance(data, list):
            flat: list[Any] = []
            for page in data:
                flat.extend(page if isinstance(page, list) else [page])
            return flat
        return data

    def graphql(self, query: str, **variables: Any) -> dict[str, Any]:
        out = self._run(
            # Header bật field parent/subIssues của Issue (sub-issues API).
            ["api", "graphql", "-H", "GraphQL-Features: sub_issues", "--input", "-"],
            json.dumps({"query": query, "variables": variables}),
        )
        data = json.loads(out)
        if data.get("errors"):
            raise GHError(f"graphql: {data['errors']}")
        return data["data"]

    def run_log(self, run_id: int | str) -> str:
        """Log các step fail của 1 workflow run (để agent đọc khi sửa CI)."""
        return self._run(["run", "view", str(run_id), "--log-failed", "-R", self.repo])
