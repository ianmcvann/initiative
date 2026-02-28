import pytest
from initiative.database import TaskStore
from initiative.models import Task, TaskStatus


@pytest.fixture
def store(tmp_path):
    db_path = tmp_path / "test.db"
    return TaskStore(str(db_path))


def test_transaction_commits_on_success(store):
    """Transaction context manager commits mutations on normal exit."""
    task_id = store.add_task("Parent", "desc")
    with store.transaction():
        store.add_tag(task_id, "test-tag", _commit=False)
    tags = store.get_tags(task_id)
    assert "test-tag" in tags


def test_transaction_rollback_on_exception(store):
    """Transaction context manager rolls back mutations on exception."""
    task_id = store.add_task("Task", "desc")
    with pytest.raises(RuntimeError):
        with store.transaction():
            store.add_tag(task_id, "will-be-rolled-back", _commit=False)
            raise RuntimeError("intentional failure")
    tags = store.get_tags(task_id)
    assert "will-be-rolled-back" not in tags


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

    pending, pending_total = store.list_tasks(status=TaskStatus.PENDING)
    in_progress, ip_total = store.list_tasks(status=TaskStatus.IN_PROGRESS)
    assert len(pending) == 2
    assert len(in_progress) == 1


def test_list_tasks_all(store):
    store.add_task("Task 1", "desc")
    store.add_task("Task 2", "desc")
    all_tasks, total = store.list_tasks()
    assert len(all_tasks) == 2
    assert total == 2


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
    assert status["cancelled"] == 0


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
    """Manual retry on a non-failed task returns None."""
    task_id = store.add_task("Pending task", "desc")
    task = store.retry_task(task_id)
    assert task is None


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

    bug_tasks, bug_total = store.list_tasks(tag="bug")
    assert len(bug_tasks) == 2
    titles = [t.title for t in bug_tasks]
    assert "Bug task" in titles
    assert "Both task" in titles

    feature_tasks, feat_total = store.list_tasks(tag="feature")
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

    pending_bugs, total = store.list_tasks(status=TaskStatus.PENDING, tag="bug")
    assert len(pending_bugs) == 1
    assert pending_bugs[0].title == "Bug pending"


def test_list_tasks_no_tag_filter_returns_all(store):
    """list_tasks without tag filter returns all tasks."""
    store.add_task("Task 1", "desc", tags=["bug"])
    store.add_task("Task 2", "desc")
    all_tasks, total = store.list_tasks()
    assert len(all_tasks) == 2
    assert total == 2


def test_dependency_on_nonexistent_task_raises(store):
    """Depending on a non-existent task raises an error (FK constraint)."""
    with pytest.raises(Exception):
        store.add_task("Orphan dep", "desc", depends_on=[9999])


def test_circular_dependency_detected(store):
    """Circular dependency chains are detected and rejected."""
    # Build chain: A <- B <- C  (C depends on B, B depends on A)
    a_id = store.add_task("Task A", "desc")
    b_id = store.add_task("Task B", "desc", depends_on=[a_id])
    c_id = store.add_task("Task C", "desc", depends_on=[b_id])
    assert c_id is not None  # linear chain is fine

    # To create a cycle that add_task can detect, we need the new task's ID
    # to appear among the ancestors of one of its deps.  Since the task is
    # brand-new, we predict its ID and inject a back-edge before calling add_task.
    next_id_row = store._conn.execute(
        "SELECT MAX(id) + 1 as nid FROM tasks"
    ).fetchone()
    future_id = next_id_row["nid"]

    # Temporarily disable FK constraints so we can reference the not-yet-existing task.
    store._conn.execute("PRAGMA foreign_keys=OFF")
    store._conn.execute(
        "INSERT INTO task_dependencies (task_id, depends_on_id) VALUES (?, ?)",
        (a_id, future_id),
    )
    store._conn.commit()
    store._conn.execute("PRAGMA foreign_keys=ON")

    # Now add_task for future_id with depends_on=[b_id].
    # Ancestor walk: b_id -> a_id -> future_id (the new task itself) => cycle!
    with pytest.raises(ValueError, match="Circular dependency"):
        store.add_task("Task D", "desc", depends_on=[b_id])


def test_foreign_keys_enabled(store):
    """Foreign key constraints are enforced."""
    # Try to insert a tag for a non-existent task
    with pytest.raises(Exception):
        store._conn.execute(
            "INSERT INTO task_tags (task_id, tag) VALUES (?, ?)",
            (9999, "orphan"),
        )
        store._conn.commit()


