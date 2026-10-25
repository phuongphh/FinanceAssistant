"""Đọc ``.github/agent-loop.yml`` thành dataclass có default an toàn.

Mọi key đều optional: repo khác chỉ cần ghi những gì khác default.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path(".github/agent-loop.yml")


@dataclass(frozen=True)
class Labels:
    ready: str = "agent:ready"
    wip: str = "agent:wip"
    blocked: str = "agent:blocked"
    needs_fix: str = "agent:needs-fix"
    rejected: str = "agent:rejected"
    conflict: str = "agent:conflict"
    pr: str = "agent"

    @property
    def skip(self) -> frozenset[str]:
        """Issue mang một trong các label này thì dispatcher không nhặt."""
        return frozenset({self.wip, self.blocked, self.needs_fix, self.rejected})


@dataclass(frozen=True)
class LoopConfig:
    labels: Labels = field(default_factory=Labels)
    wip_limit: int = 2
    daily_run_cap: int = 12
    max_turns: int = 80
    max_auto_fix: int = 2
    area_prefix: str = "area:"
    default_area: str = "area:general"
    exclusive_areas: frozenset[str] = frozenset({"area:db"})
    project_owner: str = ""
    project_number: int = 0
    status_field: str = "Status"
    status_in_progress: str = "In Progress"
    priority_field: str = "Priority"
    priority_order: tuple[str, ...] = ("P0", "P1", "P2", "P3")
    branch_prefix: str = "agent/issue-"
    base_branch: str = "main"
    timezone: str = "Asia/Ho_Chi_Minh"
    active_hours: tuple[int, int] = (7, 23)
    auto_update_branch: bool = True
    auto_fix_ci: bool = True
    ci_workflows: tuple[str, ...] = ("CI",)
    gates: dict[str, str] = field(default_factory=dict)
    forbidden_paths: tuple[str, ...] = (
        ".env", ".env.*", ".github/**", "scripts/agent_loop/**",
        "scripts/delivery/**", "docs/contracts/**", ".claude/skills/implement-issue/**",
    )
    allowed_paths: tuple[str, ...] = (".env.example",)
    immutable_existing: tuple[str, ...] = ()
    skill_path: str = ".claude/skills/implement-issue/SKILL.md"
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> LoopConfig:
        d = data or {}
        labels = Labels(**{k: str(v) for k, v in (d.get("labels") or {}).items()})
        limits = d.get("limits") or {}
        areas = d.get("areas") or {}
        project = d.get("project") or {}
        guard = d.get("guard") or {}
        hours = d.get("active_hours") or [7, 23]
        default = cls()
        return cls(
            labels=labels,
            wip_limit=int(limits.get("wip_limit", default.wip_limit)),
            daily_run_cap=int(limits.get("daily_run_cap", default.daily_run_cap)),
            max_turns=int(limits.get("max_turns", default.max_turns)),
            max_auto_fix=int(limits.get("max_auto_fix", default.max_auto_fix)),
            area_prefix=str(areas.get("prefix", default.area_prefix)),
            default_area=str(areas.get("default", default.default_area)),
            exclusive_areas=frozenset(areas.get("exclusive", default.exclusive_areas)),
            project_owner=str(project.get("owner", "")),
            project_number=int(project.get("number", 0) or 0),
            status_field=str(project.get("status_field", default.status_field)),
            status_in_progress=str(project.get("in_progress", default.status_in_progress)),
            priority_field=str(project.get("priority_field", default.priority_field)),
            priority_order=tuple(project.get("priority_order", default.priority_order)),
            branch_prefix=str(d.get("branch_prefix", default.branch_prefix)),
            base_branch=str(d.get("base_branch", default.base_branch)),
            timezone=str(d.get("timezone", default.timezone)),
            active_hours=(int(hours[0]), int(hours[1])),
            auto_update_branch=bool(d.get("auto_update_branch", default.auto_update_branch)),
            auto_fix_ci=bool(d.get("auto_fix_ci", default.auto_fix_ci)),
            ci_workflows=tuple(d.get("ci_workflows", default.ci_workflows)),
            gates={str(k): str(v) for k, v in (d.get("gates") or {}).items()},
            forbidden_paths=tuple(guard.get("forbidden", default.forbidden_paths)),
            allowed_paths=tuple(guard.get("allowed", default.allowed_paths)),
            immutable_existing=tuple(guard.get("immutable_existing", ())),
            skill_path=str(d.get("skill", default.skill_path)),
            raw=d,
        )


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> LoopConfig:
    with path.open(encoding="utf-8") as fh:
        return LoopConfig.from_dict(yaml.safe_load(fh))


def get_path(data: dict[str, Any], dotted: str) -> Any:
    """``get_path(raw, "limits.max_turns")`` — dùng cho ``cli config-get``."""
    node: Any = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(dotted)
        node = node[part]
    return node
