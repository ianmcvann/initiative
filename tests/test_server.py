import pytest
import json
from initiative.server import create_server


@pytest.fixture
def server(tmp_path):
    db_path = str(tmp_path / "test.db")
    return create_server(db_path=db_path)


async def call_tool(server, name, args=None):
    tool = await server.get_tool(name)
    result = await tool.run(args or {})
    return json.loads(result.content[0].text)


@pytest.mark.anyio
async def test_add_task_tool(server):
    data = await call_tool(server, "add_task", {"title": "Test task", "description": "A test", "priority": 5})
    assert data["task_id"] == 1
    assert data["title"] == "Test task"


@pytest.mark.anyio
async def test_get_next_task_tool(server):
    await call_tool(server, "add_task", {"title": "Task 1", "description": "desc", "priority": 1})
    await call_tool(server, "add_task", {"title": "Task 2", "description": "desc", "priority": 10})
    data = await call_tool(server, "get_next_task")
    assert data["title"] == "Task 2"
    assert data["status"] == "in_progress"


@pytest.mark.anyio
async def test_get_next_task_empty(server):
    data = await call_tool(server, "get_next_task")
    assert data["message"] == "No pending tasks"


@pytest.mark.anyio
async def test_complete_task_tool(server):
    add_data = await call_tool(server, "add_task", {"title": "Task", "description": "desc"})
    task_id = add_data["task_id"]
    await call_tool(server, "get_next_task")
    data = await call_tool(server, "complete_task", {"task_id": task_id, "result": "All done"})
    assert data["status"] == "completed"


@pytest.mark.anyio
async def test_fail_task_tool_auto_retry(server):
    """With default max_retries=2, first failure auto-retries."""
    add_data = await call_tool(server, "add_task", {"title": "Task", "description": "desc"})
    task_id = add_data["task_id"]
    await call_tool(server, "get_next_task")
    data = await call_tool(server, "fail_task", {"task_id": task_id, "error": "Broke"})
    assert data["status"] == "pending"
    assert data["retries"] == 1
    assert data["max_retries"] == 2
    assert "auto-retried" in data["message"]


@pytest.mark.anyio
async def test_fail_task_tool_permanent(server):
    """With max_retries=0, failure is permanent."""
    add_data = await call_tool(server, "add_task", {"title": "Task", "description": "desc", "max_retries": 0})
    task_id = add_data["task_id"]
    await call_tool(server, "get_next_task")
    data = await call_tool(server, "fail_task", {"task_id": task_id, "error": "Broke"})
    assert data["status"] == "failed"
    assert "permanently failed" in data["message"]


@pytest.mark.anyio
async def test_list_tasks_tool(server):
    await call_tool(server, "add_task", {"title": "T1", "description": "d"})
    await call_tool(server, "add_task", {"title": "T2", "description": "d"})
    data = await call_tool(server, "list_tasks")
    assert len(data["tasks"]) == 2


@pytest.mark.anyio
async def test_list_tasks_filtered(server):
    await call_tool(server, "add_task", {"title": "T1", "description": "d"})
    await call_tool(server, "add_task", {"title": "T2", "description": "d"})
    await call_tool(server, "get_next_task")
    data = await call_tool(server, "list_tasks", {"status": "pending"})
    assert len(data["tasks"]) == 1


@pytest.mark.anyio
async def test_get_status_tool(server):
    await call_tool(server, "add_task", {"title": "T1", "description": "d"})
    await call_tool(server, "add_task", {"title": "T2", "description": "d"})
    data = await call_tool(server, "get_status")
    assert data["total"] == 2
    assert data["pending"] == 2


@pytest.mark.anyio
async def test_retry_task_tool(server):
    """Manual retry requeues a failed task."""
    add_data = await call_tool(server, "add_task", {"title": "Fail me", "description": "d", "max_retries": 0})
    task_id = add_data["task_id"]
    await call_tool(server, "get_next_task")
    await call_tool(server, "fail_task", {"task_id": task_id, "error": "Broke"})
    data = await call_tool(server, "retry_task", {"task_id": task_id})
    assert data["status"] == "pending"
    assert data["message"] == "Task has been requeued for retry"


