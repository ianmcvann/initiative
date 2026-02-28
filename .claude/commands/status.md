---
description: "Check Initiative task queue status"
---

Call the `get_status` tool to get queue counts, then call `list_tasks` to show recent tasks. Present a concise summary to the user showing: total tasks, how many are pending/in-progress/completed/failed, and the titles of any in-progress tasks. For pending tasks, show the ready vs blocked split using `pending_ready` and `pending_blocked` from `get_status`, e.g., "3 pending (2 ready, 1 blocked)".
