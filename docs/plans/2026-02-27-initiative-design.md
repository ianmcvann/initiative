# Initiative — Design Document

**Date:** 2026-02-27
**Status:** Approved

## Overview

Initiative is a Claude Code plugin that provides autonomous, never-stopping AI task orchestration. It manages a task queue, dispatches parallel subagents, and — when the queue empties — autonomously analyzes the project to generate new tasks. It works on any project type, not just code.

## Core Principles

- **Fully autonomous:** Makes its own judgment calls based on project context. No human-in-the-loop required for decisions.
- **Never stops:** The loop runs continuously until the user explicitly stops it. If the analyzer can't find critical work, it finds lower-priority improvements.
- **Project-agnostic:** Works on code, writing, research, data analysis — anything. No hardcoded domain-specific checks.
- **Parallel execution:** Multiple subagents work on different tasks simultaneously.

## Architecture

Initiative is a Claude Code plugin with three components:

### 1. MCP Server (Python)

The orchestration brain. A Python-based MCP server that:

- Manages a **SQLite task database** tracking all tasks (status, priority, assigned worker, results, history)
- Exposes tools for Claude Code to call:
  - `get_next_task` — Pull the highest-priority pending task
  - `complete_task` — Mark a task as completed with results
  - `fail_task` — Mark a task as failed with error details
  - `add_task` — Manually add a task to the queue
  - `list_tasks` — Query tasks by status, priority, etc.
  - `get_status` — Get overall orchestration status
- Handles task state transitions: pending → in_progress → completed/failed

### 2. Skills

- **Main orchestration skill:** Entry point invoked by the user. Kicks off the autonomous loop:
  1. Check the task queue for pending tasks
  2. Dispatch tasks to subagents in parallel (each in an isolated git worktree)
  3. Collect results, merge worktree changes back
  4. When queue is empty, run the Project Analyzer
  5. Repeat forever

- **Project Analyzer skill:** A general-purpose prompt that asks Claude Code to:
  1. Explore the project in its current state
  2. Understand its goals and context
  3. Assess what needs doing next
  4. Generate prioritized tasks

  No hardcoded checks — relies entirely on Claude Code's judgment for any project type.

### 3. Hooks

- Auto-start the MCP server when the plugin loads
- Lifecycle management for clean shutdown

## Task Lifecycle

```
User provides tasks ──┐
                      ├──→ [pending] ──→ [in_progress] ──→ [completed]
Analyzer generates ───┘         │                              │
tasks                           │                              │
                                │         ┌── [failed] ←───────┘
                                │         │     (retry or skip)
                                │         │
                                └─────────┘

When queue is empty:
  Orchestrator → Project Analyzer → New tasks → Back to queue
```

## Parallel Execution & Conflict Resolution

- Each subagent works in its own **git worktree** (isolated copy of the repo)
- Parallel agents never interfere with each other during execution
- On task completion, the orchestrator **merges** the worktree back into the main branch
- Merge conflicts are resolved automatically by Claude Code, or the conflicting task is queued for retry

## User Interaction

- **Start:** Invoke the Initiative skill with optional direction (e.g., "work on improving this project" or "build a web app that does X")
- **Monitor:** Ask Claude Code "what's Initiative working on?" or "show me completed tasks"
- **Control:** Add tasks manually, reprioritize, pause, or stop — all through natural conversation
- **Overnight mode:** Let it run, come back for a status report

## Technology Stack

- **Language:** Python
- **Database:** SQLite (file-based, lightweight)
- **Distribution:** Claude Code plugin marketplace
- **Integration:** MCP protocol, Claude Code subagent system, git worktrees

## Plugin Structure

```
initiative/
├── .claude-plugin/
│   └── plugin.json              # Plugin manifest
├── src/
│   └── initiative/
│       ├── __init__.py
│       ├── server.py            # MCP server (orchestration brain)
│       ├── database.py          # SQLite task store
│       ├── analyzer.py          # Project analyzer logic
│       └── models.py            # Task data models
├── skills/
│   ├── initiative/
│   │   └── SKILL.md             # Main orchestration skill
│   └── analyze/
│       └── SKILL.md             # Project analyzer skill
├── hooks/
│   └── hooks.json               # Lifecycle hooks
├── .mcp.json                    # MCP server config
├── pyproject.toml               # Python project config
└── README.md
```
