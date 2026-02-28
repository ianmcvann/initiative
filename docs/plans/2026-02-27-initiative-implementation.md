# Initiative Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Claude Code plugin that provides autonomous, never-stopping AI task orchestration via an MCP server, skills, and hooks.

**Architecture:** A Python MCP server (FastMCP) manages a SQLite task database and exposes tools for task lifecycle management. Skills drive the orchestration loop — dispatching subagents in parallel worktrees and invoking the project analyzer when the queue is empty. Hooks handle MCP server lifecycle.

**Tech Stack:** Python 3.10+, FastMCP, SQLite, Claude Code plugin system (skills, hooks, MCP)

---

### Task 1: Scaffold Plugin Structure

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `pyproject.toml`
- Create: `src/initiative/__init__.py`
- Create: `.mcp.json`

**Step 1: Create plugin manifest**

Create `.claude-plugin/plugin.json`:
```json
{
  "name": "initiative",
  "description": "Autonomous AI task orchestration — never-stopping background worker",
  "version": "0.1.0",
  "author": {
    "name": "Ian McVann"
  },
  "license": "MIT",
  "skills": "./skills/",
  "commands": "./commands/",
  "hooks": "./hooks/hooks.json"
}
```

**Step 2: Create pyproject.toml**

Create `pyproject.toml`:
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "initiative"
version = "0.1.0"
description = "Autonomous AI task orchestration for Claude Code"
requires-python = ">=3.10"
dependencies = [
    "fastmcp>=2.3.2,<3",
]

[project.scripts]
initiative = "initiative.server:main"

