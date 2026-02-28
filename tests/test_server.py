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
