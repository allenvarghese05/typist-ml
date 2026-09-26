# Typist-ML

A typing coach built as a controlled experiment: it finds the letter pairs you are weakest at,
generates practice drills aimed at them with three methods (dictionary heuristic, Markov chain,
on-device 1B language model), and tests whether any of them beat plain practice.

Status: milestone 0. No results yet.

Design: [docs/design/Typist-ML_Technical_Design.pdf](docs/design/Typist-ML_Technical_Design.pdf)

## Setup (macOS, Apple Silicon)

1. Install the tools: [uv](https://docs.astral.sh/uv/), Node 22, pnpm (`npm install -g pnpm`),
   then `uv tool install rust-just`, `uv tool install pre-commit` and `uv python install 3.12`.
2. Activate the commit hooks once per clone: `pre-commit install`.
3. Run `just` to list the recipes. Run `just check` before pushing (see
   [D21](docs/decisions/D21-just-check.md)). `just dev` runs on macOS only.

### Installed versions (milestone 0, recorded 2026-09-25)

After milestone 0 the lockfiles (`apps/web/pnpm-lock.yaml`, `services/api/uv.lock`) are the source
of truth for library versions.

| Tool | Command | Version |
|---|---|---|
| just | `just --version` | just 1.58.0 |
| pre-commit | `pre-commit --version` | pre-commit 4.6.2 |
| uv | `uv --version` | uv 0.12.18 (Homebrew 2026-09-22 aarch64-apple-darwin) |
| pnpm | `pnpm --version` | 12.6.0 |
| Node | `node --version` | v22.22.2 |
| Python | `uv run --no-project --python 3.12 python --version` | Python 3.12.2 |