@pytest.mark.anyio
async def test_retry_task_not_failed(server):
    """Manual retry on a non-failed task returns an error."""
    add_data = await call_tool(server, "add_task", {"title": "Pending", "description": "d"})
    task_id = add_data["task_id"]
    data = await call_tool(server, "retry_task", {"task_id": task_id})
    assert "error" in data
    assert data["status"] == "pending"


@pytest.mark.anyio
async def test_retry_task_not_found(server):
    """Manual retry on a non-existent task returns an error."""
    data = await call_tool(server, "retry_task", {"task_id": 999})
    assert data["error"] == "Task not found"


@pytest.mark.anyio
async def test_add_task_with_max_retries(server):
    """add_task accepts optional max_retries parameter."""
    data = await call_tool(server, "add_task", {"title": "Custom", "description": "d", "max_retries": 5})
    assert data["max_retries"] == 5


@pytest.mark.anyio
async def test_auto_retry_full_cycle(server):
    """Task auto-retries through all attempts then permanently fails."""
    add_data = await call_tool(server, "add_task", {"title": "Fragile", "description": "d", "max_retries": 1})
    task_id = add_data["task_id"]

    # First attempt fails - should auto-retry
    await call_tool(server, "get_next_task")
    data = await call_tool(server, "fail_task", {"task_id": task_id, "error": "Error 1"})
    assert data["status"] == "pending"
    assert data["retries"] == 1

    # Second attempt fails - should permanently fail
    await call_tool(server, "get_next_task")
    data = await call_tool(server, "fail_task", {"task_id": task_id, "error": "Error 2"})
    assert data["status"] == "failed"
    assert "permanently failed" in data["message"]


@pytest.mark.anyio
async def test_add_task_with_depends_on(server):
    """add_task accepts depends_on parameter."""
    dep = await call_tool(server, "add_task", {"title": "Dep", "description": "d"})
    data = await call_tool(server, "add_task", {"title": "Blocked", "description": "d", "depends_on": [dep["task_id"]]})
    assert data["depends_on"] == [dep["task_id"]]


@pytest.mark.anyio
async def test_get_next_task_skips_blocked(server):
    """get_next_task skips tasks with uncompleted dependencies."""
    dep = await call_tool(server, "add_task", {"title": "Dep", "description": "d", "priority": 1})
    await call_tool(server, "add_task", {"title": "Blocked", "description": "d", "priority": 10, "depends_on": [dep["task_id"]]})
    data = await call_tool(server, "get_next_task")
    assert data["title"] == "Dep"


@pytest.mark.anyio
async def test_blocked_task_available_after_dep_completes(server):
    """After completing a dependency, the blocked task becomes available."""
    dep = await call_tool(server, "add_task", {"title": "Dep", "description": "d"})
    await call_tool(server, "add_task", {"title": "Blocked", "description": "d", "depends_on": [dep["task_id"]]})
    # Complete the dependency
    await call_tool(server, "get_next_task")
    await call_tool(server, "complete_task", {"task_id": dep["task_id"]})
    # Now blocked task should be available
    data = await call_tool(server, "get_next_task")
    assert data["title"] == "Blocked"
    assert data["blocked_by"] == []


@pytest.mark.anyio
async def test_add_task_with_tags(server):
    """add_task accepts tags parameter."""
    data = await call_tool(server, "add_task", {"title": "Tagged", "description": "d", "tags": ["bug", "urgent"]})
    assert data["tags"] == ["bug", "urgent"]


@pytest.mark.anyio
async def test_add_task_without_tags(server):
    """add_task without tags returns empty list."""
    data = await call_tool(server, "add_task", {"title": "No tags", "description": "d"})
    assert data["tags"] == []


@pytest.mark.anyio
async def test_add_tag_tool(server):
    """add_tag tool adds a tag to a task."""
    add_data = await call_tool(server, "add_task", {"title": "Task", "description": "d"})
    task_id = add_data["task_id"]
    data = await call_tool(server, "add_tag", {"task_id": task_id, "tag": "important"})
    assert data["message"] == "Tag added"
    assert data["tag"] == "important"
    # Verify the tag appears when listing
    tasks = await call_tool(server, "list_tasks")
    assert "important" in tasks["tasks"][0]["tags"]


