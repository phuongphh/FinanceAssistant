"""Guard test: services flush, callers commit (Phase B1).

Layer contract (CLAUDE.md §0.1):
- Services own business logic, not the transaction boundary.
- Workers, routers, and scheduled jobs own the commit.

Committing inside a service creates partial-commit bugs in multi-step
flows (e.g. onboarding step_3 = set_name + set_goal + advance_step —
if step 3 commits early and step 2 rolls back, the DB is wedged).

This test greps service modules for ``db.commit()`` / ``.commit()``
calls and fails the build if any slip in. An allowlist below should
only ever be used while actively migrating a single service — keep
it empty whenever possible.
"""
from __future__ import annotations

import re
from pathlib import Path


SERVICES_DIR = Path(__file__).resolve().parents[1] / "services"

# Files whose commits we haven't migrated yet. Shrink to empty; PRs
# that extend this list must justify it in the commit message.
LEGACY_ALLOWLIST: set[str] = set()

# Match ``db.commit()`` or ``self.commit()`` etc. Stricter than a
# substring match: must look like a method call.
COMMIT_CALL = re.compile(r"\b(\w+)\.commit\s*\(\s*\)")


def test_services_do_not_commit():
    offenders: list[str] = []

    for path in SERVICES_DIR.rglob("*.py"):
        if path.name in LEGACY_ALLOWLIST:
            continue
        source = path.read_text()
        for match in COMMIT_CALL.finditer(source):
            # Ignore the allowed pattern in docstrings like "commit()",
            # which would sit inside triple-quoted strings — cheap
            # heuristic: ignore if the match is inside a backtick span
            # on the same line (docs reference).
            line_start = source.rfind("\n", 0, match.start()) + 1
            line_end = source.find("\n", match.end())
            if line_end == -1:
                line_end = len(source)
            line = source[line_start:line_end]
            if line.count("`") >= 2 or line.strip().startswith("#"):
                continue
            line_no = source.count("\n", 0, match.start()) + 1
            offenders.append(
                f"{path.relative_to(SERVICES_DIR.parent)}:{line_no}  {line.strip()}"
            )

    assert not offenders, (
        "Services must not call ``.commit()`` — the caller "
        "(worker/router/job) owns the transaction boundary. "
        "Use ``await db.flush()`` if you need the INSERT's generated "
        "id before returning. Offenders:\n  "
        + "\n  ".join(offenders)
    )


# ---------------------------------------------------------------------------
# Services depend on ports, not adapters (Phase B3).
# ---------------------------------------------------------------------------

FORBIDDEN_SERVICE_IMPORTS = [
    # Services should use the Notifier port instead of reaching into
    # the Telegram adapter directly. ``telegram_service`` is a legacy
    # name for today's Telegram adapter — the guard catches both the
    # flat module form and the future ``backend.adapters.*`` form.
    ("backend.services.telegram_service", "Use backend.ports.notifier.get_notifier"),
    ("backend.adapters.", "Services should depend on ports, not concrete adapters"),
]

# morning_report_service migrated in B3; others (gmail, ocr) still
# legitimately wrap third-party SDKs today — leave them for now and
# shrink the allowlist as each is ported behind its own port.
SERVICE_IMPORT_ALLOWLIST: set[str] = {
    # Example if we ever need to allow a legacy file:
    # "legacy_foo_service.py",
}


def test_services_depend_on_ports_not_adapters():
    offenders: list[str] = []

    for path in SERVICES_DIR.rglob("*.py"):
        if path.name in SERVICE_IMPORT_ALLOWLIST:
            continue
        # telegram_service.py IS the legacy adapter — skip self-scan.
        if path.name == "telegram_service.py":
            continue
        source = path.read_text()
        for forbidden, hint in FORBIDDEN_SERVICE_IMPORTS:
            if forbidden in source:
                # Only count actual imports, not comments or docstrings.
                for ln_no, line in enumerate(source.splitlines(), start=1):
                    stripped = line.strip()
                    if stripped.startswith("#"):
                        continue
                    if forbidden in line and (
                        stripped.startswith("import ")
                        or stripped.startswith("from ")
                    ):
                        offenders.append(
                            f"{path.relative_to(SERVICES_DIR.parent)}:{ln_no}  "
                            f"imports {forbidden!r} — {hint}"
                        )

    assert not offenders, (
        "Services must program against abstract ports, not concrete "
        "adapters. Offenders:\n  " + "\n  ".join(offenders)
    )
