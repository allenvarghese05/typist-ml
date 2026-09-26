#!/usr/bin/env bash
# Paste into the setup script of your Claude Code on the web environment.
# Installs the tools the repo expects on the Linux cloud VM. Safe to re-run.
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"

command -v uv   >/dev/null 2>&1 || pip install --quiet uv
command -v just >/dev/null 2>&1 || uv tool install rust-just
command -v pre-commit >/dev/null 2>&1 || uv tool install pre-commit
command -v semgrep >/dev/null 2>&1 || uv tool install semgrep==1.178.0
command -v pnpm >/dev/null 2>&1 || npm install -g pnpm@12.6.0

# Install project dependencies once the apps exist (no mlx extra on Linux)
if [ -f services/api/pyproject.toml ]; then (cd services/api && uv sync); fi
if [ -f apps/web/package.json ];       then (cd apps/web && pnpm install); fi
