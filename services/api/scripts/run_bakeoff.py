"""Standalone benchmark runner for the model bake-off (design doc 13.6; D10, D29; T3.3).

Executes the bake-off evaluation protocol on Apple Silicon or simulates execution with
FakeLLMRuntime when --fake is specified.
"""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from typist.corpus.word_index import WordIndex
from typist.generation.llm.bakeoff import (
    CHALLENGER_MODEL_ID,
    CHALLENGER_MODEL_REVISION,
    DEFAULT_DRILLS_PER_SET,
    DEFAULT_MAX_ATTEMPTS,
    SYNTHETIC_TARGET_SETS,
    ModelBakeoffSummary,
    evaluate_bakeoff,
    select_bakeoff_winner,
)
from typist.generation.llm.runtime import (
    DEFAULT_MODEL_ID,
    DEFAULT_MODEL_REVISION,
    FakeLLMRuntime,
    LLMRuntimeProtocol,
    MLXRuntime,
    configure_hub_env,
    is_apple_silicon,
)
from typist.generation.validator import ValidatorConfig


def format_summary_table(summaries: Sequence[ModelBakeoffSummary]) -> str:
    """Format a text comparison table from model summaries."""
    headers = [
        "Model ID",
        "Accept %",
        "1st-Att %",
        "Att/Drill",
        "Density",
        "Real-Word",
        "TPS",
        "RAM (MB)",
        "Pass TPS",
    ]
    lines = [" | ".join(headers), "-" * 85]
    for s in summaries:
        att_str = f"{s.attempts_per_accepted_drill:.2f}" if s.attempts_per_accepted_drill else "N/A"
        density_str = f"{s.mean_density:.3f}" if s.mean_density else "N/A"
        rw_str = f"{s.mean_real_word_ratio:.3f}" if s.mean_real_word_ratio else "N/A"
        row = [
            s.model_id.split("/")[-1][:20],
            f"{s.acceptance_rate * 100:.1f}%",
            f"{s.first_attempt_acceptance_rate * 100:.1f}%",
            att_str,
            density_str,
            rw_str,
            f"{s.mean_tokens_per_sec:.1f}",
            f"{s.peak_memory_mb:.1f}",
            "YES" if s.meets_tps_threshold else "NO",
        ]
        lines.append(" | ".join(row))
    return "\n".join(lines)


def run_benchmark(
    runtime: LLMRuntimeProtocol,
    index: WordIndex,
    config: ValidatorConfig,
    model_id: str,
    revision: str,
    drills_per_set: int,
    max_attempts: int,
) -> ModelBakeoffSummary:
    """Run benchmark for one model and return the summary."""
    _, summary = evaluate_bakeoff(
        runtime=runtime,
        index=index,
        config=config,
        model_id=model_id,
        revision=revision,
        target_sets=SYNTHETIC_TARGET_SETS,
        drills_per_set=drills_per_set,
        max_attempts=max_attempts,
    )
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Typist-ML model bake-off benchmark (design doc 13.6)."
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL_ID,
        help=f"Model ID to evaluate (default: {DEFAULT_MODEL_ID})",
    )
    parser.add_argument(
        "--revision",
        default=DEFAULT_MODEL_REVISION,
        help="Model revision SHA (default: pinned Llama 3.2 revision)",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Compare both default (Llama-3.2-1B) and challenger (Qwen3-1.7B)",
    )
    parser.add_argument(
        "--drills-per-set",
        type=int,
        default=DEFAULT_DRILLS_PER_SET,
        help=f"Drills per target set (default: {DEFAULT_DRILLS_PER_SET})",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=DEFAULT_MAX_ATTEMPTS,
        help=f"Max attempts per drill (default: {DEFAULT_MAX_ATTEMPTS})",
    )
    parser.add_argument(
        "--fake",
        action="store_true",
        help="Use FakeLLMRuntime instead of loading MLX weights",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Path to write JSON summary results",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    if not args.fake and not is_apple_silicon():
        print("Live MLX model evaluation requires macOS on Apple Silicon. Use --fake to test.")
        return 2

    configure_hub_env(offline=True)

    # Standard validator config and word index
    config = ValidatorConfig(
        min_length_chars=270,
        min_coverage=3,
        max_word_repeats=3,
        max_bigram_run=2,
        min_real_word_ratio=0.8,
    )

    # Load word index from default corpus or generate words for fake
    corpus_words_path = Path("data/words.json")
    corpus_bigrams_path = Path("data/top_bigrams.json")
    if corpus_words_path.exists() and corpus_bigrams_path.exists():
        index = WordIndex.load(Path("data"))
    else:
        # Fallback for headless environments without pre-built corpus
        sample_words = tuple(["the", "weather", "in", "east", "spring", "season"] * 50)
        index = WordIndex(
            words=sample_words,
            frequencies={w: 1.0 for w in sample_words},
            tracked_bigrams=(),
            by_bigram={},
        )

    summaries: list[ModelBakeoffSummary] = []

    models_to_run = (
        [
            (DEFAULT_MODEL_ID, DEFAULT_MODEL_REVISION),
            (CHALLENGER_MODEL_ID, CHALLENGER_MODEL_REVISION),
        ]
        if args.compare
        else [(args.model, args.revision)]
    )

    for model_id, revision in models_to_run:
        print(
            f"Evaluating {model_id} (drills_per_set={args.drills_per_set}, max_attempts={args.max_attempts})..."
        )
        runtime: LLMRuntimeProtocol
        if args.fake:
            runtime = FakeLLMRuntime(
                canned_text="the weather in east is great today this morning everyone is there thinking about season",
                tokens_per_sec=45.0,
                peak_memory_mb=850.0,
            )
        else:
            runtime = MLXRuntime(model_id=model_id, revision=revision)

        summary = run_benchmark(
            runtime=runtime,
            index=index,
            config=config,
            model_id=model_id,
            revision=revision,
            drills_per_set=args.drills_per_set,
            max_attempts=args.max_attempts,
        )
        summaries.append(summary)

    print("\nBake-Off Results Table:")
    print(format_summary_table(summaries))

    if len(summaries) == 2:
        winner, reason = select_bakeoff_winner(summaries[0], summaries[1])
        print(f"\nSelection: {winner}")
        print(f"Reason: {reason}")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        data = [s.__dict__ for s in summaries]
        args.output.write_text(json.dumps(data, indent=2))
        print(f"\nWrote results to {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
