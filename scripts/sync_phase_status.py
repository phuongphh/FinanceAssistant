#!/usr/bin/env python3
"""
Sync phase status from docs/current/phase-status.yaml to marker sections in target files.

This script renders two types of marker sections:
- `phase-status:current-line`: a single-line summary of the active phase
- `phase-status:roadmap-table`: a full markdown table of all phases

Files can opt-in to either marker by including the BEGIN/END comments.
Files without a marker are skipped silently (no error).

Usage:
    python scripts/sync_phase_status.py              # sync all target files
    python scripts/sync_phase_status.py --dry-run    # show what would change

Exit codes:
    0 = success (any number of files updated, including zero)
    1 = error (e.g., phase-status.yaml missing or malformed)
"""

import argparse
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
PHASE_STATUS_FILE = REPO_ROOT / "docs/current/phase-status.yaml"
CURRENT_DIR = REPO_ROOT / "docs/current"

# Marker seeded into every phase-*-test-cases.md that lacks one.
_SIGNOFF_MARKER_BLOCK = """\
<!-- testing-signoff: need to be signed -->
<!--
  Sign-off marker — driven by scripts/archive_phase.py.
  When testing is complete, change "need to be signed" → "signed" on the
  line above. The next archive-phase workflow run will move every
  phase-X-* doc (except the detailed_doc) into docs/archive/.
-->
"""
_SIGNOFF_RE = re.compile(r"<!--\s*testing-signoff:", re.IGNORECASE)

# Files that may contain marker sections. Each file independently opts-in
# by including the marker BEGIN/END comments. Missing markers are skipped.
TARGET_FILES = [
    REPO_ROOT / "CLAUDE.md",
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs/README.md",
    REPO_ROOT / "docs/current/strategy.md",
]

CURRENT_LINE_MARKER = "phase-status:current-line"
ROADMAP_TABLE_MARKER = "phase-status:roadmap-table"

# Map phase status → emoji used in rendered output.
STATUS_EMOJI = {
    "done": "✅",
    "current": "🚀",
    "testing": "🧪",
    "next": "📋",
    "planned": "🔮",
    "blocked": "⛔",
    "skeleton": "🚧",
}


def load_phase_status() -> dict:
    """Load and validate phase-status.yaml. Returns parsed dict."""
    if not PHASE_STATUS_FILE.exists():
        print(f"ERROR: {PHASE_STATUS_FILE.relative_to(REPO_ROOT)} does not exist",
              file=sys.stderr)
        sys.exit(1)

    with open(PHASE_STATUS_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict) or "phases" not in data:
        print(f"ERROR: {PHASE_STATUS_FILE.relative_to(REPO_ROOT)} must contain a 'phases' list",
              file=sys.stderr)
        sys.exit(1)

    return data


def find_active_phase(phases: list) -> dict | None:
    """Find the phase that's currently being worked on (status: current or testing)."""
    # Priority: 'current' > 'testing' (if both, pick first 'current')
    for status_priority in ("current", "testing"):
        for phase in phases:
            if phase.get("status") == status_priority:
                return phase
    return None


def render_current_line(data: dict) -> str:
    """Render the active phase as a single line."""
    active = find_active_phase(data["phases"])
    if not active:
        return "_(No active phase — all phases done or planned)_"

    emoji = STATUS_EMOJI.get(active["status"], "📌")
    name = active.get("name", active.get("id", "Unnamed phase"))
    status_label = active["status"]
    detail_doc = active.get("detail_doc", "#")

    return f"{emoji} **{name}** ({status_label}) — [detail]({detail_doc})"


def render_roadmap_table(data: dict) -> str:
    """Render full roadmap as a markdown table."""
    lines = ["| Phase | Status | Duration | Detailed Doc | Description |"]
    lines.append("|---|---|---|---|---|")

    for phase in data["phases"]:
        emoji = STATUS_EMOJI.get(phase["status"], "📌")
        name = phase.get("name", phase.get("id", "Unnamed"))
        status_cell = f"{emoji} {phase['status']}"
        duration = phase.get("duration", "TBD")
        description = phase.get("description", "TODO")

        detail_doc = phase.get("detail_doc")
        if detail_doc:
            detail_cell = f"[{Path(detail_doc).name}]({detail_doc})"
        else:
            detail_cell = "—"

        lines.append(
            f"| {name} | {status_cell} | {duration} | {detail_cell} | {description} |"
        )

    return "\n".join(lines)


