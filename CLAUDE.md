# Typist-ML: instructions for coding agents

Typist-ML is a typing coach built as a controlled experiment. The full design is in
`docs/design/Typist-ML_Technical_Design.pdf`. Read sections 1, 2, 12 and 13 before
changing telemetry, attribution or drill generation.

## Layout
- `apps/web`: Vite 8 + React 19 + TypeScript (strict). pnpm, Biome, Vitest.
- `services/api`: Python 3.12 via uv. FastAPI, SQLModel, Alembic, SQLite. ruff, pyright, pytest.
- `docs/`: design doc, analysis plan, ADRs in `docs/decisions/`.

## Workflow rules
- Never push to `main`. Work on a branch named after the task (e.g. `t1-3-text-cursor`)
  and open a pull request. CI must pass before merge.
- Conventional commits: `feat:`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:`.
- Run `just check` (lint, types, tests for both apps) before pushing.
- One task per PR. If a task grows, split it.

## Environment facts
- Cloud sessions and CI run on Linux. The model runtime (mlx-lm) only runs on Apple Silicon.
  - `mlx-lm` lives in an optional dependency group with the marker
    `sys_platform == 'darwin' and platform_machine == 'arm64'`.
  - Tests that load a model are marked `@pytest.mark.mlx` and are skipped off-Mac.
  - Code that talks to the model goes through `MLXRuntime`; tests use a fake runtime.
- Never commit anything under `data/` (database, corpus artifacts).

## Correctness rules
- Bigram attribution runs only in Python (`services/api/src/typist/services/attribution.py`).
  The browser computes display stats only.
- `services/api/tests/fixtures/golden_session.json` is the source of truth for what counts
  as an error. Both TextCursor (TS) and attribution (Python) must pass it. Never edit expected
  values to make a test pass; flag it in the PR instead.
- Randomness always comes from a seeded generator passed in by the caller.
- Never change keys in `experiment_config` after they are frozen.
- `keystroke_events` rows are append-only (except filling in key-up time).

## How work gets done (pipeline)

Every task from design doc section 16 goes through five phases. Each phase has
one owner, and the owner's model is fixed in its subagent file.

| Phase | Command | Subagent | Model | Output |
|---|---|---|---|---|
| 1 Understand | /understand T1.3 | analyst | opus | docs/plans/T1.3-brief.md |
| 2 Blueprint | /blueprint T1.3 | architect | opus | docs/plans/T1.3-plan.md |
| 3 Build | /build T1.3 | builder | sonnet | code, tests, commits |
| 4 Review | /review T1.3 | reviewer (+ builder fixes) | opus | verdict |
| 5 Ship | /ship T1.3 | main session | - | pull request |

Rules for the main session:
- You are the orchestrator. Delegate each phase to its subagent; do not do a
  subagent's work yourself.
- Stop at every gate and wait for the owner. Never skip phases 1 or 2.
- Never change a plan during build. Plan problems go back to the owner.
- Never merge PRs.


## Do not
- Copy code from Monkeytype or any GPL project. Behaviour reference only.
- Add cloud AI APIs, telemetry services, or analytics. Everything stays local.
- Claim WASM, or write result numbers into the README before real data exists.