def test_context_manager(tmp_path):
    """TaskStore works as a context manager."""
    db_path = tmp_path / "ctx.db"
    with TaskStore(str(db_path)) as store:
        task_id = store.add_task("Context task", "desc")
        assert task_id == 1
    # After closing, operations should fail
    with pytest.raises(Exception):
        store.add_task("Should fail", "desc")


def test_close(tmp_path):
    """TaskStore.close() closes the connection."""
    db_path = tmp_path / "close.db"
    store = TaskStore(str(db_path))
    store.add_task("Before close", "desc")
    store.close()
    with pytest.raises(Exception):
        store.add_task("After close", "desc")


def test_get_next_task_sets_started_at(store):
    """get_next_task sets started_at timestamp."""
    task_id = store.add_task("Task", "desc")
    task = store.get_task(task_id)
    assert task.started_at is None
    task = store.get_next_task()
    assert task.started_at is not None


def test_complete_task_sets_completed_at(store):
    """complete_task sets completed_at timestamp."""
    task_id = store.add_task("Task", "desc")
    store.get_next_task()
    store.complete_task(task_id, result="done")
    task = store.get_task(task_id)
    assert task.completed_at is not None
    assert task.started_at is not None


def test_fail_task_permanent_sets_completed_at(store):
    """Permanent failure sets completed_at timestamp."""
    task_id = store.add_task("Task", "desc", max_retries=0)
    store.get_next_task()
    store.fail_task(task_id, error="broke")
    task = store.get_task(task_id)
    assert task.completed_at is not None


def test_fail_task_retry_no_completed_at(store):
    """Auto-retry does not set completed_at."""
    task_id = store.add_task("Task", "desc", max_retries=2)
    store.get_next_task()
    store.fail_task(task_id, error="retry me")
    task = store.get_task(task_id)
    assert task.completed_at is None
    assert task.status == TaskStatus.PENDING


def test_get_status_includes_metrics(store):
    """get_status includes execution metrics."""
    status = store.get_status()
    assert "avg_completion_time_seconds" in status
    assert "tasks_completed_last_hour" in status
    assert "oldest_pending_task_age_seconds" in status


def test_get_status_avg_completion_time(store):
    """avg_completion_time_seconds is computed for completed tasks."""
    task_id = store.add_task("Task", "desc")
    store.get_next_task()
    store.complete_task(task_id, result="done")
    status = store.get_status()
    assert status["avg_completion_time_seconds"] is not None
    assert status["avg_completion_time_seconds"] >= 0


def test_get_status_no_completed_tasks(store):
    """avg_completion_time_seconds is None when no tasks completed."""
    store.add_task("Task", "desc")
    status = store.get_status()
    assert status["avg_completion_time_seconds"] is None


def test_get_status_oldest_pending_age(store):
    """oldest_pending_task_age_seconds tracks oldest pending task."""
    store.add_task("Old task", "desc")
    status = store.get_status()
    assert status["oldest_pending_task_age_seconds"] is not None
    assert status["oldest_pending_task_age_seconds"] >= 0


def test_get_status_no_pending_tasks(store):
    """oldest_pending_task_age_seconds is None when no pending tasks."""
    task_id = store.add_task("Task", "desc")
    store.get_next_task()
    store.complete_task(task_id)
    status = store.get_status()
    assert status["oldest_pending_task_age_seconds"] is None


def test_get_summary_all(store):
    """get_summary returns lightweight task info."""
    store.add_task("Task 1", "long description here", priority=5)
    store.add_task("Task 2", "another long description", priority=10)
    summaries, total = store.get_summary()
    assert len(summaries) == 2
    assert total == 2
    # Should be ordered by priority DESC
    assert summaries[0]["title"] == "Task 2"
    assert summaries[0]["priority"] == 10
    # Should only have id, title, status, priority - no description
    assert "description" not in summaries[0]


def test_get_summary_filtered(store):
    """get_summary can filter by status."""
    store.add_task("Pending", "desc")
    task_id = store.add_task("Will complete", "desc", priority=10)
    store.get_next_task()
    store.complete_task(task_id)
    pending, p_total = store.get_summary(status=TaskStatus.PENDING)
    assert len(pending) == 1
    assert pending[0]["title"] == "Pending"
    completed, c_total = store.get_summary(status=TaskStatus.COMPLETED)
    assert len(completed) == 1
    assert completed[0]["title"] == "Will complete"