@pytest.mark.anyio
async def test_add_tag_task_not_found(server):
    """add_tag on a non-existent task returns an error."""
    data = await call_tool(server, "add_tag", {"task_id": 999, "tag": "bug"})
    assert data["error"] == "Task not found"


@pytest.mark.anyio
async def test_remove_tag_tool(server):
    """remove_tag tool removes a tag from a task."""
    add_data = await call_tool(server, "add_task", {"title": "Task", "description": "d", "tags": ["bug", "urgent"]})
    task_id = add_data["task_id"]
    data = await call_tool(server, "remove_tag", {"task_id": task_id, "tag": "bug"})
    assert data["message"] == "Tag removed"
    # Verify the tag is gone
    tasks = await call_tool(server, "list_tasks")
    assert "bug" not in tasks["tasks"][0]["tags"]
    assert "urgent" in tasks["tasks"][0]["tags"]


@pytest.mark.anyio
async def test_remove_tag_task_not_found(server):
    """remove_tag on a non-existent task returns an error."""
    data = await call_tool(server, "remove_tag", {"task_id": 999, "tag": "bug"})
    assert data["error"] == "Task not found"


@pytest.mark.anyio
async def test_list_tasks_with_tag_filter(server):
    """list_tasks can filter by tag."""
    await call_tool(server, "add_task", {"title": "Bug", "description": "d", "tags": ["bug"]})
    await call_tool(server, "add_task", {"title": "Feature", "description": "d", "tags": ["feature"]})
    await call_tool(server, "add_task", {"title": "Both", "description": "d", "tags": ["bug", "feature"]})

    data = await call_tool(server, "list_tasks", {"tag": "bug"})
    assert data["count"] == 2
    titles = [t["title"] for t in data["tasks"]]
    assert "Bug" in titles
    assert "Both" in titles

    data = await call_tool(server, "list_tasks", {"tag": "feature"})
    assert data["count"] == 2
    titles = [t["title"] for t in data["tasks"]]
    assert "Feature" in titles
    assert "Both" in titles


@pytest.mark.anyio
async def test_list_tasks_with_tag_and_status_filter(server):
    """list_tasks can filter by both tag and status."""
    await call_tool(server, "add_task", {"title": "Bug1", "description": "d", "tags": ["bug"], "priority": 10})
    await call_tool(server, "add_task", {"title": "Bug2", "description": "d", "tags": ["bug"]})
    await call_tool(server, "add_task", {"title": "Feature", "description": "d", "tags": ["feature"]})
    await call_tool(server, "get_next_task")  # moves Bug1 (highest priority) to in_progress

    data = await call_tool(server, "list_tasks", {"tag": "bug", "status": "pending"})
    assert data["count"] == 1
    assert data["tasks"][0]["title"] == "Bug2"


# --- Input validation tests ---


@pytest.mark.anyio
async def test_add_task_empty_title(server):
    """add_task rejects empty title."""
    data = await call_tool(server, "add_task", {"title": "", "description": "d"})
    assert "error" in data


@pytest.mark.anyio
async def test_add_task_title_too_long(server):
    """add_task rejects title over 1000 chars."""
    data = await call_tool(server, "add_task", {"title": "x" * 1001, "description": "d"})
    assert "error" in data


@pytest.mark.anyio
async def test_add_task_empty_description(server):
    """add_task rejects empty description."""
    data = await call_tool(server, "add_task", {"title": "T", "description": ""})
    assert "error" in data


@pytest.mark.anyio
async def test_add_task_negative_priority(server):
    """add_task rejects negative priority."""
    data = await call_tool(server, "add_task", {"title": "T", "description": "d", "priority": -1})
    assert "error" in data


@pytest.mark.anyio
async def test_add_task_priority_too_high(server):
    """add_task rejects priority over 1000."""
    data = await call_tool(server, "add_task", {"title": "T", "description": "d", "priority": 1001})
    assert "error" in data


@pytest.mark.anyio
async def test_add_task_negative_max_retries(server):
    """add_task rejects negative max_retries."""
    data = await call_tool(server, "add_task", {"title": "T", "description": "d", "max_retries": -1})
    assert "error" in data


@pytest.mark.anyio
async def test_add_task_too_many_tags(server):
    """add_task rejects more than 50 tags."""
    tags = [f"tag{i}" for i in range(51)]
    data = await call_tool(server, "add_task", {"title": "T", "description": "d", "tags": tags})
    assert "error" in data


