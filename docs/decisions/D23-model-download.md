# D23: One-time download of the model weights from the Hugging Face Hub

- Date: 2026-09-29
- Status: accepted
- Task: T0.5

## Context

D09 runs the model in-process with the mlx-lm Python API, and D10 names the default model,
`mlx-community/Llama-3.2-1B-Instruct-4bit`. Its weights are published on the Hugging Face Hub, so
they have to be downloaded once. D19 and CLAUDE.md keep everything local and forbid cloud AI APIs
and telemetry, but no decision covered downloading open weights (T0.5 brief, open question 6).

## Decision

| ID | Decision | Choice | Why | Revisit if |
|---|---|---|---|---|
| D23 | Model download | The weights are downloaded once, on purpose, by the owner with `just mlx-smoke --download`, at a pinned Hugging Face commit (`08231374eeacb049a0eade7922910865b8fce912` for the D10 model, pinned in `services/api/scripts/mlx_smoke.py`), into the default Hugging Face cache outside the repository. Every later load sets `HF_HUB_OFFLINE=1` and `HF_HUB_DISABLE_TELEMETRY=1` before the Hub library is imported and reads the pinned snapshot from the cache, so it makes no network request. The Hub is a file source, not a cloud AI API: generation runs on the MacBook (D06, D09), and no code, prompt, output or participant data is sent anywhere. | Open weights must be on the machine once; a pinned commit keeps the pilot reproducible (design doc sections 5 and 13.1), and offline loads keep D19 | The Hub changes what a download collects, the model repository becomes gated, or another model is needed (the T3.3 bake-off follows the same rule with its own pinned commit) |

## Consequences

- The download is owner-run on the MacBook. CI never installs the `mlx` extra and never
  downloads the model, and neither do the builder and reviewer sandboxes.
- The cache stays outside the repository. `HF_HOME`, `HF_HUB_CACHE` and `HUGGINGFACE_HUB_CACHE`
  must not point inside it (only `/data/` is gitignored).
- A load that does not find the pinned commit in the cache fails with a message naming
  `just mlx-smoke --download`; it never falls back to downloading.
- mlx-lm and mlx are pinned exactly in the `mlx` extra of `services/api/pyproject.toml`, with the
  marker `sys_platform == 'darwin' and platform_machine == 'arm64'`; everything else is in
  `services/api/uv.lock`. `uv sync --locked` without `--extra mlx`, the CI `api` job and the
  `uv export` in `just security-py` do not include the extra, so pip-audit does not audit the
  model runtime's dependencies.
- T3.2's `MLXRuntime` follows the same rule: resolve the pinned snapshot from the cache while
  offline, then load that directory.
- The weights are under the Llama 3.2 Community License. They are downloaded for local use, never
  committed and never redistributed.
