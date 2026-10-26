---
name: ship
description: Phase 5 - push the branch and open the PR. Use when running Phase 5 of a Typist-ML task or when /ship <task-id> is invoked.
---

# Phase 5: Ship (`ship`)

Target task: `<task-id>` (e.g. `T2.5`) passed by the user.

1. Run `just check` (or the per-app checks if the justfile does not exist). Stop if anything fails.
2. Push the branch to `origin`.
3. Open a pull request into `main` with `gh pr create`, using `.github/pull_request_template.md`. Fill in:
   - **What**: from the plan summary.
   - **Why**: task id and the `D`-numbers from the brief.
   - **How I tested it**: the check results.
   - **Notes for review**: the plan's review focus list, the reviewer's `MINOR` findings, and every question the orchestrator answered on the owner's behalf (with its source) so the owner can override any of them.
   Title: `"<task-id>: <task title>"`.
   If `gh` is not signed in, do not try to fix authentication. Instead print the filled-in PR title and description, and the link `https://github.com/<owner>/<repo>/compare/main...<branch>` so the user can open it directly.
4. Show the user the PR link. Never merge it.
