"""Initiative MCP server — the orchestration brain."""

from __future__ import annotations

import json
import logging
from typing import Optional, Sequence

from fastmcp import FastMCP

from .database import TaskStore
from .models import TaskStatus

logger = logging.getLogger("initiative.server")


def _validate_task_id(task_id: int) -> str | None:
    """Return error message if task_id is invalid, else None."""
    if task_id <= 0:
        return "task_id must be a positive integer"
    return None


def create_server(db_path: str = "initiative.db") -> FastMCP:
    mcp = FastMCP("initiative")
    store = TaskStore(db_path)

    @mcp.tool()
    async def add_task(
        title: str,
        description: str,
        priority: int = 0,
        max_retries: int = 2,
        depends_on: Optional[Sequence[int]] = None,
        tags: Optional[Sequence[str]] = None,
    ) -> str:
        """Add a new task to the Initiative queue.

        Args:
            title: Short title for the task
            description: Detailed description of what needs to be done
            priority: Higher number = higher priority (default 0)
            max_retries: Maximum number of automatic retries on failure (default 2)
            depends_on: List of task IDs that must complete before this task can start
            tags: List of tags to categorize the task
        """
        # Input validation
        if not title or not title.strip():
            return json.dumps({"error": "title must not be empty"})
        if len(title) > 1000:
            return json.dumps({"error": "title must be 1000 characters or fewer"})
        if not description or not description.strip():
            return json.dumps({"error": "description must not be empty"})
        if len(description) > 50000:
            return json.dumps({"error": "description must be 50000 characters or fewer"})
        if not 0 <= priority <= 1000:
            return json.dumps({"error": "priority must be between 0 and 1000"})
        if not 0 <= max_retries <= 100:
            return json.dumps({"error": "max_retries must be between 0 and 100"})
        deps = list(depends_on) if depends_on else None
        tag_list = list(tags) if tags else None
        if tag_list:
            if len(tag_list) > 50:
                return json.dumps({"error": "maximum 50 tags allowed"})
            for t in tag_list:
                if len(t) > 100:
                    return json.dumps({"error": f"tag must be 100 characters or fewer: {t[:20]}..."})
        logger.info("add_task called: title=%r priority=%d depends_on=%s tags=%s", title, priority, deps, tag_list)
        try:
            task_id = store.add_task(title, description, priority, max_retries=max_retries, depends_on=deps, tags=tag_list)
        except ValueError as e:
            return json.dumps({"error": str(e)})
        return json.dumps({"task_id": task_id, "title": title, "status": "pending", "max_retries": max_retries, "depends_on": deps or [], "tags": tag_list or []})

    @mcp.tool()
    async def get_next_task() -> str:
        """Pull the highest-priority pending task and mark it in-progress."""
        logger.info("get_next_task called")
        task = store.get_next_task()
        if task is None:
            logger.warning("get_next_task: no pending tasks available")
            return json.dumps({"message": "No pending tasks"})
        return json.dumps(task.to_dict())

    @mcp.tool()
    async def complete_task(task_id: int, result: str = "") -> str:
        """Mark a task as completed.

        Args:
            task_id: ID of the task to complete
            result: Summary of what was accomplished
        """
        err = _validate_task_id(task_id)
        if err:
            return json.dumps({"error": err, "task_id": task_id})
        logger.info("complete_task called: task_id=%d", task_id)
        success = store.complete_task(task_id, result)
        if not success:
            task = store.get_task(task_id)
            if task is None:
                return json.dumps({"error": "Task not found", "task_id": task_id})
            return json.dumps({"error": f"Task is {task.status}, not in_progress", "task_id": task_id, "status": str(task.status)})
        return json.dumps({"task_id": task_id, "status": "completed", "result": result})

    @mcp.tool()
    async def fail_task(task_id: int, error: str = "") -> str:
        """Mark a task as failed. If the task has retries remaining, it will be
        automatically requeued as pending instead of being marked as failed.

        Args:
            task_id: ID of the task that failed
            error: Description of what went wrong
        """
        err = _validate_task_id(task_id)
        if err:
            return json.dumps({"error": err, "task_id": task_id})
        logger.info("fail_task called: task_id=%d", task_id)
        # Check current status before attempting fail
        current = store.get_task(task_id)
        if current is None:
            return json.dumps({"error": "Task not found", "task_id": task_id})
        if current.status != TaskStatus.IN_PROGRESS:
            return json.dumps({"error": f"Task is {current.status}, not in_progress", "task_id": task_id, "status": str(current.status)})
        task = store.fail_task(task_id, error)
        if task.status == TaskStatus.PENDING:
            return json.dumps({
                "task_id": task_id,
                "status": "pending",
                "message": f"Task auto-retried (attempt {task.retries}/{task.max_retries})",
                "retries": task.retries,
                "max_retries": task.max_retries,
                "error": error,
            })
        return json.dumps({
            "task_id": task_id,
            "status": "failed",
            "message": "Task permanently failed after exhausting all retries",
            "retries": task.retries,
            "max_retries": task.max_retries,
            "error": error,
        })

    @mcp.tool()
    async def retry_task(task_id: int) -> str:
        """Manually retry a failed task by resetting it to pending status.

        Args:
            task_id: ID of the failed task to retry
        """
        err = _validate_task_id(task_id)
        if err:
            return json.dumps({"error": err, "task_id": task_id})
        logger.info("retry_task called: task_id=%d", task_id)
        # Check current task status before attempting retry
        current = store.get_task(task_id)
        if current is None:
            return json.dumps({"error": "Task not found", "task_id": task_id})
        if current.status != TaskStatus.FAILED:
            return json.dumps({
                "error": "Task is not in failed status",
                "task_id": task_id,
                "status": str(current.status),
            })
        task = store.retry_task(task_id)
        return json.dumps({
            "task_id": task_id,
            "status": "pending",
            "message": "Task has been requeued for retry",
        })

    @mcp.tool()
    async def add_tag(task_id: int, tag: str) -> str:
        """Add a tag to a task.

        Args:
            task_id: ID of the task to tag
            tag: Tag string to add
        """
        err = _validate_task_id(task_id)
        if err:
            return json.dumps({"error": err, "task_id": task_id})
        logger.info("add_tag called: task_id=%d tag=%r", task_id, tag)
        task = store.get_task(task_id)
        if task is None:
            return json.dumps({"error": "Task not found", "task_id": task_id})
        store.add_tag(task_id, tag)
        return json.dumps({"task_id": task_id, "tag": tag, "message": "Tag added"})

    @mcp.tool()
    async def remove_tag(task_id: int, tag: str) -> str:
        """Remove a tag from a task.

        Args:
            task_id: ID of the task to remove the tag from
            tag: Tag string to remove
        """
        err = _validate_task_id(task_id)
        if err:
            return json.dumps({"error": err, "task_id": task_id})
        logger.info("remove_tag called: task_id=%d tag=%r", task_id, tag)
        task = store.get_task(task_id)
        if task is None:
            return json.dumps({"error": "Task not found", "task_id": task_id})
        store.remove_tag(task_id, tag)
        return json.dumps({"task_id": task_id, "tag": tag, "message": "Tag removed"})

    @mcp.tool()
    async def list_tasks(
        status: Optional[str] = None,
        tag: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> str:
        """List tasks, optionally filtered by status and/or tag.

        Args:
            status: Filter by status (pending, in_progress, completed, failed). Omit for all.
            tag: Filter by tag. Only tasks with this tag will be returned.
            limit: Maximum number of tasks to return (1-200, default 50).
            offset: Number of tasks to skip (default 0).
        """
        logger.info("list_tasks called: status=%r tag=%r limit=%d offset=%d", status, tag, limit, offset)
        if not 1 <= limit <= 200:
            return json.dumps({"error": "limit must be between 1 and 200"})
        if offset < 0:
            return json.dumps({"error": "offset must be >= 0"})
        try:
            task_status = TaskStatus(status) if status else None
        except ValueError:
            valid = ", ".join(str(s) for s in TaskStatus)
            return json.dumps({"error": f"Invalid status. Must be one of: {valid}"})
        tasks, total = store.list_tasks(status=task_status, tag=tag, limit=limit, offset=offset)
        return json.dumps({
            "tasks": [t.to_dict() for t in tasks],
            "count": len(tasks),
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(tasks) < total,
        })

    @mcp.tool()
    async def get_status() -> str:
        """Get a summary of the current task queue status."""
        logger.info("get_status called")
        return json.dumps(store.get_status())

    @mcp.tool()
    async def get_summary(
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> str:
        """Get a lightweight summary of tasks (id, title, status, priority only).
        Use this instead of list_tasks when you only need an overview to save context.

        Args:
            status: Filter by status (pending, in_progress, completed, failed). Omit for all.
            limit: Maximum number of tasks to return (1-200, default 50).
            offset: Number of tasks to skip (default 0).
        """
        logger.info("get_summary called: status=%r limit=%d offset=%d", status, limit, offset)
        if not 1 <= limit <= 200:
            return json.dumps({"error": "limit must be between 1 and 200"})
        if offset < 0:
            return json.dumps({"error": "offset must be >= 0"})
        try:
            task_status = TaskStatus(status) if status else None
        except ValueError:
            valid = ", ".join(str(s) for s in TaskStatus)
            return json.dumps({"error": f"Invalid status. Must be one of: {valid}"})
        tasks, total = store.get_summary(status=task_status, limit=limit, offset=offset)
        return json.dumps({
            "tasks": tasks,
            "count": len(tasks),
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(tasks) < total,
        })

    return mcp


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    server = create_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