def update_marker(content: str, marker_id: str, new_content: str) -> tuple[str, bool]:
    """
    Replace content between <!-- BEGIN: <marker_id> --> and <!-- END: <marker_id> -->.

    Returns:
        (new_content, found): where `found` is True if the marker pair was present.
        If marker is missing, returns content unchanged with found=False.
    """
    pattern = re.compile(
        rf"(<!-- BEGIN: {re.escape(marker_id)} -->\n).*?(\n<!-- END: {re.escape(marker_id)} -->)",
        re.DOTALL,
    )

    if not pattern.search(content):
        return content, False

    return pattern.sub(rf"\1{new_content}\2", content), True


def sync_file(path: Path, current_line: str, roadmap_table: str, dry_run: bool = False) -> bool:
    """
    Update markers in a single file. Returns True if file was changed.
    Skips silently if file doesn't exist or no markers present.
    """
    rel_path = path.relative_to(REPO_ROOT)

    if not path.exists():
        print(f"  SKIP: {rel_path} (does not exist)")
        return False

    content = path.read_text(encoding="utf-8")
    original = content

    content, current_found = update_marker(content, CURRENT_LINE_MARKER, current_line)
    content, roadmap_found = update_marker(content, ROADMAP_TABLE_MARKER, roadmap_table)

    if not (current_found or roadmap_found):
        print(f"  SKIP: {rel_path} (no markers found)")
        return False

    if content == original:
        markers = []
        if current_found:
            markers.append("current-line")
        if roadmap_found:
            markers.append("roadmap-table")
        print(f"  UNCHANGED: {rel_path} (markers: {', '.join(markers)})")
        return False

    if dry_run:
        print(f"  WOULD UPDATE: {rel_path}")
    else:
        path.write_text(content, encoding="utf-8")

    markers_updated = []
    if current_found:
        markers_updated.append("current-line")
    if roadmap_found:
        markers_updated.append("roadmap-table")
    action = "WOULD UPDATE" if dry_run else "✓ UPDATED"
    print(f"  {action}: {rel_path} (markers: {', '.join(markers_updated)})")
    return True


def seed_test_cases_markers(dry_run: bool = False) -> list[Path]:
    """Insert the testing-signoff marker into any phase-*-test-cases*.md
    in docs/current/ (recursive) that is missing it.

    Inserts the marker block after the first H1 heading line (or at the
    top of the file if no H1 is found). Returns list of files written.
    """
    seeded: list[Path] = []
    for path in sorted(CURRENT_DIR.rglob("*.md")):
        if "test-cases" not in path.name:
            continue
        if not re.match(r"phase-", path.name, re.IGNORECASE):
            continue
        text = path.read_text(encoding="utf-8")
        if _SIGNOFF_RE.search(text):
            continue  # already has marker

        # Insert after the first H1 line (and its trailing newline), or
        # prepend if no H1 found.
        h1_match = re.search(r"^(# .+\n)", text, re.MULTILINE)
        if h1_match:
            insert_at = h1_match.end()
            new_text = (
                text[:insert_at]
                + "\n"
                + _SIGNOFF_MARKER_BLOCK
                + text[insert_at:]
            )
        else:
            new_text = _SIGNOFF_MARKER_BLOCK + "\n" + text

        rel = path.relative_to(REPO_ROOT)
        if dry_run:
            print(f"  WOULD SEED marker: {rel}")
        else:
            path.write_text(new_text, encoding="utf-8")
            print(f"  ✓ SEEDED marker: {rel}")
        seeded.append(path)
    return seeded


def main():
    parser = argparse.ArgumentParser(description="Sync phase status to marker sections.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing files.",
    )
    args = parser.parse_args()

    data = load_phase_status()
    current_line = render_current_line(data)
    roadmap_table = render_roadmap_table(data)

    print(f"Phase status source: {PHASE_STATUS_FILE.relative_to(REPO_ROOT)}")
    print(f"Active phase line: {current_line}")
    print(f"Total phases in roadmap: {len(data['phases'])}")
    print()

    print("Seeding testing-signoff markers into test-cases files...")
    seeded = seed_test_cases_markers(dry_run=args.dry_run)
    if not seeded:
        print("  All test-cases files already have markers.")
    print()

    print(f"Syncing to {len(TARGET_FILES)} target files...")

    any_updated = False
    for target in TARGET_FILES:
        if sync_file(target, current_line, roadmap_table, dry_run=args.dry_run):
            any_updated = True

    print()
    if any_updated or seeded:
        if args.dry_run:
            print("(dry-run) Would have updated some files.")
        else:
            print("✓ Phase status sync complete.")
    else:
        print("No changes needed.")


if __name__ == "__main__":
    main()