def test_complete_task_returns_false_for_nonexistent(store):
    """complete_task returns False for nonexistent task."""
    assert store.complete_task(9999) is False


def test_complete_task_returns_false_for_pending(store):
    """complete_task returns False for a pending task (not in_progress)."""
    task_id = store.add_task("Task", "desc")
    assert store.complete_task(task_id) is False
    task = store.get_task(task_id)
    assert task.status == TaskStatus.PENDING


def test_complete_task_returns_false_for_already_completed(store):
    """complete_task returns False if task already completed."""
    task_id = store.add_task("Task", "desc")
    store.get_next_task()
    assert store.complete_task(task_id) is True
    assert store.complete_task(task_id) is False


def test_fail_task_returns_none_for_pending(store):
    """fail_task on a pending task returns None (not in_progress)."""
    task_id = store.add_task("Task", "desc")
    result = store.fail_task(task_id, error="nope")
    assert result is None
    # Task should be unchanged
    task = store.get_task(task_id)
    assert task.status == TaskStatus.PENDING
    assert task.error is None


def test_fail_task_returns_none_for_nonexistent(store):
    """fail_task on a nonexistent task returns None."""
    result = store.fail_task(9999, error="nope")
    assert result is None


def test_fail_task_returns_none_for_completed(store):
    """fail_task on a completed task returns None (not in_progress)."""
    task_id = store.add_task("Task", "desc")
    store.get_next_task()
    store.complete_task(task_id)
    result = store.fail_task(task_id, error="nope")
    assert result is None
    # Task should be unchanged
    task = store.get_task(task_id)
    assert task.status == TaskStatus.COMPLETED


def test_retry_task_resets_completed_at(store):
    """retry_task resets completed_at and started_at to None."""
    task_id = store.add_task("Task", "desc", max_retries=0)
    store.get_next_task()
    store.fail_task(task_id, error="broke")
    task = store.get_task(task_id)
    assert task.completed_at is not None
    assert task.started_at is not None

    task = store.retry_task(task_id)
    assert task.completed_at is None
    assert task.started_at is None
    assert task.status == TaskStatus.PENDING


def test_list_tasks_pagination(store):
    """list_tasks supports limit and offset."""
    for i in range(5):
        store.add_task(f"Task {i}", "desc")
    tasks, total = store.list_tasks(limit=2, offset=0)
    assert len(tasks) == 2
    assert total == 5
    tasks2, total2 = store.list_tasks(limit=2, offset=2)
    assert len(tasks2) == 2
    assert total2 == 5
    tasks3, total3 = store.list_tasks(limit=2, offset=4)
    assert len(tasks3) == 1
    assert total3 == 5


def test_list_tasks_pagination_offset_beyond_total(store):
    """list_tasks with offset beyond total returns empty."""
    store.add_task("Task", "desc")
    tasks, total = store.list_tasks(limit=10, offset=100)
    assert len(tasks) == 0
    assert total == 1


def test_get_summary_pagination(store):
    """get_summary supports limit and offset."""
    for i in range(5):
        store.add_task(f"Task {i}", "desc")
    summaries, total = store.get_summary(limit=3, offset=0)
    assert len(summaries) == 3
    assert total == 5
    summaries2, total2 = store.get_summary(limit=3, offset=3)
    assert len(summaries2) == 2
    assert total2 == 5


def test_recover_stale_tasks_none_stale(store):
    """recover_stale_tasks returns 0 when no tasks are stale."""
    store.add_task("Task", "desc")
    store.get_next_task()
    count = store.recover_stale_tasks(timeout_minutes=30)
    assert count == 0


def test_recover_stale_tasks_recovers_old(store):
    """recover_stale_tasks resets tasks with old updated_at."""
    task_id = store.add_task("Task", "desc")
    store.get_next_task()
    # Manually backdate updated_at to simulate a stale task
    store._conn.execute(
        "UPDATE tasks SET updated_at = datetime('now', '-60 minutes') WHERE id = ?",
        (task_id,),
    )
    store._conn.commit()
    count = store.recover_stale_tasks(timeout_minutes=30)
    assert count == 1
    task = store.get_task(task_id)
    assert task.status == TaskStatus.PENDING
    assert task.started_at is None


def test_recover_stale_tasks_ignores_pending(store):
    """recover_stale_tasks does not affect pending tasks."""
    store.add_task("Task", "desc")
    count = store.recover_stale_tasks(timeout_minutes=1)
    assert count == 0


