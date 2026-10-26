---
name: review
description: Phase 4 - independent review with fix loop (Claude Opus 5.5 Medium reviewer, Claude Sonnet 4.6 Medium builder fixes). Use when running Phase 4 of a Typist-ML task or when /review <task-id> is invoked.
---

# Phase 4: Review (`review`)

Target task: `<task-id>` (e.g. `T2.5`) passed by the user.

1. Ensure the `reviewer` subagent is defined in the current session (from `.agents/agents/reviewer.md` via `define_subagent` with `EnableWriteTools: true` if not yet defined).
2. Invoke the `reviewer` subagent via `invoke_subagent` to review this branch against `docs/plans/<task-id>-brief.md` and `docs/plans/<task-id>-plan.md` (configured for Claude Opus 5.5 on Medium thinking).

If the verdict is `CHANGES NEEDED`:
- Send only the `BLOCKING` findings to the `builder` subagent to fix.
- Run the `reviewer` subagent again.
- Do this at most twice. If it is still `CHANGES NEEDED`, stop and show the user the findings.

If a finding says the plan itself is wrong, do not send it to the builder. Stop and show it to the user.

When the verdict is `APPROVE`, show the user the verdict and any `MINOR` findings, and continue to `/ship`.
