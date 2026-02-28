---
description: "Show history of completed and failed tasks"
---

Show the user a history of what Initiative has accomplished. Call `list_tasks` with `status=completed` to get completed tasks, then call `list_tasks` with `status=failed` to get failed tasks. Present the results as a chronological report:

1. **Completed tasks** — listed from oldest to newest, showing: task ID, title, result summary (from the result field), and completion time
2. **Failed tasks** (if any) — listed with: task ID, title, error message, and number of retries attempted
3. **Summary line** — "X tasks completed, Y failed" with the total time span from first task started to last task completed

Format it as a clean, readable report that gives the user a clear picture of what was accomplished during the session.
