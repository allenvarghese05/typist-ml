---
description: Phase 2 - complete guided implementation plan (Opus architect)
argument-hint: <task-id>
---

Task: $ARGUMENTS

Check that docs/plans/$ARGUMENTS-brief.md exists and that every open question
in it has an answer under "## Owner answers". If not, stop and list what is
missing.

Use the architect subagent to write docs/plans/$ARGUMENTS-plan.md.

When it returns, show me:
1. The plan summary and design choice.
2. The file map.
3. The step titles only.
4. The review focus list.

Then stop and wait for "approved" or my changes. If I request changes, send
them to the architect subagent to revise the plan, and show me the diff of
the plan.
