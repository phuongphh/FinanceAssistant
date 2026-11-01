import pytest

from agent_loop.config import LoopConfig, get_path


def test_defaults_are_safe() -> None:
    cfg = LoopConfig.from_dict(None)
    assert cfg.wip_limit == 2
    assert ".env" in cfg.forbidden_paths
    assert cfg.labels.wip in cfg.labels.skip
    assert cfg.labels.ready not in cfg.labels.skip


def test_partial_override_keeps_other_defaults() -> None:
    cfg = LoopConfig.from_dict(
        {"limits": {"wip_limit": 3}, "labels": {"ready": "bot:go"}, "areas": {"exclusive": []}}
    )
    assert cfg.wip_limit == 3
    assert cfg.daily_run_cap == LoopConfig().daily_run_cap
    assert cfg.labels.ready == "bot:go"
    assert cfg.labels.wip == "agent:wip"
    assert cfg.exclusive_areas == frozenset()


def test_get_path() -> None:
    data = {"limits": {"max_turns": 50}}
    assert get_path(data, "limits.max_turns") == 50
    with pytest.raises(KeyError):
        get_path(data, "limits.nope")
