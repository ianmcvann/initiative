---
description: "Start Initiative autonomous orchestration"
argument-hint: "[optional direction]"
---

Invoke the initiative:initiative skill and follow it exactly. If the user provided a direction argument, use the `add_task` tool to create an initial task from their direction before starting the loop. When creating the task, use the direction as the title and generate a helpful description that expands on what needs to be done, including any relevant context about the project. Set priority to 80 for user-directed tasks.
