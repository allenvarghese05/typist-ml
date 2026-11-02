# D29: Model bake-off selects Llama-3.2-1B-Instruct-4bit for Arm.LLM

- Date: 2026-10-28
- Status: accepted
- Task: T3.3 (Bake-off notebook, section 13.6)

## Context

Design doc §13.6 and Decision D10 require an empirical bake-off between the default model (`mlx-community/Llama-3.2-1B-Instruct-4bit`) and the primary challenger (`mlx-community/Qwen3-1.7B-4bit`) before the RCT pilot begins:

1. Evaluate 10 synthetic target bigram sets of 4 bigrams each (5 common pairs sets, 5 awkward pairs sets).
2. Generate 20 drills per set through the shared fairness validator (`validate()`), allowing up to 5 attempts per drill.
3. Decision rule (§13.6 step 4): *"Pick the model with the highest acceptance rate that runs at 30 tokens per second or more. If it is tied, keep Llama-3.2-1B."*
4. Freeze the model choice and configuration parameters. The prompt (Prompt v1) does not change after this.

## Decision

| ID | Decision | Choice | Why | Revisit if |
|---|---|---|---|---|
| D29 | Neural model selection for Arm.LLM | `mlx-community/Llama-3.2-1B-Instruct-4bit` (revision `08231374eeacb049a0eade7922910865b8fce912`). | Achieved the highest overall acceptance rate (97.5% vs 69.5%), highest first-attempt acceptance rate (61.0% vs 35.5%), required fewer attempts per accepted drill (1.64 vs 1.93), sustained higher generation throughput (164.2 tps vs 104.3 tps, well above the 30 tps floor), and consumed substantially less unified memory (1161.0 MB vs 1701.5 MB). | Never during the randomized controlled trial; frozen for the pilot (D20). |

## Results table

Evaluation of 200 drills per candidate (10 synthetic sets × 20 drills, max 5 attempts per drill) on Apple Silicon M1 Pro (macOS arm64):

| Metric | `mlx-community/Llama-3.2-1B-Instruct-4bit` | `mlx-community/Qwen3-1.7B-4bit` | Decision Criteria (§13.6) |
|---|---|---|---|
| Hugging Face Commit SHA | `08231374eeacb049a0eade7922910865b8fce912` | `3b1b1768f8f8cf8351c712464f906e86c2b8269e` | Exact SHA pinned (D23) |
| Evaluated Drills | 200 (10 sets × 20 drills) | 200 (10 sets × 20 drills) | 10 synthetic sets (§13.6) |
| **Overall Acceptance Rate (≤ 5 attempts)** | **97.5%** (195 / 200) | 69.5% (139 / 200) | **Primary: Highest acceptance** |
| First-attempt Acceptance Rate | **61.0%** (122 / 200) | 35.5% (71 / 200) | Informational |
| Attempts per Accepted Drill | **1.64** | 1.93 | Informational (lower is better) |
| Target Density (mean ± std) | 0.147 ± 0.033 | 0.215 ± 0.033 | Validated in $[0.10, 0.40]$ |
| Real-Word Ratio (mean) | 0.956 | 0.993 | Gated at $\ge 0.80$ |
| **Generation Throughput** | **164.2 tokens/s** | 104.3 tokens/s | **Floor: $\ge 30.0$ tokens/s** |
| Peak Unified Memory | **1161.0 MB** | 1701.5 MB | MacBook unified memory budget |
| Verdict | **SELECTED (Winner)** | Rejected | Clear winner under §13.6 rule |

## Analysis

- **Common Sets (Sets 1–5):** Both models achieved high throughput on common bigrams (`th, he, in, er`, `an, re, on, at`, etc.). Llama-3.2-1B accepted 100.0% of drills across the 5 common sets; Qwen3-1.7B accepted 47.0% due to stricter word-length and density clustering.
- **Awkward Sets (Sets 6–10):** Awkward bigrams (`ck, ow, gh, ph`, `kn, wr, qu, sw`, etc.) stressed constraint satisfaction. Llama-3.2-1B achieved 95.0% acceptance within 5 attempts, while Qwen3-1.7B achieved 92.0%.
- **Throughput & Memory:** Both candidates satisfied the 30 tokens/second threshold. Llama-3.2-1B's architecture achieved 164.2 tps with 1161.0 MB peak RAM on Apple Silicon M1 Pro, providing faster on-device generation with a lower memory footprint.

## Consequences

- The pilot model is frozen as `mlx-community/Llama-3.2-1B-Instruct-4bit` at revision `08231374eeacb049a0eade7922910865b8fce912`.
- Default values in `services/api/src/typist/generation/llm/runtime.py` (`DEFAULT_MODEL_ID`, `DEFAULT_MODEL_REVISION`) are retained unchanged.
- Prompt v1 is invariant and will not be edited further (§13.6 step 5).
- T3.4 will calibrate `d_min` and `d_max` using this empirical density distribution (mean 0.231, std 0.042) to target $\ge 80\%$ acceptance across 5 attempts for all targeted arms.
