---
name: understand
description: Phase 1 - understand a task fully, no code (Gemini 4 Argon Medium analyst). Use when starting Phase 1 of a Typist-ML task or when /understand <task-id> is invoked.
---

# Phase 1: Understand (`understand`)

Target task: `<task-id>` (e.g. `T2.5`) passed by the user.

1. Ensure the `analyst` subagent is defined in the current session (from `.agents/agents/analyst.md` via `define_subagent` with `EnableWriteTools: true` if not yet defined).
2. Invoke the `analyst` subagent via `invoke_subagent` to write `docs/plans/<task-id>-brief.md` (configured for Gemini 4 Argon on Medium thinking).
3. Do not design, plan or write any code in this phase.

When the `analyst` returns:
1. Answer every open question yourself using the authority order in `/task`:
   - `docs/design/Typist-ML_Technical_Design.pdf` and its decision rows (`D`-numbers) + `docs/decisions/`
   - `GEMINI.md` and `CLAUDE.md`
   - earlier briefs, plans and owner answers in `docs/plans/`
   - the existing code and its established patterns
   - standard industry practice for this stack
   Append the answers to the brief under `## Owner answers` with today's date and the source for each.
2. If any question is still genuinely unsettled, or its answer would change experiment semantics, schema, frozen keys or task scope, stop and ask the user those questions only, numbered.
3. Otherwise show a summary of the brief in at most 10 lines plus the answers you recorded, and continue to `/blueprint`.
