# Typist-ML task runner. Run `just` (or `just --list`) to see the recipes.
#
# Every recipe skips an app that is not scaffolded yet: it prints a message and exits 0.
# `check` is defined by decision D21 (docs/decisions/D21-just-check.md).
#
# Contracts later tasks must meet for these recipes to work unchanged:
#   apps/web (T0.2):     package.json with a `dev` script; @biomejs/biome, typescript, vitest and
#                        vite as dev dependencies; tsconfig files set "noEmit" so `tsc -b` only checks.
#   services/api (T0.3): pyproject.toml with ruff, pyright and pytest in the dev group;
#                        FastAPI app factory `typist.main:create_app`; alembic.ini in services/api.
#   worker (T2.5):       services/api/src/typist/worker.py and the `typist worker` command.
#   gen-types:           placeholder until the task that adds openapi-typescript replaces it.

[private]
default:
    @"{{just_executable()}}" --list --justfile "{{justfile()}}"

# Lint both apps (`biome ci` for apps/web: lint, format and import order; ruff for services/api).
lint:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{justfile_directory()}}"
    if [ -f apps/web/package.json ]; then
        (cd apps/web && pnpm exec biome ci .)
    else
        echo "apps/web not yet scaffolded, skipping lint"
    fi
    if [ -f services/api/pyproject.toml ]; then
        (cd services/api && uv run ruff check .)
    else
        echo "services/api not yet scaffolded, skipping lint"
    fi

# Check formatting of both apps without changing files (Biome, ruff format --check).
format-check:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{justfile_directory()}}"
    if [ -f apps/web/package.json ]; then
        (cd apps/web && pnpm exec biome format .)
    else
        echo "apps/web not yet scaffolded, skipping format-check"
    fi
    if [ -f services/api/pyproject.toml ]; then
        (cd services/api && uv run ruff format --check .)
    else
        echo "services/api not yet scaffolded, skipping format-check"
    fi

# Type-check both apps (tsc for apps/web, pyright for services/api).
types:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{justfile_directory()}}"
    if [ -f apps/web/package.json ]; then
        (cd apps/web && pnpm exec tsc -b)
    else
        echo "apps/web not yet scaffolded, skipping types"
    fi
    if [ -f services/api/pyproject.toml ]; then
        (cd services/api && uv run pyright)
    else
        echo "services/api not yet scaffolded, skipping types"
    fi

# Run the tests of both apps (Vitest for apps/web, pytest for services/api).
test:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{justfile_directory()}}"
    if [ -f apps/web/package.json ]; then
        (cd apps/web && pnpm exec vitest run)
    else
        echo "apps/web not yet scaffolded, skipping test"
    fi
    if [ -f services/api/pyproject.toml ]; then
        (cd services/api && uv run pytest)
    else
        echo "services/api not yet scaffolded, skipping test"
    fi

# Build apps/web for production (vite build). services/api has no build step.
build:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{justfile_directory()}}"
    if [ -f apps/web/package.json ]; then
        (cd apps/web && pnpm exec vite build)
    else
        echo "apps/web not yet scaffolded, skipping build"
    fi

# Lint, format-check, type-check, test and build both apps (decision D21). Run before pushing.
check: lint format-check types test build
    @echo "just check: all steps passed (apps not yet scaffolded were skipped)"

# Start the web app, API and worker together (macOS only). Ctrl-C stops all of them.
dev:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{justfile_directory()}}"
    if [ "$(uname -s)" != "Darwin" ]; then
        echo "just dev requires macOS (the worker needs mlx-lm on Apple Silicon), exiting"
        exit 0
    fi
    pids=""
    cleanup() {
        if [ -n "$pids" ]; then
            kill $pids 2>/dev/null || true
        fi
    }
    trap cleanup EXIT
    trap 'exit 130' INT TERM
    if [ -f apps/web/package.json ]; then
        (cd apps/web && exec pnpm run dev) &
        pids="$pids $!"
    else
        echo "apps/web not yet scaffolded, skipping web"
    fi
    if [ -f services/api/pyproject.toml ]; then
        (cd services/api && exec uv run uvicorn --factory typist.main:create_app --host 127.0.0.1 --port 8000 --reload) &
        pids="$pids $!"
    else
        echo "services/api not yet scaffolded, skipping api"
    fi
    if [ -f services/api/src/typist/worker.py ]; then
        (cd services/api && exec uv run typist worker) &
        pids="$pids $!"
    else
        echo "worker not yet implemented (M2)"
    fi
    if [ -z "$pids" ]; then
        echo "nothing to start yet, exiting"
        exit 0
    fi
    wait

# Apply database migrations (Alembic in services/api).
migrate:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{justfile_directory()}}"
    if [ ! -f services/api/pyproject.toml ]; then
        echo "services/api not yet scaffolded, skipping migrate"
        exit 0
    fi
    if [ ! -f services/api/alembic.ini ]; then
        echo "migrations not yet set up (services/api/alembic.ini missing), skipping migrate"
        exit 0
    fi
    cd services/api
    uv run alembic upgrade head

# Run the generation worker on its own (macOS only; arrives in M2).
worker:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{justfile_directory()}}"
    if [ "$(uname -s)" != "Darwin" ]; then
        echo "just worker requires macOS (mlx-lm on Apple Silicon), exiting"
        exit 0
    fi
    if [ ! -f services/api/src/typist/worker.py ]; then
        echo "worker not yet implemented (M2)"
        exit 0
    fi
    cd services/api
    uv run typist worker

# Generate apps/web/src/api/schema.d.ts from the API's OpenAPI schema (not ready yet).
gen-types:
    @echo "gen-types not yet implemented (needs services/api and apps/web), skipping"
