#!/usr/bin/env python3
"""
Sync phase status from docs/current/phase-status.yaml to marker sections in target files.

This script renders four types of marker sections:
- `phase-status:current-line`: a single-line summary of the active phase
- `phase-status:current-block`: a multi-line block (id, name, docs, scope)
- `phase-status:status-list`: a bullet list of every phase, flagging the active one
- `phase-status:roadmap-table`: a full markdown table of all phases

The "active phase" is resolved from ``current_phase`` in the YAML (so a
phase with status ``next`` is shown once dev finishes the prior phase),
falling back to the first phase with status ``current``/``testing``.

Files can opt-in to any marker by including the BEGIN/END comments.
Files without a marker are skipped silently (no error).

Also seeds a ``<!-- testing-signoff: need to be signed -->`` marker into any
``phase-*-test-cases*.md`` in ``docs/current/`` that is missing one, so the
archive-phase workflow can detect tester sign-off automatically.

Called by two workflows:
- ``.github/workflows/sync-phase-status.yml`` — on every push touching phase-status.yaml
- ``.github/workflows/archive-phase.yml`` — after archiving, to sync updated doc paths

Usage:
    python scripts/sync_phase_status.py              # sync all target files
    python scripts/sync_phase_status.py --dry-run    # show what would change

Exit codes:
    0 = success (any number of files updated, including zero)
    1 = error (e.g., phase-status.yaml missing or malformed)
"""

import argparse
import os
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
STATUS_LIST_MARKER = "phase-status:status-list"
CURRENT_BLOCK_MARKER = "phase-status:current-block"

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


def find_active_phase(data: dict) -> dict | None:
    """Find the phase the team is focused on.

    Resolution order:
      1. The phase whose ``id`` matches ``current_phase`` (the schema's
         declared focus — works for ``current``, ``testing`` *and* ``next``).
      2. Fallback: first phase with status ``current`` then ``testing``.
    """
    phases = data["phases"]
    current_id = data.get("current_phase")
    if current_id is not None:
        for phase in phases:
            if str(phase.get("id")) == str(current_id):
                return phase
    # Priority: 'current' > 'testing' (if both, pick first 'current')
    for status_priority in ("current", "testing"):
        for phase in phases:
            if phase.get("status") == status_priority:
                return phase
    return None


def render_current_line(data: dict) -> str:
    """Render the active phase as a single line."""
    active = find_active_phase(data)
    if not active:
        return "_(No active phase — all phases done or planned)_"

    emoji = STATUS_EMOJI.get(active["status"], "📌")
    name = active.get("name", active.get("id", "Unnamed phase"))
    status_label = active["status"]
    detail_doc = active.get("detail_doc") or "#"

    return f"{emoji} **{name}** ({status_label}) — [detail]({detail_doc})"


def render_current_block(data: dict) -> str:
    """Render the active phase as a multi-line block (id, name, docs, scope)."""
    active = find_active_phase(data)
    if not active:
        return "_(No active phase — all phases done or planned)_"

    emoji = STATUS_EMOJI.get(active["status"], "📌")
    phase_id = active.get("id", "?")
    name = active.get("name", "Unnamed phase")
    duration = active.get("duration", "TBD")
    description = active.get("description", "TODO")

    lines = [f"{emoji} **Phase {phase_id} — {name}** ({duration})", ""]

    detail_doc = active.get("detail_doc")
    if detail_doc:
        lines.append(f"- 📖 Detailed doc: [{detail_doc}]({detail_doc})")
    issues_doc = active.get("issues_doc")
    if issues_doc:
        lines.append(f"- 📋 Issues: [{issues_doc}]({issues_doc})")
    lines.append(f"- 📝 Scope: {description}")

    return "\n".join(lines)


def render_status_list(data: dict) -> str:
    """Render every phase as a bullet list, flagging the active one."""
    current_id = data.get("current_phase")
    lines = []
    for phase in data["phases"]:
        emoji = STATUS_EMOJI.get(phase["status"], "📌")
        phase_id = phase.get("id", "?")
        name = phase.get("name", "Unnamed")
        line = f"- {emoji} Phase {phase_id}: {name}"
        if current_id is not None and str(phase.get("id")) == str(current_id):
            flag = "current" if phase.get("status") in ("current", "testing") else "next"
            line += f" ← **{flag}**"
        lines.append(line)
    return "\n".join(lines)


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


_MD_LINK_RE = re.compile(r"\]\(([^)]+)\)")


def rewrite_links_relative(text: str, target_dir: Path) -> str:
    """Rewrite repo-root-relative markdown links to be relative to ``target_dir``.

    The phase-status YAML stores doc paths relative to the repo root
    (e.g. ``docs/current/phase-4.4/...``). That resolves correctly for
    target files at the repo root (CLAUDE.md, README.md) but 404s from a
    file inside a subdirectory (docs/README.md would resolve them to
    ``docs/docs/current/...``). Re-anchor each in-repo link to the target
    file's directory so links work from wherever the marker lives.

    External links (http, mailto, anchors, absolute paths) are left as-is.
    """
    rel_dir = target_dir.relative_to(REPO_ROOT)
    if rel_dir == Path("."):
        return text  # already correct for repo-root targets

    def _rewrite(match: re.Match) -> str:
        link = match.group(1)
        if link.startswith(("http://", "https://", "mailto:", "#", "/")):
            return match.group(0)
        # Split off any #anchor so it survives the relpath computation.
        path_part, _, anchor = link.partition("#")
        new_path = os.path.relpath(path_part, rel_dir)
        if anchor:
            new_path = f"{new_path}#{anchor}"
        return f"]({new_path})"

    return _MD_LINK_RE.sub(_rewrite, text)


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


def sync_file(path: Path, rendered: dict[str, str], dry_run: bool = False) -> bool:
    """
    Update markers in a single file. Returns True if file was changed.
    Skips silently if file doesn't exist or no markers present.

    ``rendered`` maps marker_id → rendered content for every supported marker.
    """
    rel_path = path.relative_to(REPO_ROOT)

    if not path.exists():
        print(f"  SKIP: {rel_path} (does not exist)")
        return False

    content = path.read_text(encoding="utf-8")
    original = content

    found_markers = []
    for marker_id, new_content in rendered.items():
        new_content = rewrite_links_relative(new_content, path.parent)
        content, found = update_marker(content, marker_id, new_content)
        if found:
            # short label = part after the colon
            found_markers.append(marker_id.split(":", 1)[-1])

    if not found_markers:
        print(f"  SKIP: {rel_path} (no markers found)")
        return False

    if content == original:
        print(f"  UNCHANGED: {rel_path} (markers: {', '.join(found_markers)})")
        return False

    if not dry_run:
        path.write_text(content, encoding="utf-8")

    action = "WOULD UPDATE" if dry_run else "✓ UPDATED"
    print(f"  {action}: {rel_path} (markers: {', '.join(found_markers)})")
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
    rendered = {
        CURRENT_LINE_MARKER: render_current_line(data),
        ROADMAP_TABLE_MARKER: render_roadmap_table(data),
        STATUS_LIST_MARKER: render_status_list(data),
        CURRENT_BLOCK_MARKER: render_current_block(data),
    }

    print(f"Phase status source: {PHASE_STATUS_FILE.relative_to(REPO_ROOT)}")
    print(f"Active phase line: {rendered[CURRENT_LINE_MARKER]}")
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
        if sync_file(target, rendered, dry_run=args.dry_run):
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
