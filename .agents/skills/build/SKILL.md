---
name: build
description: Phase 3 - implement the approved plan exactly (Claude Sonnet 4.6 Medium builder). Use when running Phase 3 of a Typist-ML task or when /build <task-id> is invoked.
---

# Phase 3: Build (`build`)

Target task: `<task-id>` (e.g. `T2.5`) passed by the user.

1. Make sure you are on a branch for this task. If you are on `main`, create one named after the task (for example `t2-5-worker-loop`).
2. Check `docs/plans/<task-id>-plan.md` exists. Commit the brief and plan on this branch if they are not committed yet (`"docs: <task-id> brief and plan"`).
3. Ensure the `builder` subagent is defined in the current session (from `.agents/agents/builder.md` via `define_subagent` with `EnableWriteTools: true` if not yet defined).
4. Invoke the `builder` subagent via `invoke_subagent` to implement the plan (configured for Claude Sonnet 4.6 on Medium thinking).

If the builder reports a step it could not complete, stop and show the user the report. Do not fix it yourself and do not change the plan. If the builder asks a question that the plan already answers, point it at the plan and let it continue; if the plan is genuinely silent, send the question to the architect to amend the plan, then resume the builder.

When it finishes, show the user the steps completed, files changed and the check result. Then continue to `/review` unless something failed.
