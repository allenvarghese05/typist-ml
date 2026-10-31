# Typist-ML

[![CI](https://github.com/allenvarghese05/typist-ml/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/allenvarghese05/typist-ml/actions/workflows/ci.yml)

A typing coach built as a controlled experiment: does a small on-device language model write better typing drills than a dictionary heuristic or Markov chain? Plain practice serves as the control comparison.

Typist-ML identifies the character bigrams where a typist exhibits elevated error rates or latency, generates targeted practice drills across competing generation strategies, and tests whether targeted practice outperforms plain text practice.

Status: milestone 4 (Pilot complete).

Design: [docs/design/Typist-ML_Technical_Design.pdf](docs/design/Typist-ML_Technical_Design.pdf)

Analysis plan (pre-registered): [docs/analysis-plan.md](docs/analysis-plan.md)

## Pilot Results

The pilot evaluation was completed using a 10-practice-day reference protocol (14 completed sessions, 25,022 total keystrokes) in the pre-registered two-set contingency mode comparing plain practice (`control`, Set A) against dictionary-targeted practice (`heuristic`, Set B).

### Primary Outcome: Error Rate Change

![Per-set error rate change](docs/figures/set_error_rate_change.png)

The primary outcome is the change in per-set error rate $d(s) = e_{\text{ret}}(s) - e_{\text{base}}(s)$ on assigned bigrams between baseline (Form A) and retest (Form B), evaluated under Jeffreys 95% Beta credible intervals and posterior targeting effect draws:

| Set | Arm | Assigned Bigrams | Baseline Errors / Attempts | Baseline 95% CI | Retest Errors / Attempts | Retest 95% CI | Error Rate Change $d(s)$ | Targeting Effect $E(s)$ | $P(E(s) < 0)$ |
|---|---|---|---:|---|---:|---|---:|---:|---:|
| A | control | `be`, `ev`, `ly`, `nc` | 13/77 (16.9%) | [0.0981, 0.2639] | 7/155 (4.5%) | [0.0204, 0.0866] | -12.36% | - | - |
| B | heuristic | `ay`, `fr`, `no`, `rs` | 14/84 (16.7%) | [0.0989, 0.2570] | 9/143 (6.3%) | [0.0316, 0.1117] | -10.38% | +1.98% | 37.7% |

### Key Secondary Outcome: Inter-Key Interval (IKI) Shift

The key secondary outcome is the clean inter-key interval (IKI) shift $c(s) = m_{\text{ret}}(s) - m_{\text{base}}(s)$ evaluated across clean first-attempt keystrokes, with empirical bootstrap 95% confidence intervals:

| Set | Arm | Baseline Median IKI (n) | Baseline IQR | Retest Median IKI (n) | Retest IQR | Shift $c(s)$ | Targeting Effect $F(s)$ | Bootstrap 95% CI |
|---|---|---:|---:|---:|---:|---:|---:|---|
| A | control | 142.2ms (64) | 20.0ms | 140.6ms (148) | 19.8ms | -1.6ms | - | - |
| B | heuristic | 139.3ms (70) | 16.0ms | 137.2ms (134) | 20.9ms | -2.0ms | -0.4ms | [-8.4, +7.9] |

### Generation Summary Table

| Arm | Drills | Mean Density | Real-Word Ratio | Acceptance Rate |
|---|---:|---:|---:|---:|
| control | 24 | 0.000 | 1.000 | 100.0% |
| heuristic | 24 | 0.245 | 1.000 | 100.0% |
| markov | 0 | - | - | - |
| llm | 0 | - | - | - |

### Overhead & Throughput

Instrumentation overhead: handler p95 = 0.20 ms (target < 1.0 ms), dispatch lag p95 = 0.50 ms. LLM generation: N/A.

### Limitations

This pilot reports findings from N = 1 participant (builder, unblinded) across 14 completed sessions and 25,022 total keystrokes. The primary participant is the author and system builder, who was unblinded to arm assignments during typing; results are descriptive within-person comparisons and should be evaluated with this limitation in mind.

### Findings & Interpretation

In this pilot participant, error rates dropped substantially across both sets (-12.36% in Set A control, -10.38% in Set B heuristic), reflecting general motor practice and task familiarisation across the 10 practice days. The targeting effect $E(s) = d(\text{heuristic}) - d(\text{control}) = +1.98\%$ indicates no meaningful divergence between heuristic drill targeting and general plain-text typing practice within this single-subject evaluation. Posterior distributions show $P(E(s) < 0) = 37.7\%$, consistent with parity between conditions. Clean inter-key interval shifts showed similar modest speed-ups across both arms (-1.6 ms in control, -2.0 ms in heuristic; targeting effect $F(s) = -0.4\text{ ms}$, bootstrap 95% CI $[-8.4, +7.9]\text{ ms}$). Because this is an $N=1$ unblinded pilot, these results serve to validate system instrumentation, attribution pipelines, and analysis workflows rather than establish population claims.

### Verification & Reproducibility

All claims in this document trace directly to SQLite database records. The results can be inspected and regenerated locally:
- `just figures`: Regenerates outcome charts and markdown snippets into `docs/figures/`.
- `just check-readme`: Verifies that every number, interval, and table in this document matches database records ($0.00$ claim divergence).
- Interactive exploration is available via Jupyter notebook `notebooks/03_results.ipynb` and the web dashboard at `#/dashboard`.

## Experimental Method

- **Within-Person Comparison (D01):** Each participant acts as their own control. Rather than comparing between different typists with divergent baseline proficiencies, each participant trains simultaneously on distinct target bigram sets assigned to different generation arms.
- **Held-Out Control Set (D02):** One set of weak bigrams (Set A) is explicitly held out from targeted practice and receives only natural text practice, providing the baseline motor learning control against which targeted drill effects are measured.
- **Four-Arm RCT & Pre-Registered Contingency Mode (D03, §3.1):** The full design specifies a four-arm randomized controlled trial (`control`, `heuristic`, `markov`, `llm`). The pre-registered protocol (`docs/analysis-plan.md`, §3.1) specifies a two-set fallback contingency mode (`control`, `heuristic`) when running on resource-constrained platforms or pilot configurations without GPU acceleration.
- **Snake-Order Dealing & Assignment Freeze (D04):** Baseline bigrams with error rates above median are ranked and dealt to sets in snake order (`A, B, B, A...`) to balance baseline difficulty across arms before training begins. Assignments freeze permanently upon practice commencement.
- **Shared Validator Fairness Gate (D16, D30):** All candidate drills across all generators must satisfy identical acceptance criteria: character length (120–180 characters), target bigram density (10%–40%), real-word vocabulary ratio ($\ge 85\%$), profanity filtering, and grammar bounds. Drills failing validation are rejected by the background worker.
- **Keystroke Telemetry & Attribution Invariants (D14, D15, D24, D27):** Monotonic sub-millisecond timestamps capture dwell times and inter-key intervals (IKI). Errors are attributed strictly to first-attempt character substitutions; post-error keystrokes and backspaces are tracked but excluded from error rate denominators. Keystroke pauses exceeding 2000 ms are excluded from latency metrics.
- **Blinding & Unblinded Author Disclosure (D18, D19):** In participant trials, participants are blinded to arm assignments. For this reference pilot dataset, the participant is the system builder and author (`is_builder=True`), who was unblinded to assignment conditions; this status is permanently recorded in the database schema and explicitly disclosed.

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
   On Apple Silicon only, `(cd services/api && uv sync --locked --extra mlx)` also installs the
   model runtime (mlx-lm); a later `uv sync --locked` without `--extra mlx` removes it again.
   `just mlx-smoke --download` fetches the pinned model once into the Hugging Face cache outside
   the repo (see [D23](docs/decisions/D23-model-download.md)); `just mlx-smoke` then runs the
   model smoke test offline.
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

### Model runtime (services/api `mlx` extra, macOS arm64 only, recorded 2026-09-29)

Recorded by the T0.5 smoke test (`just mlx-smoke`). mlx-lm and mlx are pinned in
`services/api/pyproject.toml` (extra `mlx`), mlx-metal and the other dependencies in
`services/api/uv.lock`, and the model revision in `services/api/scripts/mlx_smoke.py`
(see [D23](docs/decisions/D23-model-download.md)). None of them is upgraded during the pilot.
Speed and memory measurements are in the T0.5 pull request, not here.

| Item | Version |
|---|---|
| mlx-lm | 0.31.3 |
| mlx | 0.32.3 |
| mlx-metal | 0.32.3 |
| Model | `mlx-community/Llama-3.2-1B-Instruct-4bit` |
| Model revision (Hugging Face commit) | `08231374eeacb049a0eade7922910865b8fce912` |
| macOS | 15.3.2 |
| Chip | Apple M1 Pro |
| RAM | 16 GB |
| Python | 3.12.2 |

## Data and licences

The word list and word frequencies come from
[`wordfreq`](https://pypi.org/project/wordfreq/) (Robyn Speer), pinned to `3.1.1`
(decision D17). `wordfreq`'s English data is distributed under the Creative Commons
Attribution-ShareAlike 4.0 (CC BY-SA 4.0) licence; it combines several freely available
corpora (see the package's data credits). The corpus artifacts built from it
(`data/corpus/words.json`, `data/corpus/top_bigrams.json`) are gitignored and are never
committed. No network access is needed at runtime: `wordfreq` ships its data in-package.

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
