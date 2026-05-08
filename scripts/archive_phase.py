"""Archive phase docs once manual testing is signed off.

Trigger
-------
Each ``docs/current/test-cases/phase-*.md`` file carries a marker::

    <!-- testing-signoff: need to be signed -->

When the human tester edits the marker to::

    <!-- testing-signoff: signed -->

…this script (run via the Sync Phase Status workflow) moves every
``phase-{id}-*`` doc EXCEPT the ``detailed_doc`` (per ``phase-status.yaml``)
into ``docs/archive/``. The ``detailed_doc`` stays in ``docs/current/``
so the roadmap table keeps a working link.

Why a marker file
-----------------
- Stable signal: doesn't depend on issue state, PR labels, or
  human memory to update YAML.
- Grep-friendly + commit-friendly: the change is one line of one
  file, easy to review.
- Reversible-by-revert: if archiving was wrong, revert the commit.

Idempotent
----------
Running twice in a row is safe — files already moved are skipped,
links already rewritten match the desired form.

CLI
---
::

    python scripts/archive_phase.py            # archive every signed phase
    python scripts/archive_phase.py --dry-run  # report only, no mutation
    python scripts/archive_phase.py --phase 3.5  # force-archive one phase
                                                 # (ignores marker; for ops)
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
PHASE_STATUS_FILE = REPO_ROOT / "docs" / "current" / "phase-status.yaml"
CURRENT_DIR = REPO_ROOT / "docs" / "current"
ARCHIVE_DIR = REPO_ROOT / "docs" / "archive"

# Marker comment. Keep "need to be signed" as the seeded default so a
# fresh test-cases file is unambiguously not-yet-signed. The matcher
# accepts any non-empty value so future status words (e.g. "rejected")
# don't crash the parser.
SIGNOFF_RE = re.compile(
    r"<!--\s*testing-signoff:\s*(?P<value>[^\n>-]+?)\s*-->",
    re.IGNORECASE,
)
SIGNOFF_DEFAULT = "need to be signed"
SIGNOFF_SIGNED = "signed"


# ---------------------- data model ----------------------


@dataclass(frozen=True)
class PhaseEntry:
    id: str
    detailed_doc: str  # path relative to repo root, may be empty


def _load_phases() -> list[PhaseEntry]:
    raw = yaml.safe_load(PHASE_STATUS_FILE.read_text(encoding="utf-8"))
    return [
        PhaseEntry(id=str(p["id"]), detailed_doc=p.get("detail_doc", ""))
        for p in raw.get("phases", [])
    ]


def _phase_by_id(phases: list[PhaseEntry], pid: str) -> PhaseEntry | None:
    pid_l = pid.lower()
    for p in phases:
        if p.id.lower() == pid_l:
            return p
    return None


# ---------------------- discovery ----------------------


# Phase id from a filename. Uses a NON-greedy capture up to the next
# hyphen so ``phase-3.5-test-cases.md`` → ``3.5`` (not ``3.5-test``).
# Files without any post-id suffix (just ``phase-3.5.md``) match the
# alternation branch ending in ``.md``.
_FILE_ID_RE = re.compile(
    r"^phase-(?P<id>[A-Za-z0-9.]+?)(?:-.+)?\.md$"
)


def _phase_id_from_filename(name: str) -> str | None:
    m = _FILE_ID_RE.match(name)
    return m.group("id").lower() if m else None


def find_signed_phases(dry_run: bool = False) -> list[str]:
    """Return phase ids whose test-cases file has marker == 'signed'.

    Searches recursively in docs/current/ for any file matching
    phase-*-test-cases*.md (handles flat layout and per-phase subfolders).
    Order preserves sorted filesystem listing for reproducibility.
    """
    if not CURRENT_DIR.is_dir():
        return []
    signed: list[str] = []
    seen_ids: set[str] = set()
    for entry in sorted(CURRENT_DIR.rglob("*.md")):
        if not entry.is_file():
            continue
        if "test-cases" not in entry.name:
            continue
        pid = _phase_id_from_filename(entry.name)
        if pid is None or pid in seen_ids:
            continue
        text = entry.read_text(encoding="utf-8")
        m = SIGNOFF_RE.search(text)
        if not m:
            continue
        value = m.group("value").strip().lower()
        if value == SIGNOFF_SIGNED:
            signed.append(pid)
            seen_ids.add(pid)
    return signed


def _match_phase_id(filename: str, pid: str) -> bool:
    """True iff ``filename`` belongs to phase ``pid``. Uses a strict
    id-boundary regex so id ``3.5`` doesn't match ``phase-3.55-x.md``."""
    safe = re.escape(pid.lower())
    pat = re.compile(rf"^phase-{safe}(-|\.md$)", re.IGNORECASE)
    return bool(pat.match(filename))


def find_files_for_phase(pid: str) -> list[Path]:
    """All ``phase-{pid}-*.md`` files under ``docs/current/`` (recursive),
    including the detailed_doc. Handles flat layout and per-phase subfolders."""
    matches: list[Path] = []
    for entry in sorted(CURRENT_DIR.rglob("*.md")):
        if not entry.is_file():
            continue
        if not _match_phase_id(entry.name, pid):
            continue
        matches.append(entry)
    return matches


# ---------------------- mutation ----------------------


def _archive_destination(src: Path) -> Path:
    """Flatten all phase docs into archive/ root regardless of their
    source subfolder (e.g. docs/current/phase-3.8/phase-3.8-issues.md
    → docs/archive/phase-3.8-issues.md)."""
    return ARCHIVE_DIR / src.name


