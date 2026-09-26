#!/usr/bin/env bash
# pre-commit hook: auto-fix and format staged services/api Python files with the ruff
# version pinned in services/api/uv.lock. Called by .pre-commit-config.yaml from the repo root
# with repo-relative paths.
set -euo pipefail
if [ "$#" -eq 0 ]; then
    exit 0
fi
if [ ! -f services/api/pyproject.toml ]; then
    echo "services/api not yet scaffolded, skipping ruff"
    exit 0
fi
files=()
for f in "$@"; do
    files+=("${f#services/api/}")
done
cd services/api
uv run ruff check --fix --force-exclude "${files[@]}"
uv run ruff format --force-exclude "${files[@]}"
