import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_UNSET = object()

_MIGRATIONS: Dict[int, str] = {
    1: """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY,
        state TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        plan_hash TEXT NOT NULL,
        plan_path TEXT NOT NULL,
        bundle_path TEXT NOT NULL,
        current_step INTEGER NOT NULL DEFAULT 0,
        checkpoint_id TEXT,
        next_checkpoint TEXT,
        locked_by TEXT,
        locked_at TEXT,
        error TEXT,
        metadata_json TEXT
    );
    CREATE INDEX IF NOT EXISTS tasks_state_idx ON tasks(state);
    CREATE INDEX IF NOT EXISTS tasks_plan_hash_idx ON tasks(plan_hash);
    CREATE TABLE IF NOT EXISTS approvals (
        id TEXT PRIMARY KEY,
        plan_hash TEXT NOT NULL,
        checkpoint_id TEXT,
        approved_at TEXT NOT NULL,
        approved_by TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS approvals_lookup_idx ON approvals(plan_hash, checkpoint_id);
    """,
}


@dataclass(frozen=True)
class TaskRecord:
    id: str
    state: str
    created_at: str
    updated_at: str
    plan_hash: str
    plan_path: str
    bundle_path: str
    current_step: int
    checkpoint_id: Optional[str]
    next_checkpoint: Optional[str]
    locked_by: Optional[str]
    locked_at: Optional[str]
    error: Optional[str]
    metadata: Dict[str, Any]


@dataclass(frozen=True)
class ApprovalRecord:
    id: str
    plan_hash: str
    checkpoint_id: Optional[str]
    approved_at: str
    approved_by: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def apply_migrations(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    current = conn.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()[
        "v"
    ]
    current_version = int(current or 0)
    for version in sorted(_MIGRATIONS.keys()):
        if version <= current_version:
            continue
        with conn:
            conn.executescript(_MIGRATIONS[version])
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, _utc_now()),
            )


def ensure_task_store(db_path: Path) -> "TaskStore":
    store = TaskStore(db_path)
    return store


def _parse_metadata(value: Optional[str]) -> Dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    if isinstance(parsed, dict):
        return parsed
    return {}