@pytest.mark.anyio
async def test_list_tasks_invalid_status(server):
    """list_tasks returns error for invalid status string."""
    data = await call_tool(server, "list_tasks", {"status": "bogus"})
    assert "error" in data


@pytest.mark.anyio
async def test_get_summary_tool(server):
    """get_summary returns lightweight task info."""
    await call_tool(server, "add_task", {"title": "T1", "description": "long desc", "priority": 5})
    await call_tool(server, "add_task", {"title": "T2", "description": "long desc", "priority": 10})
    data = await call_tool(server, "get_summary")
    assert data["count"] == 2
    assert "description" not in data["tasks"][0]
    assert data["tasks"][0]["title"] == "T2"  # higher priority first


@pytest.mark.anyio
async def test_get_summary_filtered(server):
    """get_summary can filter by status."""
    await call_tool(server, "add_task", {"title": "Pending", "description": "d"})
    await call_tool(server, "add_task", {"title": "Done", "description": "d", "priority": 10})
    await call_tool(server, "get_next_task")
    await call_tool(server, "complete_task", {"task_id": 2})
    data = await call_tool(server, "get_summary", {"status": "pending"})
    assert data["count"] == 1
    assert data["tasks"][0]["title"] == "Pending"


@pytest.mark.anyio
async def test_get_summary_invalid_status(server):
    """get_summary returns error for invalid status."""
    data = await call_tool(server, "get_summary", {"status": "bogus"})
    assert "error" in data


@pytest.mark.anyio
async def test_complete_task_not_found(server):
    """complete_task returns error for nonexistent task."""
    data = await call_tool(server, "complete_task", {"task_id": 999})
    assert data["error"] == "Task not found"


@pytest.mark.anyio
async def test_complete_task_not_in_progress(server):
    """complete_task returns error for pending task."""
    add_data = await call_tool(server, "add_task", {"title": "T", "description": "d"})
    data = await call_tool(server, "complete_task", {"task_id": add_data["task_id"]})
    assert "error" in data
    assert "not in_progress" in data["error"]


@pytest.mark.anyio
async def test_fail_task_not_in_progress(server):
    """fail_task returns error for pending task."""
    add_data = await call_tool(server, "add_task", {"title": "T", "description": "d"})
    data = await call_tool(server, "fail_task", {"task_id": add_data["task_id"]})
    assert "error" in data
    assert "not in_progress" in data["error"]


@pytest.mark.anyio
async def test_list_tasks_pagination(server):
    """list_tasks supports pagination."""
    for i in range(5):
        await call_tool(server, "add_task", {"title": f"T{i}", "description": "d"})
    data = await call_tool(server, "list_tasks", {"limit": 2, "offset": 0})
    assert data["count"] == 2
    assert data["total"] == 5
    assert data["has_more"] is True
    assert data["limit"] == 2
    assert data["offset"] == 0


@pytest.mark.anyio
async def test_list_tasks_pagination_last_page(server):
    """list_tasks pagination on last page."""
    for i in range(3):
        await call_tool(server, "add_task", {"title": f"T{i}", "description": "d"})
    data = await call_tool(server, "list_tasks", {"limit": 2, "offset": 2})
    assert data["count"] == 1
    assert data["total"] == 3
    assert data["has_more"] is False


@pytest.mark.anyio
async def test_list_tasks_invalid_limit(server):
    """list_tasks rejects invalid limit."""
    data = await call_tool(server, "list_tasks", {"limit": 0})
    assert "error" in data
    data = await call_tool(server, "list_tasks", {"limit": 201})
    assert "error" in data


@pytest.mark.anyio
async def test_list_tasks_invalid_offset(server):
    """list_tasks rejects negative offset."""
    data = await call_tool(server, "list_tasks", {"offset": -1})
    assert "error" in data


@pytest.mark.anyio
async def test_get_summary_pagination(server):
    """get_summary supports pagination."""
    for i in range(5):
        await call_tool(server, "add_task", {"title": f"T{i}", "description": "d"})
    data = await call_tool(server, "get_summary", {"limit": 3})
    assert data["count"] == 3
    assert data["total"] == 5
    assert data["has_more"] is True
