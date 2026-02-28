"""SQLite task store for Initiative."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import Task, TaskStatus

logger = logging.getLogger("initiative.database")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    priority INTEGER NOT NULL DEFAULT 0,
    worker_id TEXT,
    result TEXT,
    error TEXT,
    retries INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 2,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class TaskStore:
    def __init__(self, db_path: str = "initiative.db"):
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        logger.debug("Database connected: %s", db_path)

    def add_task(self, title: str, description: str, priority: int = 0, max_retries: int = 2) -> int:
        now = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.execute(
            "INSERT INTO tasks (title, description, priority, max_retries, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (title, description, priority, max_retries, TaskStatus.PENDING, now, now),
        )
        self._conn.commit()
        task_id = cursor.lastrowid
        logger.info("Task added: id=%d title=%r", task_id, title)
        return task_id

    def get_task(self, task_id: int) -> Task | None:
        row = self._conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_task(row)

    def get_next_task(self) -> Task | None:
        row = self._conn.execute(
            "SELECT * FROM tasks WHERE status = ? ORDER BY priority DESC, created_at ASC LIMIT 1",
            (TaskStatus.PENDING,),
        ).fetchone()
        if row is None:
            logger.debug("No pending tasks available")
            return None
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
            (TaskStatus.IN_PROGRESS, now, row["id"]),
        )
        self._conn.commit()
        task = self._row_to_task(row)
        task.status = TaskStatus.IN_PROGRESS
        logger.info("Task started: id=%d title=%r", task.id, task.title)
        return task

    def complete_task(self, task_id: int, result: str = "") -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE tasks SET status = ?, result = ?, updated_at = ? WHERE id = ?",
            (TaskStatus.COMPLETED, result, now, task_id),
        )
        self._conn.commit()
        logger.info("Task completed: id=%d", task_id)

    def fail_task(self, task_id: int, error: str = "") -> Task | None:
        task = self.get_task(task_id)
        if task is None:
            return None
        now = datetime.now(timezone.utc).isoformat()
        if task.retries < task.max_retries:
            # Auto-retry: increment retries and set back to pending
            self._conn.execute(
                "UPDATE tasks SET status = ?, error = ?, retries = retries + 1, updated_at = ? WHERE id = ?",
                (TaskStatus.PENDING, error, now, task_id),
            )
            self._conn.commit()
            logger.info("Task auto-retried: id=%d retries=%d/%d", task_id, task.retries + 1, task.max_retries)
        else:
            # Max retries exceeded: mark as permanently failed
            self._conn.execute(
                "UPDATE tasks SET status = ?, error = ?, updated_at = ? WHERE id = ?",
                (TaskStatus.FAILED, error, now, task_id),
            )
            self._conn.commit()
            logger.info("Task permanently failed: id=%d", task_id)
        return self.get_task(task_id)

    def retry_task(self, task_id: int) -> Task | None:
        """Manually retry a failed task by resetting its status to pending."""
        task = self.get_task(task_id)
        if task is None:
            return None
        if task.status != TaskStatus.FAILED:
            return task
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE tasks SET status = ?, error = NULL, retries = 0, updated_at = ? WHERE id = ?",
            (TaskStatus.PENDING, now, task_id),
        )
        self._conn.commit()
        logger.info("Task manually retried: id=%d", task_id)
        return self.get_task(task_id)

    def list_tasks(self, status: TaskStatus | None = None) -> list[Task]:
        if status is not None:
            rows = self._conn.execute(
                "SELECT * FROM tasks WHERE status = ? ORDER BY priority DESC, created_at ASC",
                (str(status),),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM tasks ORDER BY priority DESC, created_at ASC"
            ).fetchall()
        return [self._row_to_task(row) for row in rows]

    def get_status(self) -> dict:
        rows = self._conn.execute(
            "SELECT status, COUNT(*) as count FROM tasks GROUP BY status"
        ).fetchall()
        counts = {str(s): 0 for s in TaskStatus}
        for row in rows:
            counts[row["status"]] = row["count"]
        return {
            "total": sum(counts.values()),
            **counts,
        }

    def _row_to_task(self, row: sqlite3.Row) -> Task:
        return Task(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            status=TaskStatus(row["status"]),
            priority=row["priority"],
            worker_id=row["worker_id"],
            result=row["result"],
            error=row["error"],
            retries=row["retries"],
            max_retries=row["max_retries"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
