# Typist-ML task runner. Run `just` (or `just --list`) to see the recipes.
#
# Every recipe skips an app that is not scaffolded yet: it prints a message and exits 0.
# `check` is defined by decision D21 (docs/decisions/D21-just-check.md).
# `security` and its parts are defined by decision D22 (docs/decisions/D22-security-scanning.md).
# They also skip a missing tool or an unreachable registry, and they are not part of `check`.
#
# Contracts later tasks must meet for these recipes to work unchanged:
#   apps/web (T0.2):     package.json with a `dev` script; @biomejs/biome, typescript, vitest and
#                        vite as dev dependencies; tsconfig files set "noEmit" so `tsc -b` only checks.
#   services/api (T0.3): pyproject.toml with ruff, pyright and pytest in the dev group;
#                        FastAPI app factory `typist.main:create_app`; alembic.ini in services/api.
#   worker (T2.5):       services/api/src/typist/worker.py and the `typist worker` command.
#   gen-types:           placeholder until the task that adds openapi-typescript replaces it.
#   security-py (T0.3):  placeholder; T0.3 replaces its body with bandit and pip-audit, both added
#                        as dev dependencies in services/api/pyproject.toml (decision D22).

# semgrep CLI version pinned by decision D22. Keep it equal to README.md and scripts/cloud-setup.sh.
semgrep_version := "1.178.0"

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

# Run the security scans: semgrep, then security-py and security-web (decision D22). Uses the network.
security:
    #!/usr/bin/env bash
    # Every part runs; the recipe fails at the end if any part failed. A missing tool, a missing app
    # or an unreachable registry is a skip, not a failure. Must stay bash 3.2 compatible (macOS).
    set -euo pipefail
    cd "{{justfile_directory()}}"
    summary=""
    failed=""
    # semgrep downloads the public ruleset p/security-audit and uploads nothing. --metrics=off and
    # SEMGREP_ENABLE_VERSION_CHECK=0 turn off its other two outbound calls (D19, D22).
    if ! command -v semgrep >/dev/null 2>&1; then
        echo "semgrep not found, skipping semgrep (run: uv tool install semgrep=={{semgrep_version}})"
        summary="${summary}  semgrep: skipped (not installed)"$'\n'
    elif command -v curl >/dev/null 2>&1 && ! curl --silent --head --output /dev/null --connect-timeout 5 --max-time 10 https://semgrep.dev/; then
        echo "couldn't reach the registry, skipping semgrep (https://semgrep.dev not reachable)"
        summary="${summary}  semgrep: skipped (registry unreachable)"$'\n'
    else
        installed="$(SEMGREP_ENABLE_VERSION_CHECK=0 semgrep --version 2>/dev/null || true)"
        if [ "$installed" != "{{semgrep_version}}" ]; then
            echo "warning: semgrep ${installed:-unknown} is installed but D22 pins {{semgrep_version}}; results may differ"
        fi
        if SEMGREP_ENABLE_VERSION_CHECK=0 semgrep --config=p/security-audit --metrics=off --error --quiet .; then
            rc=0
        else
            rc=$?
        fi
        case "$rc" in
            0) summary="${summary}  semgrep: passed"$'\n' ;;
            1) summary="${summary}  semgrep: FAILED (findings, see output above)"$'\n'
               failed="${failed} semgrep" ;;
            *) summary="${summary}  semgrep: FAILED (semgrep error, exit ${rc}, see output above)"$'\n'
               failed="${failed} semgrep" ;;
        esac
    fi
    # The sub-recipes run as child just processes so that a failure in one does not stop the other.
    # Every skip message contains "skipping"; that is how a skip is told apart from a pass.
    for part in security-py security-web; do
        if out="$("{{just_executable()}}" --justfile "{{justfile()}}" "$part" 2>&1)"; then
            rc=0
        else
            rc=$?
        fi
        printf '%s\n' "$out"
        if [ "$rc" -ne 0 ]; then
            summary="${summary}  ${part}: FAILED (exit ${rc}, see output above)"$'\n'
            failed="${failed} ${part}"
        else
            case "$out" in
                *skipping*) summary="${summary}  ${part}: skipped (see message above)"$'\n' ;;
                *) summary="${summary}  ${part}: passed"$'\n' ;;
            esac
        fi
    done
    echo
    echo "just security summary:"
    printf '%s' "$summary"
    if [ -n "$failed" ]; then
        echo "just security: FAILED:${failed}"
        exit 1
    fi
    echo "just security: no failures (skipped parts are listed above)"

# Python security scan for services/api: a placeholder until T0.3 replaces it (decision D22).
security-py:
    @echo "security-py not yet implemented (T0.3 replaces it with bandit and pip-audit), skipping"

# Audit apps/web dependencies, dev dependencies included: pnpm audit --audit-level=high (decision D22).
security-web:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{justfile_directory()}}"
    if [ ! -f apps/web/package.json ]; then
        echo "apps/web not yet scaffolded, skipping security-web"
        exit 0
    fi
    if ! command -v pnpm >/dev/null 2>&1; then
        echo "pnpm not found, run corepack enable (skipping security-web)"
        exit 0
    fi
    if command -v curl >/dev/null 2>&1 && ! curl --silent --head --output /dev/null --connect-timeout 5 --max-time 10 https://registry.npmjs.org/; then
        echo "couldn't reach the registry, skipping security-web (https://registry.npmjs.org not reachable)"
        exit 0
    fi
    cd apps/web
    pnpm audit --audit-level=high