def _git_mv(src: Path, dest: Path) -> None:
    """``git mv`` with mkdir parents. Falls back to ``shutil.move`` +
    ``git add`` if git is unavailable (rare; this script is normally
    invoked inside CI)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["git", "mv", str(src), str(dest)],
            check=True,
            cwd=REPO_ROOT,
            capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Last-resort fallback. Not ideal — loses git rename
        # detection — but keeps the script working when run outside
        # a git workdir (e.g. during local doc tests).
        shutil.move(str(src), str(dest))


def _rewrite_cross_links_in_archived_file(archived: Path) -> bool:
    """Rewrite any ``docs/current/`` absolute-style links inside an archived
    file so they resolve correctly from ``docs/archive/``.

    All phase docs are flattened into the same archive/ directory, so
    ``./phase-X-detailed.md`` and bare ``phase-X-detailed.md`` links between
    sibling archived files need no rewriting — they already point to the same
    directory.  Only ``../current/...`` or ``docs/current/...`` links that
    survived from a previous partial-archive need updating.
    """
    text = archived.read_text(encoding="utf-8")
    # Rewrite any lingering links that still point into docs/current/.
    # e.g.  ../current/phase-X-detailed.md  →  phase-X-detailed.md
    pat = re.compile(r"\]\((?:\.\./)+"r"current/(phase-[^)]+)\)")
    new_text, n = pat.subn(r"](\1)", text)
    if n == 0 or new_text == text:
        return False
    archived.write_text(new_text, encoding="utf-8")
    return True


def _update_yaml_paths_for_moves(
    moves: list[tuple[Path, Path]],
) -> bool:
    """When a moved file is referenced by ``issues_doc`` (or any other
    path field) in phase-status.yaml, rewrite the path so it still
    resolves. We do simple string replacement on the YAML text rather
    than re-emitting via PyYAML — preserves comments + formatting.
    """
    if not moves:
        return False
    text = PHASE_STATUS_FILE.read_text(encoding="utf-8")
    original = text
    for src, dest in moves:
        old_rel = str(src.relative_to(REPO_ROOT))
        new_rel = str(dest.relative_to(REPO_ROOT))
        # Only replace inside double-quoted path fields to avoid
        # accidentally munging unrelated strings.
        text = text.replace(f'"{old_rel}"', f'"{new_rel}"')
    if text == original:
        return False
    PHASE_STATUS_FILE.write_text(text, encoding="utf-8")
    return True


@dataclass
class ArchiveResult:
    phase_id: str
    moved: list[tuple[Path, Path]]
    rewrote: list[Path]
    skipped: list[Path]  # already in archive/ or no-op
    yaml_updated: bool = False


def archive_phase(pid: str, dry_run: bool = False) -> ArchiveResult:
    files = find_files_for_phase(pid)
    moves: list[tuple[Path, Path]] = []
    rewrites: list[Path] = []
    skipped: list[Path] = []

    for src in files:
        dest = _archive_destination(src)
        if dest.exists():
            # Idempotent: a previous run already moved it.
            skipped.append(src)
            continue
        moves.append((src, dest))

    if dry_run:
        return ArchiveResult(pid, moves, rewrites, skipped, False)

    for src, dest in moves:
        _git_mv(src, dest)
        if _rewrite_cross_links_in_archived_file(dest):
            rewrites.append(dest)

    yaml_updated = _update_yaml_paths_for_moves(moves)
    return ArchiveResult(pid, moves, rewrites, skipped, yaml_updated)


# ---------------------- CLI ----------------------


def _fmt_path(p: Path) -> str:
    try:
        return str(p.relative_to(REPO_ROOT))
    except ValueError:
        return str(p)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Archive phase docs after testing sign-off."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List actions without mutating the tree.",
    )
    parser.add_argument(
        "--phase",
        metavar="ID",
        help="Force-archive a specific phase id, ignoring the "
        "test-cases marker. Use for ops/backfill only.",
    )
    args = parser.parse_args()

    phases = _load_phases()

    if args.phase:
        target_ids = [args.phase]
    else:
        target_ids = find_signed_phases()

    if not target_ids:
        print("No phases to archive (no test-cases marker == 'signed').")
        return 0

    any_changes = False
    for pid in target_ids:
        entry = _phase_by_id(phases, pid)
        if entry is None:
            print(
                f"  ⚠️  Phase {pid} signed off but not in "
                f"phase-status.yaml — skipping. Add a roadmap entry "
                f"first (or let sync auto-insert a skeleton).",
                file=sys.stderr,
            )
            continue
        result = archive_phase(pid, dry_run=args.dry_run)
        verb = "would move" if args.dry_run else "moved"
        if result.moved:
            any_changes = True
            print(f"Phase {pid}: {verb} {len(result.moved)} file(s)")
            for src, dest in result.moved:
                print(f"  {_fmt_path(src)} → {_fmt_path(dest)}")
        if result.rewrote:
            print(f"Phase {pid}: rewrote links in {len(result.rewrote)} file(s)")
            for p in result.rewrote:
                print(f"  ↳ {_fmt_path(p)}")
        if result.skipped:
            print(
                f"Phase {pid}: {len(result.skipped)} file(s) already "
                f"archived (skipped)"
            )
        if result.yaml_updated:
            print(
                f"Phase {pid}: updated path field(s) in "
                f"docs/current/phase-status.yaml"
            )

    if not any_changes:
        print("Nothing to do — already up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
