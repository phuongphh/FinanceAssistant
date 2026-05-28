from pathlib import Path
import re


def test_alembic_revision_ids_fit_version_table_column() -> None:
    """Guardrail: alembic_version.version_num is varchar(32) by default."""
    revision_pattern = re.compile(r'^revision\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)

    too_long = []
    for migration_file in Path("alembic/versions").glob("*.py"):
        content = migration_file.read_text(encoding="utf-8")
        match = revision_pattern.search(content)
        if not match:
            continue
        revision = match.group(1)
        if len(revision) > 32:
            too_long.append((migration_file.name, revision, len(revision)))

    assert not too_long, (
        "Alembic revision id must be <= 32 chars to fit alembic_version.version_num. "
        f"Found: {too_long}"
    )
