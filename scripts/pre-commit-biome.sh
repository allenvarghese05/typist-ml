#!/usr/bin/env bash
# pre-commit hook: auto-fix and format staged apps/web files with the Biome version pinned in
# apps/web/pnpm-lock.yaml. Called by .pre-commit-config.yaml from the repo root with
# repo-relative paths.
set -euo pipefail
if [ "$#" -eq 0 ]; then
    exit 0
fi
if [ ! -f apps/web/package.json ]; then
    echo "apps/web not yet scaffolded, skipping biome"
    exit 0
fi
files=()
for f in "$@"; do
    files+=("${f#apps/web/}")
done
cd apps/web
pnpm exec biome check --write --no-errors-on-unmatched --files-ignore-unknown=true "${files[@]}"