def test_schema_migration_applied(store):
    """Schema version table exists and has correct version."""
    row = store._conn.execute("SELECT MAX(version) as v FROM schema_version").fetchone()
    assert row["v"] == 2


# --- cancel_task tests ---


def test_cancel_pending_task(store):
    """cancel_task cancels a pending task."""
    task_id = store.add_task("Cancel me", "desc")
    assert store.cancel_task(task_id) is True
    task = store.get_task(task_id)
    assert task.status == TaskStatus.CANCELLED


def test_cancel_in_progress_task(store):
    """cancel_task cancels an in_progress task."""
    task_id = store.add_task("Cancel me", "desc")
    store.get_next_task()
    assert store.cancel_task(task_id) is True
    task = store.get_task(task_id)
    assert task.status == TaskStatus.CANCELLED


def test_cancel_completed_task_returns_false(store):
    """cancel_task returns False for a completed task."""
    task_id = store.add_task("Task", "desc")
    store.get_next_task()
    store.complete_task(task_id)
    assert store.cancel_task(task_id) is False
    task = store.get_task(task_id)
    assert task.status == TaskStatus.COMPLETED


def test_cancel_failed_task_returns_false(store):
    """cancel_task returns False for a failed task."""
    task_id = store.add_task("Task", "desc", max_retries=0)
    store.get_next_task()
    store.fail_task(task_id, error="broke")
    assert store.cancel_task(task_id) is False
    task = store.get_task(task_id)
    assert task.status == TaskStatus.FAILED


def test_cancel_already_cancelled_returns_false(store):
    """cancel_task returns False for an already cancelled task."""
    task_id = store.add_task("Task", "desc")
    assert store.cancel_task(task_id) is True
    assert store.cancel_task(task_id) is False


def test_cancel_nonexistent_task_returns_false(store):
    """cancel_task returns False for a nonexistent task."""
    assert store.cancel_task(9999) is False


def test_cancelled_task_not_picked_up(store):
    """get_next_task does not return cancelled tasks."""
    task_id = store.add_task("Cancel me", "desc", priority=10)
    store.add_task("Pick me", "desc", priority=1)
    store.cancel_task(task_id)
    task = store.get_next_task()
    assert task.title == "Pick me"


# --- update_task tests ---


def test_update_task_title(store):
    """update_task updates the title of a pending task."""
    task_id = store.add_task("Old title", "desc")
    task = store.update_task(task_id, title="New title")
    assert task is not None
    assert task.title == "New title"
    assert task.description == "desc"


def test_update_task_description(store):
    """update_task updates the description of a pending task."""
    task_id = store.add_task("Title", "Old desc")
    task = store.update_task(task_id, description="New desc")
    assert task is not None
    assert task.description == "New desc"
    assert task.title == "Title"


def test_update_task_priority(store):
    """update_task updates the priority of a pending task."""
    task_id = store.add_task("Title", "desc", priority=1)
    task = store.update_task(task_id, priority=99)
    assert task is not None
    assert task.priority == 99


def test_update_task_multiple_fields(store):
    """update_task can update multiple fields at once."""
    task_id = store.add_task("Old", "Old desc", priority=1)
    task = store.update_task(task_id, title="New", description="New desc", priority=50)
    assert task is not None
    assert task.title == "New"
    assert task.description == "New desc"
    assert task.priority == 50


def test_update_task_no_fields_returns_unchanged(store):
    """update_task with no fields returns the task unchanged."""
    task_id = store.add_task("Title", "desc", priority=5)
    task = store.update_task(task_id)
    assert task is not None
    assert task.title == "Title"
    assert task.priority == 5


def test_update_task_nonexistent_returns_none(store):
    """update_task returns None for a nonexistent task."""
    assert store.update_task(9999, title="New") is None


def test_update_task_in_progress_returns_none(store):
    """update_task returns None for an in_progress task."""
    task_id = store.add_task("Title", "desc")
    store.get_next_task()
    assert store.update_task(task_id, title="New") is None


def test_update_task_completed_returns_none(store):
    """update_task returns None for a completed task."""
    task_id = store.add_task("Title", "desc")
    store.get_next_task()
    store.complete_task(task_id)
    assert store.update_task(task_id, title="New") is None


def test_update_task_cancelled_returns_none(store):
    """update_task returns None for a cancelled task."""
    task_id = store.add_task("Title", "desc")
    store.cancel_task(task_id)
    assert store.update_task(task_id, title="New") is None


