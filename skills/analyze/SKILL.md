---
name: analyze
description: "Use when Initiative needs to discover what work should be done on a project. Dispatches expert agents in parallel to analyze the project from multiple perspectives."
---

# Project Analyzer — Expert Panel

You are analyzing a project to figure out what needs to be done next. Rather than analyzing alone, you dispatch a panel of specialist agents who each examine the project from their unique perspective. This ensures thorough, multi-dimensional analysis.

## Process

### 1. Understand the project

Quickly explore the project to understand:
- What is this project? What are its goals?
- What's the current state? What exists so far?
- What type of project is it? (software, writing, research, data, etc.)

### 2. Dispatch expert panel

Launch the following specialist agents **in parallel** using the Agent tool. Each expert should explore the codebase independently and return a prioritized list of findings — not just problems, but also **new features to build, improvements to make, and opportunities to pursue**. The goal is forward momentum, not just bug-fixing.

**For software projects, dispatch all 8 experts:**

#### Security Expert
> Scan the project for security weaknesses. Look for:
> - Input validation gaps (SQL injection, XSS, command injection)
> - Exposed secrets, hardcoded credentials, insecure defaults
> - Missing authentication/authorization checks
> - Insecure dependencies or configurations
> - Data exposure risks
>
> Return a prioritized list of findings with severity (critical/high/medium/low).

#### Architecture Expert
> Review the project's architecture and code structure. Look for:
> - Tight coupling between modules
> - Violations of separation of concerns
> - Missing abstractions or over-engineering
> - Scalability bottlenecks
> - Inconsistent patterns or conventions
>
> Return a prioritized list of findings with impact assessment.

#### Testing Expert
> Assess the project's test coverage and quality. Look for:
> - Untested code paths and missing edge cases
> - Critical functionality without tests
> - Test quality issues (flaky tests, poor assertions, missing mocks)
> - Missing test types (unit, integration, end-to-end)
> - Error handling paths that aren't tested
>
> Return a prioritized list of gaps with risk assessment.

#### Documentation Expert
> Evaluate the project's documentation. Look for:
> - Missing or outdated README sections
> - Undocumented public APIs or interfaces
> - Missing inline documentation for complex logic
> - Outdated comments that no longer match the code
> - Missing setup/deployment/contribution guides
>
> Return a prioritized list of documentation gaps.

#### Performance Expert
> Analyze the project for performance issues. Look for:
> - N+1 query patterns or redundant database calls
> - Unnecessary computation or allocations
> - Missing caching opportunities
> - Memory leak patterns
> - Blocking I/O in async contexts
>
> Return a prioritized list of performance concerns.

#### Product Management Expert
> Evaluate the project from a product perspective. Think about both what's missing AND what should be built next:
> - What new features would users love? What's the next logical capability to add?
> - What could be improved to make existing features more powerful or delightful?
> - Incomplete user workflows or dead ends that need finishing
> - Feature prioritization: what should be built next for maximum user value?
> - Gaps between the project's stated goals and what's actually implemented
>
> Return a prioritized list of feature ideas, product gaps, and improvements with user impact assessment.

#### UX Expert
> Assess the user experience of the project. Look for:
> - Confusing interfaces, unclear naming, or unintuitive flows
> - Missing feedback loops (user does something but gets no confirmation)
> - Accessibility issues (for CLI tools: unclear help text, missing examples, poor error messages)
> - Inconsistent terminology or interaction patterns
> - Steep learning curve areas that could be simplified
>
> Return a prioritized list of UX improvements with usability impact.

#### Marketing Expert
> Evaluate the project's positioning and discoverability. Look for:
> - Missing or weak value proposition in README/docs
> - Lack of compelling examples or demos
> - Missing comparison with alternatives (why use this over X?)
> - Incomplete distribution story (package registry, marketplace, install instructions)
> - Missing social proof elements (badges, screenshots, usage stats)
>
> Return a prioritized list of marketing/positioning improvements.

**For non-software projects**, adapt the expert panel to relevant domains (e.g., Content Expert, Research Expert, Data Quality Expert).

### 3. Synthesize findings into tasks

After all experts report back, synthesize their findings:

1. **Deduplicate** — Multiple experts may flag the same issue from different angles
2. **Prioritize** — Critical security issues > product gaps > architectural problems > UX issues > test gaps > docs > performance > marketing
3. **Create tasks** — Generate 3-5 concrete tasks using `add_task`, each with:
   - A clear, actionable title
   - A detailed description that includes the expert's findings and recommended approach
   - A priority (0-10, where 10 is most urgent)
   - Appropriate tags (e.g., "security", "testing", "docs", "performance", "architecture", "product", "ux", "marketing")

## Guidelines

- **Build forward** — Mix of fixing problems AND building new features. At least half the generated tasks should be additive (new capabilities, new features, new integrations) rather than purely defensive (fixing bugs, closing gaps)
- Be specific — "Add input validation to add_task title parameter" not "Improve security"
- Be practical — suggest tasks that can be completed in a single focused session
- Be diverse — spread tasks across different expert domains, not just one area
- Be bold — suggest meaningful improvements, not just cosmetic changes
- Use expert context — include the expert's reasoning in the task description so the implementer understands the "why"
