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
async def test_fail_task_tool(server):
    add_data = await call_tool(server, "add_task", {"title": "Task", "description": "desc"})
    task_id = add_data["task_id"]
    await call_tool(server, "get_next_task")
    data = await call_tool(server, "fail_task", {"task_id": task_id, "error": "Broke"})
    assert data["status"] == "failed"


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
