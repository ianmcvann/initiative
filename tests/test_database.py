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
