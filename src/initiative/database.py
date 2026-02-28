"""SQLite task store for Initiative."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone

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

CREATE TABLE IF NOT EXISTS task_dependencies (
    task_id INTEGER NOT NULL,
    depends_on_id INTEGER NOT NULL,
    PRIMARY KEY (task_id, depends_on_id),
    FOREIGN KEY (task_id) REFERENCES tasks(id),
    FOREIGN KEY (depends_on_id) REFERENCES tasks(id)
);

CREATE TABLE IF NOT EXISTS task_tags (
    task_id INTEGER,
    tag TEXT,
    PRIMARY KEY (task_id, tag),
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);
"""


class TaskStore:
    def __init__(self, db_path: str = "initiative.db"):
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, timeout=5.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        logger.debug("Database connected: %s", db_path)

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
        logger.debug("Database closed: %s", self._db_path)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def __del__(self):
        try:
            self._conn.close()
        except Exception:
            pass

    def add_task(
        self,
        title: str,
        description: str,
        priority: int = 0,
        max_retries: int = 2,
        depends_on: list[int] | None = None,
        tags: list[str] | None = None,
    ) -> int:
        if depends_on:
            for dep_id in depends_on:
                if self._would_create_cycle(dep_id, set()):
                    raise ValueError(f"Circular dependency detected: task {dep_id} would create a cycle")
        now = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.execute(
            "INSERT INTO tasks (title, description, priority, max_retries, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (title, description, priority, max_retries, TaskStatus.PENDING, now, now),
        )
        task_id = cursor.lastrowid
        if depends_on:
            for dep_id in depends_on:
                self._conn.execute(
                    "INSERT INTO task_dependencies (task_id, depends_on_id) VALUES (?, ?)",
                    (task_id, dep_id),
                )
        if tags:
            for tag in tags:
                self._conn.execute(
                    "INSERT INTO task_tags (task_id, tag) VALUES (?, ?)",
                    (task_id, tag),
                )
        self._conn.commit()
        logger.info("Task added: id=%d title=%r depends_on=%s tags=%s", task_id, title, depends_on, tags)
        return task_id

    def _would_create_cycle(self, task_id: int, visited: set[int]) -> bool:
        """Check if adding a dependency on task_id would create a cycle."""
        if task_id in visited:
            return True
        visited.add(task_id)
        rows = self._conn.execute(
            "SELECT depends_on_id FROM task_dependencies WHERE task_id = ?",
            (task_id,),
        ).fetchall()
        for row in rows:
            if self._would_create_cycle(row["depends_on_id"], visited):
                return True
        return False

    def get_task(self, task_id: int) -> Task | None:
        row = self._conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_task(row)

    def get_next_task(self) -> Task | None:
        row = self._conn.execute(
            """SELECT t.* FROM tasks t
            WHERE t.status = ?
            AND NOT EXISTS (
                SELECT 1 FROM task_dependencies d
                JOIN tasks dep ON dep.id = d.depends_on_id
                WHERE d.task_id = t.id AND dep.status != ?
            )
            ORDER BY t.priority DESC, t.created_at ASC LIMIT 1""",
            (TaskStatus.PENDING, TaskStatus.COMPLETED),
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

    def list_tasks(self, status: TaskStatus | None = None, tag: str | None = None) -> list[Task]:
        query = "SELECT t.* FROM tasks t"
        params: list = []
        conditions: list[str] = []

        if tag is not None:
            query += " JOIN task_tags tt ON tt.task_id = t.id"
            conditions.append("tt.tag = ?")
            params.append(tag)

        if status is not None:
            conditions.append("t.status = ?")
            params.append(str(status))

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY t.priority DESC, t.created_at ASC"

        rows = self._conn.execute(query, params).fetchall()
        return self._batch_rows_to_tasks(rows)

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

    def get_blocked_by(self, task_id: int) -> list[int]:
        """Return IDs of uncompleted tasks that this task depends on."""
        rows = self._conn.execute(
            """SELECT d.depends_on_id FROM task_dependencies d
            JOIN tasks dep ON dep.id = d.depends_on_id
            WHERE d.task_id = ? AND dep.status != ?""",
            (task_id, TaskStatus.COMPLETED),
        ).fetchall()
        return [row["depends_on_id"] for row in rows]

    def add_tag(self, task_id: int, tag: str) -> None:
        """Add a tag to a task."""
        self._conn.execute(
            "INSERT OR IGNORE INTO task_tags (task_id, tag) VALUES (?, ?)",
            (task_id, tag),
        )
        self._conn.commit()
        logger.info("Tag added: task_id=%d tag=%r", task_id, tag)

    def remove_tag(self, task_id: int, tag: str) -> None:
        """Remove a tag from a task."""
        self._conn.execute(
            "DELETE FROM task_tags WHERE task_id = ? AND tag = ?",
            (task_id, tag),
        )
        self._conn.commit()
        logger.info("Tag removed: task_id=%d tag=%r", task_id, tag)

    def get_tags(self, task_id: int) -> list[str]:
        """Return list of tag strings for a task."""
        rows = self._conn.execute(
            "SELECT tag FROM task_tags WHERE task_id = ? ORDER BY tag",
            (task_id,),
        ).fetchall()
        return [row["tag"] for row in rows]

    def _row_to_task(self, row: sqlite3.Row) -> Task:
        """Convert a single row to a Task (makes 2 extra queries for tags/deps)."""
        task_id = row["id"]
        return Task(
            id=task_id,
            title=row["title"],
            description=row["description"],
            status=TaskStatus(row["status"]),
            priority=row["priority"],
            worker_id=row["worker_id"],
            result=row["result"],
            error=row["error"],
            retries=row["retries"],
            max_retries=row["max_retries"],
            blocked_by=self.get_blocked_by(task_id),
            tags=self.get_tags(task_id),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _batch_rows_to_tasks(self, rows: list[sqlite3.Row]) -> list[Task]:
        """Convert multiple rows to Tasks using batch queries (3 queries total)."""
        if not rows:
            return []
        task_ids = [row["id"] for row in rows]
        placeholders = ",".join("?" * len(task_ids))

        # Batch fetch all tags
        tag_rows = self._conn.execute(
            f"SELECT task_id, tag FROM task_tags WHERE task_id IN ({placeholders}) ORDER BY tag",
            task_ids,
        ).fetchall()
        tags_by_id: dict[int, list[str]] = {tid: [] for tid in task_ids}
        for tr in tag_rows:
            tags_by_id[tr["task_id"]].append(tr["tag"])

        # Batch fetch all uncompleted dependencies
        dep_rows = self._conn.execute(
            f"""SELECT d.task_id, d.depends_on_id FROM task_dependencies d
            JOIN tasks dep ON dep.id = d.depends_on_id
            WHERE d.task_id IN ({placeholders}) AND dep.status != ?""",
            [*task_ids, str(TaskStatus.COMPLETED)],
        ).fetchall()
        deps_by_id: dict[int, list[int]] = {tid: [] for tid in task_ids}
        for dr in dep_rows:
            deps_by_id[dr["task_id"]].append(dr["depends_on_id"])

        # Build Task objects using lookup dicts
        tasks = []
        for row in rows:
            tid = row["id"]
            tasks.append(Task(
                id=tid,
                title=row["title"],
                description=row["description"],
                status=TaskStatus(row["status"]),
                priority=row["priority"],
                worker_id=row["worker_id"],
                result=row["result"],
                error=row["error"],
                retries=row["retries"],
                max_retries=row["max_retries"],
                blocked_by=deps_by_id[tid],
                tags=tags_by_id[tid],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            ))
        return tasks
