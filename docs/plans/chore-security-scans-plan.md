# chore-security-scans plan: local security scans, drop Codacy

Architect: phase 2 (Blueprint). Source: `docs/plans/chore-security-scans-brief.md`, including
"Owner answers (2026-09-26)" and the "Codacy resolution" line. Where they conflict, the owner answers
override the rest of the brief. Also read: CLAUDE.md, `justfile`, `docs/decisions/D21-just-check.md`,
`.claude/agents/reviewer.md`, `README.md`, `scripts/cloud-setup.sh`, `.github/pull_request_template.md`,
`.pre-commit-config.yaml`, `.gitignore`, `docs/plans/T0.2-plan.md` (for format).
Branch: `chore-security-scans`, created off `main` in step 0.

---

## 1. Summary

When this plan is done:
- `.github/workflows/codacy.yml` is deleted.
- The justfile has three new recipes. `security` runs semgrep (pinned CLI, `p/security-audit`,
  `--metrics=off`, `SEMGREP_ENABLE_VERSION_CHECK=0`) and then the two sub-recipes. `security-py` is
  a placeholder. `security-web` runs `pnpm audit --audit-level=high`. Every part runs. A missing
  tool, a missing app or an unreachable registry is skipped with a message. At the end `security`
  prints a summary and exits non-zero if any part failed.
- A `.semgrepignore` file keeps semgrep out of `node_modules/`, `.venv/`, `dist/`,
  `.claude/worktrees/` and `data/`.
- D22 is recorded in `docs/decisions/D22-security-scanning.md`.
- The reviewer has a new item 6 and may run `just security`. The README, `scripts/cloud-setup.sh`
  and the PR template mention semgrep and `just security`. `just check` and D21 do not change.

## 2. Design

- **One orchestrating recipe plus two sub-recipes.** `security` is a bash recipe. It runs the
  semgrep part inline, then calls `security-py` and `security-web` as child `just` processes
  (`"{{just_executable()}}" --justfile "{{justfile()}}" <name>`, the same idiom as `default`). It
  records each part's result and exits 1 at the end if any part failed (owner answer 6). It does
  not use recipe dependencies (`security: security-py security-web`), because `just` stops at the
  first failing dependency and always runs dependencies first.
- **Result classification.** Each part ends in one of three states: passed, skipped or FAILED.
  - semgrep's state is known inline.
  - For a sub-recipe, `security` captures its output. Exit 0 with the word `skipping` in the output
    means skipped. Exit 0 without it means passed. Any non-zero exit means FAILED.
  - Contract: every skip message in the three recipes contains `skipping`.
- **Exit codes relied on.**
  - semgrep with `--error`: exit `0` means no findings and `1` means findings. Both are documented
    semgrep exit codes. Any other code (2 fatal, 7 bad config, and so on) is reported as
    "FAILED (semgrep error, exit N)".
  - `pnpm audit`: exit `0` means no advisory at or above `high`. Non-zero means advisories or an
    audit error. The two cannot be told apart by exit code, so both are reported as
    "FAILED (exit N, see output above)" with pnpm's own output shown.
  - The plan does **not** rely on semgrep's or pnpm's exit codes or messages to detect network
    failure. Those are undocumented or overlap with other errors.
- **How "unreachable" is detected.** Before semgrep or `pnpm audit` runs, a `curl` HEAD probe
  checks the registry host:
  ```
  curl --silent --head --output /dev/null --connect-timeout 5 --max-time 10 <url>
  ```
  - The URL is `https://semgrep.dev/` for semgrep and `https://registry.npmjs.org/` for pnpm.
  - The probe has no `--fail`, so curl exits 0 for **any** HTTP response, including 4xx and 5xx
    (the host was reached).
  - curl exits non-zero only when no HTTP exchange happened: 6 (DNS), 7 (connect refused),
    28 (timeout), 35 (TLS), 56 (proxy refused the CONNECT, which is how a sandbox proxy denial
    usually looks), and so on. A non-zero probe means "couldn't reach the registry, skipping"
    (owner answer 8).
  - If `curl` is not installed, the probe is skipped and the tool runs. Its exit code then decides.
  - Honest limits: the probe is a separate request from the tool's own request. If the probe
    succeeds and the tool's request still fails, the result is FAILED, not skipped. The npm probe
    checks the default registry, not a custom one set in `.npmrc`.
