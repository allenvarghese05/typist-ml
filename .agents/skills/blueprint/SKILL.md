---
name: blueprint
description: Phase 2 - complete guided implementation plan (Gemini 4 Argon Medium architect). Use when running Phase 2 of a Typist-ML task or when /blueprint <task-id> is invoked.
---

# Phase 2: Blueprint (`blueprint`)

Target task: `<task-id>` (e.g. `T2.5`) passed by the user.

1. Check that `docs/plans/<task-id>-brief.md` exists and that every open question in it has an answer under `## Owner answers`. If one is missing, answer it per the `/task` authority order before continuing; ask the user only if it is genuinely unsettled.
2. Ensure the `architect` subagent is defined in the current session (from `.agents/agents/architect.md` via `define_subagent` with `EnableWriteTools: true` if not yet defined).
3. Invoke the `architect` subagent via `invoke_subagent` to write `docs/plans/<task-id>-plan.md` (configured for Gemini 4 Argon on Medium thinking).

When the `architect` returns, read the plan critically:
- Does it cover every acceptance criterion?
- Does it respect every `D`-number in the brief?
- Does it stay inside the task's scope?

If the architect left questions, answer them in the plan under `## Orchestrator answers` (same authority order) or send them back to the architect for a revision if the answer changes the plan's structure.

Show the user:
1. The plan summary and design choice.
2. The file map.
3. The step titles only.
4. The review focus list.

Then continue to `/build`. Stop only if the plan conflicts with the brief, the design doc or `GEMINI.md` / `CLAUDE.md`, or if it widens scope beyond the task.
