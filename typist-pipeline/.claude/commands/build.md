---
description: Phase 3 - implement the approved plan exactly (Sonnet builder)
argument-hint: <task-id>
---

Task: $ARGUMENTS

1. Make sure you are on a branch for this task. If you are on main, create
   one named after the task (for example `t1-3-text-cursor`).
2. Check docs/plans/$ARGUMENTS-plan.md exists. Commit the brief and plan on
   this branch if they are not committed yet ("docs: $ARGUMENTS brief and plan").
3. Use the builder subagent to implement the plan.

If the builder reports a step it could not complete, stop and show me the
report. Do not fix it yourself and do not change the plan.

When it finishes, show me the steps completed, files changed and the check
result. Then continue to /review unless something failed.