- **Skip order in `security-web`.** First the app is checked (`apps/web/package.json` missing:
  "apps/web not yet scaffolded, skipping security-web"). Then pnpm (not on PATH: "pnpm not found,
  run corepack enable (skipping security-web)", owner answer 14). Then the registry probe. Then
  `pnpm audit --audit-level=high` runs from `apps/web`, without `--prod` (owner answer 7).
- **`security-py`** is an unconditional placeholder like `gen-types` (owner answer 12). It names
  bandit and pip-audit only in its message and in the header contract. No dependency is added
  (owner answer 13).
- **semgrep pin (owner answer 4(b)).**
  - A justfile variable, `semgrep_version := "<SEMGREP_VERSION>"`, is the single source that
    recipes read. The same value is written to the README version table, README setup step 1 and
    `scripts/cloud-setup.sh`.
  - The missing-tool message prints the pinned install command.
  - If the installed version differs from the pin, `security` prints one warning line and
    continues. It does not fail.
  - The ruleset is referenced only by its alias `p/security-audit`. The rules are not vendored.
- **Where the version comes from.** The builder must look it up in step 2. It is not known now.
  - If semgrep is already installed, the pin is its installed version, so the owner's machine is
    not changed.
  - Otherwise the builder runs `uv tool install semgrep`, and the pin is the version that installs
    (latest).
- **semgrep network and telemetry.** `--metrics=off` is on the command line. `SEMGREP_ENABLE_VERSION_CHECK=0`
  is prefixed to both semgrep invocations: `--version` and the scan. `~/.semgrep/` is left alone
  (owner answer 16).
- **Scan scope.** semgrep runs from the repo root on `.`. It keeps its default git filtering (only
  tracked files and untracked files that are not ignored). `.semgrepignore` adds the owner's five
  explicit exclusions (owner answer 15). Step 6 proves that `.semgrepignore` alone excludes them,
  by running with `--no-git-ignore` and a local rule, offline.
- **bash 3.2.** All recipe code must run on macOS `/bin/bash` 3.2: no arrays, no `mapfile`, no
  `${var,,}`. Strings are appended with `x="${x}..."`. Skip detection uses
  `case "$out" in *skipping*)`, which involves no pipe, so `pipefail` cannot interfere.
- **Rejected alternatives:**
  - A separate `scripts/security.sh`: the repo keeps recipe logic in the justfile, and the scope
    names justfile recipes.
  - Detecting "offline" by grepping tool output for `ENOTFOUND` and similar strings: not
    documented and fragile across versions.
  - Vendoring the semgrep rules: rejected by the owner (answer 4(c)).
  - Adding `security` to `check`: rejected by the owner (answer 2).

## 3. File map

| File | Action | Purpose |
|---|---|---|
| `docs/plans/chore-security-scans-brief.md`, `docs/plans/chore-security-scans-plan.md` | commit only (do not edit) | Pipeline records. |
| `docs/decisions/D22-security-scanning.md` | create | Decision D22, in D21's exact format. |
| `.github/workflows/codacy.yml` | delete | Removes the third-party upload (Codacy resolution: delete). |
| `justfile` | modify (insertions only) | Header lines for D22 and the `security-py` contract, `semgrep_version` variable, and the recipes `security`, `security-py`, `security-web`. |
| `.semgrepignore` | create | Explicit semgrep exclusions: `node_modules/`, `.venv/`, `dist/`, `.claude/worktrees/`, `data/`. |
| `.claude/agents/reviewer.md` | modify | Extends the Bash allow-list sentence to `just security`. Adds item 6 "Security and data handling". |
| `README.md` | modify | semgrep in setup step 1 and in the installed-versions table. |
| `scripts/cloud-setup.sh` | modify | One line: install the pinned semgrep with `uv tool install`. |
| `.github/pull_request_template.md` | modify | One checkbox: `just security` passes (or reason noted). |

No other file may be created, modified or deleted. In particular, `.github/workflows/codeql.yml`,
`scripts/bootstrap-github.sh`, `.pre-commit-config.yaml`, `.gitignore`, `CLAUDE.md`,
`docs/decisions/D21-just-check.md`, `docs/plans/T0.1-*`, `docs/plans/T0.2-*`, everything under
`apps/` and `services/`, and every other `.claude/**` file stay untouched.

## 4. Steps

Run every command from the worktree root
`/Users/allen/Downloads/typist-ml/.claude/worktrees/trusting-lumiere-29c6ca` unless a command
`cd`s itself.

Placeholders, filled in at build time:
- `<SEMGREP_VERSION>`: fixed in step 2, for example `1.139.0`. Digits and dots only.
- `<TODAY>`: today's date as `YYYY-MM-DD`.
- `<ROOT>`: the output of `pwd` at the worktree root.

**Sandbox rule.** These commands need the network or write outside the worktree: steps 2 and 7,
`pnpm install`, `uv tool install` and a real `just security`. If one is sandbox-blocked, look for a
network error, `EPERM`/`EACCES` outside the worktree, or `Operation not permitted`. Then stop and
report the step, the command and the error. Never use `dangerouslyDisableSandbox`. Resume points
are marked.

**Protected paths.** Step 8 edits `.claude/agents/reviewer.md`. If the edit is refused by a
permission prompt or rule, stop and report. Do not work around it.

**Commits.** Use exactly the message given in each step, with `git commit -F - <<'EOF' ... EOF`.
Every message ends with a blank line and the trailer shown. Never use `--no-verify`. The pre-commit
hooks (ruff and biome) match no file in this task and report "Skipped" or "no files to check".

---

### Step 0: Create or switch to the task branch

- Files: none.
- Commands:
  ```bash
  git status --porcelain
  git worktree list
  if git show-ref --verify --quiet refs/heads/chore-security-scans; then
      git switch chore-security-scans
  else
      git switch -c chore-security-scans main
  fi
  git branch --show-current
  git log --oneline main..HEAD
  git rev-parse HEAD main
  ```
- Tests:
  1. Before switching, `git status --porcelain` lists only
     `?? docs/plans/chore-security-scans-brief.md` and `?? docs/plans/chore-security-scans-plan.md`.
     Anything else: stop and report.
  2. If `git worktree list` shows `chore-security-scans` checked out in another worktree, `git switch`
     will fail. Stop and report.
  3. `git branch --show-current` prints exactly `chore-security-scans`.
  4. `git log --oneline main..HEAD` prints nothing. If the branch existed and already has commits,
     stop and report them. Do not reset or rebase.
  5. `git rev-parse HEAD main` prints the same hash twice.
- Verify: tests 1 to 5. The two untracked plan files are still present (`git status --porcelain`).

### Step 1: Commit the pipeline records

- Files: none edited.
- Commands:
  ```bash
  git add docs/plans/chore-security-scans-brief.md docs/plans/chore-security-scans-plan.md
  git commit -F - <<'EOF'
  docs: chore-security-scans brief and plan

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  EOF
  ```
- Verify: `git status --porcelain` prints nothing. `git log -1 --format=%B` ends with the
  `Co-Authored-By` line.

### Step 2: Preflight and semgrep pin (RESUME POINT A)

- Files: none.
- Commands:
  ```bash
  just --version
  curl --version | head -n 1
  pnpm --version
  (cd apps/web && pnpm audit --help) | grep -c -- '--audit-level'
  command -v semgrep && SEMGREP_ENABLE_VERSION_CHECK=0 semgrep --version
  ```
- If `command -v semgrep` prints nothing, install the latest semgrep. This needs the network and
  writes to `~/.local`. If it is sandbox-blocked, stop and report. The owner then runs this line in
  their own terminal, and the builder resumes by re-running the command block above.
  ```bash
  uv tool install semgrep
  SEMGREP_ENABLE_VERSION_CHECK=0 semgrep --version
  ```
- If `apps/web/node_modules/` does not exist, install the web dependencies (network, same resume
  rule):
  ```bash
  (cd apps/web && pnpm install --frozen-lockfile)
  ```
- Baseline gate: `just check` exits 0 and ends with
  `just check: all steps passed (apps not yet scaffolded were skipped)`.
- Tests:
  1. `curl --version` prints a line starting `curl `.
  2. `pnpm --version` prints `12.6.0`. If it prints another version, record it in the final report
     and continue.
  3. The `grep -c -- '--audit-level'` count is at least `1`. If it is `0` or `pnpm audit --help`
     fails, stop and report. The pnpm audit interface differs from what this plan assumes.
  4. `SEMGREP_ENABLE_VERSION_CHECK=0 semgrep --version` prints one line matching
     `^[0-9]+\.[0-9]+\.[0-9]+$`. Record it as `<SEMGREP_VERSION>`. If the output has any other
     form, stop and report it.
  5. `just check` passes (baseline, before any change).
- Verify: tests 1 to 5. Record `<SEMGREP_VERSION>` for steps 3, 5 and 9. Nothing to commit.

### Step 3: Add decision D22

- File: `docs/decisions/D22-security-scanning.md` (create). Content, exactly (fill `<TODAY>`). The
  table row is a single line:

  ```markdown
  # D22: Security scanning stays local

  - Date: <TODAY>
  - Status: accepted
  - Task: chore-security-scans

  ## Context

  The repository ran a Codacy workflow (`.github/workflows/codacy.yml`) that uploaded code analysis
  results to Codacy, a third-party service. That conflicts with D19 and with CLAUDE.md ("Everything
  stays local"), and T0.2 owner answer 20 dropped it. The reviewer (pipeline phase 4) also had no
  single command for a security pass. D01 to D20 are in design doc section 2; D21 is in this
  directory.

  ## Decision

  | ID | Decision | Choice | Why | Revisit if |
  |---|---|---|---|---|
  | D22 | Security scanning | Local static analysis only, through `just security`: semgrep with the public ruleset alias `p/security-audit`, `--metrics=off` and `SEMGREP_ENABLE_VERSION_CHECK=0`, with the semgrep CLI version pinned (justfile `semgrep_version`, README version table); `security-py` for services/api (bandit and pip-audit, added by T0.3; a placeholder until then); `security-web` for apps/web (`pnpm audit --audit-level=high`, dev dependencies included). No third-party upload service: the Codacy workflow is removed. CodeQL stays, because it runs inside GitHub, where the code already lives. Downloading rule definitions and checking package names and versions against public advisory databases is allowed; no code or participant data leaves the machine. Every part runs, then the recipe fails if any part failed. A missing tool, a missing app or an unreachable registry is skipped with a message. Not part of `just check` (D21). | Keeps code and participant data on the machine (D19) while still catching insecure code patterns and vulnerable dependencies before review | a tool changes its default network or telemetry behavior, T0.4 decides CI's role for this, or the Codacy decision changes |

  ## Consequences

  - `just security` is run by hand and by the reviewer (`.claude/agents/reviewer.md` item 6); the
    pull request template asks for it. `just check` and D21 are unchanged.
  - "Unreachable" means a `curl` HEAD probe of the registry host (`https://semgrep.dev/`,
    `https://registry.npmjs.org/`) got no HTTP response. If the probe succeeds and the tool still
    fails, that counts as a failure, not a skip. Without `curl` the tool runs and its exit code
    decides.
  - Only the semgrep CLI is pinned. `p/security-audit` is a registry alias whose rules Semgrep can
    change, so a result can change without a code change.
  - semgrep skips `node_modules/`, `.venv/`, `dist/`, `.claude/worktrees/` and `data/`
    (`.semgrepignore`). `data/` is listed explicitly because it holds participant data, even
    though `.gitignore` already excludes it.
  - T0.3 must add bandit and pip-audit as dev dependencies of services/api (pinned in
    `services/api/uv.lock`), add a local bandit pre-commit hook that runs through `uv run` from
    services/api (the same pattern as the ruff hook, not pre-commit's upstream bandit repository),
    and replace the body of the `security-py` recipe.
  - T0.4 decides whether CI runs `just security` or its parts.
  - Deleting the workflow file does not touch GitHub-side Codacy items (repository secret, app,
    existing code-scanning alerts). Cleaning them up is not part of this decision.
  ```

- Tests:
  1. `grep -c '^| D22 |' docs/decisions/D22-security-scanning.md` prints `1`.
  2. `grep -c '^## ' docs/decisions/D22-security-scanning.md` prints `3`, and
     `grep -n '^## ' docs/decisions/D22-security-scanning.md` lists `Context`, `Decision`,
     `Consequences` in that order.
  3. `grep -c '^- Task: chore-security-scans$' docs/decisions/D22-security-scanning.md` prints `1`.
  4. `grep -c '<TODAY>' docs/decisions/D22-security-scanning.md` prints `0`.
  5. `git status --porcelain` lists only `?? docs/decisions/D22-security-scanning.md`.
- Verify: tests 1 to 5.
- Commit:
  ```bash
  git add docs/decisions/D22-security-scanning.md
  git commit -F - <<'EOF'
  docs: add D22 security scanning decision

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  EOF
  ```

### Step 4: Delete the Codacy workflow

- File: `.github/workflows/codacy.yml` (delete).
- Command: `git rm -q .github/workflows/codacy.yml`
- Tests:
  1. `test ! -e .github/workflows/codacy.yml && echo gone` prints `gone`.
  2. `test -f .github/workflows/codeql.yml && echo kept` prints `kept`.
  3. `git grep -il codacy` lists exactly these files: `docs/decisions/D22-security-scanning.md`,
     `docs/plans/T0.2-brief.md`, `docs/plans/T0.2-plan.md`,
     `docs/plans/chore-security-scans-brief.md` and `docs/plans/chore-security-scans-plan.md`.
     Any other file: stop and report.
  4. `git status --porcelain` lists exactly `D  .github/workflows/codacy.yml`.
- Verify: tests 1 to 4.
- Commit:
  ```bash
  git commit -F - <<'EOF'
  chore: remove Codacy workflow (D22)

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  EOF
  ```

### Step 5: justfile security recipes

File: `justfile`. **Insertions only.** Do not change or delete any existing line. Indent recipe
bodies with 4 spaces, no tabs.

(a) After line 4 (``# `check` is defined by decision D21 (docs/decisions/D21-just-check.md).``),
insert these two lines:
```
# `security` and its parts are defined by decision D22 (docs/decisions/D22-security-scanning.md).
# They also skip a missing tool or an unreachable registry, and they are not part of `check`.
```

(b) After the line
`#   gen-types:           placeholder until the task that adds openapi-typescript replaces it.`,
insert these two lines. The label column is 21 characters wide, like the lines above:
```
#   security-py (T0.3):  placeholder; T0.3 replaces its body with bandit and pip-audit, both added
#                        as dev dependencies in services/api/pyproject.toml (decision D22).
```

(c) Directly after (b), insert one blank line and then these two lines. The existing blank line
before `[private]` stays, so there is exactly one blank line between the new variable and
`[private]`. Fill in `<SEMGREP_VERSION>`:
```
# semgrep CLI version pinned by decision D22. Keep it equal to README.md and scripts/cloud-setup.sh.
semgrep_version := "<SEMGREP_VERSION>"
```

(d) Append at the end of the file, after the `gen-types` recipe, with one blank line before the
first new comment and one blank line between recipes:
```just
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
```

- Tests (run all of them; none needs the network):
  1. Parse and list:
     `just --list` exits 0. `just --list | grep -cE '^[[:space:]]+security(-py|-web)?[[:space:]]+#'`
     prints `3`.
  2. Pin value: `just --evaluate semgrep_version` prints `<SEMGREP_VERSION>` exactly.
  3. Insert-only and `check` unchanged:
     - `git diff main -- justfile | grep -cE '^-[^-]'` prints `0`.
     - `diff <(git show main:justfile | sed -n '/^check:/,/^$/p') <(sed -n '/^check:/,/^$/p' justfile) && echo check-same`
       prints `check-same`.
  4. No tabs: `grep -c "$(printf '\t')" justfile` prints `0`.
  5. `just security-py; echo "exit=$?"` prints
     `security-py not yet implemented (T0.3 replaces it with bandit and pip-audit), skipping` and
     `exit=0`.
  6. Behaviour with fake tools. Run this script exactly:
     ```bash
     bash <<'SCRIPT'
     J="$(command -v just)"
     ROOT="$(pwd)"
     fake="$(mktemp -d)"
     tmpj="$(mktemp -d)"
     cat > "$fake/curl" <<'EOF'
     #!/bin/sh
     case "$*" in
       *semgrep.dev*) exit "${FAKE_CURL_SEMGREP:-0}" ;;
       *) exit "${FAKE_CURL_NPM:-0}" ;;
     esac
     EOF
     cat > "$fake/semgrep" <<'EOF'
     #!/bin/sh
     if [ "$1" = "--version" ]; then echo "${FAKE_SEMGREP_VERSION:-0.0.0}"; exit 0; fi
     echo "fake semgrep: $* (SEMGREP_ENABLE_VERSION_CHECK=${SEMGREP_ENABLE_VERSION_CHECK:-unset}, in $(pwd))"
     exit "${FAKE_SEMGREP_EXIT:-0}"
     EOF
     cat > "$fake/pnpm" <<'EOF'
     #!/bin/sh
     echo "fake pnpm: $* (in $(pwd))"
     exit "${FAKE_PNPM_EXIT:-0}"
     EOF
     chmod +x "$fake/curl" "$fake/semgrep" "$fake/pnpm"
     V="$("$J" --evaluate semgrep_version)"
     run() { name="$1"; shift; echo "=== $name"; env "$@" PATH="$fake:$PATH" "$J" security; echo "exit=$?"; }
     run A FAKE_SEMGREP_VERSION="$V"
     run B FAKE_SEMGREP_VERSION="$V" FAKE_SEMGREP_EXIT=1
     run C FAKE_SEMGREP_VERSION="$V" FAKE_SEMGREP_EXIT=2
     run D FAKE_SEMGREP_VERSION="$V" FAKE_PNPM_EXIT=1
     run E FAKE_SEMGREP_VERSION="$V" FAKE_SEMGREP_EXIT=1 FAKE_PNPM_EXIT=1
     run F FAKE_SEMGREP_VERSION="$V" FAKE_CURL_SEMGREP=7 FAKE_CURL_NPM=56
     run G FAKE_SEMGREP_VERSION=0.0.0
     echo "=== H precondition"; env PATH=/usr/bin:/bin sh -c 'command -v semgrep; command -v pnpm; echo done'
     echo "=== H"; env PATH=/usr/bin:/bin "$J" security; echo "exit=$?"
     cp justfile "$tmpj/justfile"
     echo "=== I"; env FAKE_SEMGREP_VERSION="$V" PATH="$fake:$PATH" "$J" --justfile "$tmpj/justfile" security; echo "exit=$?"
     echo "=== K"; (cd apps/web && env FAKE_SEMGREP_VERSION="$V" PATH="$fake:$PATH" "$J" security); echo "exit=$?"
     echo "=== L"; env FAKE_PNPM_EXIT=1 PATH="$fake:$PATH" "$J" security-web; echo "exit=$?"
     echo "ROOT=$ROOT"
     rm -rf "$fake" "$tmpj"
     SCRIPT
     ```
     Expected, per case. "Summary" means the lines after `just security summary:`. `<ROOT>` is the
     printed `ROOT=` value. A line `error: Recipe ... failed on line N with exit code 1` from `just`
     is expected wherever the exit is 1. Its line number does not matter.
     - **A** (all pass):
       - The output contains
         `fake semgrep: --config=p/security-audit --metrics=off --error --quiet . (SEMGREP_ENABLE_VERSION_CHECK=0, in <ROOT>)`,
         then the security-py skip message, then `fake pnpm: audit --audit-level=high (in <ROOT>/apps/web)`.
       - The summary is exactly `  semgrep: passed`, `  security-py: skipped (see message above)`,
         `  security-web: passed`.
       - Then `just security: no failures (skipped parts are listed above)` and `exit=0`.
       - The output has no line starting `warning:`.
     - **B** (semgrep findings): the `fake pnpm: audit ...` line is still printed, so the other
       parts ran after the failure. Summary: `  semgrep: FAILED (findings, see output above)`,
       `  security-py: skipped (see message above)`, `  security-web: passed`. Then
       `just security: FAILED: semgrep` and `exit=1`.
     - **C** (semgrep error): the summary contains
       `  semgrep: FAILED (semgrep error, exit 2, see output above)`, then
       `just security: FAILED: semgrep` and `exit=1`.
     - **D** (audit fails): the summary contains `  semgrep: passed` and
       `  security-web: FAILED (exit 1, see output above)`. Then `just security: FAILED: security-web`
       and `exit=1`.
     - **E** (both fail): the summary is followed by `just security: FAILED: semgrep security-web`
       and `exit=1`.
     - **F** (registry unreachable):
       - The output contains
         `couldn't reach the registry, skipping semgrep (https://semgrep.dev not reachable)` and
         `couldn't reach the registry, skipping security-web (https://registry.npmjs.org not reachable)`.
       - It has **no** `fake semgrep: --config` line and **no** `fake pnpm:` line.
       - Summary: `  semgrep: skipped (registry unreachable)`,
         `  security-py: skipped (see message above)`, `  security-web: skipped (see message above)`.
       - Then `exit=0`.
     - **G** (version mismatch): the output contains
       `warning: semgrep 0.0.0 is installed but D22 pins <SEMGREP_VERSION>; results may differ`,
       the scan still runs (a `fake semgrep: --config` line is present), and `exit=0`.
     - **H precondition**: prints only `done`. If it prints a path for semgrep or pnpm, case H
       cannot be tested this way. Record that and skip H.
     - **H** (tools missing):
       - The output contains
         `semgrep not found, skipping semgrep (run: uv tool install semgrep==<SEMGREP_VERSION>)` and
         `pnpm not found, run corepack enable (skipping security-web)`.
       - Summary: `  semgrep: skipped (not installed)`, `  security-py: skipped (see message above)`,
         `  security-web: skipped (see message above)`.
       - Then `exit=0`.
     - **I** (apps/web missing; the justfile is copied to a temp directory):
       - The `fake semgrep: --config` line shows `in ` followed by a temporary directory, not `<ROOT>`.
       - The output contains `apps/web not yet scaffolded, skipping security-web`, and there is no
         `fake pnpm:` line.
       - Then `exit=0`.
     - **K** (run from `apps/web`): the `fake semgrep: --config` line ends `in <ROOT>)`, and the
       `fake pnpm:` line ends `in <ROOT>/apps/web)`. Then `exit=0`.
     - **L** (sub-recipe alone): prints `fake pnpm: audit --audit-level=high (in <ROOT>/apps/web)`
       and `exit=1`.
  7. `git status --porcelain` lists exactly ` M justfile`. The fake-tool script left nothing in
     the worktree.
- Verify: tests 1 to 7 all pass. If any expected line differs, fix the typing of the recipe to match
  this plan. If the plan's code itself is wrong, stop and report. Do not redesign.
- Commit:
  ```bash
  git add justfile
  git commit -F - <<'EOF'
  chore: add just security, security-py and security-web recipes (D22)

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  EOF
  ```

### Step 6: .semgrepignore and proof that it excludes the right paths (offline)

- File: `.semgrepignore` (create, repo root). Content, exactly:
  ```
  # Paths semgrep never scans (decision D22). When this file exists, semgrep does not apply its
  # built-in ignore list, so every directory to skip is listed here. data/ holds participant data
  # and is listed explicitly even though .gitignore already excludes it.
  node_modules/
  .venv/
  dist/
  .claude/worktrees/
  data/
  ```
- Tests. This check uses real semgrep with a local rule, so no registry and no network. It uses
  `--no-git-ignore`, so git's ignore rules are off and only `.semgrepignore` decides.
  1. Precondition: `test ! -e .claude/worktrees && test ! -e zz-probe && echo clean` prints
     `clean`. If it does not, stop and report. Never create or delete anything in an existing
     `.claude/worktrees`.
  2. Run exactly:
     ```bash
     bash <<'SCRIPT'
     set -u
     rules="$(mktemp -d)"
     cat > "$rules/probe.yaml" <<'EOF'
     rules:
       - id: zz-probe
         pattern: zz_probe_marker()
         message: probe
         languages: [python]
         severity: WARNING
     EOF
     for d in zz-probe/ok zz-probe/node_modules zz-probe/.venv zz-probe/dist zz-probe/data .claude/worktrees/zz-probe; do
         mkdir -p "$d"
         printf 'zz_probe_marker()\n' > "$d/probe.py"
     done
     SEMGREP_ENABLE_VERSION_CHECK=0 semgrep --config "$rules/probe.yaml" --metrics=off --no-git-ignore --json --quiet . > "$rules/out.json"
     echo "semgrep-exit=$?"
     grep -o '"path": *"[^"]*probe\.py"' "$rules/out.json"
     rm -r zz-probe .claude/worktrees/zz-probe
     rmdir .claude/worktrees
     rm -r "$rules"
     SCRIPT
     ```
     Expected:
     - `semgrep-exit=0`.
     - The `grep` prints exactly one line, ending in `zz-probe/ok/probe.py"`. Nothing is printed
       for `node_modules`, `.venv`, `dist`, `data` or `.claude/worktrees`.
     - If semgrep rejects `--no-git-ignore` or exits non-zero, stop and report the full output.
     - If more than one line is printed, stop and report. `.semgrepignore` is not working as
       designed. Do not change its patterns on your own.
  3. `test ! -e zz-probe && test ! -e .claude/worktrees && echo cleaned` prints `cleaned`.
  4. `git status --porcelain` lists exactly `?? .semgrepignore`.
- Verify: tests 1 to 4.
- Commit:
  ```bash
  git add .semgrepignore
  git commit -F - <<'EOF'
  chore: add .semgrepignore for just security (D22)

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  EOF
  ```

### Step 7: Real `just security` run (network; RESUME POINT B; no commit)

- Files: none. **Do not change any file because of this run's results.** Do not add `nosemgrep`
  comments, `.semgrepignore` entries, `pnpm audit` ignores or overrides.
- Command: `just security; echo "exit=$?"`
- Acceptable outcomes. Record the full summary block and the exit in the final report:
  - `exit=0` with `semgrep: passed` or skipped, and `security-web: passed` or skipped. Every skip
    line must be one of the messages defined in step 5.
  - `exit=1` with findings or advisories. List each semgrep finding (rule id, file and line) and
    each advisory (package, severity) in the final report for the owner. The PR will note the
    reason, as the PR template allows.
  - `semgrep: FAILED (semgrep error, exit N ...)`, for example because `~/.semgrep` is not writable
    under the sandbox. Report the error output. Do not bypass the sandbox. The owner may run
    `just security` in their own terminal and paste the result. That output then replaces this
    step's record.
- Verify: `git status --porcelain` prints nothing, and semgrep wrote nothing into the worktree.

### Step 8: Reviewer security pass

- File: `.claude/agents/reviewer.md`. Replace the whole file with exactly this content. Compared
  with the current file, only two things change: the allow-list sentence and the added item 6.
  ```markdown
  ---
  name: reviewer
  description: Phase 4. Reviews a built task against its brief and plan before a PR is opened. Read-only; runs checks and reports a verdict with findings, never edits code.
  tools: Read, Grep, Glob, Bash
  model: opus
  ---

  You are the reviewer for Typist-ML. You decide whether a change is correct and
  safe to merge. Never edit files. Use Bash only for read-only commands: git diff,
  git log, git status, the lint, type and test commands, and `just security` (it
  makes read-only network calls: it downloads scan rules and checks package
  versions against public advisories, and never modifies the repo, so running it
  does not conflict with never editing files).

  Read CLAUDE.md, docs/plans/<task>-brief.md, docs/plans/<task>-plan.md, and
  `git diff main...HEAD`.

  Check, in this order:
  1. Plan fidelity: every step done, nothing extra, interfaces match the plan.
  2. Correctness: each acceptance criterion is met and proven by a test.
  3. Experiment safety: frozen config untouched; attribution follows design doc
     section 12; timing uses event.timeStamp; keystroke rows append-only; every
     drill arm goes through the shared validator; golden fixture unchanged.
  4. Tests: behaviour and edge cases from the brief are covered, not only the
     happy path.
  5. Quality: naming, function size, types (no `any`, no untyped Python), dead
     code, new dependencies.
  6. Security and data handling: Run `just security` if it exists (falls back
     cleanly if the tools or apps behind it aren't set up yet). Also check by
     hand: no secrets or API keys committed; no participant data (aliases aside)
     written anywhere outside data/; no new network call added anywhere (this
     project makes none, per D19); SQL is parameterised, never string-built from
     user/participant input. A clean tool run doesn't excuse skipping the manual
     checks — the tools don't know this project's specific privacy rules.

  Run the checks yourself and include the result.

  Return the verdict APPROVE or CHANGES NEEDED, then findings. Mark each finding
  BLOCKING or MINOR, with file and line and one sentence on the fix. No praise.
  ```
  The dash in "manual checks — the tools" is an em dash (U+2014), copied from the owner's text.
- Tests:
  1. Item 6 matches the owner's text, minus the "Pass 5 — " prefix (owner answer 1):
     ```bash
     awk '/^6\. /,/privacy rules\.$/' .claude/agents/reviewer.md | tr '\n' ' ' | sed -E 's/ +/ /g; s/ $//'
     ```
     prints exactly:
     `6. Security and data handling: Run `just security` if it exists (falls back cleanly if the tools or apps behind it aren't set up yet). Also check by hand: no secrets or API keys committed; no participant data (aliases aside) written anywhere outside data/; no new network call added anywhere (this project makes none, per D19); SQL is parameterised, never string-built from user/participant input. A clean tool run doesn't excuse skipping the manual checks — the tools don't know this project's specific privacy rules.`
  2. `grep -c 'Pass 5' .claude/agents/reviewer.md` prints `0`.
     `grep -cE '^[1-6]\. ' .claude/agents/reviewer.md` prints `6`.
  3. `git diff -U0 .claude/agents/reviewer.md` shows exactly two hunks:
     - one replaces the line `git log, git status, and the lint, type and test commands.` with
       the four new allow-list lines;
     - one adds the seven item-6 lines after `   code, new dependencies.`
     No other line changes.
  4. `git status --porcelain` lists exactly ` M .claude/agents/reviewer.md`.
- Verify: tests 1 to 4.
- Commit:
  ```bash
  git add .claude/agents/reviewer.md
  git commit -F - <<'EOF'
  docs: add security and data handling check to the reviewer (D22)

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  EOF
  ```

### Step 9: README, cloud-setup.sh, PR template

**`README.md`**, two edits. Change nothing else.

(a) Replace setup step 1 (the current three lines starting `1. Install the tools:`) with these five
lines:
```markdown
1. Install the tools: [uv](https://docs.astral.sh/uv/), Node 22 (exact version in `.nvmrc`),
   pnpm (`npm install -g pnpm@12.6.0`, the version pinned in `apps/web/package.json`),
   then `uv tool install rust-just`, `uv tool install pre-commit`,
   `uv tool install semgrep==<SEMGREP_VERSION>` (for `just security`, see
   [D22](docs/decisions/D22-security-scanning.md)) and `uv python install 3.12`.
```

(b) In the table under `### Installed versions (milestone 0, recorded 2026-09-25)`, insert this row
directly after the `| pre-commit | ... |` row:
```markdown
| semgrep | `semgrep --version` | <SEMGREP_VERSION> |
```

**`scripts/cloud-setup.sh`**: insert this line directly after the
`command -v pre-commit >/dev/null 2>&1 || uv tool install pre-commit` line:
```bash
command -v semgrep >/dev/null 2>&1 || uv tool install semgrep==<SEMGREP_VERSION>
```

**`.github/pull_request_template.md`**: insert this line directly after
``- [ ] `just check` passes locally``:
```markdown
- [ ] `just security` passes (or reason noted if not)
```

- Tests:
  1. `V="$(just --evaluate semgrep_version)"; grep -c "semgrep==$V" README.md scripts/cloud-setup.sh`
     prints `README.md:1` and `scripts/cloud-setup.sh:1`.
  2. `grep -cE "^\| semgrep \| \`semgrep --version\` \| $(just --evaluate semgrep_version) \|$" README.md`
     prints `1`.
  3. `bash -n scripts/cloud-setup.sh && echo syntax-ok` prints `syntax-ok`.
     `git diff --numstat scripts/cloud-setup.sh` prints `1	0	scripts/cloud-setup.sh`.
  4. `git diff --numstat .github/pull_request_template.md` prints
     `1	0	.github/pull_request_template.md`.
     `grep -c 'just security' .github/pull_request_template.md` prints `1`.
  5. `git diff --numstat README.md` prints `4	1	README.md`: the last line of step 1 is replaced
     by three lines, and one table row is added. The first two lines of step 1 are unchanged.
  6. `grep -c '<SEMGREP_VERSION>\|<TODAY>' README.md scripts/cloud-setup.sh justfile docs/decisions/D22-security-scanning.md`
     prints `0` for each file.
- Verify: tests 1 to 6.
- Commit:
  ```bash
  git add README.md scripts/cloud-setup.sh .github/pull_request_template.md
  git commit -F - <<'EOF'
  docs: add semgrep to setup and cloud setup, add just security to the PR template

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  EOF
  ```

### Step 10: Final gate

- Files: none.
- Commands, in order:
  ```bash
  just check
  pre-commit run --all-files
  just security-py
  git status --porcelain
  git diff --name-status main...HEAD
  git log --format='%B' main..HEAD | grep -c '^Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>$'
  ```
- Expected:
  - `just check` exits 0 and ends with
    `just check: all steps passed (apps not yet scaffolded were skipped)`.
  - `pre-commit run --all-files` exits 0 and changes no file.
  - `just security-py` exits 0 and prints the placeholder message.
  - `git status --porcelain` prints nothing.
  - `git diff --name-status main...HEAD` lists exactly these 10 entries:
    `M .claude/agents/reviewer.md`, `M .github/pull_request_template.md`,
    `D .github/workflows/codacy.yml`, `A .semgrepignore`, `M README.md`,
    `A docs/decisions/D22-security-scanning.md`, `A docs/plans/chore-security-scans-brief.md`,
    `A docs/plans/chore-security-scans-plan.md`, `M justfile`, `M scripts/cloud-setup.sh`.
    If any other path appears or one is missing, stop and report.
  - The trailer count is `7`, one for each of the commits in steps 1, 3, 4, 5, 6, 8 and 9.
- Do not push and do not open the PR. Shipping is phase 5. Include in the final report: the
  `<SEMGREP_VERSION>` and where it came from (already installed, or installed in step 2), the step 7
  record, and whether case H ran.

## 5. Dependencies

None added to any project manifest (`apps/web/package.json`, lockfiles, and no `services/api`). No
bandit, no pip-audit. semgrep is a developer tool installed with `uv tool install`, like `just` and
`pre-commit`. Its version `<SEMGREP_VERSION>` (fixed in step 2) is pinned in the justfile
(`semgrep_version`), the README and `scripts/cloud-setup.sh`. `curl` is used when present and is
optional.

## 6. Acceptance check

| Criterion (brief section 1 and owner answers) | Proven by |
|---|---|
| Codacy workflow deleted; CodeQL kept (scope 1, Codacy resolution) | Step 4 tests 1 to 3; step 10 name-status |
| Three recipes exist with descriptions (scope 2) | Step 5 test 1 |
| `security-web` runs `pnpm audit --audit-level=high` in apps/web, no `--prod` (scope 2, answer 7) | Step 5 test 6 case A (`fake pnpm: audit --audit-level=high (in <ROOT>/apps/web)`) |
| `security-py` is an unconditional placeholder (scope 2, answer 12) | Step 5 test 5 |
| `security` runs the exact semgrep command with `SEMGREP_ENABLE_VERSION_CHECK=0` (scope 2, answer 16) | Step 5 test 6 case A |
| Missing semgrep skips with "run: uv tool install semgrep"; the other parts still run (scope 2, answer 6) | Step 5 test 6 case H |
| All parts run, non-zero exit at the end, with a summary (answer 6) | Step 5 test 6 cases B, C, D, E |
| Unreachable registry skips with "couldn't reach the registry, skipping" (answer 8) | Step 5 test 6 case F |
| Missing pnpm skips with "pnpm not found, run corepack enable" (answer 14) | Step 5 test 6 case H |
| Missing apps/web skips | Step 5 test 6 case I |
| Location-independent run | Step 5 test 6 case K |
| `check` and D21 unchanged (answer 2) | Step 5 test 3; step 10 (D21 not in the diff) |
| semgrep CLI version pinned and recorded in the README (answer 4) | Step 2 test 4; step 5 tests 2 and 6 G; step 9 tests 1 and 2 |
| `.semgrepignore` excludes the five paths, `data/` explicitly (answer 15) | Step 6 test 2 |
| D22 in D21's format, with the owner's Task and Revisit-if (scope 3, answer 9) | Step 3 tests 1 to 3 |
| Reviewer item 6 text; allow-list includes `just security` (scope 4, answers 1 and 17) | Step 8 tests 1 to 3 |
| README and cloud-setup mention the pinned semgrep (answer 10) | Step 9 tests 1 to 3 |
| PR template checkbox (answer 18) | Step 9 test 4 |
| Header contract names bandit and pip-audit for T0.3 (answer 13) | Step 5 change (b); step 5 test 3 (insert only) |
| No bandit or pip-audit dependency added (scope 5) | Step 10 name-status (no manifest or lockfile changes) |
| Branch `chore-security-scans` off `main` (answer 19) | Step 0 tests 3 to 5 |

## 7. Out of scope

- Do not edit `.github/workflows/codeql.yml` (the matrix belongs to T0.4) or
  `scripts/bootstrap-github.sh`. Do not create `.github/workflows/ci.yml`.
- Do not add `security` to `check`, and do not edit D21 or any existing justfile line.
- Do not add bandit, pip-audit or anything under `services/`. Do not add a bandit pre-commit hook.
  Do not edit `.pre-commit-config.yaml`.
- Do not vendor semgrep rules. Do not use `--config auto` (it requires metrics). Do not add
  `nosemgrep` comments, audit ignores, pnpm overrides or dependency upgrades, whatever step 7
  reports.
- Do not touch GitHub settings (Codacy secret, app, alerts) or CodeQL.
- Do not edit CLAUDE.md, `.gitignore`, the T0.1 or T0.2 plan records, `docs/decisions/D21-just-check.md`
  or any `.claude/**` file other than `reviewer.md`. Do not add a mention of `just security` to
  README step 4.
- Do not upgrade or downgrade an already installed semgrep. Do not change the pnpm store or the
  `~/.semgrep` location. Never disable the sandbox.
- The "Note for T0.4" already sits in the brief. D22's Consequences repeats it so that T0.4's
  analyst finds it among the decisions. No other action.
- Do not push or open the PR.

## 8. Risks

1. **`just security` red on day one.** Current web dependencies may have high or critical
   advisories. `p/security-audit` may also flag existing files such as `scripts/*.sh` or
   `codeql.yml`. Step 7 records this instead of hiding it, and the PR notes the reason. Fixing
   findings is a separate task for the owner.
2. **The probe and the tool disagree.** The HEAD probe can succeed while semgrep's rule download or
   pnpm's audit request fails (proxy rules per path, retired npm audit endpoint, pnpm version
   switch download). The result is then reported as FAILED with the tool's output, not as skipped.
   The failure is visible, not silent.
