"""Model smoke test (T0.5): load the D10 model with mlx-lm and generate one line, twice.

Runs on macOS arm64 with the `mlx` extra installed (`uv sync --locked --extra mlx`):

    just mlx-smoke --download   # once: fetch the pinned model revision (network, D23)
    just mlx-smoke              # offline: two generations with the same seed

Prints the installed versions, a check of the design doc section 13.5 names, the installed
signatures of the mlx-lm calls, and for each generation the text, token count, tokens per
second and peak memory in MB, then whether both texts match. The last line is `SMOKE OK`.
Exit codes: 0 ok, 2 wrong platform or bad arguments, 3 a section 13.5 name or call does not
match the installed mlx-lm, 4 the pinned model revision is not in the Hugging Face cache,
5 mlx-lm is not installed.

This is a one-off check, not application code: MLXRuntime arrives in T3.2. mlx, mlx_lm and
huggingface_hub are imported inside functions only, so this module imports on Linux
(tests/unit/test_mlx_smoke.py).
"""

import argparse
import inspect
import json
import os
import platform
import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any

DEFAULT_MODEL_ID = "mlx-community/Llama-3.2-1B-Instruct-4bit"  # D10
# Hugging Face commit of DEFAULT_MODEL_ID, pinned by T0.5 (D23). Never changed during the pilot.
MODEL_REVISION = "08231374eeacb049a0eade7922910865b8fce912"
DEFAULT_SEED = 0
MAX_TOKENS = 40  # T0.5 owner answer 8
TEMP = 0.8  # design doc section 13.5 sampler
TOP_P = 0.9  # design doc section 13.5 sampler
MESSAGES: tuple[dict[str, str], ...] = (
    {
        "role": "user",
        "content": (
            "Write one line of ten common lowercase English words separated by single spaces."
            " Reply with the line only."
        ),
    },
)
API_NAMES = (
    "mlx.core.random.seed",
    "mlx_lm.load",
    "mlx_lm.stream_generate",
    "mlx_lm.sample_utils.make_sampler",
)
RESPONSE_FIELDS = ("text", "generation_tokens", "generation_tps", "peak_memory")
VERSION_PACKAGES = ("mlx-lm", "mlx", "mlx-metal", "transformers", "huggingface-hub")
COMMIT_SHA = re.compile(r"[0-9a-f]{40}")


@dataclass(frozen=True)
class SmokeArgs:
    """The parsed command line."""

    model: str
    revision: str
    seed: int
    download: bool


@dataclass(frozen=True)
class GenerationResult:
    """One generation: the whole text and the counters from mlx-lm's last response."""

    text: str
    tokens: int
    tokens_per_sec: float
    peak_memory_mb: float


@dataclass(frozen=True)
class SmokeReport:
    """Two generations with the same seed and whether their texts are identical."""

    runs: tuple[GenerationResult, GenerationResult]
    same_text: bool


class ApiDriftError(Exception):
    """Names from design doc section 13.5 that the installed mlx-lm does not provide."""

    def __init__(self, names: list[str]) -> None:
        super().__init__(", ".join(names))
        self.names = names


def parse_args(argv: Sequence[str] | None = None) -> SmokeArgs:
    """Parse the command line; exits with code 2 (argparse) on a bad argument.

    --revision defaults to MODEL_REVISION for the default model and is required with any other
    --model. The revision must be a full 40-character lowercase commit SHA, and --seed must be
    zero or greater.
    """
    parser = argparse.ArgumentParser(
        description="T0.5 model smoke test: generate one line with mlx-lm, twice, same seed."
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL_ID, help="Hugging Face model id (default: the D10 model)"
    )
    parser.add_argument(
        "--revision",
        default=None,
        help="full Hugging Face commit SHA of --model (default: MODEL_REVISION)",
    )
    parser.add_argument(
        "--seed", type=int, default=DEFAULT_SEED, help="seed for mlx.core.random.seed (default: 0)"
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="download the pinned revision once (uses the network), then exit",
    )
    namespace = parser.parse_args(argv)
    model: str = namespace.model
    revision: str | None = namespace.revision
    seed: int = namespace.seed
    if revision is None:
        if model != DEFAULT_MODEL_ID:
            parser.error("--revision is required with --model (a full Hugging Face commit SHA)")
        revision = MODEL_REVISION
    if COMMIT_SHA.fullmatch(revision) is None:
        parser.error(f"--revision must be a full 40-character commit SHA, got {revision!r}")
    if seed < 0:
        parser.error("--seed must be 0 or greater")
    return SmokeArgs(model=model, revision=revision, seed=seed, download=bool(namespace.download))