def test_update_task_updates_timestamp(store):
    """update_task updates the updated_at timestamp."""
    task_id = store.add_task("Title", "desc")
    task_before = store.get_task(task_id)
    task_after = store.update_task(task_id, title="New")
    assert task_after.updated_at >= task_before.updated_at


# --- get_status with cancelled count ---


# --- cascade cancel tests ---


def test_cascade_cancel_single_level(store):
    """Cancelling A cascades to B which depends on A."""
    a_id = store.add_task("Task A", "desc")
    b_id = store.add_task("Task B", "desc", depends_on=[a_id])
    store.cancel_task(a_id)
    b = store.get_task(b_id)
    assert b.status == TaskStatus.CANCELLED


def test_cascade_cancel_multi_level(store):
    """Cancelling A cascades through A -> B -> C chain."""
    a_id = store.add_task("Task A", "desc")
    b_id = store.add_task("Task B", "desc", depends_on=[a_id])
    c_id = store.add_task("Task C", "desc", depends_on=[b_id])
    store.cancel_task(a_id)
    b = store.get_task(b_id)
    c = store.get_task(c_id)
    assert b.status == TaskStatus.CANCELLED
    assert c.status == TaskStatus.CANCELLED


def test_cascade_cancel_partial(store):
    """C depends on both A and B. Cancelling A cascades to C."""
    a_id = store.add_task("Task A", "desc")
    b_id = store.add_task("Task B", "desc")
    c_id = store.add_task("Task C", "desc", depends_on=[a_id, b_id])
    store.cancel_task(a_id)
    c = store.get_task(c_id)
    assert c.status == TaskStatus.CANCELLED
    # B should be unaffected
    b = store.get_task(b_id)
    assert b.status == TaskStatus.PENDING


def test_cascade_cancel_on_permanent_fail(store):
    """Permanent failure of A cascades cancel to B."""
    a_id = store.add_task("Task A", "desc", max_retries=0)
    b_id = store.add_task("Task B", "desc", depends_on=[a_id])
    # Move A to in_progress then fail it permanently
    store.get_next_task()
    store.fail_task(a_id, error="fatal")
    a = store.get_task(a_id)
    assert a.status == TaskStatus.FAILED
    b = store.get_task(b_id)
    assert b.status == TaskStatus.CANCELLED


def test_cascade_cancel_skips_completed(store):
    """Cascade does not cancel already-completed tasks."""
    a_id = store.add_task("Task A", "desc")
    b_id = store.add_task("Task B", "desc", depends_on=[a_id])
    store._conn.execute(
        "UPDATE tasks SET status = ? WHERE id = ?",
        (TaskStatus.COMPLETED.value, b_id),
    )
    store._conn.commit()
    b = store.get_task(b_id)
    assert b.status == TaskStatus.COMPLETED
    # Now cancel A — B should stay completed
    store.cancel_task(a_id)
    b = store.get_task(b_id)
    assert b.status == TaskStatus.COMPLETED


# --- get_status ready vs blocked tests ---


def test_get_status_pending_ready_and_blocked(store):
    """get_status reports pending_ready and pending_blocked counts correctly."""
    a_id = store.add_task("Task A", "desc")
    b_id = store.add_task("Task B", "desc", depends_on=[a_id])
    c_id = store.add_task("Task C", "desc")

    status = store.get_status()
    assert status["pending"] == 3
    assert status["pending_ready"] == 2
    assert status["pending_blocked"] == 1

    store.get_next_task()
    store.complete_task(a_id)
    status = store.get_status()
    assert status["pending"] == 2
    assert status["pending_ready"] == 2
    assert status["pending_blocked"] == 0


def test_get_status_all_ready(store):
    """When no tasks have dependencies, all pending tasks are ready."""
    store.add_task("Task 1", "desc")
    store.add_task("Task 2", "desc")
    store.add_task("Task 3", "desc")

    status = store.get_status()
    assert status["pending"] == 3
    assert status["pending_ready"] == 3
    assert status["pending_blocked"] == 0


def test_get_status_includes_cancelled(store):
    """get_status includes the cancelled count."""
    store.add_task("Task 1", "desc")
    task_id = store.add_task("Task 2", "desc")
    store.cancel_task(task_id)
    status = store.get_status()
    assert status["cancelled"] == 1
    assert status["pending"] == 1
    assert status["total"] == 2
