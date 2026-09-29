# Typist-ML

[![CI](https://github.com/allenvarghese05/typist-ml/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/allenvarghese05/typist-ml/actions/workflows/ci.yml)

A typing coach built as a controlled experiment: it finds the letter pairs you are weakest at,
generates practice drills aimed at them with three methods (dictionary heuristic, Markov chain,
on-device 1B language model), and tests whether any of them beat plain practice.

Status: milestone 0. No results yet.

Design: [docs/design/Typist-ML_Technical_Design.pdf](docs/design/Typist-ML_Technical_Design.pdf)

## Setup (macOS, Apple Silicon)

1. Install the tools: [uv](https://docs.astral.sh/uv/), Node 22 (exact version in `.nvmrc`),
   pnpm (`npm install -g pnpm@12.6.0`, the version pinned in `apps/web/package.json`),
   then `uv tool install rust-just`, `uv tool install pre-commit`,
   `uv tool install semgrep==1.178.0` (for `just security`, see
   [D22](docs/decisions/D22-security-scanning.md)),
   `uv tool install actionlint-py==1.7.12.25` (the pre-commit hook for workflow files)
   and `uv python install 3.12`.
2. Activate the commit hooks once per clone: `pre-commit install`.
3. Install the web dependencies: `(cd apps/web && pnpm install --frozen-lockfile)`.
4. Install the API dependencies: `(cd services/api && uv sync --locked)`. The database is
   `data/typist.db` at the repo root (gitignored); `TYPIST_*` variables or `services/api/.env`
   override the settings (see `services/api/.env.example`). `just migrate` applies migrations.
5. Run `just` to list the recipes. Run `just check` before pushing (see
   [D21](docs/decisions/D21-just-check.md)); `just check-web` and `just check-api` run the same
   checks for one app, as the CI jobs do. `just dev` runs on macOS only.

### Installed versions (milestone 0, recorded 2026-09-25)

After milestone 0 the lockfiles (`apps/web/pnpm-lock.yaml`, `services/api/uv.lock`) are the source
of truth for library versions.

| Tool | Command | Version |
|---|---|---|
| just | `just --version` | just 1.58.0 |
| pre-commit | `pre-commit --version` | pre-commit 4.6.2 |
| actionlint | `actionlint -version` (first line) | 1.7.12 |
| semgrep | `semgrep --version` | 1.178.0 |
| uv | `uv --version` | uv 0.12.18 (Homebrew 2026-09-22 aarch64-apple-darwin) |
| pnpm | `pnpm --version` | 12.6.0 |
| Node | `node --version` | v22.22.2 |
| Python | `uv run --no-project --python 3.12 python --version` | Python 3.12.2 |

### Web library versions (apps/web, recorded 2026-09-25)

Exact versions pinned in `apps/web/package.json`; transitive versions are in `apps/web/pnpm-lock.yaml`.

| Package | Version |
|---|---|
| vite | 8.3.1 |
| react | 19.3.0 |
| react-dom | 19.3.0 |
| typescript | 6.0.3 |
| @biomejs/biome | 2.5.14 |
| vitest | 4.1.11 |
| tailwindcss | 4.3.3 |
| @tailwindcss/vite | 4.3.3 |
| @vitejs/plugin-react | 6.1.1 |

### Python library versions (services/api, recorded 2026-09-28)

Exact versions pinned in `services/api/pyproject.toml`; transitive versions are in
`services/api/uv.lock`. The build backend is `uv_build` 0.12.19.

| Package | Version |
|---|---|
| alembic | 1.20.0 |
| fastapi | 0.141.1 |
| pydantic-settings | 2.15.0 |
| sqlmodel | 0.0.47 |
| typer | 0.27.2 |
| uvicorn | 0.54.0 |
| bandit | 1.9.4 |
| httpx | 0.28.1 |
| pip-audit | 2.10.1 |
| pyright | 1.1.414 |
| pytest | 9.1.1 |
| ruff | 0.16.9 |

## Continuous integration

GitHub Actions runs on every pull request to `main`, every push to `main`, and by hand
(`workflow_dispatch`). The jobs only read the repository: nothing is deployed or uploaded.

- `ci.yml`, job `web`: `biome ci .`, `biome format .`, `tsc -b`, `vitest run` and `vite build` in
  `apps/web` (the same commands as `just check-web`).
- `ci.yml`, job `api`: `ruff check .`, `ruff format --check .`, pyright and pytest in
  `services/api` (the same commands as `just check-api`), then bandit on `src/` and semgrep
  (`p/security-audit`) on the whole repository (see D22).
- `web` and `api` are the required checks for merging into `main`.
- `codeql.yml`: CodeQL (`security-extended`) for the workflows, `apps/web` and `services/api`, on
  pull requests, pushes to `main` and weekly. Not a required check.
- `audit.yml`: `just security-py` and `just security-web` (pip-audit and `pnpm audit`), weekly and
  by hand. Not a required check.
- Dependabot proposes updates for the pinned GitHub Actions weekly.

CI uses Node from `.nvmrc`, pnpm from `apps/web/package.json` (through corepack), uv 0.12.18, a
uv-managed Python 3.12, just 1.58.0 and the semgrep version pinned in the justfile.
