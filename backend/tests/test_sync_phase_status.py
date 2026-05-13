"""Tests for ``scripts.sync_phase_status``.

The sync script is an ops tool, not part of the runtime — but it's
the engine behind a contract every doc consumer trusts ("if I edit
phase-status.yaml, the README changes"). The most painful failure
mode is silent: a regex bug that drops content but doesn't error.
These tests pin the behaviour we care about.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _import_sync_module():
    """Load ``scripts/sync_phase_status.py`` as a module without
    putting ``scripts/`` on sys.path globally (only this test needs it)."""
    path = REPO_ROOT / "scripts" / "sync_phase_status.py"
    spec = importlib.util.spec_from_file_location("sync_phase_status", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["sync_phase_status"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def sync_mod():
    return _import_sync_module()


@pytest.fixture
def sample_status(sync_mod):
    Phase = sync_mod.Phase
    PhaseStatus = sync_mod.PhaseStatus
    return PhaseStatus(
        current_phase="3.5",
        roadmap=[
            Phase(
                id="3A",
                name="Wealth Foundation",
                status="done",
                duration="4 tuần",
                detailed_doc="docs/current/phase-3a-detailed.md",
                issues_doc="",
                description="Asset model + net worth",
                completed_date="",
                icon="✅",
            ),
            Phase(
                id="3.5",
                name="Intent Understanding Layer",
                status="done",
                duration="3 tuần",
                detailed_doc="docs/current/phase-3.5-detailed.md",
                issues_doc="docs/current/phase-3.5-issues.md",
                description="Rule + LLM intent classifier",
                completed_date="2026-05-02",
                icon="✅",
            ),
            Phase(
                id="3B",
                name="Market Intelligence",
                status="next",
                duration="TBD",
                detailed_doc="",
                issues_doc="",
                description="Real market data",
                completed_date="",
                icon="📋",
            ),
        ],
    )


class TestRenderers:
    def test_current_line_uses_current_phase(self, sync_mod, sample_status):
        out = sync_mod.render_current_line(sample_status)
        assert "Phase 3.5" in out
        assert "Intent Understanding Layer" in out
        # Other phases must NOT appear in the one-line snippet.
        assert "Phase 3A" not in out
        assert "Phase 3B" not in out

    def test_status_list_marks_current(self, sync_mod, sample_status):
        out = sync_mod.render_status_list(sample_status)
        # Each phase appears as a bullet.
        assert "- ✅ Phase 3A" in out
        assert "- ✅ Phase 3.5" in out
        assert "- 📋 Phase 3B" in out
        # The current phase is annotated. Either "current" (in-progress)
        # or "just shipped" (done) — sample is done, expect the latter.
        assert "just shipped" in out

    def test_roadmap_table_bolds_current(self, sync_mod, sample_status):
        out = sync_mod.render_roadmap_table(sample_status)
        # Markdown table header.
        assert "| Phase | Status | Duration |" in out
        # Current row is bolded.
        assert "**Phase 3.5: Intent Understanding Layer**" in out
        # Non-current rows aren't bolded.
        assert "| Phase 3A: Wealth Foundation |" in out

    def test_current_block_links_detail_doc(self, sync_mod, sample_status):
        out = sync_mod.render_current_block(sample_status)
        assert "phase-3.5-detailed.md" in out
        assert "phase-3.5-issues.md" in out
        assert "Rule + LLM intent classifier" in out


class TestRewriteFile:
    """The marker rewriter is the part that bit us first time around —
    a regex group bug silently dropped END markers. These cases pin
    the contract: BEGIN + END both preserved, body replaced, no drift
    on second run."""

    def _write(self, tmp_path: Path, content: str) -> Path:
        path = tmp_path / "doc.md"
        path.write_text(content, encoding="utf-8")
        return path

    def test_rewrites_marked_section(self, sync_mod, sample_status, tmp_path):
        path = self._write(
            tmp_path,
            "intro\n"
            "<!-- BEGIN: phase-status:current-line -->\n"
            "<!-- END: phase-status:current-line -->\n"
            "outro\n",
        )
        changed = sync_mod.rewrite_file(path, sample_status)
        assert changed is True
        out = path.read_text()
        assert "<!-- BEGIN: phase-status:current-line -->" in out
        assert "<!-- END: phase-status:current-line -->" in out
        assert "Phase 3.5" in out
        assert out.startswith("intro\n")
        assert out.endswith("outro\n")

    def test_idempotent_on_second_run(self, sync_mod, sample_status, tmp_path):
        path = self._write(
            tmp_path,
            "<!-- BEGIN: phase-status:current-line -->\n"
            "<!-- END: phase-status:current-line -->\n",
        )
        sync_mod.rewrite_file(path, sample_status)
        first = path.read_text()
        changed = sync_mod.rewrite_file(path, sample_status)
        assert changed is False
        assert path.read_text() == first

    def test_two_separate_sections_in_one_file(
        self, sync_mod, sample_status, tmp_path
    ):
        path = self._write(
            tmp_path,
            "<!-- BEGIN: phase-status:current-line -->\n"
            "<!-- END: phase-status:current-line -->\n"
            "between\n"
            "<!-- BEGIN: phase-status:status-list -->\n"
            "<!-- END: phase-status:status-list -->\n",
        )
        sync_mod.rewrite_file(path, sample_status)
        out = path.read_text()
        # Both sections rendered + both END markers preserved.
        assert out.count("<!-- BEGIN: phase-status:") == 2
        assert out.count("<!-- END: phase-status:") == 2
        # The "between" filler stays put.
        assert "between\n" in out

    def test_unknown_marker_left_untouched(
        self, sync_mod, sample_status, tmp_path, capsys
    ):
        path = self._write(
            tmp_path,
            "<!-- BEGIN: phase-status:bogus-name -->\n"
            "original body\n"
            "<!-- END: phase-status:bogus-name -->\n",
        )
        sync_mod.rewrite_file(path, sample_status)
        out = path.read_text()
        # Body left alone; warning printed.
        assert "original body" in out
        captured = capsys.readouterr()
        assert "Unknown marker" in captured.err

    def test_returns_false_when_no_markers(
        self, sync_mod, sample_status, tmp_path
    ):
        path = self._write(tmp_path, "no markers here\n")
        assert sync_mod.rewrite_file(path, sample_status) is False

    def test_missing_file_returns_false(self, sync_mod, sample_status, tmp_path):
        missing = tmp_path / "nope.md"
        assert sync_mod.rewrite_file(missing, sample_status) is False


class TestRealRepoSyncIsClean:
    """Run the sync against the real repo files — they should already
    match the YAML (CI runs the script on every push). If this test
    fails locally, the dev forgot to run the script before committing."""

    def test_real_files_in_sync_with_yaml(self, sync_mod):
        status = sync_mod.load_status()
        for path in sync_mod.TARGET_FILES:
            if not path.exists():
                continue
            before = path.read_text(encoding="utf-8")
            sync_mod.rewrite_file(path, status)
            after = path.read_text(encoding="utf-8")
            assert before == after, (
                f"{path.relative_to(sync_mod.REPO_ROOT)} drifted from "
                "phase-status.yaml — run `python scripts/sync_phase_status.py` "
                "to fix."
            )
