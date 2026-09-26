# D21: What `just check` runs

- Date: 2026-09-25
- Status: accepted
- Task: T0.1

## Context

CLAUDE.md, the pull request template and the pipeline agents all require `just check` before
pushing ("lint, types, tests for both apps"). The design doc (sections 5.3 and 7) names `just lint`,
`just types` and `just test` but never defines `check`. Without a definition, what counts as
"passing" could differ between the builder, the reviewer and CI.

## Decision

| ID | Decision | Choice | Why | Revisit if |
|---|---|---|---|---|
| D21 | `just check` | Runs `lint`, `format-check`, `types`, `test`, `build` in that order for both apps (apps/web: `biome ci .` (Biome lint, format and import-order checks, the same checks the pre-commit hook fixes), Biome format check, `tsc -b`, Vitest, `vite build`; services/api: ruff check, `ruff format --check`, pyright, pytest; no build step). Stops at the first failure. Never rewrites source files (`vite build` writes only the gitignored `apps/web/dist/`). A recipe skips an app that is not scaffolded yet (prints a message, exits 0). | One command that matches what CI will check, so passing locally predicts passing in CI | CI (T0.4) needs a check that `just check` does not cover |

## Consequences

- `just check` passes on a repository where neither app exists yet (T0.1), and on one where only
  apps/web exists (T0.2).
- Formatting is part of the gate. The pre-commit hooks auto-fix formatting, while `check` only
  reports it.
- pyright and the test suites run in `check` and in CI, not in the pre-commit hook.
- Amended 2026-09-25 by T0.2 (owner answers 8 and 14): the web lint step became `biome ci .` so the
  gate matches the pre-commit hook, and a `build` step (`vite build`) was added so a broken build
  or Tailwind setup fails the gate.
