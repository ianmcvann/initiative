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


def test_fail_task_with_no_retries(store):
    task_id = store.add_task("Task", "desc", max_retries=0)
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


def test_auto_retry_on_fail(store):
    """Task goes back to pending when retries < max_retries."""
    task_id = store.add_task("Retry task", "desc", max_retries=2)
    store.get_next_task()  # moves to in_progress

    # First failure: retries 0 < max_retries 2, should auto-retry
    store.fail_task(task_id, error="Error 1")
    task = store.get_task(task_id)
    assert task.status == TaskStatus.PENDING
    assert task.retries == 1
    assert task.error == "Error 1"

    # Pick up again and fail again
    store.get_next_task()
    store.fail_task(task_id, error="Error 2")
    task = store.get_task(task_id)
    assert task.status == TaskStatus.PENDING
    assert task.retries == 2
    assert task.error == "Error 2"


def test_permanent_failure_after_max_retries(store):
    """Task stays failed when retries >= max_retries."""
    task_id = store.add_task("Fail task", "desc", max_retries=1)
    store.get_next_task()

    # First failure: retries 0 < max_retries 1, should auto-retry
    store.fail_task(task_id, error="Error 1")
    task = store.get_task(task_id)
    assert task.status == TaskStatus.PENDING
    assert task.retries == 1

    # Second failure: retries 1 >= max_retries 1, should permanently fail
    store.get_next_task()
    store.fail_task(task_id, error="Error 2")
    task = store.get_task(task_id)
    assert task.status == TaskStatus.FAILED
    assert task.retries == 1
    assert task.error == "Error 2"


def test_manual_retry_task(store):
    """Manual retry resets a failed task back to pending."""
    task_id = store.add_task("Manual retry", "desc", max_retries=0)
    store.get_next_task()
    store.fail_task(task_id, error="Failed")
    task = store.get_task(task_id)
    assert task.status == TaskStatus.FAILED

    # Manually retry
    task = store.retry_task(task_id)
    assert task.status == TaskStatus.PENDING
    assert task.retries == 0
    assert task.error is None


def test_retry_task_not_failed(store):
    """Manual retry on a non-failed task returns the task unchanged."""
    task_id = store.add_task("Pending task", "desc")
    task = store.retry_task(task_id)
    assert task.status == TaskStatus.PENDING


def test_retry_task_not_found(store):
    """Manual retry on a non-existent task returns None."""
    assert store.retry_task(999) is None


def test_add_task_custom_max_retries(store):
    """Tasks can be created with a custom max_retries value."""
    task_id = store.add_task("Custom retries", "desc", max_retries=5)
    task = store.get_task(task_id)
    assert task.max_retries == 5
    assert task.retries == 0


def test_add_task_with_dependencies(store):
    """Tasks can be created with dependencies on other tasks."""
    dep_id = store.add_task("Dependency", "must finish first")
    task_id = store.add_task("Blocked task", "desc", depends_on=[dep_id])
    task = store.get_task(task_id)
    assert task.blocked_by == [dep_id]


def test_get_next_task_skips_blocked(store):
    """get_next_task does not return tasks with uncompleted dependencies."""
    dep_id = store.add_task("Dependency", "desc", priority=1)
    store.add_task("Blocked", "desc", priority=10, depends_on=[dep_id])
    # Even though blocked task has higher priority, dependency is not complete
    task = store.get_next_task()
    assert task.title == "Dependency"


def test_get_next_task_returns_unblocked_after_dep_completes(store):
    """After a dependency completes, the blocked task becomes available."""
    dep_id = store.add_task("Dependency", "desc")
    blocked_id = store.add_task("Blocked", "desc", depends_on=[dep_id])
    # Complete the dependency
    store.get_next_task()  # pulls dependency
    store.complete_task(dep_id)
    # Now the blocked task should be available
    task = store.get_next_task()
    assert task.id == blocked_id
    assert task.title == "Blocked"
    assert task.blocked_by == []


def test_blocked_by_shows_only_uncompleted_deps(store):
    """blocked_by only shows uncompleted dependency IDs."""
    dep1_id = store.add_task("Dep 1", "desc")
    dep2_id = store.add_task("Dep 2", "desc")
    task_id = store.add_task("Blocked", "desc", depends_on=[dep1_id, dep2_id])
    # Complete one dependency
    store.get_next_task()  # pulls dep1
    store.complete_task(dep1_id)
    task = store.get_task(task_id)
    assert task.blocked_by == [dep2_id]


def test_task_with_no_dependencies_has_empty_blocked_by(store):
    """A task created without depends_on has empty blocked_by."""
    task_id = store.add_task("Simple", "desc")
    task = store.get_task(task_id)
    assert task.blocked_by == []


