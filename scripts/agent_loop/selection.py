"""Logic chọn issue tiếp theo — hàm thuần, không gọi mạng, test được.

Quy tắc (xem docs/architecture/loop-engineering.md §Dispatcher):

1. Chỉ nhặt issue *lá* (không còn sub-issue mở), có label ``agent:ready``,
   không mang label skip (wip/blocked/needs-fix/rejected), không có blocker
   đang mở, chưa có PR agent đang mở.
2. Số slot = min(wip_limit - số WIP, daily_run_cap - số run hôm nay).
3. Hai issue chạy song song chỉ khi *không chung area* (``area:*``). Issue
   thiếu area label rơi vào ``default_area`` → các issue đó chạy tuần tự.
4. Area exclusive (vd ``area:db`` vì migration Alembic phải tuyến tính) chỉ
   chạy khi không có gì đang WIP, và khi nó chạy thì không nhận thêm việc.
   Nếu issue exclusive đứng đầu hàng đợi mà chưa chạy được → *drain*: dừng
   nhận việc mới để WIP về 0 rồi chạy nó (tránh bị bỏ đói mãi).
5. Thứ tự: priority (P0 trước) → số Epic cha (Epic cũ trước, giữ US cùng
   Epic gần nhau) → số issue.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from agent_loop.config import LoopConfig

_BLOCKER_RE = re.compile(
    r"(?:blocked\s+by|depends\s+on|phụ\s+thuộc(?:\s+vào)?)\s*:?\s*"
    r"(#\d+(?:\s*(?:,|&|và|and)?\s*#\d+)*)",
    re.IGNORECASE,
)
_ISSUE_REF_RE = re.compile(r"#(\d+)")


@dataclass(frozen=True)
class Issue:
    number: int
    title: str
    labels: frozenset[str] = frozenset()
    body: str = ""
    state: str = "OPEN"
    parent: int | None = None
    open_sub_issues: int = 0
    priority: str | None = None
    # Chỉ các blocker CÒN MỞ — cli resolve trạng thái trước khi gọi select().
    blockers: tuple[int, ...] = ()


@dataclass
class SelectionResult:
    selected: list[Issue] = field(default_factory=list)
    skipped: list[tuple[int, str]] = field(default_factory=list)
    drained: bool = False


def parse_blockers(body: str | None) -> set[int]:
    """Tìm "Blocked by #12, #13" / "Depends on #7" / "Phụ thuộc #5" trong body."""
    found: set[int] = set()
    for match in _BLOCKER_RE.finditer(body or ""):
        found.update(int(n) for n in _ISSUE_REF_RE.findall(match.group(1)))
    return found


def areas_of(issue: Issue, cfg: LoopConfig) -> frozenset[str]:
    areas = frozenset(lb for lb in issue.labels if lb.startswith(cfg.area_prefix))
    return areas or frozenset({cfg.default_area})


def is_exclusive(issue: Issue, cfg: LoopConfig) -> bool:
    return bool(areas_of(issue, cfg) & cfg.exclusive_areas)


def sort_key(issue: Issue, cfg: LoopConfig) -> tuple[int, int, int]:
    order = list(cfg.priority_order)
    rank = order.index(issue.priority) if issue.priority in order else len(order)
    return (rank, issue.parent or issue.number, issue.number)


def in_active_hours(now: datetime, cfg: LoopConfig) -> bool:
    """``active_hours = (7, 23)`` nghĩa là 07:00 ≤ giờ VN < 23:00."""
    local = now.astimezone(ZoneInfo(cfg.timezone))
    start, end = cfg.active_hours
    if start <= end:
        return start <= local.hour < end
    return local.hour >= start or local.hour < end  # khung qua nửa đêm


def slugify(text: str, max_len: int = 40) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:max_len].rstrip("-") or "task"


def branch_name(issue: Issue, cfg: LoopConfig) -> str:
    slug = slugify(issue.title)
    # project-done.yml đọc số issue từ branch bằng regex ``issues?[-_](\d+(?:[-_]\d+)*)``
    # — slug bắt đầu bằng chữ số sẽ bị hiểu nhầm thành thêm số issue.
    if slug[0].isdigit():
        slug = f"t-{slug}"
    return f"{cfg.branch_prefix}{issue.number}-{slug}"


def issue_from_branch(branch: str, cfg: LoopConfig) -> int | None:
    match = re.match(rf"^{re.escape(cfg.branch_prefix)}(\d+)", branch or "")
    return int(match.group(1)) if match else None


def skip_reason(issue: Issue, cfg: LoopConfig, open_pr_issues: Iterable[int] = ()) -> str | None:
    """Lý do issue KHÔNG đủ điều kiện, hoặc None nếu đủ điều kiện."""
    labels = cfg.labels
    if issue.state.upper() != "OPEN":
        return "issue đã đóng"
    if labels.ready not in issue.labels:
        return f"thiếu label {labels.ready}"
    hit = sorted(issue.labels & labels.skip)
    if hit:
        return f"đang mang label {', '.join(hit)}"
    if issue.open_sub_issues:
        return f"còn {issue.open_sub_issues} sub-issue mở (Epic)"
    if issue.blockers:
        return "bị chặn bởi " + ", ".join(f"#{n}" for n in issue.blockers)
    if issue.number in set(open_pr_issues):
        return "đã có PR agent đang mở"
    return None


def select(
    candidates: Sequence[Issue],
    wip_issues: Sequence[Issue],
    runs_today: int,
    cfg: LoopConfig,
    open_pr_issues: Iterable[int] = (),
) -> SelectionResult:
    result = SelectionResult()
    open_prs = set(open_pr_issues)

    eligible: list[Issue] = []
    for issue in candidates:
        reason = skip_reason(issue, cfg, open_prs)
        if reason:
            result.skipped.append((issue.number, reason))
        else:
            eligible.append(issue)
    eligible.sort(key=lambda i: sort_key(i, cfg))

    slots = min(cfg.wip_limit - len(wip_issues), cfg.daily_run_cap - runs_today)
    busy_areas: set[str] = set()
    for issue in wip_issues:
        busy_areas |= areas_of(issue, cfg)
    exclusive_running = any(is_exclusive(i, cfg) for i in wip_issues)

    for issue in eligible:
        if slots <= 0:
            if runs_today >= cfg.daily_run_cap:
                result.skipped.append((issue.number, f"đã chạm trần {cfg.daily_run_cap} run/ngày"))
            else:
                result.skipped.append((issue.number, f"đủ {cfg.wip_limit} việc đang chạy"))
            continue
        if exclusive_running:
            result.skipped.append((issue.number, "đang chạy 1 việc exclusive (vd migration)"))
            continue
        if result.drained:
            result.skipped.append((issue.number, "đang drain chờ việc exclusive"))
            continue

        areas = areas_of(issue, cfg)
        if is_exclusive(issue, cfg):
            if wip_issues or result.selected:
                if not result.selected:
                    # Exclusive đứng đầu hàng đợi: ngừng nhận việc mới để nó
                    # được chạy ngay khi WIP về 0.
                    result.drained = True
                result.skipped.append((issue.number, "exclusive — chờ WIP về 0"))
                continue
            result.selected.append(issue)
            exclusive_running = True
            slots -= 1
            continue

        clash = sorted(areas & busy_areas)
        if clash:
            result.skipped.append((issue.number, f"trùng area {', '.join(clash)} với việc đang chạy"))
            continue

        result.selected.append(issue)
        busy_areas |= areas
        slots -= 1

    return result
