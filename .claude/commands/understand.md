---
description: Phase 1 - understand a task fully, no code (Opus analyst)
argument-hint: <task-id, e.g. T1.3>
---

Task: $ARGUMENTS

Use the analyst subagent to write docs/plans/$ARGUMENTS-brief.md.

Do not design, plan or write any code in this phase.

When the analyst returns:
1. Answer every open question yourself using the authority order in
   /task (design doc, CLAUDE.md, earlier plans, existing code, industry
   practice). Append the answers to the brief under "## Owner answers" with
   today's date and the source for each.
2. If any question is still genuinely unsettled, or its answer would change
   experiment semantics, schema, frozen keys or task scope, stop and ask me
   those questions only, numbered.
3. Otherwise show me a summary of the brief in at most 10 lines plus the
   answers you recorded, and continue to /blueprint.