3. **Sandbox effects.** semgrep may be unable to write `~/.semgrep` under the sandbox. That shows
   as "semgrep error". The owner's own terminal gives the real result.
4. **Unstable ruleset.** Only the CLI is pinned. Rules behind `p/security-audit` can change between
   runs (D22 Consequences).
5. **Custom npm registry.** The npm probe checks `registry.npmjs.org` only. A machine configured
   with another registry could be probed wrongly. There is none today.
6. **Skip detection by keyword.** A sub-recipe that exits 0 and prints "skipping" for another
   reason would be labelled skipped instead of passed. It never shows a failure as a pass. The
   contract is written in the recipe comment, and T0.3 must keep it when it replaces `security-py`.
7. **corepack vs npm.** The owner's pnpm-missing message says "run corepack enable", while the
   README and cloud-setup install pnpm with npm. Both work with Node 22. The message is kept
   verbatim.

## 9. Review focus

1. **`security` control flow (step 5 (d)).** Check the `set -e` interplay:
   - `if cmd; then rc=0; else rc=$?; fi` keeps the real exit code, and a failing part never aborts
     the loop.
   - The `case` maps semgrep 0 to passed, 1 to findings, and anything else to error.
   - The `failed` string produces `FAILED: semgrep security-web`.
   - The code is bash 3.2 compatible.
   - The step 5 test 6 transcript shows cases A to L.
