"""Shared fakes for the Phase 5.1 suite.

``tests/`` has no ``__init__.py`` but ``tests/test_phase_5_1/`` does, so
pytest's rootdir insertion stops at ``tests/`` and a bare
``import backend`` fails. pytest imports this file before any test
module in the package, so the ``sys.path`` fix happens once here and
each test file keeps its imports at the top.

CI has no database — not Postgres and not even aiosqlite — so the fakes
below stand in for a session. :class:`FakeMediaSession` is not a generic
ORM emulator: it understands exactly the three statements
``media_url_service`` and ``cleanup_media`` issue, matched on the SQL
they compile to, and raises on anything else. A test can therefore never
pass because the fake quietly swallowed a query the real database would
have rejected — if the production code changes shape, the fake stops
recognising it and the suite fails loudly rather than silently.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.ports.media_storage import StoredObject  # noqa: E402


class InMemoryStorage:
    """:class:`~backend.ports.media_storage.MediaStorage` in a dict.

    Mirrors the filesystem adapter's contract where it matters: missing
    keys read as None and delete as False rather than raising, because
    both the resolver and the cleanup job depend on that.
    """

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.mtimes: dict[str, datetime] = {}
        self.write_error: Exception | None = None

    async def write(self, key: str, data: bytes) -> None:
        if self.write_error is not None:
            raise self.write_error
        self.objects[key] = data
        self.mtimes[key] = datetime.now(timezone.utc)

    async def read(self, key: str) -> bytes | None:
        return self.objects.get(key)

    async def delete(self, key: str) -> bool:
        self.mtimes.pop(key, None)
        return self.objects.pop(key, None) is not None

    async def list_keys(self) -> list[StoredObject]:
        return [
            StoredObject(key=key, modified_at=self.mtimes[key])
            for key in self.objects
        ]

    def age(self, key: str, moment: datetime) -> None:
        """Backdate a key's write time so the grace period has elapsed."""
        self.mtimes[key] = moment


class FakeMediaSession:
    """Stand-in for ``AsyncSession`` over a ``media_objects`` table.

    Holds rows in a list and answers the specific statements the service
    and the job issue. ``commits`` is counted rather than ignored: the
    service must never commit, and that is an assertion here, not a
    convention.
    """

    def __init__(self, rows: list | None = None) -> None:
        self.rows: list = list(rows or [])
        self.pending: list = []
        self.commits = 0
        self.flushes = 0

    # -- session surface -------------------------------------------------

    def add(self, row) -> None:
        self.pending.append(row)

    async def flush(self) -> None:
        self.flushes += 1
        # Mimics the DB assigning defaults at flush time. The real column
        # default is a Python-side uuid4, but SQLAlchemy only applies it
        # on INSERT, so an unflushed row genuinely has id=None.
        for row in self.pending:
            if getattr(row, "id", None) is None:
                row.id = uuid.uuid4()
            if getattr(row, "created_at", None) is None:
                row.created_at = datetime.now(timezone.utc)
        self.rows.extend(self.pending)
        self.pending = []

    async def commit(self) -> None:
        self.commits += 1
        await self.flush()

    async def rollback(self) -> None:
        # Matches a real rollback closely enough for the orphan test:
        # nothing that was only flushed becomes visible.
        self.pending = []

    async def execute(self, stmt):
        from sqlalchemy.sql import Select, Update

        if isinstance(stmt, Select):
            return self._run_select(stmt)
        if isinstance(stmt, Update):
            return self._run_update(stmt)
        raise AssertionError(f"FakeMediaSession got unexpected {type(stmt)}")

    # -- statement handling ----------------------------------------------

    def _run_select(self, stmt) -> "_FakeResult":
        compiled = stmt.compile()
        text = str(compiled)
        params = compiled.params

        if "media_objects.token_hash = " in text and "expires_at >" in text:
            # media_url_service.resolve. The cutoff comes from the bind
            # param rather than a fresh now(), so the fake filters on
            # exactly the instant the production code asked about.
            wanted = params["token_hash_1"]
            cutoff = params["expires_at_1"]
            hits = [
                row
                for row in self.rows
                if row.token_hash == wanted
                and row.deleted_at is None
                and row.expires_at > cutoff
            ]
            return _FakeResult(rows=hits, scalars=hits)

        if "expires_at <=" in text:
            # cleanup_media._sweep_expired — selects (id, storage_key).
            cutoff = params["expires_at_1"]
            hits = [
                row
                for row in self.rows
                if row.deleted_at is None and row.expires_at <= cutoff
            ]
            limit = params.get("param_1")
            if limit is not None:
                hits = hits[:limit]
            return _FakeResult(rows=hits, scalars=hits)

        if "media_objects.storage_key IN" in text:
            # cleanup_media._sweep_orphans — selects storage_key only, and
            # reads it through .scalars(), so the scalar list is strings.
            wanted = set(params["storage_key_1"])
            hits = [row for row in self.rows if row.storage_key in wanted]
            return _FakeResult(
                rows=hits, scalars=[row.storage_key for row in hits]
            )

        raise AssertionError(f"FakeMediaSession got unexpected SELECT:\n{text}")

    def _run_update(self, stmt) -> "_FakeResult":
        compiled = stmt.compile()
        text = str(compiled)
        params = compiled.params

        if "UPDATE media_objects" not in text or "deleted_at" not in text:
            raise AssertionError(
                f"FakeMediaSession got unexpected UPDATE:\n{text}"
            )

        stamped = params["deleted_at"]
        # ``id.in_([...])`` compiles to a single expanding bind holding the
        # whole list (``id_1``), not one param per element.
        targets = set(params["id_1"])
        for row in self.rows:
            if row.id in targets and row.deleted_at is None:
                row.deleted_at = stamped
        return _FakeResult(rows=[], scalars=[])


class _FakeResult:
    """Result proxy.

    ``rows`` are the ORM objects, which is what ``.all()`` consumers want
    (they read ``.id`` / ``.storage_key`` off them, exactly as they would
    off a real ``Row``). ``scalars`` is tracked separately because a
    ``select(MediaObject.storage_key)`` yields bare strings through
    ``.scalars()``, not row objects.
    """

    def __init__(self, rows: list, scalars: list) -> None:
        self._rows = rows
        self._scalars = scalars

    def all(self) -> list:
        return self._rows

    def scalar_one_or_none(self):
        if not self._scalars:
            return None
        if len(self._scalars) > 1:
            raise AssertionError("scalar_one_or_none got multiple rows")
        return self._scalars[0]

    def scalars(self) -> "_FakeScalars":
        return _FakeScalars(self._scalars)


class _FakeScalars:
    def __init__(self, values: list) -> None:
        self._values = values

    def all(self) -> list:
        return self._values

    def first(self):
        return self._values[0] if self._values else None
