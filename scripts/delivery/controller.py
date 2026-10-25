"""Persistent admission/lease ledger owned by a trusted controller, not by a worker.

No timer steals an expired lease. Confirm executor death before reconciliation.
Keep this DB outside workspaces, under a different OS identity from product workers.
"""

from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo
from decimal import Decimal, ROUND_CEILING
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import sqlite3
import time
import uuid

ACTIVE = ("reserved", "running", "orphaned")
TERMINAL = (
    "review_ready",
    "blocked",
    "test_failed",
    "timeout",
    "auth_failed",
    "rate_limited",
    "infra_failed",
    "scope_violation",
    "cancelled",
)


class Denied(RuntimeError):
    pass


class LeaseLost(Denied):
    pass


class DuplicateRequest(Denied):
    def __init__(self, run_id):
        self.run_id = run_id
        super().__init__(
            "Event already recorded; use existing receipt, never start another executor"
        )


def digest(task):
    return hashlib.sha256(
        json.dumps(task, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def micros(value):
    n = Decimal(str(value))
    if not n.is_finite() or n <= 0:
        raise Denied("Budget must be positive and finite")
    return int((n * 1000000).to_integral_value(rounding=ROUND_CEILING))


class Ledger:
    def __init__(
        self,
        directory: Path,
        *,
        daily_usd,
        approvers,
        clock=time.time,
        budget_timezone="Asia/Ho_Chi_Minh",
    ):
        self.directory = Path(directory).absolute()
        if self.directory.is_symlink():
            raise Denied("State directory cannot be a symlink")
        self.directory.mkdir(parents=True, mode=0o700, exist_ok=True)
        st = self.directory.stat()
        if st.st_uid != os.getuid() or st.st_mode & 0o077:
            raise Denied("Controller state must be privately owned (0700)")
        self.daily = micros(daily_usd)
        self.approvers = frozenset(approvers)
        self.clock = clock
        self.budget_timezone = ZoneInfo(budget_timezone)
        path = self.directory / "ledger.sqlite"
        if path.is_symlink():
            raise Denied("State file cannot be a symlink")
        if not path.exists():
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        if path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
            raise Denied("Controller DB must be privately owned (0600)")
        self.db = sqlite3.connect(path, timeout=10, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
          PRAGMA journal_mode=WAL;
          PRAGMA foreign_keys=ON;
          CREATE TABLE IF NOT EXISTS grants(
            task_id TEXT PRIMARY KEY, repository TEXT NOT NULL, issue INTEGER NOT NULL,
            fingerprint TEXT NOT NULL, actor TEXT NOT NULL, approval_ref TEXT NOT NULL,
            task_budget INTEGER NOT NULL, max_attempts INTEGER NOT NULL, max_seconds INTEGER NOT NULL,
            revoked INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL);
          CREATE TABLE IF NOT EXISTS runs(
            run_id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, task_id TEXT NOT NULL REFERENCES grants(task_id),
            repository TEXT NOT NULL, issue INTEGER NOT NULL, engine TEXT NOT NULL,
            phase TEXT NOT NULL, token TEXT NOT NULL, expires REAL NOT NULL,
            started REAL NOT NULL, deadline REAL NOT NULL, day TEXT NOT NULL, reserved INTEGER NOT NULL,
            session_id TEXT, checkpoint TEXT, evidence TEXT);
          CREATE UNIQUE INDEX IF NOT EXISTS active_issue ON runs(repository,issue)
            WHERE phase IN ('reserved','running','orphaned');
        """)

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def approve(self, task, *, actor, verified_reference):
        # This method is only for the authenticated operator/controller endpoint.
        # No prompt/issue/model invocation is allowed to call it.
        if (
            actor not in self.approvers
            or verified_reference != task["approval"]["reference"]
        ):
            raise Denied("No trusted approval")
        limits = task["limits"]
        seconds = int(limits["max_minutes"]) * 60
        attempts = int(limits["max_fix_rounds"]) + 1
        if not (0 < seconds <= 7200 and 1 <= attempts <= 3):
            raise Denied("Limits exceed policy")
        fp = digest(task)
        with self.transaction():
            old = self.db.execute(
                "SELECT * FROM grants WHERE task_id=?", (task["task_id"],)
            ).fetchone()
            if old:
                if old["fingerprint"] != fp or old["revoked"]:
                    raise Denied("Grant differs or revoked")
                return
            self.db.execute(
                "INSERT INTO grants VALUES(?,?,?,?,?,?,?,?,?,0,?)",
                (
                    task["task_id"],
                    task["repository"],
                    task["issue_number"],
                    fp,
                    actor,
                    verified_reference,
                    micros(limits["max_cost_usd"]),
                    attempts,
                    seconds,
                    self.clock(),
                ),
            )

    def acquire(self, task, *, request_id, reservation_usd, ttl=30):
        now = self.clock()
        amount = micros(reservation_usd)
        if not isinstance(request_id, str) or not request_id or len(request_id) > 256:
            raise Denied("Stable request ID required")
        if not 2 <= ttl <= 300:
            raise Denied("Lease TTL out of bounds")
        day = datetime.fromtimestamp(now, self.budget_timezone).date().isoformat()
        with self.transaction():
            grant = self.db.execute(
                "SELECT * FROM grants WHERE task_id=?", (task["task_id"],)
            ).fetchone()
            if not grant or grant["revoked"] or grant["fingerprint"] != digest(task):
                raise Denied("Task not admitted by trusted controller")
            existing = self.db.execute(
                "SELECT run_id,task_id FROM runs WHERE request_id=?", (request_id,)
            ).fetchone()
            if existing:
                if existing["task_id"] != task["task_id"]:
                    raise Denied("Event ID belongs to another task")
                raise DuplicateRequest(existing["run_id"])
            if self.db.execute(
                "SELECT 1 FROM runs WHERE task_id=? AND phase='review_ready'",
                (task["task_id"],),
            ).fetchone():
                raise Denied("Task already review-ready; do not execute it again")
            # Expiry is a signal to reconcile, never permission to replace a live process.
            if self.db.execute(
                "SELECT 1 FROM runs WHERE phase IN ('reserved','running','orphaned')"
            ).fetchone():
                raise Denied(
                    "Global concurrency is 1; active/expired executor must settle first"
                )
            history = self.db.execute(
                "SELECT COUNT(*) AS n,COALESCE(SUM(reserved),0) AS spent,COALESCE(SUM(MAX(0,expires-started)),0) AS elapsed FROM runs WHERE task_id=?",
                (task["task_id"],),
            ).fetchone()
            remaining = grant["max_seconds"] - math.ceil(history["elapsed"])
            if remaining <= 0:
                raise Denied("Task time budget exhausted")
            if history["n"] >= grant["max_attempts"]:
                raise Denied("Task attempt limit exhausted")
            if history["spent"] + amount > grant["task_budget"]:
                raise Denied("Task budget exhausted")
            daily = self.db.execute(
                "SELECT COALESCE(SUM(reserved),0) FROM runs WHERE day=?", (day,)
            ).fetchone()[0]
            if daily + amount > self.daily:
                raise Denied("Daily reservation budget exhausted")
            run_id = str(uuid.uuid4())
            token = secrets.token_hex(24)
            self.db.execute(
                "INSERT INTO runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    run_id,
                    request_id,
                    task["task_id"],
                    task["repository"],
                    task["issue_number"],
                    task["engine"],
                    "reserved",
                    token,
                    min(now + ttl, now + remaining),
                    now,
                    now + remaining,
                    day,
                    amount,
                    None,
                    None,
                    None,
                ),
            )
            return {
                "run_id": run_id,
                "token": token,
                "max_seconds": remaining,
                "reservation_usd": str(Decimal(amount) / 1000000),
            }

    def _owned(self, run_id, token, *, allow_expired=False):
        row = self.db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if (
            not row
            or not secrets.compare_digest(row["token"], token)
            or row["phase"] not in ACTIVE
            or (not allow_expired and row["expires"] <= self.clock())
        ):
            raise LeaseLost("Lease no longer valid; stop executor and do not publish")
        grant = self.db.execute(
            "SELECT revoked FROM grants WHERE task_id=?", (row["task_id"],)
        ).fetchone()
        if grant["revoked"]:
            raise LeaseLost("Approval revoked; stop executor")
        return row

    def heartbeat(self, run_id, token, *, ttl=30, session_id=None, checkpoint=None):
        if not 2 <= ttl <= 300:
            raise Denied("Lease TTL out of bounds")
        with self.transaction():
            row = self._owned(run_id, token)
            self.db.execute(
                "UPDATE runs SET phase=?,expires=?,session_id=?,checkpoint=? WHERE run_id=?",
                (
                    "running",
                    min(self.clock() + ttl, row["deadline"]),
                    session_id or row["session_id"],
                    checkpoint or row["checkpoint"],
                    run_id,
                ),
            )

    def finish(
        self,
        run_id,
        token,
        *,
        status,
        evidence,
        gate_passed=False,
        scope_passed=False,
        executor_stopped=False,
    ):
        if status not in TERMINAL or not evidence:
            raise Denied("Terminal outcome/evidence required")
        if status == "review_ready" and not (gate_passed and scope_passed):
            raise Denied(
                "Independent gates and scope checks required; model done is insufficient"
            )
        with self.transaction():
            self._owned(
                run_id,
                token,
                allow_expired=executor_stopped and status != "review_ready",
            )
            # Full reservation remains spent even when cost is unknown; no unsafe refund.
            self.db.execute(
                "UPDATE runs SET phase=?,evidence=?,expires=? WHERE run_id=?",
                (status, evidence, self.clock(), run_id),
            )

    def reconcile_dead(self, run_id, *, actor, executor_death_receipt):
        if actor not in self.approvers or not executor_death_receipt:
            raise Denied(
                "Verified executor death receipt required from controller/operator"
            )
        with self.transaction():
            row = self.db.execute(
                "SELECT * FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if not row or row["phase"] not in ACTIVE:
                raise Denied("No active run to reconcile")
            self.db.execute(
                "UPDATE runs SET phase=?,evidence=?,expires=? WHERE run_id=?",
                ("cancelled", executor_death_receipt, self.clock(), run_id),
            )

    def revoke(self, task_id, *, actor):
        if actor not in self.approvers:
            raise Denied("Only trusted approver may revoke")
        self.db.execute("UPDATE grants SET revoked=1 WHERE task_id=?", (task_id,))

    def status(self):
        # Never expose fencing tokens or full task content to workers/PM.
        rows = [
            dict(r)
            for r in self.db.execute(
                "SELECT run_id,request_id,task_id,repository,issue,engine,phase,expires,day,reserved,session_id,checkpoint,evidence FROM runs ORDER BY started"
            )
        ]
        for row in rows:
            row["lease_expired"] = (
                row["phase"] in ACTIVE and row["expires"] <= self.clock()
            )
        return rows
