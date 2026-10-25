---
name: task
description: Run the whole 5-phase Typist-ML pipeline for one task autonomously, asking only when genuinely unsure. Use when /task <task-id> is invoked.
---

# Full Task Pipeline (`task`)

Run the full pipeline for `<task-id>` without stopping between phases:

1. `/understand <task-id>` (`analyst` — Gemini 4 Argon, Medium)
2. `/blueprint <task-id>` (`architect` — Gemini 4 Argon, Medium)
3. `/build <task-id>` (`builder` — Claude Opus 5.5, Medium)
4. `/review <task-id>` (`reviewer` — Claude Opus 5.5, Medium)
5. `/ship <task-id>` (orchestrator)

You are the orchestrator. Every phase is delegated to its subagent (`define_subagent` from `.agents/agents/<name>.md` + `invoke_subagent`); you never do a subagent's work yourself. Between phases you decide whether the output makes sense and the next phase can start. Do not wait for owner approval when it does.

## Answering questions
When a subagent returns open questions, answer them yourself first, in this order of authority:
  a. the design doc (`docs/design/Typist-ML_Technical_Design.pdf`) and its decision rows (`D`-numbers) + `docs/decisions/`
  b. `GEMINI.md` and `CLAUDE.md`
  c. earlier briefs, plans and owner answers in `docs/plans/`
  d. the existing code and its established patterns
  e. standard industry practice for this stack

Write each answer under `## Owner answers` in the brief (or `## Orchestrator answers` in the plan) with today's date, the source you used (a-e), and one sentence of reasoning. Then continue.

Ask the user only when a question is still genuinely unsettled after a-e, or when answering it would change experiment semantics, the schema, a frozen key, or the scope of the task. Batch those questions, number them, say which gate you are at, and stop. Never stop for a question you could answer from a-e.

Always stop when: a builder step cannot be completed, the reviewer says the plan itself is wrong, the review loop fails twice, or `just check` fails.
Never merge a PR.

At the end, report: the PR link, every question you answered yourself (with source), and anything you want the owner to double-check.