def _task_from_row(row: sqlite3.Row) -> TaskRecord:
    return TaskRecord(
        id=row["id"],
        state=row["state"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        plan_hash=row["plan_hash"],
        plan_path=row["plan_path"],
        bundle_path=row["bundle_path"],
        current_step=int(row["current_step"]),
        checkpoint_id=row["checkpoint_id"],
        next_checkpoint=row["next_checkpoint"],
        locked_by=row["locked_by"],
        locked_at=row["locked_at"],
        error=row["error"],
        metadata=_parse_metadata(row["metadata_json"]),
    )


def _approval_from_row(row: sqlite3.Row) -> ApprovalRecord:
    return ApprovalRecord(
        id=row["id"],
        plan_hash=row["plan_hash"],
        checkpoint_id=row["checkpoint_id"],
        approved_at=row["approved_at"],
        approved_by=row["approved_by"],
    )


class TaskStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn = _connect(db_path)
        apply_migrations(self._conn)

    def close(self) -> None:
        self._conn.close()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def create_task(
        self,
        *,
        plan_hash: str,
        plan_path: Path,
        bundle_path: Path,
        metadata: Optional[Dict[str, Any]] = None,
        state: str = "queued",
        task_id: Optional[str] = None,
    ) -> TaskRecord:
        task_id = task_id or f"tsk_{uuid.uuid4().hex}"
        now = _utc_now()
        metadata_json = json.dumps(metadata) if metadata else None
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO tasks (
                    id, state, created_at, updated_at, plan_hash, plan_path, bundle_path,
                    current_step, checkpoint_id, next_checkpoint, locked_by, locked_at, error,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    state,
                    now,
                    now,
                    plan_hash,
                    str(plan_path),
                    str(bundle_path),
                    0,
                    None,
                    None,
                    None,
                    None,
                    None,
                    metadata_json,
                ),
            )
        return self.get_task(task_id)

    def get_task(self, task_id: str) -> TaskRecord:
        row = self._conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise KeyError(f"task not found: {task_id}")
        return _task_from_row(row)

    def list_tasks(
        self, *, state: Optional[str] = None, limit: int = 100, offset: int = 0
    ) -> List[TaskRecord]:
        params: List[Any] = []
        sql = "SELECT * FROM tasks"
        if state:
            sql += " WHERE state = ?"
            params.append(state)
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self._conn.execute(sql, params).fetchall()
        return [_task_from_row(row) for row in rows]

    def count_tasks_by_state(self, *, state: Optional[str] = None) -> Dict[str, int]:
        params: List[Any] = []
        sql = "SELECT state, COUNT(*) AS count FROM tasks"
        if state:
            sql += " WHERE state = ?"
            params.append(state)
        sql += " GROUP BY state ORDER BY state"
        rows = self._conn.execute(sql, params).fetchall()
        return {row["state"]: int(row["count"]) for row in rows}

    def claim_task(self, task_id: str, *, expected_state: str, worker_id: str) -> bool:
        now = _utc_now()
        with self._conn:
            updated = self._conn.execute(
                """
                UPDATE tasks
                SET state = ?, locked_by = ?, locked_at = ?, updated_at = ?
                WHERE id = ? AND state = ?
                """,
                ("running", worker_id, now, now, task_id, expected_state),
            )
        return updated.rowcount == 1

    def claim_next_task(self, *, worker_id: str) -> Optional[TaskRecord]:
        now = _utc_now()
        with self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            row = self._conn.execute(
                "SELECT * FROM tasks WHERE state = ? "
                "ORDER BY updated_at ASC, created_at ASC LIMIT 1",
                ("queued",),
            ).fetchone()
            if row is None:
                return None
            task_id = row["id"]
            updated = self._conn.execute(
                """
                UPDATE tasks
                SET state = ?, locked_by = ?, locked_at = ?, updated_at = ?
                WHERE id = ? AND state = ?
                """,
                ("running", worker_id, now, now, task_id, "queued"),
            )
            if updated.rowcount == 0:
                return None
        return self.get_task(task_id)

    def update_task_state(
        self,
        task_id: str,
        *,
        state: str,
        error: Optional[str] = None,
        checkpoint_id: Optional[str] = None,
        next_checkpoint: Optional[str] | object = _UNSET,
        current_step: Optional[int] = None,
        locked_by: Optional[str] = None,
        locked_at: Optional[str] = None,
        clear_lock: bool = False,
    ) -> TaskRecord:
        now = _utc_now()
        fields = ["state = ?", "updated_at = ?"]
        values: List[Any] = [state, now]
        if error is not None:
            fields.append("error = ?")
            values.append(error)
        if checkpoint_id is not None:
            fields.append("checkpoint_id = ?")
            values.append(checkpoint_id)
        if next_checkpoint is not _UNSET:
            fields.append("next_checkpoint = ?")
            values.append(next_checkpoint)
        if current_step is not None:
            fields.append("current_step = ?")
            values.append(current_step)
        if clear_lock:
            fields.append("locked_by = NULL")
            fields.append("locked_at = NULL")
        else:
            if locked_by is not None:
                fields.append("locked_by = ?")
                values.append(locked_by)
            if locked_at is not None:
                fields.append("locked_at = ?")
                values.append(locked_at)
        values.append(task_id)
        with self._conn:
            self._conn.execute(
                f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?",
                values,
            )
        return self.get_task(task_id)

    def record_approval(
        self,
        *,
        plan_hash: str,
        approved_by: str,
        checkpoint_id: Optional[str] = None,
    ) -> ApprovalRecord:
        approval_id = f"apr_{uuid.uuid4().hex}"
        now = _utc_now()
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO approvals (id, plan_hash, checkpoint_id, approved_at, approved_by)
                VALUES (?, ?, ?, ?, ?)
                """,
                (approval_id, plan_hash, checkpoint_id, now, approved_by),
            )
        row = self._conn.execute(
            "SELECT * FROM approvals WHERE id = ?", (approval_id,)
        ).fetchone()
        if row is None:
            raise RuntimeError("approval insert failed")
        return _approval_from_row(row)

    def latest_approval(
        self, *, plan_hash: str, checkpoint_id: Optional[str] = None
    ) -> Optional[ApprovalRecord]:
        if checkpoint_id is None:
            row = self._conn.execute(
                """
                SELECT * FROM approvals
                WHERE plan_hash = ? AND checkpoint_id IS NULL
                ORDER BY approved_at DESC
                LIMIT 1
                """,
                (plan_hash,),
            ).fetchone()
        else:
            row = self._conn.execute(
                """
                SELECT * FROM approvals
                WHERE plan_hash = ? AND checkpoint_id = ?
                ORDER BY approved_at DESC
                LIMIT 1
                """,
                (plan_hash, checkpoint_id),
            ).fetchone()
        if row is None:
            return None
        return _approval_from_row(row)

    def latest_approval_any(self, *, plan_hash: str) -> Optional[ApprovalRecord]:
        row = self._conn.execute(
            """
            SELECT * FROM approvals
            WHERE plan_hash = ?
            ORDER BY approved_at DESC
            LIMIT 1
            """,
            (plan_hash,),
        ).fetchone()
        if row is None:
            return None
        return _approval_from_row(row)

    def schema_version(self) -> int:
        row = self._conn.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()
        return int(row["v"] or 0)
