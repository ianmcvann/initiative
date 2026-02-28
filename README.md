# Initiative

Start it before bed. Wake up to a codebase that's been analyzed by 8 specialist agents, tasks prioritized and executed in parallel worktrees, with commits ready for review.

Initiative is an autonomous task orchestration plugin for Claude Code. It turns Claude into a never-stopping background worker that continuously pulls tasks from a priority queue, executes them in isolated git worktrees, and when the queue runs dry, convenes a panel of 8 expert agents to analyze your project and generate new high-impact tasks automatically. It doesn't just fix problems -- it builds forward.

## How It Works

Initiative runs as an MCP server that provides task management tools to Claude Code. The orchestration loop is simple:

1. **Check for tasks** -- Pull the highest-priority pending task (respecting dependency order)
2. **Execute in parallel** -- Dispatch up to 3 subagents in isolated git worktrees for concurrent execution
3. **Analyze** -- When the queue is empty, convene an 8-agent expert panel to explore the project and generate 3-5 new tasks
4. **Repeat** -- Never stop unless the user says so

## Installation

```bash
# Clone the repository
git clone https://github.com/ianmcvann/initiative.git
cd initiative

# Add as a Claude Code plugin
claude plugin add ./
```

### Marketplace (Coming Soon)

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

## Usage

Initiative provides seven commands:

### `/initiative:start [direction]`

Start autonomous orchestration. Optionally provide a direction to seed the initial task:

```
/initiative:start
/initiative:start "Add authentication to the API"
```

### `/initiative:stop`

Stop the orchestration loop and show a final status summary:

```
/initiative:stop
```

### `/initiative:status`

Check the current state of the task queue:

```
/initiative:status
```

Shows total tasks, counts by status, average completion time, throughput, and titles of any in-progress tasks.

### `/initiative:add [task description]`

Add a task to the queue without starting the orchestration loop:

```
/initiative:add "Refactor the database layer to use connection pooling"
```

### `/initiative:clear`

Clear all pending tasks from the queue:

```
/initiative:clear
```

### `/initiative:view [task_id]`

View details of a specific task by ID:

```
/initiative:view 42
```

### `/initiative:history`

Show completed and failed task history:

```
/initiative:history
```

## Expert Panel

When the task queue is empty, Initiative doesn't just sit idle -- it convenes a panel of 8 specialist agents that analyze your project in parallel, each from a different perspective. This is what makes Initiative more than a task runner: it's a team of experts that continuously discovers what your project needs next.

| Expert | Focus |
|--------|-------|
| **Security** | Vulnerabilities, input validation gaps, exposed secrets, insecure defaults |
| **Architecture** | Code structure, coupling, separation of concerns, scalability bottlenecks |
| **Testing** | Coverage gaps, missing edge cases, flaky tests, untested error paths |
| **Documentation** | Missing or outdated docs, undocumented APIs, incomplete guides |
| **Performance** | N+1 queries, unnecessary computation, missing caching, memory leaks |
| **Product Management** | Missing features, incomplete workflows, user value gaps, feature prioritization |
| **UX** | Confusing interfaces, poor feedback, accessibility, inconsistent patterns |
| **Marketing** | Value proposition, examples, comparisons with alternatives, distribution |

After all 8 experts report back, Initiative synthesizes their findings: deduplicates overlapping concerns, prioritizes across domains (critical security > product gaps > architecture > UX > testing > docs > performance > marketing), chains related tasks with dependencies, and generates 3-5 concrete, actionable tasks. At least half of generated tasks are additive -- new features and capabilities, not just fixes.

## Architecture

```
src/initiative/
  models.py      # Task dataclass and TaskStatus enum
  database.py    # SQLite task store with priority queue
  server.py      # FastMCP server exposing task management tools
```

**Task Store** -- SQLite database with WAL journaling. Tasks have a title, description, priority (0-1000, higher = more urgent), status, tags, dependency tracking, auto-retry support, and timestamps. The priority queue returns the highest-priority pending task first (ties broken by creation time), skipping any task whose dependencies haven't completed yet.

**MCP Server** -- Built on [FastMCP](https://github.com/jlowin/fastmcp), exposes 16 tools over stdio transport:

| Tool | Description |
|------|-------------|
| `add_task` | Add a new task with title, description, priority, and optional dependencies/tags |
| `get_next_task` | Pull the highest-priority pending task (respecting dependencies) and mark it in-progress |
| `complete_task` | Mark a task as completed with a result summary |
| `fail_task` | Mark a task as failed (auto-retries if retries remain, otherwise permanently fails) |
| `cancel_task` | Cancel a pending or in-progress task |
| `update_task` | Update a pending task's title, description, or priority |
| `retry_task` | Manually retry a failed task by resetting it to pending |
| `add_tag` | Add a tag to a task for categorization and filtering |
| `remove_tag` | Remove a tag from a task |
| `list_tasks` | List tasks, optionally filtered by status and/or tag, with pagination |
| `get_task` | Get full details of a specific task by ID |
| `get_status` | Get queue summary (total, pending, in-progress, completed, failed, cancelled, throughput) |
| `get_summary` | Lightweight task overview (id, title, status, priority only) -- saves context in long sessions |
| `recover_stale_tasks` | Reset tasks stuck in in-progress back to pending (recovers from crashes) |
| `decompose_task` | Break a task into ordered subtasks with automatic dependency chaining |
| `purge_completed` | Delete completed tasks (and optionally failed/cancelled) to clean up the queue |

### Task Statuses

| Status | Description |
|--------|-------------|
| `pending` | Waiting to be picked up (or waiting for dependencies to complete) |
| `in_progress` | Currently being worked on by an agent |
| `completed` | Successfully finished with a result summary |
| `failed` | Permanently failed after exhausting all retries |
| `cancelled` | Cancelled by the user or by decomposition into subtasks |

### Task Features

- **Priority queue** -- Tasks are ordered by priority (0-1000, higher first), with ties broken by creation time
- **Dependencies** -- Tasks can depend on other tasks via `depends_on`; blocked tasks won't be picked up until all dependencies complete
- **Auto-retry** -- Failed tasks are automatically retried up to `max_retries` times (default 2) before being permanently marked as failed
- **Tags** -- Categorize and filter tasks with arbitrary string tags
- **Decomposition** -- Break large tasks into ordered subtask chains using `decompose_task`; the parent is tagged as an "epic" and cancelled, replaced by its subtasks

**Skills** -- Two Claude Code skills drive the orchestration:
- `initiative` -- The main autonomous loop (check for tasks, execute, analyze, repeat)
- `analyze` -- Expert panel analysis and task generation

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
