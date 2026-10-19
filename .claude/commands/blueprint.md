---
description: Phase 2 - complete guided implementation plan (Opus architect)
argument-hint: <task-id>
---

Task: $ARGUMENTS

Check that docs/plans/$ARGUMENTS-brief.md exists and that every open question
in it has an answer under "## Owner answers". If one is missing, answer it per
the /task authority order before continuing; ask me only if it is genuinely
unsettled.

Use the architect subagent to write docs/plans/$ARGUMENTS-plan.md.

When it returns, read the plan critically: does it cover every acceptance
criterion, respect every D-number in the brief, and stay inside the task's
scope? If the architect left questions, answer them in the plan under
"## Orchestrator answers" (same authority order) or send them back to the
architect for a revision if the answer changes the plan's structure.

Show me:
1. The plan summary and design choice.
2. The file map.
3. The step titles only.
4. The review focus list.

Then continue to /build. Stop only if the plan conflicts with the brief, the
design doc or CLAUDE.md, or if it widens scope beyond the task.
