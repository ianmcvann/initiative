"""Initiative MCP server — the orchestration brain."""

from __future__ import annotations

import json
from typing import Optional

from fastmcp import FastMCP

from .database import TaskStore
from .models import TaskStatus


def create_server(db_path: str = "initiative.db") -> FastMCP:
    mcp = FastMCP("initiative")
    store = TaskStore(db_path)

    @mcp.tool()
    async def add_task(title: str, description: str, priority: int = 0) -> str:
        """Add a new task to the Initiative queue.

        Args:
            title: Short title for the task
            description: Detailed description of what needs to be done
            priority: Higher number = higher priority (default 0)
        """
        task_id = store.add_task(title, description, priority)
        return json.dumps({"task_id": task_id, "title": title, "status": "pending"})

    @mcp.tool()
    async def get_next_task() -> str:
        """Pull the highest-priority pending task and mark it in-progress."""
        task = store.get_next_task()
        if task is None:
            return json.dumps({"message": "No pending tasks"})
        return json.dumps(task.to_dict())

    @mcp.tool()
    async def complete_task(task_id: int, result: str = "") -> str:
        """Mark a task as completed.

        Args:
            task_id: ID of the task to complete
            result: Summary of what was accomplished
        """
        store.complete_task(task_id, result)
        return json.dumps({"task_id": task_id, "status": "completed", "result": result})

    @mcp.tool()
    async def fail_task(task_id: int, error: str = "") -> str:
        """Mark a task as failed.

        Args:
            task_id: ID of the task that failed
            error: Description of what went wrong
        """
        store.fail_task(task_id, error)
        return json.dumps({"task_id": task_id, "status": "failed", "error": error})

    @mcp.tool()
    async def list_tasks(status: Optional[str] = None) -> str:
        """List tasks, optionally filtered by status.

        Args:
            status: Filter by status (pending, in_progress, completed, failed). Omit for all.
        """
        task_status = TaskStatus(status) if status else None
        tasks = store.list_tasks(status=task_status)
        return json.dumps({"tasks": [t.to_dict() for t in tasks], "count": len(tasks)})

    @mcp.tool()
    async def get_status() -> str:
        """Get a summary of the current task queue status."""
        return json.dumps(store.get_status())

    return mcp


def main():
    server = create_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
