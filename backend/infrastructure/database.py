from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.core.compat import UTC
from backend.scheduler.models import TaskStatus


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self.connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    tool_id TEXT NOT NULL,
                    tool_version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    params_json TEXT NOT NULL,
                    current INTEGER NOT NULL DEFAULT 0,
                    total INTEGER,
                    progress REAL,
                    message TEXT NOT NULL DEFAULT '',
                    speed REAL,
                    success_count INTEGER NOT NULL DEFAULT 0,
                    failure_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    updated_at TEXT NOT NULL,
                    output_path TEXT,
                    source_task_id TEXT,
                    error_summary TEXT,
                    revision INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
                CREATE INDEX IF NOT EXISTS idx_tasks_status_created
                    ON tasks(status, created_at DESC);
                CREATE TABLE IF NOT EXISTS task_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    event_type TEXT NOT NULL,
                    level TEXT,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_task_events_task ON task_events(task_id, id);
                CREATE TABLE IF NOT EXISTS task_failures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    item TEXT NOT NULL,
                    error TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS task_conflicts (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    source_path TEXT NOT NULL,
                    target_path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    action TEXT,
                    scope TEXT,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_task_conflicts_pending
                    ON task_conflicts(task_id) WHERE status='pending';
                CREATE TABLE IF NOT EXISTS presets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    params_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self._lock, self.connect() as connection:
            row = connection.execute(
                "SELECT value_json FROM settings WHERE key=?",
                (key,),
            ).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value_json"])
        except (TypeError, json.JSONDecodeError):
            return default

    def set_settings(self, values: dict[str, Any]) -> None:
        now = utc_now()
        with self._lock, self.connect() as connection:
            connection.executemany(
                """
                INSERT INTO settings(key,value_json,updated_at) VALUES(?,?,?)
                ON CONFLICT(key) DO UPDATE SET
                    value_json=excluded.value_json,
                    updated_at=excluded.updated_at
                """,
                [
                    (key, json.dumps(value, ensure_ascii=False), now)
                    for key, value in values.items()
                ],
            )

    def clear_settings(self, keys: list[str]) -> None:
        if not keys:
            return
        placeholders = ",".join("?" for _ in keys)
        with self._lock, self.connect() as connection:
            connection.execute(
                f"DELETE FROM settings WHERE key IN ({placeholders})",  # noqa: S608
                keys,
            )

    def create_task(
        self,
        *,
        task_id: str,
        tool_id: str,
        tool_version: str,
        params: dict[str, Any],
        output_path: str,
        source_task_id: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        with self._lock, self.connect() as connection:
            connection.execute(
                """
                INSERT INTO tasks (
                    id, tool_id, tool_version, status, params_json, created_at,
                    updated_at, output_path, source_task_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    tool_id,
                    tool_version,
                    TaskStatus.PENDING,
                    json.dumps(params, ensure_ascii=False),
                    now,
                    now,
                    output_path,
                    source_task_id,
                ),
            )
            connection.execute(
                "INSERT INTO task_events(task_id,event_type,message,created_at) VALUES(?,?,?,?)",
                (task_id, "task.created", "任务已创建", now),
            )
        task = self.get_task(task_id)
        assert task is not None
        return task

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self._lock, self.connect() as connection:
            row = connection.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return self._task_from_row(row) if row else None

    def list_tasks(
        self,
        *,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM tasks"
        values: list[Any] = []
        if status:
            sql += " WHERE status=?"
            values.append(status)
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        values.extend((limit, offset))
        with self._lock, self.connect() as connection:
            rows = connection.execute(sql, values).fetchall()
        return [self._task_from_row(row) for row in rows]

    def list_pending(self, limit: int) -> list[dict[str, Any]]:
        with self._lock, self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM tasks WHERE status=? ORDER BY created_at ASC LIMIT ?",
                (TaskStatus.PENDING, limit),
            ).fetchall()
        return [self._task_from_row(row) for row in rows]

    def list_active(self, limit: int = 100) -> list[dict[str, Any]]:
        statuses = (
            TaskStatus.PENDING,
            TaskStatus.RUNNING,
            TaskStatus.PAUSED,
            TaskStatus.CANCELLING,
        )
        placeholders = ",".join("?" for _ in statuses)
        with self._lock, self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM tasks WHERE status IN ({placeholders})
                ORDER BY
                    CASE status
                        WHEN 'running' THEN 0
                        WHEN 'paused' THEN 1
                        WHEN 'cancelling' THEN 2
                        ELSE 3
                    END,
                    created_at ASC
                LIMIT ?
                """,  # noqa: S608
                (*statuses, limit),
            ).fetchall()
        return [self._task_from_row(row) for row in rows]

    def list_history(
        self,
        *,
        statuses: list[str] | None = None,
        tool_id: str | None = None,
        query: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int, dict[str, int]]:
        terminal_statuses = [
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.INTERRUPTED,
        ]

        def filters(include_selected_statuses: bool) -> tuple[str, list[Any]]:
            clauses: list[str] = []
            values: list[Any] = []
            selected = statuses if include_selected_statuses and statuses else terminal_statuses
            placeholders = ",".join("?" for _ in selected)
            clauses.append(f"status IN ({placeholders})")
            values.extend(selected)
            if tool_id:
                clauses.append("tool_id=?")
                values.append(tool_id)
            if date_from:
                clauses.append("created_at>=?")
                values.append(date_from)
            if date_to:
                clauses.append("created_at<=?")
                values.append(date_to)
            if query:
                pattern = f"%{query.strip()}%"
                clauses.append(
                    "(id LIKE ? OR output_path LIKE ? OR message LIKE ? OR error_summary LIKE ?)"
                )
                values.extend((pattern, pattern, pattern, pattern))
            return " AND ".join(clauses), values

        where_sql, values = filters(True)
        counts_where_sql, counts_values = filters(False)
        with self._lock, self.connect() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) FROM tasks WHERE {where_sql}",  # noqa: S608
                values,
            ).fetchone()[0]
            rows = connection.execute(
                f"""
                SELECT * FROM tasks WHERE {where_sql}
                ORDER BY created_at DESC LIMIT ? OFFSET ?
                """,  # noqa: S608
                (*values, limit, offset),
            ).fetchall()
            count_rows = connection.execute(
                f"""
                SELECT status,COUNT(*) AS count FROM tasks
                WHERE {counts_where_sql} GROUP BY status
                """,  # noqa: S608
                counts_values,
            ).fetchall()
        counts = {status.value: 0 for status in terminal_statuses}
        counts.update({row["status"]: row["count"] for row in count_rows})
        return [self._task_from_row(row) for row in rows], total, counts

    def delete_task(self, task_id: str) -> bool:
        with self._lock, self.connect() as connection:
            cursor = connection.execute("DELETE FROM tasks WHERE id=?", (task_id,))
            return cursor.rowcount > 0

    def update_task(self, task_id: str, **fields: Any) -> dict[str, Any]:
        allowed = {
            "status",
            "current",
            "total",
            "progress",
            "message",
            "speed",
            "success_count",
            "failure_count",
            "started_at",
            "finished_at",
            "error_summary",
            "output_path",
        }
        updates = {key: value for key, value in fields.items() if key in allowed}
        updates["updated_at"] = utc_now()
        assignments = ", ".join(f"{key}=?" for key in updates)
        values = list(updates.values())
        values.append(task_id)
        with self._lock, self.connect() as connection:
            connection.execute(
                f"UPDATE tasks SET {assignments}, revision=revision+1 WHERE id=?",  # noqa: S608
                values,
            )
        task = self.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        return task

    def append_event(
        self,
        task_id: str,
        event_type: str,
        message: str,
        level: str | None = None,
    ) -> None:
        with self._lock, self.connect() as connection:
            connection.execute(
                """
                INSERT INTO task_events(task_id,event_type,level,message,created_at)
                VALUES(?,?,?,?,?)
                """,
                (task_id, event_type, level, message, utc_now()),
            )

    def add_failure(self, task_id: str, item: str, error: str) -> None:
        with self._lock, self.connect() as connection:
            connection.execute(
                "INSERT INTO task_failures(task_id,item,error,created_at) VALUES(?,?,?,?)",
                (task_id, item, error, utc_now()),
            )

    def get_logs(self, task_id: str, after_id: int = 0, limit: int = 500) -> list[dict[str, Any]]:
        with self._lock, self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id,event_type,level,message,created_at FROM task_events
                WHERE task_id=? AND id>? ORDER BY id ASC LIMIT ?
                """,
                (task_id, after_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_failures(self, task_id: str) -> list[dict[str, Any]]:
        with self._lock, self.connect() as connection:
            rows = connection.execute(
                "SELECT id,item,error,created_at FROM task_failures WHERE task_id=? ORDER BY id",
                (task_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_conflict(
        self,
        *,
        conflict_id: str,
        task_id: str,
        source_path: str,
        target_path: str,
    ) -> dict[str, Any]:
        now = utc_now()
        with self._lock, self.connect() as connection:
            connection.execute(
                """
                INSERT INTO task_conflicts(
                    id,task_id,source_path,target_path,status,created_at
                ) VALUES(?,?,?,?,?,?)
                """,
                (conflict_id, task_id, source_path, target_path, "pending", now),
            )
        conflict = self.get_pending_conflict(task_id)
        assert conflict is not None
        return conflict

    def get_pending_conflict(self, task_id: str) -> dict[str, Any] | None:
        with self._lock, self.connect() as connection:
            row = connection.execute(
                """
                SELECT id,task_id,source_path,target_path,status,action,scope,
                       created_at,resolved_at
                FROM task_conflicts WHERE task_id=? AND status='pending'
                ORDER BY created_at DESC LIMIT 1
                """,
                (task_id,),
            ).fetchone()
        return dict(row) if row else None

    def resolve_conflict(
        self,
        task_id: str,
        conflict_id: str,
        action: str,
        scope: str,
    ) -> dict[str, Any]:
        now = utc_now()
        with self._lock, self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE task_conflicts SET status='resolved',action=?,scope=?,resolved_at=?
                WHERE id=? AND task_id=? AND status='pending'
                """,
                (action, scope, now, conflict_id, task_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("待处理冲突不存在或已经解决")
            row = connection.execute(
                """
                SELECT id,task_id,source_path,target_path,status,action,scope,
                       created_at,resolved_at
                FROM task_conflicts WHERE id=?
                """,
                (conflict_id,),
            ).fetchone()
        assert row is not None
        return dict(row)

    def abandon_pending_conflict(self, task_id: str) -> None:
        with self._lock, self.connect() as connection:
            connection.execute(
                """
                UPDATE task_conflicts SET status='abandoned',resolved_at=?
                WHERE task_id=? AND status='pending'
                """,
                (utc_now(), task_id),
            )

    def mark_interrupted(self) -> int:
        now = utc_now()
        statuses = (
            TaskStatus.RUNNING,
            TaskStatus.PAUSED,
            TaskStatus.CANCELLING,
        )
        placeholders = ",".join("?" for _ in statuses)
        with self._lock, self.connect() as connection:
            cursor = connection.execute(
                f"""
                UPDATE tasks SET status=?, message=?, error_summary=?, finished_at=?,
                    updated_at=?, revision=revision+1
                WHERE status IN ({placeholders})
                """,  # noqa: S608
                (
                    TaskStatus.INTERRUPTED,
                    "应用异常退出，任务已中断",
                    "应用在任务运行期间退出",
                    now,
                    now,
                    *statuses,
                ),
            )
            connection.execute(
                """
                UPDATE task_conflicts SET status='abandoned',resolved_at=?
                WHERE status='pending'
                """,
                (now,),
            )
            return cursor.rowcount

    def _task_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["params"] = json.loads(result.pop("params_json"))
        result["pending_conflict"] = self.get_pending_conflict(result["id"])
        return result
