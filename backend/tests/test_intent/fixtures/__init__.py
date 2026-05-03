"""Pytest helpers for loading shared intent fixtures.

Other tests do ``from backend.tests.test_intent.fixtures import
load_query_fixtures`` so that the YAML lives in one place and any test
that touches the classifier can iterate over the same vetted examples.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_FIXTURE_PATH = Path(__file__).parent / "query_examples.yaml"


@dataclass(frozen=True)
class QueryFixture:
    """One row from query_examples.yaml, as a typed record."""

    text: str
    expected_intent: str
    expected_parameters: dict[str, Any]
    expected_min_confidence: float
    notes: str
    section: str  # "canonical" | "edge_cases"


def load_query_fixtures(
    section: str | None = None,
) -> list[QueryFixture]:
    """Read the YAML and return one ``QueryFixture`` per entry.

    ``section`` filters to ``"canonical"`` or ``"edge_cases"``; default
    returns both.
    """
    with _FIXTURE_PATH.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    sections = ["canonical", "edge_cases"] if section is None else [section]
    out: list[QueryFixture] = []
    for sect in sections:
        rows = raw.get(sect, []) or []
        for row in rows:
            min_conf = row.get("expected_min_confidence")
            if min_conf is None:
                min_conf = 0.85 if sect == "canonical" else 0.5
            out.append(
                QueryFixture(
                    text=row["text"],
                    expected_intent=row["expected_intent"],
                    expected_parameters=row.get("expected_parameters") or {},
                    expected_min_confidence=float(min_conf),
                    notes=row.get("notes", ""),
                    section=sect,
                )
            )
    return out


__all__ = ["QueryFixture", "load_query_fixtures"]
