# Typist-ML

[![CI](https://github.com/allenvarghese05/typist-ml/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/allenvarghese05/typist-ml/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](services/api/)
[![React: 19](https://img.shields.io/badge/React-19-blue.svg)](apps/web/)
[![Apple Silicon MLX](https://img.shields.io/badge/MLX-Apple%20Silicon-orange.svg)](https://github.com/ml-explore/mlx)

An on-device AI-powered typing coach engineered as a single-blind randomized controlled trial (RCT). Typist-ML instruments hardware-level keystroke physics, discovers individual letter-pair weaknesses via Empirical Bayes, synthesizes targeted practice drills across competing generative strategies (dictionary heuristic, character Markov chains, on-device 1B LLM), and evaluates whether generative AI drills outperform plain text practice under pre-registered Bayesian difference-in-differences analysis.

Status: milestone 4 (Pilot complete).

Design: [docs/design/Typist-ML_Technical_Design.pdf](docs/design/Typist-ML_Technical_Design.pdf)

Analysis plan (pre-registered): [docs/analysis-plan.md](docs/analysis-plan.md)

- **Interactive Results Notebook:** [notebooks/03_results.ipynb](notebooks/03_results.ipynb)
- **Visual Analytics Dashboard:** `#/dashboard` | **Participant Debrief & Unblinding:** `#/results`

---

## Architecture Overview

Typist-ML is built as a local-first monorepo combining sub-millisecond browser telemetry, an asynchronous Python/FastAPI backend, native Apple Silicon model inference (Metal / MLX), and zero-dependency SVG statistical visualizations:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                   TYPIST-ML SYSTEM ARCHITECTURE                        │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│   APPS / WEB (Vite 8 + React 19 + TypeScript Strict + Tailwind CSS 4)                  │
│   ├── Typing Surface: Custom TextCursor state machine & monotonic event.timeStamp      │
│   ├── Analytical Dashboard (#/dashboard): 6 views, pure SVG whisker forest plots       │
│   ├── Participant Debrief (#/results): Single-blind guard & post-retest unmasking      │
│   └── Admin Portal (#/admin): Participant state, drill pool depth, worker status       │
│                                                                                        │
│                                           ▲                                            │
│                                           │  REST / Local IPC (p95 < 1.0 ms SLA)       │
│                                           ▼                                            │
│                                                                                        │
│   SERVICES / API (Python 3.12 + FastAPI + SQLModel + SQLite in WAL mode)               │
│   ├── Telemetry Engine: D14 first-attempt substitution attribution, dwell, press-press │
│   ├── Assignment Engine: Empirical Bayes Beta prior shrinkage & snake-order dealing    │
│   ├── Background Generation Worker: Batch asynchronous generator (3-day buffer)        │
│   └── Analysis Engine: Monte Carlo Beta posterior effect draws & bootstrap median IKI  │
│                                                                                        │
│                     ┌─────────────────────┴─────────────────────┐                      │
│                     ▼                                           ▼                      │
│   DRILL GENERATION STRATEGIES                 PERSISTENCE & REPRODUCIBILITY            │
│   ├── Arm A: Held-out Control (Volume)        ├── data/typist.db (SQLite WAL)          │
│   ├── Arm B: Dictionary Heuristic (wordfreq)  ├── Shared Validator (Fairness Gate)     │
│   ├── Arm C: 2nd-order Markov Pseudo-words    ├── CLI: `typist figures`, `check-readme`│
│   └── Arm D: Apple Silicon MLX (1B LLM)       └── Automated Justfile Task Runner       │
│                                                                                        │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## The Physics of Keystroke Telemetry & Mathematical Attribution

Standard typing tools (like Monkeytype) evaluate typing at the word or string level. Typist-ML treats human typing as a continuous physical process of biomechanical transitions between letter pairs (bigrams $b = (k_{j-1}, k_j)$), instrumented with sub-millisecond precision.

```
           Key-Down (j-1)      Key-Up (j-1)            Key-Down (j)        Key-Up (j)
                 │                   │                       │                  │
                 ▼                   ▼                       ▼                  ▼
Timeline: ───────●───────────────────●───────────────────────●──────────────────●───────►
                 │◄─── Dwell (j-1) ──►│                       │◄─── Dwell (j) ──►│
                 │                                           │
                 │◄─────────────── Inter-Key Interval (IKI) ─►│
```

### 1. Timing Telemetry Equations
- **Dwell Time:** The continuous duration a physical key switch is held down:
  $$\text{Dwell}_j = t_{\text{up}}(j) - t_{\text{down}}(j)$$
- **Inter-Key Interval (IKI):** Measured strictly **press-to-press** using high-resolution browser monotonic timestamps (`event.timeStamp`):
  $$\text{IKI}_j = t_{\text{down}}(j) - t_{\text{down}}(j-1)$$
  *Why Press-to-Press?* Fast typists routinely exhibit **rollover typing**, depressing the next key before the previous key has released ($\text{Release-to-Press} < 0$). Press-to-press timing is strictly positive and directly represents finger flight time.
- **Pause & Cognitive Disruption Filtering (D15, D23a):** Keystrokes following pauses $> 2000\text{ ms}$ or window blur events represent distraction rather than motor execution; they are tracked but excluded from IKI distributions.
- **Net Typing Speed (D26):** Standardized net words per minute based on correct first-attempt keystrokes:
  $$\text{WPM} = \frac{\text{Correct First-Attempt Characters} / 5}{\text{Elapsed Minutes}}$$

### 2. The D14 First-Attempt Attribution Engine
A major challenge in typing analysis is preventing error cascades from polluting downstream metrics. When a typist mistypes a character and backspaces, naive string comparisons misattribute errors to subsequent correct keystrokes.
- **Attribution Rule (D14):** A bigram attempt $(c_{j-1}, c_j)$ is registered at target index $j$ **if and only if** character $c_{j-1}$ was typed correctly on its first attempt.
- **Substitution Error:** If the typist's first key-down at position $j$ produces $k_j \ne c_j$, an error is attributed to $(c_{j-1}, c_j)$.
- **Backspace & Recovery:** Post-error backspaces and subsequent correction attempts are recorded in `keystroke_events` for telemetry audits, but are strictly excluded from the error denominator to prevent artificial inflation of sample sizes.
- **Source of Truth:** Both Python (`services/api`) and TypeScript (`apps/web`) attribution implementations are verified against the shared golden telemetry fixture (`services/api/tests/fixtures/golden_session.json`).

---

## Experimental Methodology & Bayesian Study Design

```
   14-DAY SINGLE-BLIND PROTOCOL
   ┌─────────────┐      ┌─────────────────────────┐      ┌─────────────┐      ┌─────────────┐
   │  Days 0–1   │      │        End Day 1        │      │  Days 2–11  │      │  Days 12–13 │
   │  Baseline   │ ───► │  Empirical Bayes Deal   │ ───► │ 10 Practice │ ───► │   Retest    │
   │  (Form A)   │      │  & 4-Arm Masked Assign  │      │  Sessions   │      │  (Form B)   │
   └─────────────┘      └─────────────────────────┘      └─────────────┘      └─────────────┘
                                                                                     │
                                                                                     ▼
                                                                              ┌─────────────┐
                                                                              │   Debrief   │
                                                                              │  Unmasking  │
                                                                              └─────────────┘
```

### 1. Empirical Bayes Prior Shrinkage (Weakness Discovery)
Raw empirical error rates $e_b = \frac{\text{errors}_b}{\text{attempts}_b}$ are noisy when sample counts are low (e.g. a rare bigram like `qz` with 1 attempt and 1 error looks artificially worse than `th` with 12 errors in 100 attempts).
Typist-ML applies **Empirical Bayes shrinkage** using a Beta prior estimated from the typist's aggregate baseline bigram distribution:
$$\hat{\theta}_b = \frac{\text{errors}_b + \alpha_0}{\text{attempts}_b + \alpha_0 + \beta_0}$$
This regularizes low-count bigrams toward the participant's global mean error rate, isolating true motor weakness.

### 2. Snake-Order Dealing into 4 Matched Sets (D04)
To prevent one experimental arm from receiving an easier set of bigrams, the top 16 weak bigrams are sorted by weakness score and dealt across 4 sets in bidirectional **snake order**:
$$\begin{array}{lcccc}
\text{Round 1 (Worst):} & \text{Rank 1} \to \text{Set A} & \text{Rank 2} \to \text{Set B} & \text{Rank 3} \to \text{Set C} & \text{Rank 4} \to \text{Set D} \\
\text{Round 2 (Reversed):} & \text{Rank 8} \to \text{Set A} & \text{Rank 7} \to \text{Set B} & \text{Rank 6} \to \text{Set C} & \text{Rank 5} \to \text{Set D} \\
\text{Round 3:} & \text{Rank 9} \to \text{Set A} & \text{Rank 10} \to \text{Set B} & \text{Rank 11} \to \text{Set C} & \text{Rank 12} \to \text{Set D} \\
\text{Round 4 (Reversed):} & \text{Rank 16} \to \text{Set A} & \text{Rank 15} \to \text{Set B} & \text{Rank 14} \to \text{Set C} & \text{Rank 13} \to \text{Set D}
\end{array}$$
Sets are mapped to generator arms via a seeded cryptographic shuffle and permanently frozen before practice begins.

### 3. Latin Square Block Rotation (Warm-up & Fatigue Control)
Each daily practice session contains 4 blocks (one per arm, 600 characters each). To eliminate order bias (Block 1 always suffering from cold hands, Block 4 suffering from fatigue), block presentation follows a balanced $4 \times 4$ Latin square rotated across days:
- **Day 2:** Block 1 $\to$ Block 2 $\to$ Block 3 $\to$ Block 4
- **Day 3:** Block 2 $\to$ Block 3 $\to$ Block 4 $\to$ Block 1
- **Day 4:** Block 3 $\to$ Block 4 $\to$ Block 1 $\to$ Block 2
- **Day 5:** Block 4 $\to$ Block 1 $\to$ Block 2 $\to$ Block 3

---

## The 4 Generative Arms: Architecture & Trade-Offs

Each arm represents a distinct paradigm for automated practice drill generation:

```
┌──────────────┬───────────────────────────────┬─────────────────────────────┬───────────────────────────┐
│ Arm          │ Generation Engine             │ Linguistic Realism          │ Target Bigram Density     │
├──────────────┼───────────────────────────────┼─────────────────────────────┼───────────────────────────┤
│ Control (A)  │ Frequency-Weighted Corpus     │ Real English prose (100%)   │ Natural baseline (0.00)   │
│ Heuristic (B)│ Word-List Greedy Combinator   │ Valid dictionary words (95%)│ High density (0.20–0.30)  │
│ Markov (C)   │ 2nd-Order N-gram Transitions  │ Pseudo-words ("quastic",15%)│ Very high density (>0.35) │
│ LLM (D)      │ Local 1B Quantized LM (MLX)   │ Natural sentences (~95%)    │ Calibrated (0.10–0.40)    │
└──────────────┴───────────────────────────────┴─────────────────────────────┴───────────────────────────┘
```

### The Shared Validator Fairness Gate (D16, D30)
To ensure that arms compete strictly on generative drill quality rather than drill length or cheat-density, every candidate drill must pass an identical validator before being written to the database:
1. **Length:** Exactly $250\text{ to }350$ characters ($50\text{ to }70$ words).
2. **Charset:** Lowercase English ASCII letters (`a`–`z`) and spaces only; no numbers or punctuation.
3. **Density Bounds:** Target bigram density must fall strictly within $[0.10, 0.40]$ (calibrated in T3.4 per D30).
4. **Coverage:** Every assigned target bigram must appear $\ge 3$ times in the drill.
5. **Repetition Limits:** No word may be repeated more than twice per block.

---

## Pre-Registered Statistical Formulation

All evaluation procedures were frozen in `docs/analysis-plan.md` on 2026-10-30 prior to study execution (D20).

### 1. Primary Outcome: Targeting Effect $E(s)$
The primary metric evaluates whether error rate reduction on targeted sets exceeds natural learning on the held-out control set (difference-in-differences):
$$d(s) = p_{\text{retest}}(s) - p_{\text{baseline}}(s)$$
$$E(s) = d(s) - d(\text{control})$$
A **negative** $E(s)$ indicates that targeted practice produced greater error reduction than plain volume practice.
- **Jeffreys Beta Prior:** Equal-tailed 95% credible intervals are computed using the non-informative Jeffreys prior $\text{Beta}(0.5, 0.5)$:
  $$\theta \sim \text{Beta}(\text{errors} + 0.5, \text{attempts} - \text{errors} + 0.5)$$
- **Monte Carlo Posterior Effect Draws:** 100,000 draws are sampled from baseline and retest Beta distributions to generate empirical credible intervals for $E(s)$ and compute $P(E(s) < 0)$ (the posterior probability of superior targeting effect over control).

### 2. Key Secondary Outcome: Median IKI Shift $F(s)$
The secondary confirmatory outcome evaluates clean inter-key interval changes (ms):
$$c(s) = \text{median}(\text{IKI}_{\text{retest}}(s)) - \text{median}(\text{IKI}_{\text{baseline}}(s))$$
$$F(s) = c(s) - c(\text{control})$$
- **Non-Parametric Bootstrap:** 10,000 bootstrap resamples are computed to derive robust, distribution-free 95% confidence intervals for $F(s)$.

---

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

---

## Autonomous Multi-Agent Development Pipeline

This codebase was developed following an autonomous 5-phase agentic pipeline with strict separation of concerns and independent quality gates:

```
  Phase 1: Understand ──► Phase 2: Blueprint ──► Phase 3: Build ──► Phase 4: Review ──► Phase 5: Ship
   (Gemini 4 Argon)        (Gemini 4 Argon)      (Claude Sonnet)     (Claude Opus)       (Orchestrator)
   Exhaustive Brief        Guided Step Plan       Code & Commits     Strict Security    PR & Validation
```

1. **Phase 1: Understand (`analyst` — Gemini 4 Argon)**: Researches specifications and codebase facts without designing solutions; documents edge cases, inputs, and governing D-numbers in `docs/plans/<task>-brief.md`.
2. **Phase 2: Blueprint (`architect` — Gemini 4 Argon)**: Formulates an exact, step-by-step implementation blueprint with complete types, signatures, SQL queries, and unit tests in `docs/plans/<task>-plan.md`.
3. **Phase 3: Build (`builder` — Claude Sonnet 4.6)**: Implements the blueprint step by step, committing after each step with conventional commit messages and zero unguided deviations.
4. **Phase 4: Review (`reviewer` — Claude Opus 5.5)**: Independent read-only verification auditing plan fidelity, pre-registered math, attribution invariants, security scans (`just security`), and zero data-leakage.
5. **Phase 5: Ship (`orchestrator`)**: Pushes task branch, runs full repository checks (`just check`), and opens pull requests into `main`.

---

## Setup & Quickstart (macOS, Apple Silicon)

### 1. Prerequisites
- [uv](https://docs.astral.sh/uv/) Python package manager
- Node.js 22 (pinned in `.nvmrc`) and `pnpm` 12.6.0 (`npm install -g pnpm@12.6.0`)
- [rust-just](https://github.com/casey/just) task runner (`uv tool install rust-just`)
- Security & commit tools: `uv tool install pre-commit`, `uv tool install semgrep==1.178.0`, `uv tool install actionlint-py==1.7.12.25`

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/allenvarghese05/typist-ml.git
cd typist-ml

# Install git commit hooks
pre-commit install

# Install web dependencies
(cd apps/web && pnpm install --frozen-lockfile)

# Install API dependencies (with optional Apple Silicon MLX local LLM extra)
(cd services/api && uv sync --locked --extra mlx)

# Run database migrations
just migrate

# Download pinned Llama-3.2-1B model into Hugging Face cache (Apple Silicon only)
just mlx-smoke --download
```

### 3. Running the Stack
```bash
# Start Web App, FastAPI Backend, and Generation Worker together
just dev
```
- Web Surface: `http://localhost:5173/#/`
- Analytical Dashboard: `http://localhost:5173/#/dashboard`
- Participant Debrief & Unblinding: `http://localhost:5173/#/results`
- Admin Portal: `http://localhost:5173/#/admin`
- OpenAPI Swagger Docs: `http://localhost:8000/docs`

### 4. Running Checks & Reproducibility
```bash
# Run complete test suite (TypeScript types, Biome, Vitest, Ruff, Pyright, Pytest)
just check

# Run security audits (Semgrep, Bandit, pip-audit, pnpm audit)
just security

# Regenerate README figures and verify all claims against SQLite
just figures
just check-readme
```

---

## Installed Versions

Lockfiles (`apps/web/pnpm-lock.yaml`, `services/api/uv.lock`) are the source of truth for library versions.

### Toolchain Versions

| Tool | Command | Version |
|---|---|---|
| just | `just --version` | just 1.58.0 |
| pre-commit | `pre-commit --version` | pre-commit 4.6.2 |
| actionlint | `actionlint -version` (first line) | 1.7.12 |
| semgrep | `semgrep --version` | 1.178.0 |
| uv | `uv --version` | uv 0.12.18 |
| pnpm | `pnpm --version` | 12.6.0 |
| Node | `node --version` | v22.22.2 |
| Python | `uv run python --version` | Python 3.12.2 |

### Web Libraries (`apps/web`)

| Package | Version | Purpose |
|---|---|---|
| vite | 8.3.1 | Application bundler |
| react / react-dom | 19.3.0 | UI rendering & hooks |
| typescript | 6.0.3 | Strict typechecking |
| @biomejs/biome | 2.5.14 | High-performance linter & formatter |
| vitest | 4.1.11 | Unit & component testing |
| tailwindcss | 4.3.3 | Utility-first styling |

### Python Libraries (`services/api`)

| Package | Version | Purpose |
|---|---|---|
| fastapi | 0.141.1 | Async REST API |
| sqlmodel / sqlalchemy | 0.0.47 | Relational ORM |
| alembic | 1.20.0 | Database migrations |
| uvicorn | 0.54.0 | ASGI web server |
| typer | 0.27.2 | CLI commands |
| numpy | 2.2.3 | Numerical arrays & vector math |
| scipy | 1.15.2 | Beta distribution & statistical sampling |
| matplotlib | 3.10.1 | Headless 300 DPI chart generation |
| wordfreq | 3.1.1 | English corpus frequency ranking |
| ruff | 0.16.9 | Fast Python linter & formatter |
| pyright | 1.1.414 | Strict static type checker |
| pytest | 9.1.1 | Test runner |

### On-Device Model Runtime (Apple Silicon MLX)

| Item | Specification |
|---|---|
| Runtime | Apple MLX (`mlx-lm` 0.31.3, `mlx` 0.32.3) |
| Model | `mlx-community/Llama-3.2-1B-Instruct-4bit` |
| Hugging Face Revision | `08231374eeacb049a0eade7922910865b8fce912` |
| Throughput | $>40\text{ tokens/s}$ (Apple M1 Pro, 16 GB RAM) |

---

## Data and Licences

- **Code License:** Distributed under the **[MIT License](LICENSE)** (Copyright &copy; 2026 Allen Varghese).
- **Corpus Data Attribution:** English word lists and frequency weights are derived from [`wordfreq`](https://pypi.org/project/wordfreq/) by Robyn Speer, distributed under the **Creative Commons Attribution-ShareAlike 4.0 (CC BY-SA 4.0)** license. Corpus artifacts are generated offline; no external network requests are made at runtime.
