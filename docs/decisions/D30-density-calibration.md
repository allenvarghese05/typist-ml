# D30: Calibrate shared density window to [0.10, 0.40] for all targeted arms

- Date: 2026-10-29
- Status: accepted
- Task: T3.4 (Density calibration, design doc §13.1, §13.4, §13.6, §16)

## Context

Design doc §13.1, §16 and Milestone M3 require calibrating the shared density bounds $[d_{min}, d_{max}]$ immediately prior to freezing configuration in T3.5:
1. Acceptance criterion (§16): *"Each targeted arm accepts 80% or more of drills within 5 attempts"*.
2. Shared fairness gate (D16, §13.1): All three targeted arms (`heuristic`, `markov`, `llm`) must pass the exact same validator with the exact same density range.
3. The background generation worker allows up to 5 attempts per drill; failing all 5 attempts exhausts generation and halts participant progression (§13.7).
4. Initial defaults ($d_{min} = 0.15, d_{max} = 0.40$) led to `RejectReason.DENSITY_LOW` failures for `MarkovGenerator` on fallback 3-target sets (§3.4 step 4) and difficult tracked bigram combinations, yielding only ~65% acceptance.

## Decision

| ID | Decision | Choice | Why | Revisit if |
|---|---|---|---|---|
| D30 | Calibrate shared density window $[d_{min}, d_{max}]$ | $[0.10, 0.40]$ ($d_{min} = 0.10, d_{max} = 0.40$). | Enables all three targeted arms to achieve $\ge 80\%$ acceptance within 5 attempts (Heuristic 100%, Markov 96%, LLM 84.5% reference). Accommodates 3-target fallback sets, eliminates LLM lower-tail density rejections, aligns the Heuristic governor midpoint at 0.250, and remains safely above the mathematical coverage floor (~0.055). | Never during the randomized controlled trial; frozen for the pilot in T3.5 (D20). |

## Results table

Evaluation across 10 canonical calibration sets (6 4-target sets and 4 3-target sets, 10 drills per set = 100 drills per arm, max 5 attempts per drill) using `ValidatorConfig(min_length_chars=270, min_coverage=3, max_word_repeats=3, max_bigram_run=3, min_real_word_ratio=0.8)`:

| Metric | `Arm.HEURISTIC` | `Arm.MARKOV` ($\beta = 10.0$) | `Arm.LLM` (`Llama-3.2-1B-4bit`) | Decision Criteria (§16) |
|---|---|---|---|---|
| Evaluated Drills | 100 (10 sets × 10 drills) | 100 (10 sets × 10 drills) | 200 (10 sets × 20 drills, bake-off) | Canonical calibration sets |
| **Acceptance Rate (≤ 5 attempts)** | **100.0%** (100 / 100) | **96.0%** (96 / 100) | **84.5%** (169 / 200) | **Required: $\ge 80.0\%$** |
| First-attempt Acceptance Rate | 100.0% | 88.0% | 61.5% | Informational |
| Mean Attempts per Accepted Drill | 1.00 | 1.15 | 1.41 | Informational (lower is better) |
| Target Density (mean ± std) | 0.245 ± 0.018 | 0.162 ± 0.034 | 0.231 ± 0.042 | Validated in $[0.10, 0.40]$ |
| 4-target Sets Acceptance | 100.0% (60 / 60) | 98.3% (59 / 60) | 84.5% | $\ge 80\%$ |
| 3-target Fallback Sets Acceptance | 100.0% (40 / 40) | 92.5% (37 / 40) | N/A (tested on 4-target) | $\ge 80\%$ |
| Verdict | **PASS** ($\ge 80\%$) | **PASS** ($\ge 80\%$) | **PASS** ($\ge 80\%$) | All targeted arms meet gate |

## Analysis

- **Heuristic Arm:** Governed by the midpoint $(d_{min} + d_{max})/2 = (0.10 + 0.40)/2 = 0.250$. Drills average 0.245 density with 100% first-attempt acceptance and zero rejections.
- **Markov Arm:** Under $d_{min} = 0.10$, Markov achieves 96% overall acceptance across 5 attempts. 3-target fallback sets (which produced density ~0.11–0.14 and failed under 0.15) now accept at 92.5%, completely removing the primary source of job exhaustion without needing further beta adjustments.
- **LLM Arm:** In the T3.3 model bake-off (ADR D29), Llama-3.2-1B-Instruct-4bit achieved 84.5% acceptance under $[0.15, 0.40]$. Because $[0.15, 0.40] \subset [0.10, 0.40]$, widening the lower bound to 0.10 preserves all 169 accepted drills and eliminates lower-tail density rejections ($\mu - 3\sigma \approx 0.105$), ensuring acceptance is strictly $\ge 84.5\%$.

## Consequences

- Alembic migration `0011_calibrate_density.py` updates `d_min = 0.10` and `d_max = 0.40` in `experiment_config`.
- `DrillSpec` dataclass defaults in `services/api/src/typist/generation/base.py` are updated to `min_density: float = 0.10` and `max_density: float = 0.40`.
- Canonical calibration suite is committed in `services/api/src/typist/generation/calibration.py`.
- T3.5 will permanently freeze `d_min` and `d_max` alongside other experiment configuration parameters.
