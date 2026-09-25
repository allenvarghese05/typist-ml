---
description: Phase 5 - push the branch and open the PR
argument-hint: <task-id>
---

Task: $ARGUMENTS

1. Run `just check` (or the per-app checks if the justfile does not exist).
   Stop if anything fails.
2. Push the branch.
3. Open a pull request into main with `gh pr create`, using
   .github/pull_request_template.md. Fill in:
   - What: from the plan summary.
   - Why: task id and the D-numbers from the brief.
   - How I tested it: the check results.
   - Notes for review: the plan's review focus list and the reviewer's MINOR
     findings.
   Title: "<task-id>: <task title>".
   If `gh` is not signed in, do not try to fix authentication. Instead print
   the filled-in PR title and description, and the link
   https://github.com/<owner>/<repo>/compare/main...<branch> so I can open it
   myself.
4. Show me the PR link. Never merge it.