[tool.hatch.build.targets.wheel]
packages = ["src/initiative"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

**Step 3: Create package init**

Create `src/initiative/__init__.py`:
```python
"""Initiative — Autonomous AI task orchestration for Claude Code."""

__version__ = "0.1.0"
```

**Step 4: Create MCP server config**

Create `.mcp.json`:
```json
{
  "initiative": {
    "type": "stdio",
    "command": "uv",
    "args": ["run", "--directory", "${CLAUDE_PLUGIN_ROOT}", "initiative"]
  }
}
```

**Step 5: Create placeholder directories**

```bash
mkdir -p skills/initiative skills/analyze commands hooks tests
```

**Step 6: Commit**

```bash
git add .claude-plugin/ pyproject.toml src/ .mcp.json
git commit -m "feat: scaffold Initiative plugin structure"
```

---

### Task 2: Implement Task Data Model

**Files:**
- Create: `src/initiative/models.py`
- Create: `tests/test_models.py`

**Step 1: Write the failing test**

Create `tests/test_models.py`:
```python
import pytest
from datetime import datetime, timezone
from initiative.models import Task, TaskStatus


def test_task_creation_defaults():
    task = Task(title="Fix the bug", description="There's a bug in auth")
    assert task.title == "Fix the bug"
    assert task.description == "There's a bug in auth"
    assert task.status == TaskStatus.PENDING
    assert task.priority == 0
    assert task.worker_id is None
    assert task.result is None
    assert task.error is None
    assert isinstance(task.created_at, datetime)


def test_task_status_enum():
    assert TaskStatus.PENDING == "pending"
    assert TaskStatus.IN_PROGRESS == "in_progress"
    assert TaskStatus.COMPLETED == "completed"
    assert TaskStatus.FAILED == "failed"


def test_task_to_dict():
    task = Task(id=1, title="Test task", description="desc", priority=5)
    d = task.to_dict()
    assert d["id"] == 1
    assert d["title"] == "Test task"
    assert d["priority"] == 5
    assert d["status"] == "pending"


def test_task_from_dict():
    data = {
        "id": 1,
        "title": "Test task",
        "description": "desc",
        "status": "in_progress",
        "priority": 3,
        "worker_id": "agent-1",
        "result": None,
        "error": None,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    task = Task.from_dict(data)
    assert task.id == 1
    assert task.status == TaskStatus.IN_PROGRESS
    assert task.worker_id == "agent-1"
```

**Step 2: Run test to verify it fails**

Run: `cd /home/ianmcvann/initiative && uv run pytest tests/test_models.py -v`
Expected: FAIL — module not found

**Step 3: Write minimal implementation**

Create `src/initiative/models.py`:
```python
"""Task data models for Initiative."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Task:
    title: str
    description: str
    id: int | None = None
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 0
    worker_id: str | None = None
    result: str | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": str(self.status),
            "priority": self.priority,
            "worker_id": self.worker_id,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> Task:
        return cls(
            id=data["id"],
            title=data["title"],
            description=data["description"],
            status=TaskStatus(data["status"]),
            priority=data.get("priority", 0),
            worker_id=data.get("worker_id"),
            result=data.get("result"),
            error=data.get("error"),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )
```

**Step 4: Run test to verify it passes**

Run: `cd /home/ianmcvann/initiative && uv run pytest tests/test_models.py -v`
Expected: PASS — all 4 tests pass

**Step 5: Commit**

```bash
git add src/initiative/models.py tests/test_models.py
git commit -m "feat: add Task data model with status enum"
```

---

### Task 3: Implement SQLite Task Store

**Files:**
- Create: `src/initiative/database.py`
- Create: `tests/test_database.py`

**Step 1: Write the failing tests**

Create `tests/test_database.py`:
```python
import pytest
from initiative.database import TaskStore
from initiative.models import Task, TaskStatus


@pytest.fixture
def store(tmp_path):
    db_path = tmp_path / "test.db"
    return TaskStore(str(db_path))


def test_add_and_get_task(store):
    task_id = store.add_task("Fix bug", "Fix the auth bug", priority=5)
    task = store.get_task(task_id)
    assert task.title == "Fix bug"
    assert task.description == "Fix the auth bug"
    assert task.priority == 5
    assert task.status == TaskStatus.PENDING


def test_get_next_task_returns_highest_priority(store):
    store.add_task("Low priority", "desc", priority=1)
    store.add_task("High priority", "desc", priority=10)
    store.add_task("Medium priority", "desc", priority=5)
    task = store.get_next_task()
    assert task.title == "High priority"
    assert task.status == TaskStatus.IN_PROGRESS


def test_get_next_task_returns_none_when_empty(store):
    assert store.get_next_task() is None


def test_complete_task(store):
    task_id = store.add_task("Task", "desc")
    store.get_next_task()  # moves to in_progress
    store.complete_task(task_id, result="Done successfully")
    task = store.get_task(task_id)
    assert task.status == TaskStatus.COMPLETED
    assert task.result == "Done successfully"


def test_fail_task(store):
    task_id = store.add_task("Task", "desc")
    store.get_next_task()
    store.fail_task(task_id, error="Something broke")
    task = store.get_task(task_id)
    assert task.status == TaskStatus.FAILED
    assert task.error == "Something broke"


def test_list_tasks_by_status(store):
    store.add_task("Task 1", "desc")
    store.add_task("Task 2", "desc")
    task_id = store.add_task("Task 3", "desc")
    store.get_next_task()  # moves highest to in_progress

    pending = store.list_tasks(status=TaskStatus.PENDING)
    in_progress = store.list_tasks(status=TaskStatus.IN_PROGRESS)
    assert len(pending) == 2
    assert len(in_progress) == 1


def test_list_tasks_all(store):
    store.add_task("Task 1", "desc")
    store.add_task("Task 2", "desc")
    all_tasks = store.list_tasks()
    assert len(all_tasks) == 2


def test_get_status(store):
    store.add_task("Task 1", "desc")
    store.add_task("Task 2", "desc")
    store.add_task("Task 3", "desc", priority=10)
    store.get_next_task()  # moves one to in_progress
    status = store.get_status()
    assert status["total"] == 3
    assert status["pending"] == 2
    assert status["in_progress"] == 1
    assert status["completed"] == 0
    assert status["failed"] == 0
```

**Step 2: Run test to verify it fails**

Run: `cd /home/ianmcvann/initiative && uv run pytest tests/test_database.py -v`
Expected: FAIL — module not found

**Step 3: Write minimal implementation**

Create `src/initiative/database.py`:
```python
"""SQLite task store for Initiative."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import Task, TaskStatus

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

    def add_task(self, title: str, description: str, priority: int = 0) -> int:
        now = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.execute(
            "INSERT INTO tasks (title, description, priority, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (title, description, priority, TaskStatus.PENDING, now, now),
        )
        self._conn.commit()
        return cursor.lastrowid

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
            return None
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
            (TaskStatus.IN_PROGRESS, now, row["id"]),
        )
        self._conn.commit()
        task = self._row_to_task(row)
        task.status = TaskStatus.IN_PROGRESS
        return task

    def complete_task(self, task_id: int, result: str = "") -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE tasks SET status = ?, result = ?, updated_at = ? WHERE id = ?",
            (TaskStatus.COMPLETED, result, now, task_id),
        )
        self._conn.commit()

    def fail_task(self, task_id: int, error: str = "") -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE tasks SET status = ?, error = ?, updated_at = ? WHERE id = ?",
            (TaskStatus.FAILED, error, now, task_id),
        )
        self._conn.commit()

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
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
```

**Step 4: Run test to verify it passes**

Run: `cd /home/ianmcvann/initiative && uv run pytest tests/test_database.py -v`
Expected: PASS — all 8 tests pass

**Step 5: Commit**

```bash
git add src/initiative/database.py tests/test_database.py
git commit -m "feat: add SQLite task store with CRUD and priority queue"
```

---

### Task 4: Implement MCP Server with Tools

**Files:**
- Create: `src/initiative/server.py`
- Create: `tests/test_server.py`

**Step 1: Write the failing tests**

Create `tests/test_server.py`:
```python
import pytest
import json
from unittest.mock import patch
from initiative.server import create_server


@pytest.fixture
def server(tmp_path):
    db_path = str(tmp_path / "test.db")
    return create_server(db_path=db_path)


@pytest.mark.anyio
async def test_add_task_tool(server):
    result = await server.call_tool(
        "add_task",
        {"title": "Test task", "description": "A test", "priority": 5},
    )
    data = json.loads(result[0].text)
    assert data["task_id"] == 1
    assert data["title"] == "Test task"


@pytest.mark.anyio
async def test_get_next_task_tool(server):
    await server.call_tool(
        "add_task", {"title": "Task 1", "description": "desc", "priority": 1}
    )
    await server.call_tool(
        "add_task", {"title": "Task 2", "description": "desc", "priority": 10}
    )
    result = await server.call_tool("get_next_task", {})
    data = json.loads(result[0].text)
    assert data["title"] == "Task 2"
    assert data["status"] == "in_progress"


@pytest.mark.anyio
async def test_get_next_task_empty(server):
    result = await server.call_tool("get_next_task", {})
    data = json.loads(result[0].text)
    assert data["message"] == "No pending tasks"


@pytest.mark.anyio
async def test_complete_task_tool(server):
    add_result = await server.call_tool(
        "add_task", {"title": "Task", "description": "desc"}
    )
    task_id = json.loads(add_result[0].text)["task_id"]
    await server.call_tool("get_next_task", {})
    result = await server.call_tool(
        "complete_task", {"task_id": task_id, "result": "All done"}
    )
    data = json.loads(result[0].text)
    assert data["status"] == "completed"


@pytest.mark.anyio
async def test_fail_task_tool(server):
    add_result = await server.call_tool(
        "add_task", {"title": "Task", "description": "desc"}
    )
    task_id = json.loads(add_result[0].text)["task_id"]
    await server.call_tool("get_next_task", {})
    result = await server.call_tool(
        "fail_task", {"task_id": task_id, "error": "Broke"}
    )
    data = json.loads(result[0].text)
    assert data["status"] == "failed"


@pytest.mark.anyio
async def test_list_tasks_tool(server):
    await server.call_tool("add_task", {"title": "T1", "description": "d"})
    await server.call_tool("add_task", {"title": "T2", "description": "d"})
    result = await server.call_tool("list_tasks", {})
    data = json.loads(result[0].text)
    assert len(data["tasks"]) == 2


@pytest.mark.anyio
async def test_list_tasks_filtered(server):
    await server.call_tool("add_task", {"title": "T1", "description": "d"})
    await server.call_tool("add_task", {"title": "T2", "description": "d"})
    await server.call_tool("get_next_task", {})
    result = await server.call_tool("list_tasks", {"status": "pending"})
    data = json.loads(result[0].text)
    assert len(data["tasks"]) == 1


@pytest.mark.anyio
async def test_get_status_tool(server):
    await server.call_tool("add_task", {"title": "T1", "description": "d"})
    await server.call_tool("add_task", {"title": "T2", "description": "d"})
    result = await server.call_tool("get_status", {})
    data = json.loads(result[0].text)
    assert data["total"] == 2
    assert data["pending"] == 2
```

**Step 2: Run test to verify it fails**

Run: `cd /home/ianmcvann/initiative && uv run pytest tests/test_server.py -v`
Expected: FAIL — module not found

**Step 3: Write minimal implementation**

Create `src/initiative/server.py`:
```python
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
```

**Step 4: Add anyio test dependency to pyproject.toml**

Add to `pyproject.toml` under `[project.optional-dependencies]`:
```toml
[project.optional-dependencies]
dev = [
    "pytest",
    "anyio[trio]",
    "pytest-anyio",
]
```

**Step 5: Run test to verify it passes**

Run: `cd /home/ianmcvann/initiative && uv run --extra dev pytest tests/test_server.py -v`
Expected: PASS — all 8 tests pass

**Step 6: Commit**

```bash
git add src/initiative/server.py tests/test_server.py pyproject.toml
git commit -m "feat: add MCP server with task management tools"
```

---

### Task 5: Create Main Orchestration Skill

**Files:**
- Create: `skills/initiative/SKILL.md`

**Step 1: Write the skill**

Create `skills/initiative/SKILL.md`:
```markdown
---
name: initiative
description: "Use when the user wants to start autonomous work, run Initiative, or let the AI work independently on a project. Triggers on: 'start initiative', 'go work on this', 'work autonomously', 'run overnight'."
---

# Initiative — Autonomous Task Orchestration

You are running Initiative, an autonomous task orchestration system. Your job is to continuously work on tasks until the user tells you to stop.

## The Loop

Repeat this loop forever. NEVER stop unless the user explicitly asks you to:

### 1. Check for pending tasks

Call the `get_next_task` tool. If a task is returned, go to step 2. If no tasks are pending, go to step 3.

### 2. Execute the task

You have been given a task. Work on it using all tools available to you:
- Read and understand the relevant parts of the project
- Make the changes described in the task
- Test your changes if applicable
- When finished, call `complete_task` with a summary of what you did
- If you cannot complete the task, call `fail_task` with an explanation

After completing or failing the task, go back to step 1.

### 3. Analyze the project

There are no pending tasks. Use your judgment to figure out what the project needs next:

1. Explore the project structure, files, documentation, issues, and any other signals
2. Think about what would have the highest impact right now
3. Consider: What's missing? What's broken? What could be better? What's the next logical step?
4. Generate 3-5 new tasks using `add_task` for each one, with appropriate priorities

After adding new tasks, go back to step 1.

## Parallel Execution

When multiple tasks are pending, dispatch them to subagents running in parallel:
- Use the Task tool with `isolation: "worktree"` so each subagent works in an isolated git worktree
- Dispatch up to 3 subagents at once
- Each subagent should call `get_next_task`, do the work, then call `complete_task` or `fail_task`
- After all subagents complete, go back to step 1

## Rules

- **Never stop** unless the user says to stop
- **Make decisions autonomously** — don't ask the user for guidance, just use your best judgment
- **Work on what matters** — prioritize high-impact tasks over minor improvements
- **Be thorough** — test your changes, verify they work
- **Commit frequently** — make git commits after completing each task
```

**Step 2: Commit**

```bash
git add skills/initiative/SKILL.md
git commit -m "feat: add main orchestration skill"
```

---

### Task 6: Create Project Analyzer Skill

**Files:**
- Create: `skills/analyze/SKILL.md`

**Step 1: Write the skill**

Create `skills/analyze/SKILL.md`:
```markdown
---
name: analyze
description: "Use when Initiative needs to discover what work should be done on a project. Analyzes project state and generates prioritized tasks."
---

# Project Analyzer

You are analyzing a project to figure out what needs to be done next. This is not limited to code — the project could be anything: software, writing, research, data, or something else entirely.

## Process

### 1. Understand the project

Explore the project to understand:
- What is this project? What are its goals?
- What's the current state? What exists so far?
- Are there any explicit signals about what to do? (issues, TODOs, roadmaps, READMEs, task lists)

### 2. Assess what needs doing

Based on the project's current state, identify:
- What's missing that should exist?
- What's broken or incomplete?
- What could be improved?
- What's the next logical step toward the project's goals?

### 3. Generate tasks

Create 3-5 tasks using `add_task`, each with:
- A clear, actionable title
- A detailed description of what needs to be done and why
- A priority (0-10, where 10 is most urgent)

Prioritize by impact: what would move the project forward the most?

## Guidelines

- Be specific — "Implement user login with email/password" not "Add auth"
- Be practical — suggest tasks that can be completed in a single focused session
- Be diverse — don't suggest 5 variations of the same thing
- Be bold — suggest meaningful improvements, not just cosmetic changes
```

**Step 2: Commit**

```bash
git add skills/analyze/SKILL.md
git commit -m "feat: add project analyzer skill"
```

---

### Task 7: Create User-Facing Commands

**Files:**
- Create: `commands/start.md`
- Create: `commands/status.md`
- Create: `commands/stop.md`

**Step 1: Create start command**

Create `commands/start.md`:
```markdown
---
description: "Start Initiative autonomous orchestration"
argument-hint: "[optional direction]"
---

Invoke the initiative:initiative skill and follow it exactly. If the user provided a direction argument, use the `add_task` tool to create an initial task from their direction before starting the loop.
```

**Step 2: Create status command**

Create `commands/status.md`:
```markdown
---
description: "Check Initiative task queue status"
---

Call the `get_status` tool to get queue counts, then call `list_tasks` to show recent tasks. Present a concise summary to the user showing: total tasks, how many are pending/in-progress/completed/failed, and the titles of any in-progress tasks.
```

**Step 3: Create stop command**

Create `commands/stop.md`:
```markdown
---
description: "Stop Initiative orchestration"
---

Stop the Initiative orchestration loop. Tell the user the loop has been stopped and show a final status summary using `get_status`.
```

**Step 4: Commit**

```bash
git add commands/
git commit -m "feat: add start, status, and stop commands"
```

---

### Task 8: Create Hooks for Lifecycle Management

**Files:**
- Create: `hooks/hooks.json`

**Step 1: Create hooks config**

Create `hooks/hooks.json`:
```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup",
        "hooks": [
          {
            "type": "command",
            "command": "echo 'Initiative plugin loaded. Use /initiative:start to begin autonomous orchestration.'"
          }
        ]
      }
    ]
  }
}
```

**Step 2: Commit**

```bash
git add hooks/
git commit -m "feat: add lifecycle hooks"
```

---

### Task 9: Create tests/__init__.py and Run Full Test Suite

**Files:**
- Create: `tests/__init__.py`

**Step 1: Create test init**

Create `tests/__init__.py` (empty file).

**Step 2: Run full test suite**

Run: `cd /home/ianmcvann/initiative && uv run --extra dev pytest tests/ -v`
Expected: PASS — all tests pass (4 model tests + 8 database tests + 8 server tests = 20 tests)

**Step 3: Commit**

```bash
git add tests/__init__.py
git commit -m "chore: add test init and verify full test suite passes"
```

---

### Task 10: End-to-End Verification

**Step 1: Verify plugin structure is complete**

Run: `find /home/ianmcvann/initiative -type f | head -30` to confirm all files exist:
```
.claude-plugin/plugin.json
.mcp.json
pyproject.toml
src/initiative/__init__.py
src/initiative/models.py
src/initiative/database.py
src/initiative/server.py
skills/initiative/SKILL.md
skills/analyze/SKILL.md
commands/start.md
commands/status.md
commands/stop.md
hooks/hooks.json
tests/__init__.py
tests/test_models.py
tests/test_database.py
tests/test_server.py
docs/plans/2026-02-27-initiative-design.md
docs/plans/2026-02-27-initiative-implementation.md
```

**Step 2: Verify MCP server starts**

Run: `cd /home/ianmcvann/initiative && echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' | timeout 5 uv run initiative || true`
Expected: JSON-RPC response confirming server initialized

**Step 3: Run full test suite one final time**

Run: `cd /home/ianmcvann/initiative && uv run --extra dev pytest tests/ -v --tb=short`
Expected: All tests pass

**Step 4: Final commit with all plan docs**

```bash
git add docs/plans/2026-02-27-initiative-implementation.md
git commit -m "docs: add implementation plan"
```
