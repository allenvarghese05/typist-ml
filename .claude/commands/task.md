---
description: Run the whole pipeline for one task autonomously, asking only when genuinely unsure
argument-hint: <task-id>
---

Run the full pipeline for $ARGUMENTS without stopping between phases:

1. /understand $ARGUMENTS
2. /blueprint $ARGUMENTS
3. /build $ARGUMENTS
4. /review $ARGUMENTS
5. /ship $ARGUMENTS

You are the orchestrator. Every phase is delegated to its subagent; you never
do a subagent's work yourself. Between phases you decide whether the output
makes sense and the next phase can start. Do not wait for my approval when it
does.

Answering questions: when a subagent returns open questions, answer them
yourself first, in this order of authority:
  a. the design doc and its decision rows (D-numbers)
  b. CLAUDE.md
  c. earlier briefs, plans and owner answers in docs/plans/
  d. the existing code and its established patterns
  e. standard industry practice for this stack
Write each answer under "## Owner answers" in the brief (or "## Orchestrator
answers" in the plan) with today's date, the source you used (a-e), and one
sentence of reasoning. Then continue.

Ask me only when a question is still genuinely unsettled after a-e, or when
answering it would change experiment semantics, the schema, a frozen key, or
the scope of the task. Batch those questions, number them, say which gate you
are at, and stop. Never stop for a question you could answer from a-e.

Always stop when: a builder step cannot be completed, the reviewer says the
plan itself is wrong, the review loop fails twice, or `just check` fails.
Never merge a PR.

At the end, report: the PR link, every question you answered yourself (with
source), and anything you want me to double-check.