def configure_hub_env(*, offline: bool) -> None:
    """Set the Hugging Face Hub variables (D23); call before huggingface_hub is imported.

    Telemetry is always off. offline=True makes every Hub call read the local cache only.
    """
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "1" if offline else "0"


def installed_version(distribution: str) -> str:
    """Return the installed version of a distribution, or "none" if it is not installed."""
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return "none"


def version_lines() -> list[str]:
    """Return `VERSION <name> <version>` lines: python, macos, then VERSION_PACKAGES in order."""
    lines = [
        f"VERSION python {platform.python_version()}",
        f"VERSION macos {platform.mac_ver()[0] or 'n/a'}",
    ]
    lines += [f"VERSION {name} {installed_version(name)}" for name in VERSION_PACKAGES]
    return lines


def signature_line(label: str, func: Callable[..., object]) -> str:
    """Return `SIGNATURE <label> <signature>`, or `SIGNATURE <label> unavailable`."""
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return f"SIGNATURE {label} unavailable"
    return f"SIGNATURE {label} {signature}"


def gb_to_mb(gb: float) -> float:
    """Convert mlx-lm's peak_memory (GB) to MB (GB x 1000, same base), rounded to 0.1 MB."""
    return round(gb * 1000, 1)


def run_twice(generate: Callable[[int], GenerationResult], seed: int) -> SmokeReport:
    """Call generate(seed) twice with the caller's seed and compare the two texts."""
    first = generate(seed)
    second = generate(seed)
    return SmokeReport(runs=(first, second), same_text=first.text == second.text)


def format_report(report: SmokeReport, seed: int) -> list[str]:
    """Return the RUN and TEXT lines for both generations and the SAME_TEXT line.

    Numbers are printed with one decimal; the text is JSON-quoted so it stays on one line.
    """
    lines: list[str] = []
    for number, result in enumerate(report.runs, start=1):
        lines.append(
            f"RUN {number} seed={seed} tokens={result.tokens}"
            f" tokens_per_sec={result.tokens_per_sec:.1f}"
            f" peak_memory_mb={result.peak_memory_mb:.1f}"
        )
        lines.append(f"TEXT {number} {json.dumps(result.text, ensure_ascii=False)}")
    lines.append(f"SAME_TEXT {'yes' if report.same_text else 'no'}")
    return lines


def check_api() -> list[str]:
    """Return the API_NAMES missing from the installed mlx and mlx-lm, in API_NAMES order."""
    import mlx.core as mx
    import mlx_lm

    present = {
        "mlx.core.random.seed": hasattr(mx.random, "seed"),
        "mlx_lm.load": hasattr(mlx_lm, "load"),
        "mlx_lm.stream_generate": hasattr(mlx_lm, "stream_generate"),
    }
    try:
        from mlx_lm import sample_utils
    except ImportError:
        present["mlx_lm.sample_utils.make_sampler"] = False
    else:
        present["mlx_lm.sample_utils.make_sampler"] = hasattr(sample_utils, "make_sampler")
    return [name for name in API_NAMES if not present[name]]


def api_signature_lines() -> list[str]:
    """Return SIGNATURE lines for the installed load, stream_generate and make_sampler."""
    from mlx_lm import load, stream_generate
    from mlx_lm.sample_utils import make_sampler

    return [
        signature_line("mlx_lm.load", load),
        signature_line("mlx_lm.stream_generate", stream_generate),
        signature_line("mlx_lm.sample_utils.make_sampler", make_sampler),
    ]


def resolve_model_dir(model_id: str, revision: str, *, download: bool) -> Path:
    """Return the local snapshot directory of model_id at revision (a full commit SHA).

    download=False reads only the Hugging Face cache and raises if the snapshot is not there
    (call configure_hub_env(offline=True) first). download=True fetches the snapshot.
    """
    from huggingface_hub import snapshot_download

    path = snapshot_download(repo_id=model_id, revision=revision, local_files_only=not download)
    return Path(path)


