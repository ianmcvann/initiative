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
