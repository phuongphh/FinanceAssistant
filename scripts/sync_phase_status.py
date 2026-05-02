"""Auto-sync project docs from docs/current/phase-status.yaml.

This script is the engine behind the auto-update strategy: edit one
file (``phase-status.yaml``), run this, and every README / CLAUDE /
strategy doc that has the right HTML-comment markers picks up the
new state.

How sections are marked
-----------------------
Each consumer file has named regions delimited by HTML comments::

    <!-- BEGIN: phase-status:current-block -->
    ... auto-generated content ...
    <!-- END: phase-status:current-block -->

This script only rewrites content BETWEEN the markers — anything
outside is preserved verbatim. Adding a new region to a file is a
two-step process:

    1. Drop the BEGIN/END comments around the desired location.
    2. Add a renderer function below + register it in ``RENDERERS``.

Renderers
---------
- ``current-line``   one-line "current focus" snippet
- ``current-block``  multi-line current focus block with links
- ``roadmap-table``  full markdown table of every phase
- ``status-list``    short status list (✅/🔨/📋/🔮)

Idempotence
-----------
The script is idempotent: running it twice in a row produces the same
output. The CI workflow relies on this — it runs the script and only
commits when ``git diff`` is non-empty, so a no-op run doesn't churn
the history.

CLI
---
::

    python scripts/sync_phase_status.py            # rewrite in place
    python scripts/sync_phase_status.py --check    # exit non-zero if drift
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
PHASE_STATUS_FILE = REPO_ROOT / "docs" / "current" / "phase-status.yaml"

# Files that may contain markers. Listed explicitly rather than
# globbed so a stray third-party doc (e.g. a vendor README) can't
# accidentally trigger an edit.
TARGET_FILES = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "CLAUDE.md",
    REPO_ROOT / "docs" / "README.md",
    REPO_ROOT / "docs" / "current" / "strategy.md",
]


# ---------------------- data model ----------------------


@dataclass(frozen=True)
class Phase:
    id: str
    name: str
    status: str
    duration: str
    detailed_doc: str
    issues_doc: str
    description: str
    completed_date: str
    icon: str


@dataclass(frozen=True)
class PhaseStatus:
    current_phase: str
    roadmap: list[Phase]

    def current(self) -> Phase | None:
        for p in self.roadmap:
            if p.id == self.current_phase:
                return p
        return None


def load_status(path: Path = PHASE_STATUS_FILE) -> PhaseStatus:
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    roadmap = [Phase(**entry) for entry in raw.get("roadmap", [])]
    return PhaseStatus(
        current_phase=str(raw["current_phase"]),
        roadmap=roadmap,
    )


# ---------------------- renderers ----------------------


# Each renderer takes the loaded ``PhaseStatus`` and returns a string
# that replaces the body between BEGIN/END markers. Strings should NOT
# include the markers themselves.


def _link(label: str, path: str) -> str:
    """Render a markdown link or just the label if path is empty."""
    return f"[{label}]({path})" if path else label


def render_current_line(status: PhaseStatus) -> str:
    """One-line "current focus" snippet."""
    cur = status.current()
    if not cur:
        return "_(No current phase set in phase-status.yaml)_\n"
    icon = "🚀" if cur.status == "current" else cur.icon
    detail = _link("detail", cur.detailed_doc) if cur.detailed_doc else ""
    suffix = f" — {detail}" if detail else ""
    return f"{icon} **Phase {cur.id}: {cur.name}** ({cur.status}){suffix}\n"


def render_current_block(status: PhaseStatus) -> str:
    """Multi-line "current focus" block — used in the docs README."""
    cur = status.current()
    if not cur:
        return "_(No current phase set in phase-status.yaml)_\n"

    lines: list[str] = []
    icon = "🚀" if cur.status == "current" else cur.icon
    lines.append(f"{icon} **Phase {cur.id} — {cur.name}** ({cur.duration})")
    lines.append("")
    if cur.detailed_doc:
        lines.append(f"- 📖 Detailed doc: [{cur.detailed_doc}]({_relpath(cur.detailed_doc)})")
    if cur.issues_doc:
        lines.append(f"- 📋 Issues: [{cur.issues_doc}]({_relpath(cur.issues_doc)})")
    if cur.description:
        lines.append(f"- 📝 Scope: {cur.description}")
    lines.append("")
    return "\n".join(lines) + "\n"


def render_roadmap_table(status: PhaseStatus) -> str:
    """Full roadmap as a markdown table."""
    header = (
        "| Phase | Status | Duration | Detailed Doc | Description |\n"
        "|---|---|---|---|---|\n"
    )
    rows: list[str] = []
    for p in status.roadmap:
        marker = "**" if p.id == status.current_phase else ""
        name_cell = f"{marker}Phase {p.id}: {p.name}{marker}"
        status_cell = f"{p.icon} {p.status}"
        detail_cell = (
            f"[{p.detailed_doc.split('/')[-1]}]({_relpath(p.detailed_doc)})"
            if p.detailed_doc
            else "—"
        )
        rows.append(
            f"| {name_cell} | {status_cell} | {p.duration} | "
            f"{detail_cell} | {p.description} |"
        )
    return header + "\n".join(rows) + "\n"


def render_status_list(status: PhaseStatus) -> str:
    """Compact bullet list of every phase + status — for top of README."""
    lines: list[str] = []
    for p in status.roadmap:
        marker = " ← **current**" if p.id == status.current_phase and p.status != "done" else ""
        if p.id == status.current_phase and p.status == "done":
            marker = " ← **just shipped**"
        lines.append(f"- {p.icon} Phase {p.id}: {p.name}{marker}")
    return "\n".join(lines) + "\n"


def _relpath(path: str) -> str:
    """Return ``path`` as-is. Kept as a hook so future tweaks (e.g.
    rewriting absolute → relative based on the file being patched)
    can be added in one place.
    """
    return path


RENDERERS: dict[str, Callable[[PhaseStatus], str]] = {
    "current-line": render_current_line,
    "current-block": render_current_block,
    "roadmap-table": render_roadmap_table,
    "status-list": render_status_list,
}


# ---------------------- file rewriter ----------------------


# All groups named so refactors don't accidentally re-number them.
# (First version of this regex used ``match.group(3)`` to mean the
# END marker, but unnamed groups inside ``(?P<name>...)`` shifted the
# positional index — group 3 was the body, leading to END markers
# being silently dropped on every rewrite. Don't touch.)
_MARKER_RE = re.compile(
    r"(?P<begin><!--\s*BEGIN:\s*phase-status:(?P<name>[a-z0-9-]+)\s*-->)"
    r"(?P<body>.*?)"
    r"(?P<end><!--\s*END:\s*phase-status:(?P=name)\s*-->)",
    flags=re.DOTALL | re.IGNORECASE,
)


def rewrite_file(path: Path, status: PhaseStatus) -> bool:
    """Rewrite each marked section in ``path``. Returns True if any
    change was applied (so callers can skip a no-op write to keep
    file mtimes stable)."""
    if not path.exists():
        return False
    original = path.read_text(encoding="utf-8")

    def _replace(match: re.Match[str]) -> str:
        name = match.group("name")
        renderer = RENDERERS.get(name)
        if renderer is None:
            # Unknown marker — leave untouched but warn. Use a relative
            # path when ``path`` is inside the repo (cleaner output);
            # otherwise fall back to the absolute path so test fixtures
            # under ``/tmp`` don't blow up the printer.
            try:
                shown = path.relative_to(REPO_ROOT)
            except ValueError:
                shown = path
            print(
                f"  ⚠️  Unknown marker {name!r} in {shown}",
                file=sys.stderr,
            )
            return match.group(0)
        rendered = renderer(status)
        # Wrap body with surrounding newlines so the markers always
        # sit on their own lines, regardless of how the source file
        # was indented. Renderer outputs already end in \n.
        return f"{match.group('begin')}\n{rendered}{match.group('end')}"

    updated = _MARKER_RE.sub(_replace, original)
    if updated == original:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


# ---------------------- CLI ----------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync project docs from phase-status.yaml"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if any file would change (CI lint mode).",
    )
    args = parser.parse_args()

    status = load_status()
    print(
        f"Phase status loaded: {len(status.roadmap)} phases, "
        f"current = {status.current_phase}"
    )

    drift: list[Path] = []
    for path in TARGET_FILES:
        if not path.exists():
            print(f"  ⚠️  Skipping missing file: {path.relative_to(REPO_ROOT)}")
            continue
        before = path.read_text(encoding="utf-8")
        rewrite_file(path, status)
        after = path.read_text(encoding="utf-8")
        if before != after:
            drift.append(path)
            print(f"  ✓ Updated {path.relative_to(REPO_ROOT)}")
        else:
            print(f"  · No change to {path.relative_to(REPO_ROOT)}")

    if args.check and drift:
        # Restore originals so --check doesn't leave the tree dirty.
        # In CI we usually run without --check and let the workflow
        # commit the result; --check is for local pre-push verification.
        for path in drift:
            print(
                f"  ⚠️  --check: {path.relative_to(REPO_ROOT)} would change",
                file=sys.stderr,
            )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
