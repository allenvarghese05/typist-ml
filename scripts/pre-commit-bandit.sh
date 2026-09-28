#!/usr/bin/env bash
# pre-commit hook: scan staged services/api/src Python files with the bandit version pinned in
# services/api/uv.lock, failing at medium severity and above (as `just security-py` does, D22).
# Called by .pre-commit-config.yaml from the repo root with repo-relative paths.
set -euo pipefail
if [ "$#" -eq 0 ]; then
    exit 0
fi
if [ ! -f services/api/pyproject.toml ]; then
    echo "services/api not yet scaffolded, skipping bandit"
    exit 0
fi
files=()
for f in "$@"; do
    files+=("${f#services/api/}")
done
cd services/api
uv run --locked bandit -q -ll "${files[@]}"
