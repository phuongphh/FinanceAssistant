from __future__ import annotations

import ast
from pathlib import Path


VERSIONS_DIR = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def _assigned_value(module: ast.Module, name: str):
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise AssertionError(f"Could not find assignment for {name}")


def test_default_expense_source_profile_points_to_credit_limit_revision_id():
    parent_file = VERSIONS_DIR / "20260527_credit_card_limit_and_debt.py"
    child_file = VERSIONS_DIR / "20260528_default_expense_source_profile.py"

    parent_module = ast.parse(parent_file.read_text(encoding="utf-8"))
    child_module = ast.parse(child_file.read_text(encoding="utf-8"))

    parent_revision = _assigned_value(parent_module, "revision")
    child_down_revision = _assigned_value(child_module, "down_revision")

    assert child_down_revision == parent_revision
