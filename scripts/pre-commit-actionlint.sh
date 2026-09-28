#!/usr/bin/env bash
# pre-commit hook: lint staged GitHub Actions workflow files with actionlint at the version pinned
# below (T0.4 owner answer 24). Install it with `uv tool install actionlint-py==1.7.12.25`
# (README). Called by .pre-commit-config.yaml from the repo root with repo-relative paths. Runs
# offline. shellcheck and pyflakes are turned off so the result does not depend on other tools
# that happen to be installed.
set -euo pipefail
pinned="1.7.12"
install_hint="uv tool install actionlint-py==1.7.12.25"
if [ "$#" -eq 0 ]; then
    exit 0
fi
if ! command -v actionlint >/dev/null 2>&1; then
    echo "actionlint not found; install it with: ${install_hint}"
    exit 1
fi
version_output="$(actionlint -version)"
installed="${version_output%%$'\n'*}"
if [ "$installed" != "$pinned" ]; then
    echo "actionlint ${installed} is installed but the repo pins ${pinned}; install it with: ${install_hint}"
    exit 1
fi
actionlint -shellcheck= -pyflakes= "$@"
