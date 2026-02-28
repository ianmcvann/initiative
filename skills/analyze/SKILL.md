---
name: analyze
description: "Use when Initiative needs to discover what work should be done on a project. Analyzes project state and generates prioritized tasks."
---

# Project Analyzer

You are analyzing a project to figure out what needs to be done next. This is not limited to code — the project could be anything: software, writing, research, data, or something else entirely.

## Process

### 1. Understand the project

Explore the project to understand:
- What is this project? What are its goals?
- What's the current state? What exists so far?
- Are there any explicit signals about what to do? (issues, TODOs, roadmaps, READMEs, task lists)

### 2. Assess what needs doing

Based on the project's current state, identify:
- What's missing that should exist?
- What's broken or incomplete?
- What could be improved?
- What's the next logical step toward the project's goals?

### 3. Generate tasks

Create 3-5 tasks using `add_task`, each with:
- A clear, actionable title
- A detailed description of what needs to be done and why
- A priority (0-10, where 10 is most urgent)

Prioritize by impact: what would move the project forward the most?

## Guidelines

- Be specific — "Implement user login with email/password" not "Add auth"
- Be practical — suggest tasks that can be completed in a single focused session
- Be diverse — don't suggest 5 variations of the same thing
- Be bold — suggest meaningful improvements, not just cosmetic changes
