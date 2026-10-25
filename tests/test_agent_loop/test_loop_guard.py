from agent_loop.config import LoopConfig
from agent_loop.guard import check, matches, parse_name_status

CFG = LoopConfig(immutable_existing=("alembic/versions/**",))


def test_env_files_are_forbidden_anywhere() -> None:
    res = check(["M\t.env", "A\tbackend/.env.prod"], CFG)
    assert len(res.violations) == 2


def test_env_example_is_allowed() -> None:
    assert check(["M\t.env.example"], CFG).ok


def test_workflows_are_forbidden() -> None:
    assert not check(["M\t.github/workflows/deploy.yml"], CFG).ok


def test_existing_migration_cannot_change_but_new_one_warns() -> None:
    assert not check(["M\talembic/versions/001_init.py"], CFG).ok
    res = check(["A\talembic/versions/099_new.py"], CFG)
    assert res.ok and res.warnings


def test_rename_cannot_smuggle_forbidden_file() -> None:
    assert parse_name_status(["R100\t.env\tnotes.txt"]) == [("D", ".env"), ("A", "notes.txt")]
    assert not check(["R100\t.env\tnotes.txt"], CFG).ok
    assert not check(["R090\tfoo.yml\t.github/workflows/foo.yml"], CFG).ok


def test_conflict_marker_detected() -> None:
    diff = "+++ b/x.py\n+<<<<<<< HEAD\n+a\n+=======\n+b\n+>>>>>>> main\n"
    assert not check(["M\tx.py"], CFG, diff).ok


def test_normal_code_change_passes() -> None:
    res = check(["M\tbackend/services/foo.py", "A\ttests/test_foo.py"], CFG)
    assert res.ok and not res.warnings
    assert "✅" in res.to_markdown()


def test_matches_basename_vs_path() -> None:
    assert matches("a/b/.env.local", [".env.*"])
    assert not matches("docs/env.md", [".env.*"])
    assert matches(".github/workflows/sub/x.yml", [".github/workflows/**"])


def test_migration_added_earlier_in_same_pr_can_be_edited() -> None:
    # mode fix: migration do chính PR tạo → chưa có trên base → chỉ cảnh báo
    res = check(["M\talembic/versions/099_new.py"], CFG, existed_in_base=lambda p: False)
    assert res.ok and res.warnings
    assert not check(["M\talembic/versions/099_new.py"], CFG, existed_in_base=lambda p: True).ok


def test_delivery_control_files_protected_in_defaults_and_repo_config() -> None:
    from pathlib import Path
    from agent_loop.config import load_config

    configs = [LoopConfig(), load_config(Path(__file__).resolve().parents[2] / ".github/agent-loop.yml")]
    for cfg in configs:
        for path in [".github/delivery.json", "scripts/delivery/validate.py", "docs/contracts/task.schema.json"]:
            assert not check(["M\t" + path], cfg).ok
            assert not check(["R100\t" + path + "\tordinary.txt"], cfg).ok
