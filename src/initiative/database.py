"""SQLite task store for Initiative."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone

from .models import Task, TaskStatus

logger = logging.getLogger("initiative.database")

_SCHEMA_VERSION = 1

_MIGRATIONS: dict[int, str] = {
    1: """
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
    started_at TEXT,
    completed_at TEXT,
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
""",
}


class TaskStore:
    def __init__(self, db_path: str = "initiative.db"):
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, timeout=5.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._apply_migrations()
        logger.debug("Database connected: %s", db_path)

    def _apply_migrations(self) -> None:
        """Apply pending schema migrations."""
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"
        )
        row = self._conn.execute("SELECT MAX(version) as v FROM schema_version").fetchone()
        current = row["v"] if row["v"] is not None else 0
        for version in range(current + 1, _SCHEMA_VERSION + 1):
            if version in _MIGRATIONS:
                self._conn.executescript(_MIGRATIONS[version])
                self._conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
                self._conn.commit()
                logger.info("Applied migration %d", version)
        # Re-enable foreign keys after executescript
        self._conn.execute("PRAGMA foreign_keys=ON")

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
        self._conn.execute("BEGIN IMMEDIATE")
        try:
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
                self._conn.execute("ROLLBACK")
                logger.debug("No pending tasks available")
                return None
            now = datetime.now(timezone.utc).isoformat()
            self._conn.execute(
                "UPDATE tasks SET status = ?, started_at = ?, updated_at = ? WHERE id = ?",
                (TaskStatus.IN_PROGRESS, now, now, row["id"]),
            )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        task = self._row_to_task(row)
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.fromisoformat(now)
        logger.info("Task started: id=%d title=%r", task.id, task.title)
        return task

    def complete_task(self, task_id: int, result: str = "") -> bool:
        """Mark a task as completed. Returns True on success, False if task not found or not in_progress."""
        task = self.get_task(task_id)
        if task is None:
            logger.warning("complete_task: task %d not found", task_id)
            return False
        if task.status != TaskStatus.IN_PROGRESS:
            logger.warning("complete_task: task %d is %s, not in_progress", task_id, task.status)
            return False
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE tasks SET status = ?, result = ?, completed_at = ?, updated_at = ? WHERE id = ?",
            (TaskStatus.COMPLETED, result, now, now, task_id),
        )
        self._conn.commit()
        logger.info("Task completed: id=%d", task_id)
        return True

    def fail_task(self, task_id: int, error: str = "") -> Task | None:
        task = self.get_task(task_id)
        if task is None:
            return None
        if task.status != TaskStatus.IN_PROGRESS:
            logger.warning("fail_task: task %d is %s, not in_progress", task_id, task.status)
            return task
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
                "UPDATE tasks SET status = ?, error = ?, completed_at = ?, updated_at = ? WHERE id = ?",
                (TaskStatus.FAILED, error, now, now, task_id),
            )
            self._conn.commit()
            logger.info("Task permanently failed: id=%d", task_id)
        return self.get_task(task_id)

    def cancel_task(self, task_id: int) -> bool:
        """Cancel a pending or in_progress task. Returns True on success, False if task not found or already completed/failed/cancelled."""
        task = self.get_task(task_id)
        if task is None:
            logger.warning("cancel_task: task %d not found", task_id)
            return False
        if task.status not in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS):
            logger.warning("cancel_task: task %d is %s, cannot cancel", task_id, task.status)
            return False
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
            (TaskStatus.CANCELLED, now, task_id),
        )
        self._conn.commit()
        logger.info("Task cancelled: id=%d", task_id)
        return True

    def update_task(self, task_id: int, title: str | None = None, description: str | None = None, priority: int | None = None) -> Task | None:
        """Update specified fields on a pending task. Returns the updated task or None if not found/not pending."""
        task = self.get_task(task_id)
        if task is None:
            logger.warning("update_task: task %d not found", task_id)
            return None
        if task.status != TaskStatus.PENDING:
            logger.warning("update_task: task %d is %s, not pending", task_id, task.status)
            return None
        updates: list[str] = []
        params: list = []
        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if priority is not None:
            updates.append("priority = ?")
            params.append(priority)
        if not updates:
            return task
        now = datetime.now(timezone.utc).isoformat()
        updates.append("updated_at = ?")
        params.append(now)
        params.append(task_id)
        self._conn.execute(
            f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        self._conn.commit()
        logger.info("Task updated: id=%d fields=%s", task_id, [u.split(" =")[0] for u in updates[:-1]])
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
            "UPDATE tasks SET status = ?, error = NULL, retries = 0, started_at = NULL, completed_at = NULL, updated_at = ? WHERE id = ?",
            (TaskStatus.PENDING, now, task_id),
        )
        self._conn.commit()
        logger.info("Task manually retried: id=%d", task_id)
        return self.get_task(task_id)

    def recover_stale_tasks(self, timeout_minutes: int = 30) -> int:
        """Reset tasks stuck in in_progress for longer than timeout_minutes back to pending.
        Returns the number of tasks recovered."""
        now = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.execute(
            """UPDATE tasks SET status = ?, started_at = NULL, updated_at = ?
            WHERE status = ? AND updated_at < datetime(?, ?)""",
            (TaskStatus.PENDING, now, TaskStatus.IN_PROGRESS, now, f"-{timeout_minutes} minutes"),
        )
        count = cursor.rowcount
        self._conn.commit()
        if count > 0:
            logger.info("Recovered %d stale tasks (timeout=%d min)", count, timeout_minutes)
        return count

    def _build_filter_query(
        self, select: str, status: TaskStatus | None, tag: str | None
    ) -> tuple[str, list]:
        """Build a filtered query with optional status and tag conditions."""
        query = select
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
        return query, params

    def list_tasks(
        self,
        status: TaskStatus | None = None,
        tag: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Task], int]:
        """Return tasks with pagination. Returns (tasks, total_count)."""
        # Count query
        count_query, count_params = self._build_filter_query(
            "SELECT COUNT(*) as cnt FROM tasks t", status, tag
        )
        total = self._conn.execute(count_query, count_params).fetchone()["cnt"]

        # Data query
        query, params = self._build_filter_query("SELECT t.* FROM tasks t", status, tag)
        query += " ORDER BY t.priority DESC, t.created_at ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self._conn.execute(query, params).fetchall()
        return self._batch_rows_to_tasks(rows), total

    def get_status(self) -> dict:
        rows = self._conn.execute(
            "SELECT status, COUNT(*) as count FROM tasks GROUP BY status"
        ).fetchall()
        counts = {str(s): 0 for s in TaskStatus}
        for row in rows:
            counts[row["status"]] = row["count"]

        # Average completion time for completed tasks
        avg_row = self._conn.execute(
            """SELECT AVG(
                julianday(completed_at) - julianday(started_at)
            ) * 86400 as avg_seconds
            FROM tasks
            WHERE status = ? AND started_at IS NOT NULL AND completed_at IS NOT NULL""",
            (TaskStatus.COMPLETED,),
        ).fetchone()
        avg_completion_time = round(avg_row["avg_seconds"], 2) if avg_row["avg_seconds"] else None

        # Tasks completed in last hour
        now = datetime.now(timezone.utc).isoformat()
        hour_ago_row = self._conn.execute(
            """SELECT COUNT(*) as count FROM tasks
            WHERE status = ? AND completed_at > datetime(?, '-1 hour')""",
            (TaskStatus.COMPLETED, now),
        ).fetchone()
        tasks_completed_last_hour = hour_ago_row["count"]

        # Oldest pending task age
        oldest_row = self._conn.execute(
            """SELECT MIN(created_at) as oldest FROM tasks WHERE status = ?""",
            (TaskStatus.PENDING,),
        ).fetchone()
        oldest_pending_age = None
        if oldest_row["oldest"]:
            oldest_dt = datetime.fromisoformat(oldest_row["oldest"])
            oldest_pending_age = round((datetime.now(timezone.utc) - oldest_dt).total_seconds(), 2)

        return {
            "total": sum(counts.values()),
            **counts,
            "avg_completion_time_seconds": avg_completion_time,
            "tasks_completed_last_hour": tasks_completed_last_hour,
            "oldest_pending_task_age_seconds": oldest_pending_age,
        }

    def get_summary(
        self,
        status: TaskStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """Return lightweight task summaries with pagination. Returns (summaries, total_count)."""
        if status is not None:
            total = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM tasks WHERE status = ?", (str(status),)
            ).fetchone()["cnt"]
            rows = self._conn.execute(
                "SELECT id, title, status, priority FROM tasks WHERE status = ? ORDER BY priority DESC, created_at ASC LIMIT ? OFFSET ?",
                (str(status), limit, offset),
            ).fetchall()
        else:
            total = self._conn.execute("SELECT COUNT(*) as cnt FROM tasks").fetchone()["cnt"]
            rows = self._conn.execute(
                "SELECT id, title, status, priority FROM tasks ORDER BY priority DESC, created_at ASC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [{"id": r["id"], "title": r["title"], "status": r["status"], "priority": r["priority"]} for r in rows], total

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

    @staticmethod
    def _parse_optional_dt(value: str | None) -> datetime | None:
        return datetime.fromisoformat(value) if value else None

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
            started_at=self._parse_optional_dt(row["started_at"]),
            completed_at=self._parse_optional_dt(row["completed_at"]),
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
                started_at=self._parse_optional_dt(row["started_at"]),
                completed_at=self._parse_optional_dt(row["completed_at"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            ))
        return tasks
