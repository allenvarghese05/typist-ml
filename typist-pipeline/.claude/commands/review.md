---
description: Phase 4 - independent review with fix loop (Opus reviewer, Sonnet fixes)
argument-hint: <task-id>
---

Task: $ARGUMENTS

Use the reviewer subagent to review this branch against
docs/plans/$ARGUMENTS-brief.md and docs/plans/$ARGUMENTS-plan.md.

If the verdict is CHANGES NEEDED:
- Send only the BLOCKING findings to the builder subagent to fix.
- Run the reviewer again.
- Do this at most twice. If it is still CHANGES NEEDED, stop and show me the
  findings.

If a finding says the plan itself is wrong, do not send it to the builder.
Stop and show it to me.

When the verdict is APPROVE, show me the verdict and any MINOR findings, and
stop. I will run /ship.
