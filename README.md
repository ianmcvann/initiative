# Initiative

Autonomous AI task orchestration for Claude Code. Initiative is a plugin that turns Claude into a never-stopping background worker — it continuously pulls tasks from a priority queue, executes them, and when the queue is empty, analyzes your project to generate new high-impact tasks automatically.

## How It Works

Initiative runs as an MCP server that provides task management tools to Claude Code. The orchestration loop is simple:

1. **Check for tasks** — Pull the highest-priority pending task
2. **Execute** — Work on the task using all available tools, then mark it completed or failed
3. **Analyze** — When the queue is empty, explore the project and generate 3-5 new tasks
4. **Repeat** — Never stop unless the user says so

When multiple tasks are pending, Initiative dispatches up to 3 parallel subagents in isolated git worktrees for concurrent execution.

## Installation

```bash
# Add the Initiative marketplace
claude plugin marketplace add ianmcvann/initiative

# Install Initiative plugin
claude plugin install initiative@initiative
```

### Start working!

```
/initiative:start
```

### Manual Setup (Alternative)

If you prefer manual installation:

```bash
# Clone and install dependencies
git clone https://github.com/ianmcvann/initiative.git
cd initiative
uv sync

# Add as a Claude Code plugin
claude plugin add ./initiative
```

## Usage

Initiative provides three commands:

### `/initiative:start [direction]`

Start autonomous orchestration. Optionally provide a direction to seed the initial task:

```
/initiative:start
/initiative:start "Add authentication to the API"
```

### `/initiative:status`

Check the current state of the task queue:

```
/initiative:status
```

Shows total tasks, counts by status (pending/in-progress/completed/failed), and titles of any in-progress tasks.

### `/initiative:stop`

Stop the orchestration loop and show a final status summary:

```
/initiative:stop
```

## Architecture

```
src/initiative/
  models.py      # Task dataclass and TaskStatus enum
  database.py    # SQLite task store with priority queue
  server.py      # FastMCP server exposing task management tools
```

**Task Store** — SQLite database with WAL journaling. Tasks have a title, description, priority, status, and timestamps. The priority queue returns the highest-priority pending task first (ties broken by creation time).

**MCP Server** — Built on [FastMCP](https://github.com/jlowin/fastmcp), exposes six tools over stdio transport:

| Tool | Description |
|------|-------------|
| `add_task` | Add a new task with title, description, and priority |
| `get_next_task` | Pull the highest-priority pending task and mark it in-progress |
| `complete_task` | Mark a task as completed with a result summary |
| `fail_task` | Mark a task as failed with an error description |
| `list_tasks` | List tasks, optionally filtered by status |
| `get_status` | Get queue summary (total, pending, in-progress, completed, failed) |

**Skills** — Two Claude Code skills drive the orchestration:
- `initiative` — The main autonomous loop
- `analyze` — Project analysis and task generation

## Development

```bash
# Install with dev dependencies
uv sync --extra dev

# Run tests
uv run pytest

# Run tests with verbose output
uv run pytest -v
```

The test suite covers models, database operations, and all MCP server tools across both asyncio and trio backends.

## License

MIT
