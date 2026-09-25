---
description: Phase 1 - understand a task fully, no code (Opus analyst)
argument-hint: <task-id, e.g. T1.3>
---

Task: $ARGUMENTS

Use the analyst subagent to write docs/plans/$ARGUMENTS-brief.md.

Do not design, plan or write any code in this phase.

When the analyst returns, show me:
1. A summary of the brief in at most 10 lines.
2. Every open question, numbered, exactly as written.

Then stop and wait. I will answer the questions or say "approved".
When I answer, add my answers to the end of the brief under
"## Owner answers" with today's date, then stop again.