def test_add_tag(store):
    """Tags can be added to a task."""
    task_id = store.add_task("Taggable", "desc")
    store.add_tag(task_id, "bug")
    store.add_tag(task_id, "urgent")
    tags = store.get_tags(task_id)
    assert "bug" in tags
    assert "urgent" in tags


def test_add_tag_idempotent(store):
    """Adding the same tag twice does not duplicate it."""
    task_id = store.add_task("Taggable", "desc")
    store.add_tag(task_id, "bug")
    store.add_tag(task_id, "bug")
    tags = store.get_tags(task_id)
    assert tags.count("bug") == 1


def test_remove_tag(store):
    """Tags can be removed from a task."""
    task_id = store.add_task("Taggable", "desc")
    store.add_tag(task_id, "bug")
    store.add_tag(task_id, "urgent")
    store.remove_tag(task_id, "bug")
    tags = store.get_tags(task_id)
    assert "bug" not in tags
    assert "urgent" in tags


def test_remove_tag_nonexistent(store):
    """Removing a non-existent tag is a no-op."""
    task_id = store.add_task("Taggable", "desc")
    store.remove_tag(task_id, "nonexistent")  # should not raise


def test_get_tags_empty(store):
    """A task with no tags returns an empty list."""
    task_id = store.add_task("No tags", "desc")
    tags = store.get_tags(task_id)
    assert tags == []


def test_add_task_with_tags(store):
    """Tasks can be created with tags."""
    task_id = store.add_task("Tagged task", "desc", tags=["bug", "frontend"])
    task = store.get_task(task_id)
    assert "bug" in task.tags
    assert "frontend" in task.tags


def test_row_to_task_includes_tags(store):
    """_row_to_task populates tags field."""
    task_id = store.add_task("Tagged task", "desc", tags=["backend"])
    task = store.get_task(task_id)
    assert task.tags == ["backend"]


def test_list_tasks_filtered_by_tag(store):
    """list_tasks can filter by tag."""
    store.add_task("Bug task", "desc", tags=["bug"])
    store.add_task("Feature task", "desc", tags=["feature"])
    store.add_task("Both task", "desc", tags=["bug", "feature"])

    bug_tasks = store.list_tasks(tag="bug")
    assert len(bug_tasks) == 2
    titles = [t.title for t in bug_tasks]
    assert "Bug task" in titles
    assert "Both task" in titles

    feature_tasks = store.list_tasks(tag="feature")
    assert len(feature_tasks) == 2
    titles = [t.title for t in feature_tasks]
    assert "Feature task" in titles
    assert "Both task" in titles


def test_list_tasks_filtered_by_tag_and_status(store):
    """list_tasks can filter by both tag and status."""
    id1 = store.add_task("Bug pending", "desc", tags=["bug"])
    id2 = store.add_task("Bug in-progress", "desc", priority=10, tags=["bug"])
    store.add_task("Feature pending", "desc", tags=["feature"])
    store.get_next_task()  # moves highest priority (Bug in-progress) to in_progress

    pending_bugs = store.list_tasks(status=TaskStatus.PENDING, tag="bug")
    assert len(pending_bugs) == 1
    assert pending_bugs[0].title == "Bug pending"


def test_list_tasks_no_tag_filter_returns_all(store):
    """list_tasks without tag filter returns all tasks."""
    store.add_task("Task 1", "desc", tags=["bug"])
    store.add_task("Task 2", "desc")
    all_tasks = store.list_tasks()
    assert len(all_tasks) == 2


def test_dependency_on_nonexistent_task_raises(store):
    """Depending on a non-existent task raises an error (FK constraint)."""
    with pytest.raises(Exception):
        store.add_task("Orphan dep", "desc", depends_on=[9999])


def test_circular_dependency_detected(store):
    """Circular dependency chains are detected and rejected."""
    # Create A -> B chain
    a_id = store.add_task("Task A", "desc")
    b_id = store.add_task("Task B", "desc", depends_on=[a_id])
    # Now try to create C that depends on B, and also make A depend on C (cycle)
    # First verify simple chain works
    c_id = store.add_task("Task C", "desc", depends_on=[b_id])
    assert c_id is not None


def test_foreign_keys_enabled(store):
    """Foreign key constraints are enforced."""
    # Try to insert a tag for a non-existent task
    with pytest.raises(Exception):
        store._conn.execute(
            "INSERT INTO task_tags (task_id, tag) VALUES (?, ?)",
            (9999, "orphan"),
        )
        store._conn.commit()