def load_generator(model_dir: Path) -> Callable[[int], GenerationResult]:
    """Load the model once from a local snapshot directory and return generate(seed).

    Uses the design doc section 13.5 calls directly: mlx_lm.load, then
    tokenizer.apply_chat_template(MESSAGES, add_generation_prompt=True, tokenize=False).
    generate(seed) calls mlx.core.random.seed(seed) (the caller's seed), builds
    make_sampler(temp=TEMP, top_p=TOP_P), runs stream_generate with max_tokens=MAX_TOKENS,
    joins every response's text and reads the counters from the last response. Raises
    ApiDriftError for a missing tokenizer method or response field, and RuntimeError if the
    stream yields nothing.
    """
    import mlx.core as mx
    from mlx_lm import load, stream_generate
    from mlx_lm.sample_utils import make_sampler

    model, tokenizer = load(str(model_dir))
    if not hasattr(tokenizer, "apply_chat_template"):
        raise ApiDriftError(["tokenizer.apply_chat_template"])
    prompt = tokenizer.apply_chat_template(
        list(MESSAGES), add_generation_prompt=True, tokenize=False
    )

    def generate(seed: int) -> GenerationResult:
        mx.random.seed(seed)
        sampler = make_sampler(temp=TEMP, top_p=TOP_P)
        text = ""
        last: Any = None
        for response in stream_generate(
            model, tokenizer, prompt, max_tokens=MAX_TOKENS, sampler=sampler
        ):
            text += response.text
            last = response
        if last is None:
            raise RuntimeError("stream_generate produced no output")
        missing = [f"response.{name}" for name in RESPONSE_FIELDS if not hasattr(last, name)]
        if missing:
            raise ApiDriftError(missing)
        return GenerationResult(
            text=text,
            tokens=int(last.generation_tokens),
            tokens_per_sec=float(last.generation_tps),
            peak_memory_mb=gb_to_mb(float(last.peak_memory)),
        )

    return generate


def main(argv: Sequence[str] | None = None) -> int:
    """Run the smoke test and return the exit code (see the module docstring)."""
    args = parse_args(argv)
    if sys.platform != "darwin" or platform.machine() != "arm64":
        print("mlx_smoke.py needs macOS on Apple Silicon (arm64), where mlx-lm runs; nothing to do")
        return 2
    if installed_version("mlx-lm") == "none":
        print(
            "SMOKE FAILED: mlx-lm is not installed;"
            " run: (cd services/api && uv sync --locked --extra mlx)"
        )
        return 5
    configure_hub_env(offline=not args.download)
    if args.download:
        model_dir = resolve_model_dir(args.model, args.revision, download=True)
        print(f"DOWNLOAD OK {args.model} {args.revision} {model_dir}")
        return 0
    for line in version_lines():
        print(line)
    print(f"MODEL {args.model} {args.revision}")
    missing = check_api()
    for name in API_NAMES:
        print(f"API {name} {'MISSING' if name in missing else 'ok'}")
    if missing:
        print("SMOKE FAILED: section 13.5 names are missing from the installed mlx-lm")
        return 3
    for line in api_signature_lines():
        print(line)
    try:
        model_dir = resolve_model_dir(args.model, args.revision, download=False)
    except OSError as exc:  # not-cached error is a FileNotFoundError, i.e. an OSError
        print(
            f"SMOKE FAILED: {args.model} at {args.revision} is not in the Hugging Face cache"
            f" ({type(exc).__name__}); run `just mlx-smoke --download` once"
        )
        return 4
    try:
        report = run_twice(load_generator(model_dir), args.seed)
    except ApiDriftError as exc:
        for name in exc.names:
            print(f"API {name} MISSING")
        print("SMOKE FAILED: section 13.5 names are missing from the installed mlx-lm")
        return 3
    except (AttributeError, TypeError) as exc:
        print(f"SMOKE FAILED: a section 13.5 call does not match the installed mlx-lm: {exc!r}")
        return 3
    print("API tokenizer.apply_chat_template ok")
    for name in RESPONSE_FIELDS:
        print(f"API response.{name} ok")
    for line in format_report(report, args.seed):
        print(line)
    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
