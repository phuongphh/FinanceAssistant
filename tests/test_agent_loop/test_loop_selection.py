from datetime import datetime, timezone

from agent_loop.config import LoopConfig
from agent_loop.selection import (
    Issue,
    branch_name,
    in_active_hours,
    issue_from_branch,
    parse_blockers,
    select,
    slugify,
)

CFG = LoopConfig()
READY = "agent:ready"


def issue(n: int, *labels: str, **kw) -> Issue:
    return Issue(number=n, title=kw.pop("title", f"US {n}"), labels=frozenset({READY, *labels}), **kw)


def numbers(result) -> list[int]:
    return [i.number for i in result.selected]


def test_parallel_when_areas_differ() -> None:
    res = select([issue(1, "area:ui"), issue(2, "area:api")], [], 0, CFG)
    assert numbers(res) == [1, 2]


def test_same_area_runs_sequentially() -> None:
    res = select([issue(1, "area:ui"), issue(2, "area:ui")], [], 0, CFG)
    assert numbers(res) == [1]
    assert (2, "trùng area area:ui với việc đang chạy") in res.skipped


def test_missing_area_falls_into_default_area() -> None:
    res = select([issue(1), issue(2)], [], 0, CFG)
    assert numbers(res) == [1]


def test_wip_area_blocks_candidate() -> None:
    wip = [Issue(9, "x", frozenset({"agent:wip", "area:ui"}))]
    res = select([issue(1, "area:ui"), issue(2, "area:api")], wip, 0, CFG)
    assert numbers(res) == [2]


def test_wip_limit_and_daily_cap() -> None:
    cands = [issue(1, "area:a"), issue(2, "area:b"), issue(3, "area:c")]
    assert numbers(select(cands, [], 0, CFG)) == [1, 2]
    assert numbers(select(cands, [], CFG.daily_run_cap - 1, CFG)) == [1]
    assert numbers(select(cands, [], CFG.daily_run_cap, CFG)) == []


def test_exclusive_area_runs_alone_when_idle() -> None:
    res = select([issue(1, "area:db"), issue(2, "area:ui")], [], 0, CFG)
    assert numbers(res) == [1]


def test_exclusive_at_head_drains_queue() -> None:
    wip = [Issue(9, "x", frozenset({"agent:wip", "area:api"}))]
    res = select([issue(1, "area:db"), issue(2, "area:ui")], wip, 0, CFG)
    assert res.selected == []
    assert res.drained is True


def test_exclusive_wip_blocks_everything() -> None:
    wip = [Issue(9, "x", frozenset({"agent:wip", "area:db"}))]
    assert numbers(select([issue(1, "area:ui")], wip, 0, CFG)) == []


def test_priority_then_epic_order() -> None:
    cands = [
        issue(5, "area:a", priority="P2", parent=1),
        issue(6, "area:b", priority="P0", parent=3),
        issue(7, "area:c", priority=None),
    ]
    assert numbers(select(cands, [], 0, CFG)) == [6, 5]


def test_skips_epics_blocked_labels_and_open_prs() -> None:
    cands = [
        issue(1, "area:a", open_sub_issues=2),
        issue(2, "area:b", blockers=(1,)),
        issue(3, "area:c", "agent:blocked"),
        issue(4, "area:d"),
        Issue(5, "no ready label", frozenset({"area:e"})),
        issue(6, "area:f"),
    ]
    res = select(cands, [], 0, CFG, open_pr_issues=[4])
    assert numbers(res) == [6]
    assert {n for n, _ in res.skipped} == {1, 2, 3, 4, 5}


def test_parse_blockers() -> None:
    body = "Blocked by #12, #13\nDepends on: #7\nPhụ thuộc vào #5 và #6\nSee #99"
    assert parse_blockers(body) == {12, 13, 7, 5, 6}
    assert parse_blockers(None) == set()


def test_active_hours_vietnam_time() -> None:
    # 00:30 UTC = 07:30 giờ VN → trong khung 7-23
    assert in_active_hours(datetime(2026, 10, 21, 0, 30, tzinfo=timezone.utc), CFG)
    # 16:30 UTC = 23:30 giờ VN → ngoài khung
    assert not in_active_hours(datetime(2026, 10, 21, 16, 30, tzinfo=timezone.utc), CFG)


def test_active_hours_over_midnight() -> None:
    cfg = LoopConfig.from_dict({"active_hours": [22, 6]})
    assert in_active_hours(datetime(2026, 10, 21, 16, 0, tzinfo=timezone.utc), cfg)  # 23h VN
    assert not in_active_hours(datetime(2026, 10, 21, 5, 0, tzinfo=timezone.utc), cfg)  # 12h VN


def test_slug_and_branch_roundtrip() -> None:
    assert slugify("Đăng ký chi tiêu bằng giọng nói!") == "dang-ky-chi-tieu-bang-giong-noi"
    branch = branch_name(Issue(42, "Báo cáo tuần"), CFG)
    assert branch == "agent/issue-42-bao-cao-tuan"
    assert issue_from_branch(branch, CFG) == 42
    assert issue_from_branch("claude/issue-42", CFG) is None


def test_branch_slug_starting_with_digit_gets_prefix() -> None:
    # project-done.yml sẽ đọc "issue-42-2026" thành 2 số issue nếu không có "t-".
    assert branch_name(Issue(42, "2026 báo cáo"), CFG) == "agent/issue-42-t-2026-bao-cao"
