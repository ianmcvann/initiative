---
description: "Clear all pending tasks from the Initiative queue"
---

Cancel all pending tasks in the Initiative queue. First call `list_tasks` with `status=pending` to get all pending tasks. Then call `cancel_task` for each one. After clearing, show the user how many tasks were cancelled and the current queue status using `get_status`.