2. **"Unreachable" detection.** Check that the curl probe has no `--fail`, so any HTTP response
   counts as reachable. Check that only a probe failure leads to a skip, and that a tool failure
   after a good probe is reported as FAILED. Check that the skip messages match owner answers 8
   and 14.
3. **semgrep privacy flags and pin.** Check `--metrics=off` on the scan and
   `SEMGREP_ENABLE_VERSION_CHECK=0` on **both** semgrep invocations. Check that `.` is scanned from
   the repo root (case K), that the pinned version is the same in the justfile, README and
   cloud-setup, and that a version mismatch is a warning, not a failure.
4. **`.semgrepignore` semantics.** Check that it replaces semgrep's built-in list and that step 6
   (with `--no-git-ignore`) proves each of the five exclusions, `data/` in particular. Check that
   the probe files were cleaned up.
5. **Wording fidelity.**
   - `reviewer.md` item 6: the owner's text word for word after "Security and data handling:",
     with the em dash, items 1 to 5 unchanged, and the allow-list sentence extended in one
     sentence.
   - D22 records Codacy as removed and CodeQL as kept, and D21 is unchanged.
   - Flag for the owner: item 6 uses the file's `N. Title:` colon style rather than the literal
     "6. Security and data handling." with a period. Also, item 6's "no new network call added
     anywhere" is about project code (D19), not the scan tools, as D22 explains.
