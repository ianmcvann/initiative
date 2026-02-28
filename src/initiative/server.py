"""Initiative MCP server — the orchestration brain."""

from __future__ import annotations

import json
import logging
from typing import Optional, Sequence

from fastmcp import FastMCP

from .database import TaskStore
from .models import TaskStatus

logger = logging.getLogger("initiative.server")


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
        deps = list(depends_on) if depends_on else None
        tag_list = list(tags) if tags else None
        logger.info("add_task called: title=%r priority=%d depends_on=%s tags=%s", title, priority, deps, tag_list)
        task_id = store.add_task(title, description, priority, max_retries=max_retries, depends_on=deps, tags=tag_list)
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
        logger.info("complete_task called: task_id=%d", task_id)
        store.complete_task(task_id, result)
        return json.dumps({"task_id": task_id, "status": "completed", "result": result})

    @mcp.tool()
    async def fail_task(task_id: int, error: str = "") -> str:
        """Mark a task as failed. If the task has retries remaining, it will be
        automatically requeued as pending instead of being marked as failed.

        Args:
            task_id: ID of the task that failed
            error: Description of what went wrong
        """
        logger.info("fail_task called: task_id=%d", task_id)
        task = store.fail_task(task_id, error)
        if task is None:
            return json.dumps({"error": "Task not found", "task_id": task_id})
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
        logger.info("remove_tag called: task_id=%d tag=%r", task_id, tag)
        task = store.get_task(task_id)
        if task is None:
            return json.dumps({"error": "Task not found", "task_id": task_id})
        store.remove_tag(task_id, tag)
        return json.dumps({"task_id": task_id, "tag": tag, "message": "Tag removed"})

    @mcp.tool()
    async def list_tasks(status: Optional[str] = None, tag: Optional[str] = None) -> str:
        """List tasks, optionally filtered by status and/or tag.

        Args:
            status: Filter by status (pending, in_progress, completed, failed). Omit for all.
            tag: Filter by tag. Only tasks with this tag will be returned.
        """
        logger.info("list_tasks called: status=%r tag=%r", status, tag)
        task_status = TaskStatus(status) if status else None
        tasks = store.list_tasks(status=task_status, tag=tag)
        return json.dumps({"tasks": [t.to_dict() for t in tasks], "count": len(tasks)})

    @mcp.tool()
    async def get_status() -> str:
        """Get a summary of the current task queue status."""
        logger.info("get_status called")
        return json.dumps(store.get_status())

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
