# chore-security-scans brief: local security scans, drop Codacy

Analyst: phase 1 (Understand). This brief records facts only. It does not design a solution.
Sources: CLAUDE.md; the scope the owner agreed with the orchestrator (passed on in the task
message); `justfile`; `.github/workflows/codacy.yml` and `codeql.yml`; `.claude/agents/reviewer.md`
(worktree and main checkout, identical); `.claude/agents/analyst.md`; `.claude/commands/review.md`;
`docs/decisions/D21-just-check.md`; `README.md`; `.pre-commit-config.yaml`;
`scripts/pre-commit-ruff.sh`; `scripts/cloud-setup.sh`; `scripts/bootstrap-github.sh`;
`.gitignore`; `.git/info/exclude` (main checkout); `apps/web/package.json`, `biome.json`,
`pnpm-lock.yaml`, `vite.config.ts`; `.github/pull_request_template.md`; `docs/plans/T0.1-brief.md`,
`T0.2-brief.md` (with owner answers), `T0.2-plan.md`.

Limits of this analysis:
- This is a chore, not a section-16 task. There are no design-doc acceptance criteria.
- The design doc PDF could not be rendered in this session (no `pdftoppm`). Section 2 wording
  (D19, the decision-log rule) and section 17.3 are quoted from the T0.1 and T0.2 briefs, which
  read a text extraction of the doc.
- No shell was available. Nothing was installed or run. Whether `semgrep` is installed, whether
  `pnpm audit` currently reports advisories, and what the sandbox allows over the network were not
  checked. Statements about third-party tool behaviour marked "(verify)" come from general
  knowledge, not from the installed versions.
- Worktree branch at the time of writing: `claude/chore-security-scans-e831f8` (HEAD `d83e28a`,
  "Merge pull request #2 ... t0-2-web-scaffold"). The agreed branch name is
  `chore-security-scans`, off `main`.

---

## 1. Task

- **ID:** `chore-security-scans` (not from design doc section 16)
- **Title:** none given in the design doc. Working description: remove the Codacy workflow, add
  local security-scan recipes to the justfile, record decision D22, update the reviewer's security
  pass.
- **Acceptance criteria:** the design doc has none for this chore. The agreed scope, as passed on
  by the orchestrator (word for word where it was quoted):
  1. Delete the Codacy GitHub Actions workflow file under `.github/workflows/`. Its exact path is
     `.github/workflows/codacy.yml` (the only file in the repo that mentions Codacy outside
     `docs/plans/`).
  2. Add three justfile recipes: `security`, `security-py`, `security-web`.
     - `security-web` runs `pnpm audit` inside `apps/web`.
     - `security-py` is a placeholder: `services/api` does not exist yet (T0.3 is not built). It
       must skip cleanly with a message, same pattern as other recipes that skip when their app is
       missing.
     - `security` runs `semgrep --config=p/security-audit --metrics=off --error --quiet .` then
       calls `security-py` and `security-web`. It must skip semgrep cleanly with a message
       ("run: uv tool install semgrep") if semgrep is not installed, not hard-fail.
  3. Add a new decision-log row D22 documenting: local static analysis only (bandit, pip-audit,
     pnpm audit, semgrep with `--metrics=off` and a pinned public ruleset, no third-party upload
     services); CodeQL is kept since it runs inside GitHub, where the code already lives.
  4. Update `.claude/agents/reviewer.md`'s Pass 5 paragraph to exactly (owner's text, verbatim):

     > "Pass 5 — Security and data handling. Run `just security` if it exists (falls back cleanly
     > if the tools or apps behind it aren't set up yet). Also check by hand: no secrets or API
     > keys committed; no participant data (aliases aside) written anywhere outside data/; no new
     > network call added anywhere (this project makes none, per D19); SQL is parameterised, never
     > string-built from user/participant input. A clean tool run doesn't excuse skipping the
     > manual checks — the tools don't know this project's specific privacy rules."

     (See section 4: the current `reviewer.md` has no "Pass 5" paragraph; see Open question 1.)
  5. Do NOT add bandit or pip-audit anywhere now. Record the T0.3 requirements (section 10 below).

---

## 2. Why it matters

What this chore enables later:
- Gives the reviewer (phase 4) one command, `just security`, for the security pass on every later
  task, starting with T0.3 (first Python code) and T1.x (telemetry, participant data, SQL).
- Removes the one piece of the repo that sends code or analysis results to a third-party service,
  closing T0.2 owner answer 20 ("drop Codacy: uploading code/results to a third-party service
  conflicts with CLAUDE.md's 'everything stays local, no analytics' rule"). T0.2's orchestrator
  reading deferred the removal: "removing `.github/workflows/codacy.yml` is **not** part of T0.2;
  it belongs to T0.4 or a separate change." This chore is that separate change.
- Records a decision (D22) that T0.3 and T0.4 must follow when they add Python security tools and
  CI.
- Sets requirements for T0.3 (bandit, pip-audit, a local bandit hook) before T0.3 is analysed.

What breaks if it is wrong:
- If a `security*` recipe hard-fails when a tool or app is missing, the reviewer's first step fails
  on every machine without semgrep, and on every branch before T0.3. The owner's Pass 5 text
  promises it "falls back cleanly if the tools or apps behind it aren't set up yet".
- If semgrep runs without `--metrics=off`, it sends usage metrics to Semgrep when rules come from
  the registry (verify: semgrep's default metrics setting "auto" sends metrics when registry rules
  are used). That would break CLAUDE.md's "Do not ... Add ... telemetry services, or analytics".
- If semgrep scans `node_modules/`, `.venv/`, `data/` or nested worktrees, runs are slow, findings
  are noise from third-party code, and `--error` fails on code the project does not own. If it
  reads `data/`, participant data is processed by a third-party tool (locally, but see Edge case 6).
- If the D22 wording or location breaks the section 2 / 17.3 decision-log rules, the decision log
  becomes inconsistent.
- If the reviewer.md edit lands in the wrong place (replacing "Quality" instead of adding a pass),
  the reviewer stops checking naming, types and new dependencies.
- If the T0.3 requirements are not visible to T0.3's analyst, T0.3 ships without bandit and
  pip-audit and `security-py` stays a placeholder indefinitely.

---

## 3. Governing decisions

| ID | Decision | What it forces here |
|---|---|---|
| D19 | "No cloud, no WASM" (section 2, as quoted in T0.1/T0.2 briefs). T0.1 brief: "No recipes or hooks that call cloud services or analytics." | No scan may upload code or results to a third-party service. The reason Codacy goes. semgrep must run with `--metrics=off`. `pnpm audit` and semgrep's registry fetch are outbound network calls made by dev tooling (see Open questions 4 and 5). The owner's Pass 5 text cites D19: "no new network call added anywhere (this project makes none, per D19)". |
| D21 | `just check` runs `lint`, `format-check`, `types`, `test`, `build` for both apps; "A recipe skips an app that is not scaffolded yet (prints a message, exits 0)." Revisit if: "CI (T0.4) needs a check that `just check` does not cover". | The new recipes follow the same skip convention. The agreed scope does not add `security` to `check`; doing so would change what D21 runs (Open question 2). |
| D07 | Frontend: "Vite 8, React 19, TypeScript (strict), pnpm, Biome, Vitest" | The web audit goes through pnpm (`pnpm audit`), not npm or yarn. |
| D08 | Backend: "Python 3.12, uv, FastAPI, SQLModel, Alembic, SQLite in WAL mode, Typer CLI, ruff, pyright, pytest" | Python tools (bandit, pip-audit, semgrep install) go through uv. T0.3's bandit hook runs through `uv run`. |
| D06 | Local-only on the MacBook Pro | Scans run locally. |
| D22 (new) | To be added by this chore, per the scope in section 1. | Next free number: D01 to D20 are in design doc section 2; D21 is `docs/decisions/D21-just-check.md`. |

Other rules that apply:
- Section 2: "Changing a decision means adding a row with the new choice and the date, not editing
  the old row." Section 17.3: "Any change to a decision gets a short ADR in docs/decisions/."
- CLAUDE.md "Do not": "Add cloud AI APIs, telemetry services, or analytics."
- CLAUDE.md: "Never commit anything under `data/` (database, corpus artifacts)."
- CLAUDE.md: "Conventional commits: `feat:`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:`."
  "One task per PR." "Run `just check` ... before pushing." "Never push to `main`."
- CLAUDE.md: "Copy code from Monkeytype or any GPL project" is forbidden (relevant only if semgrep
  rules are vendored into the repo; see Edge case 11).
- T0.2 owner answer 20: "Leave CodeQL's language matrix update to T0.4 (the actual CI task)".

Decisions D01 to D05 and D09 to D18, D20 do not constrain this chore.

---

## 4. Current state

### `.github/workflows/codacy.yml` (to be deleted)
- Path: `.github/workflows/codacy.yml`. Workflow `name: Codacy Security Scan`, job
  `codacy-security-scan` (display name "Codacy Security Scan").
- Triggers: `push` and `pull_request` to `main`; `schedule: - cron: '37 20 * * 3'`.
- Steps: `actions/checkout@v4`; `codacy/codacy-analysis-cli-action@d840f886c4bd4edc059706d09c6a1586111c540b`
  with `project-token: ${{ secrets.CODACY_PROJECT_TOKEN }}`, `format: sarif`,
  `max-allowed-issues: 2147483647` (never fails on findings); then
  `github/codeql-action/upload-sarif@v3` with `sarif_file: results.sarif`.
- Permissions: `contents: read`, `security-events: write`, `actions: read`.
- References to Codacy elsewhere: only in `docs/plans/T0.2-brief.md` and `docs/plans/T0.2-plan.md`
  (historical records). None in README, CLAUDE.md, `.pre-commit-config.yaml`,
  `scripts/cloud-setup.sh`, `scripts/bootstrap-github.sh`, the PR template, or any agent/command
  file.
- `scripts/bootstrap-github.sh` ruleset requires only the checks `web` and `api`
  (`"required_status_checks": [ { "context": "web" }, { "context": "api" } ]`). Codacy is not a
  required check.
- Outside the repo (not visible from files): the `CODACY_PROJECT_TOKEN` repository secret, any
  Codacy GitHub App installation, and SARIF alerts Codacy already uploaded to GitHub code scanning.

### `.github/workflows/codeql.yml` (kept, not edited by this chore)
- `name: "CodeQL Advanced"`; triggers `push`/`pull_request` to `main`, `schedule: - cron: '20 3 * * 3'`.
- Matrix has one entry only:
  ```yaml
        include:
        - language: actions
          build-mode: none
  ```
  It does not analyse `javascript-typescript` or `python`. Uses `actions/checkout@v7`,
  `github/codeql-action/init@v4`, `github/codeql-action/analyze@v4`.
- No `.github/workflows/ci.yml` exists (T0.4).

### `justfile` (verbatim, relevant parts)
Header:
```
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
```

The existing skip patterns (there are three):

(a) Per-app if/else inside a multi-app recipe, used by `lint`, `format-check`, `types`, `test`
(and `build` for web only). Example, `lint`, verbatim:
```
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
```

(b) Early exit when the app (or a sub-part) is missing, used by `migrate` and `worker`. `migrate`,
verbatim:
```
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
```

(c) Unconditional placeholder, used by `gen-types`, verbatim:
```
# Generate apps/web/src/api/schema.d.ts from the API's OpenAPI schema (not ready yet).
gen-types:
    @echo "gen-types not yet implemented (needs services/api and apps/web), skipping"
```

Marker files: `apps/web/package.json` for the web app, `services/api/pyproject.toml` for the API.
Message form: `"<app> not yet scaffolded, skipping <recipe>"`.

Other facts:
- `check: lint format-check types test build` then
  `@echo "just check: all steps passed (apps not yet scaffolded were skipped)"`. No security step.
- `dev` and `worker` exit 0 with a message on non-Darwin (`if [ "$(uname -s)" != "Darwin" ]`).
- Every recipe has a one-line comment above it, which `just --list` shows as its description.
- No recipe currently checks whether a tool (as opposed to an app) is installed. The only
  tool-presence idiom in the repo is in `scripts/cloud-setup.sh`:
  `command -v uv   >/dev/null 2>&1 || pip install --quiet uv`.
- Recipe dependencies are expressed as `check: lint format-check ...`; no recipe calls another
  recipe from inside its body.

### `.claude/agents/reviewer.md` (verbatim body; frontmatter `tools: Read, Grep, Glob, Bash`, `model: opus`)
```
You are the reviewer for Typist-ML. You decide whether a change is correct and
safe to merge. Never edit files. Use Bash only for read-only commands: git diff,
git log, git status, and the lint, type and test commands.

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

Run the checks yourself and include the result.

Return the verdict APPROVE or CHANGES NEEDED, then findings. Mark each finding
BLOCKING or MINOR, with file and line and one sentence on the fix. No praise.
```
Facts that matter:
- There is **no "Pass 5" paragraph and no security pass**. Item 5 is "Quality". The word "Pass"
  appears nowhere in the file. The main checkout's `reviewer.md` is identical.
- The checks are a numbered list, not paragraphs.
- The Bash allow-list sentence ("the lint, type and test commands") does not name `just security`,
  semgrep or `pnpm audit`.

### Decision log
- D01 to D20: design doc section 2 (a PDF; not editable in the repo).
- D21: `docs/decisions/D21-just-check.md`. Format (verbatim headings and table header):
  ```
  # D21: What `just check` runs

  - Date: 2026-09-25
  - Status: accepted
  - Task: T0.1

  ## Context
  ...
  ## Decision

  | ID | Decision | Choice | Why | Revisit if |
  |---|---|---|---|---|
  | D21 | `just check` | ... | ... | ... |

  ## Consequences
  ...
  ```
  D21 was later amended in place with a dated "Amended 2026-09-25 by T0.2 ..." bullet under
  Consequences (T0.2 owner answer 8).
- `docs/decisions/` holds `.gitkeep` and `D21-just-check.md` only. There is no index file listing
  decisions. README links D21 from setup step 4.

### README (relevant, verbatim)
- Setup step 1: "Install the tools: [uv](...), Node 22 (exact version in `.nvmrc`), pnpm
  (`npm install -g pnpm@12.6.0`, ...), then `uv tool install rust-just`, `uv tool install
  pre-commit` and `uv python install 3.12`."
- Step 4: "Run `just` to list the recipes. Run `just check` before pushing (see
  [D21](docs/decisions/D21-just-check.md))."
- Tool version table lists just, pre-commit, uv, pnpm, Node, Python. No semgrep. No mention of
  Codacy, CodeQL or security scanning.

### `scripts/cloud-setup.sh` (verbatim, tool lines)
```bash
command -v uv   >/dev/null 2>&1 || pip install --quiet uv
command -v just >/dev/null 2>&1 || uv tool install rust-just
command -v pre-commit >/dev/null 2>&1 || uv tool install pre-commit
command -v pnpm >/dev/null 2>&1 || npm install -g pnpm@12.6.0
```
Does not install semgrep.

### `.pre-commit-config.yaml` (verbatim)
```yaml
# Local hooks only: each tool runs at the version pinned in the app's lockfile
# (services/api/uv.lock, apps/web/pnpm-lock.yaml). Hooks auto-fix; a commit that a hook
# changed fails once, then passes after `git add`. pyright and tests run in `just check` and CI.
# The golden fixture is the source of truth for errors and is never touched by a tool.
exclude: ^services/api/tests/fixtures/golden_session\.json$
repos:
  - repo: local
    hooks:
      - id: ruff
        name: ruff (services/api)
        entry: bash scripts/pre-commit-ruff.sh
        language: system
        files: ^services/api/.*\.pyi?$
      - id: biome
        name: biome (apps/web)
        entry: bash scripts/pre-commit-biome.sh
        language: system
        files: ^apps/web/
```
`scripts/pre-commit-ruff.sh` skips with `echo "services/api not yet scaffolded, skipping ruff"`
when `services/api/pyproject.toml` is missing, then runs `uv run ruff ...` from `services/api`.
This is the existing local-hook pattern T0.3's bandit hook is required to follow.

### `apps/web` (relevant to `pnpm audit`)
- `apps/web/package.json`: `"packageManager": "pnpm@12.6.0"`, `"engines": {"node": ">=22.12.0 <23"}`;
  dependencies `react 19.3.0`, `react-dom 19.3.0`; devDependencies `@biomejs/biome 2.5.14`,
  `@tailwindcss/vite 4.3.3`, `@types/node 22.20.4`, `@types/react 19.3.0`,
  `@types/react-dom 19.3.0`, `@vitejs/plugin-react 6.1.1`, `tailwindcss 4.3.3`,
  `typescript 6.0.3`, `vite 8.3.1`, `vitest 4.1.11`.
- `apps/web/pnpm-lock.yaml` is a two-document YAML: the first document
  (`lockfileVersion: '9.0'`, `importers: . : packageManagerDependencies: pnpm 12.6.0`) pins pnpm
  itself with per-platform `@pnpm/exe.*` binaries; the second document (line 158 `---`,
  `lockfileVersion: '9.0'`, `settings: ...`) is the app's dependency lock.
- `apps/web/node_modules/` does **not** exist in this worktree (dependencies not installed here).
  It does exist in the other worktree `.claude/worktrees/typist-ml-overview-3379c6/apps/web/`.
- `apps/web/biome.json` has VCS integration on (`"useIgnoreFile": true`, `"root": "../.."`).
- The only URL in web source is the dev proxy `"/api": "http://127.0.0.1:8000"` in
  `apps/web/vite.config.ts` (local).

### `services/`
- `services/.gitkeep` only. No `services/api/`, no `pyproject.toml`, no `uv.lock`, no Python code.

### `.gitignore` and git excludes (relevant)
- `.gitignore`: `/data/`, `/*.db`, `*.db-wal`, `*.db-shm`, `.venv/`, `__pycache__/`,
  `node_modules/`, `dist/`, `.vite/`, `coverage/`, `.env`, `.env.*`, `!.env.example`, and others.
- Main checkout `.git/info/exclude` contains `.claude/worktrees/`. It is not part of `.gitignore`.
  Worktrees therefore live inside the main checkout's tree
  (`/Users/allen/Downloads/typist-ml/.claude/worktrees/*`) and are hidden from git only by that
  local exclude.

### Pipeline
- `.claude/commands/review.md` runs the reviewer subagent, sends BLOCKING findings to the builder,
  at most twice.
- The PR template's "How I tested it" has `- [ ] \`just check\` passes locally`; no security item.

---

## 5. Inputs and outputs

Inputs:
- Repository files listed in section 4.
- `semgrep` binary on `PATH` (optional; installed by the user with `uv tool install semgrep`).
  Rules for `p/security-audit` are downloaded from the Semgrep registry (semgrep.dev) at run time
  (verify).
- `pnpm` binary and `apps/web/pnpm-lock.yaml`. `pnpm audit` sends the dependency list from the
  lockfile to the npm registry's advisory endpoint (registry.npmjs.org, verify) and reads the
  advisories back.
- For pnpm 12.6.0 pinned by `packageManager`: a machine with a different pnpm version may first
  download pnpm 12.6.0 (verify), another network call.

Outputs (repo changes, per scope):
- Deleted: `.github/workflows/codacy.yml`.
- Modified: `justfile` (three recipes: `security`, `security-py`, `security-web`).
- New decision record D22 (location not settled; D21's precedent is
  `docs/decisions/D21-<slug>.md`; see Open question 9).
- Modified: `.claude/agents/reviewer.md` (security pass text).
- Possibly, depending on open questions: README, `scripts/cloud-setup.sh`, justfile header
  contracts, `.semgrepignore`.

Outputs (run time, not committed):
- Terminal output from semgrep and `pnpm audit`; exit codes.
- Files semgrep writes outside the repo: `~/.semgrep/` (settings, logs; verify, including whether
  it stores an anonymous user id there even with metrics off).
- pnpm may write to its cache/store outside the repo.

Outputs (outside the repo, not done by a file change):
- `CODACY_PROJECT_TOKEN` secret, Codacy GitHub App, and existing Codacy alerts in GitHub code
  scanning remain until removed in GitHub settings (Open question 11).

---

## 6. Constraints

- **No third-party uploads** (D19, CLAUDE.md). semgrep with `--metrics=off`. No SARIF upload to
  anything except GitHub's own code scanning (CodeQL).
- **Skip cleanly** (D21 convention, owner's Pass 5 text): missing app or missing tool prints a
  message and exits 0. Scope message for missing semgrep: "run: uv tool install semgrep".
- **Exact semgrep command** from the scope:
  `semgrep --config=p/security-audit --metrics=off --error --quiet .`
  `--error` makes semgrep exit non-zero when it has findings (verify). `.` is relative to where
  the recipe runs (other recipes `cd "{{justfile_directory()}}"` first, so `.` would be the repo
  root).
- **No bandit or pip-audit now.** Nothing under `services/` may be created. `security-py` is a
  placeholder.
- **Reviewer text is exact.** The owner's Pass 5 paragraph is to be used word for word, including
  the em dashes ("Pass 5 — Security", "manual checks — the tools").
- **Platforms:** macOS arm64 for development; Linux x64 for cloud sessions and (future) CI.
  semgrep ships wheels for macOS and Linux but not native Windows (verify). mlx-lm is not
  involved.
- **Sandbox:** subagent Bash runs sandboxed. Owner memory: never disable the sandbox without owner
  approval. semgrep's registry fetch, `pnpm audit`, and semgrep's writes to `~/.semgrep` may be
  blocked by the sandbox (verify).
- **Workflow:** branch `chore-security-scans` off `main`; conventional commits (`chore:`,
  `docs:`); one PR; `just check` before pushing. The worktree currently sits on
  `claude/chore-security-scans-e831f8`.
- **T0.2 plan boundary:** T0.2 was told "Do not touch `.github/workflows/**`". This chore touches
  that directory (deletion only) by owner agreement. CodeQL's matrix update stays with T0.4.
- **Decision log rules:** section 2 "adding a row ... not editing the old row"; section 17.3 "short
  ADR in docs/decisions/".

---

## 7. Edge cases

1. **semgrep not installed.** Example: fresh Mac or cloud VM; `command -v semgrep` finds nothing.
   The scope requires a message ("run: uv tool install semgrep") and continuing, not a failure.
   Whether `security-py` and `security-web` still run afterwards follows from "then calls" (see
   Open question 6).
2. **semgrep installed but offline or registry blocked.** `--config=p/security-audit` cannot
   download rules. Example: sandbox denies semgrep.dev, or the laptop is offline. semgrep exits
   non-zero with a config/network error (verify the exit code; semgrep uses distinct codes for
   findings vs errors). With `set -euo pipefail` this fails the whole recipe, which is not a
   "tool not installed" case, so the scope's clean skip does not cover it.
3. **`pnpm audit` offline or registry blocked.** Example: sandbox denies registry.npmjs.org.
   `pnpm audit` fails with a network error, indistinguishable by exit code alone from "advisories
   found" (verify).
4. **`pnpm audit` finds advisories.** `pnpm audit` exits non-zero when any advisory is found at or
   above `--audit-level` (default: low, verify). It includes devDependencies unless `--prod` is
   given. Example: a moderate advisory in a transitive dependency of `vitest` (dev-only, never
   shipped to the browser) makes `just security` fail. Whether that should fail the run is not
   settled (Open question 7).
5. **`pnpm` not installed.** Other recipes run `pnpm exec ...` and fail hard if pnpm is missing.
   The scope defines a clean skip only for missing apps and missing semgrep. Example: a Linux VM
   before `cloud-setup.sh` ran.
6. **semgrep walking into ignored directories.** Scanning `.` at the repo root. semgrep, inside a
   git repo, by default targets git-tracked and untracked-not-ignored files and applies a default
   `.semgrepignore` (which includes `node_modules/`, `.venv/`, `dist/`, `build/`, `vendor/`,
   verify) when the repo has no `.semgrepignore`. Cases to check:
   - `apps/web/node_modules/` (gitignored; does exist in the other worktree).
   - `data/` (gitignored, anchored `/data/`): participant database and corpus artifacts.
   - `services/api/.venv/` after T0.3.
   - `apps/web/dist/` after `just build`.
   - Main checkout: `.claude/worktrees/*` is hidden only by `.git/info/exclude`. If semgrep uses
     `git ls-files --exclude-standard` it honours that file; if it walks the file system, running
     `just security` in the main checkout scans every worktree, including
     `typist-ml-overview-3379c6/apps/web/node_modules/` (verify).
   - A git worktree has `.git` as a file, not a directory; semgrep's git detection must handle
     that (verify).
   - If a `.semgrepignore` file is added, semgrep stops applying its default ignore list (verify);
     it may or may not include `.gitignore` entries depending on an `:include .gitignore` line.
7. **Files semgrep will scan that are not app code.** `justfile` (not a semgrep language),
   `scripts/*.sh` (bash rules may exist), `.github/workflows/codeql.yml` (GitHub Actions YAML;
   `p/security-audit` may or may not include Actions rules, verify),
   `apps/web/pnpm-lock.yaml`, `docs/design/*.pdf` (not a target). Example: a rule flagging
   `actions/checkout@v7` (tag, not SHA pin) in `codeql.yml` would fail `--error` on a file this
   chore does not otherwise touch.
8. **`--quiet` and `--error` together.** `--quiet` suppresses progress output; findings are still
   printed (verify). With `--error`, a finding exits 1 (verify). Rules with severity INFO also
   count as findings for `--error` (verify).
9. **Where `just security` is run from.** Recipes that `cd "{{justfile_directory()}}"` are
   location-independent. A recipe that runs semgrep on `.` without that `cd` would scan the
   caller's current directory. Example: `cd apps/web && just security` would scan only
   `apps/web`.
10. **`security-py` after T0.3 scaffolds `services/api`.** Pattern (a)/(b) keys on
    `services/api/pyproject.toml`. Once T0.3 creates it, a recipe keyed on that file would take
    the "app exists" branch. If bandit and pip-audit are not yet dev dependencies at that moment,
    `uv run bandit` fails. Pattern (c) (unconditional placeholder) would keep skipping even after
    the tools arrive. Which pattern the placeholder uses decides this.
11. **"Pinned public ruleset" vs `p/security-audit`.** `p/security-audit` is a registry alias. Its
    contents change when Semgrep updates the pack; there is no version suffix in the command.
    Example: a run that was clean on Monday fails on Tuesday with no code change. The semgrep
    binary version itself is also unpinned (`uv tool install semgrep` takes the latest). Vendoring
    the rules as YAML in the repo would pin them but brings the Semgrep Rules License into the repo
    (verify its terms; it is not GPL, but CLAUDE.md forbids copying GPL code, so licence terms
    matter for any vendored third-party content).
12. **semgrep local state and identity.** Even with `--metrics=off`, semgrep creates
    `~/.semgrep/settings.yml` and may store an anonymous user id there, and may perform a version
    check request on start-up unless disabled by an environment variable (verify both). These are
    outbound requests beyond the rule download.
13. **pnpm version switch.** `apps/web/package.json` has `"packageManager": "pnpm@12.6.0"` and the
    lockfile pins pnpm 12.6.0. On a machine with a different pnpm, running `pnpm audit` may first
    download pnpm 12.6.0 (verify). Another network request, and another sandbox failure mode.
14. **`pnpm audit` without `node_modules`.** This worktree has no `apps/web/node_modules/`.
    `pnpm audit` reads the lockfile, so it likely works without an install (verify for pnpm
    12.6.0).
15. **`pnpm audit` endpoint changes.** npm has been retiring older audit endpoints in favour of the
    bulk advisory endpoint; older pnpm versions broke when endpoints changed (verify for 12.6.0).
    Example: `pnpm audit` returns an HTTP 410/404 error, failing `just security` with no
    advisories.
16. **Reviewer.md has no Pass 5.** The owner's text says "Update ... existing Pass 5 paragraph",
    but item 5 is "Quality: naming, function size, types ..., dead code, new dependencies." Example:
    replacing item 5 would delete the only instruction to check new dependencies and `any` types.
17. **Reviewer's Bash allow-list.** "Use Bash only for read-only commands: git diff, git log, git
    status, and the lint, type and test commands." `just security` is not in the list and makes
    network calls and writes `~/.semgrep`. Example: the reviewer follows the allow-list and never
    runs `just security`, or runs it and breaks its own read-only rule.
18. **Pass 5's "no new network call added anywhere".** The chore itself adds two tools that make
    network calls at run time (semgrep registry, npm audit). The Pass 5 text is about project code
    (D19), but a reviewer reading it literally could flag this very PR.
19. **`--error` and CodeQL overlap.** Findings shown by semgrep locally and CodeQL on GitHub may
    differ; CodeQL currently scans only `actions`, so TS/Python findings appear locally only.
20. **Existing Codacy alerts in GitHub code scanning.** Deleting the workflow stops new uploads;
    alerts already uploaded (tool "Codacy") stay open in the Security tab (verify how GitHub marks
    alerts from a tool that no longer runs).
21. **Scheduled run after deletion.** The Codacy cron (`'37 20 * * 3'`, Wednesdays) stops once the
    file is gone from `main`. Until the PR merges, the old workflow still runs on `main` and on this
    PR (it triggers on `pull_request` to `main`; on a PR that deletes the file, GitHub uses the
    workflow file from the PR head, so it should not run, verify).
22. **Recipe naming with hyphens.** `security-py` and `security-web` contain hyphens; `just`
    allows hyphens in recipe names (existing `format-check`, `gen-types`).
23. **`just --list` output.** Each new recipe needs a comment line to show a description, like the
    others. `[private]` hides a recipe; whether the sub-recipes are public is not stated (the scope
    names them as recipes, implying callable).

---

## 8. Risks

1. **`just security` red on day one.** `pnpm audit` may already report advisories in current web
   dependencies (not checked), or semgrep rules may flag existing files (for example
   `codeql.yml`, `scripts/*.sh`). The reviewer's first `just security` run on this very PR could
   fail.
2. **Network dependence contradicts "falls back cleanly".** Both tools need the network. In the
   sandbox or offline, they fail rather than skip, and the Pass 5 promise ("falls back cleanly if
   the tools or apps behind it aren't set up yet") does not cover "tool installed but offline".
3. **Tension with D19 and the "no network" wording.** semgrep's registry download and `pnpm
   audit`'s advisory query send data (rule requests; the full dependency list) to third parties.
   D22's "no third-party upload services" and Pass 5's "this project makes none" may be read as
   covering or excluding dev tools; unsettled.
4. **Unpinned ruleset.** `p/security-audit` plus an unpinned semgrep version gives
   non-reproducible results, contradicting D22's "pinned public ruleset" wording.
5. **Wrong reviewer edit.** Replacing "5. Quality" drops quality checks; adding a paragraph after
   the list keeps an unnumbered "Pass 5" next to a numbered item 5.
6. **Scanning too much.** Nested worktrees and `node_modules` make semgrep slow and noisy when run
   from the main checkout; `data/` exposure if ignore rules are not what they seem.
7. **T0.3 requirements lost.** They live only in this brief (and maybe D22). If T0.3's analyst does
   not read this brief, bandit, pip-audit and the hook are not added, and `security-py` never gets
   a real body.
8. **D22 location inconsistent with the log.** D01 to D20 are in a PDF; D21 is a separate ADR file.
   A D22 placed differently (README, a new index, amended D21) splits the log further.

---

## 9. Owner-agreed scope boundaries (facts, not decisions)

- In scope: delete `.github/workflows/codacy.yml`; add `security`, `security-py`, `security-web`;
  add D22; replace the reviewer security text with the owner's exact paragraph.
- Out of scope: bandit, pip-audit, anything under `services/`; CodeQL matrix (T0.4 per T0.2 owner
  answer 20); CI workflow `ci.yml` (T0.4).
- Not stated either way: README, `scripts/cloud-setup.sh`, justfile header contracts, PR template,
  `.semgrepignore`, `just check`, GitHub settings (secret, app, alerts). See Open questions.

---

## 10. Requirements for T0.3

Recorded here at the owner's request so that T0.3's analyst and architect pick them up. T0.3
("Scaffold services/api: uv, FastAPI, SQLModel, Alembic, ruff, pyright, pytest; /health",
acceptance "curl /api/v1/health returns ok") must, once `services/api/src` exists:

1. Add **bandit** and **pip-audit** as dev dependencies in `services/api/pyproject.toml` (so their
   versions are pinned in `services/api/uv.lock`).
2. Add a **local bandit pre-commit hook** that runs through `uv run` from `services/api`, **not**
   pre-commit's upstream bandit repository. The existing local-hook pattern to match is the
   `ruff` hook: `repo: local`, `language: system`, `entry: bash scripts/pre-commit-ruff.sh`,
   `files: ^services/api/.*\.pyi?$`, with the script skipping when
   `services/api/pyproject.toml` is missing and otherwise running `uv run ...` from
   `services/api`.

Related facts T0.3 will meet:
- `security-py` in the justfile is a placeholder created by this chore. Whether T0.3 replaces it
  with real bandit / pip-audit calls is not stated (Open question 12).
- pip-audit queries an online vulnerability database (PyPI / OSV, verify), the same network
  question as `pnpm audit` (Open question 5).
- bandit runs offline.

---

## 11. Open questions

1. **Reviewer "Pass 5" does not exist.** `reviewer.md` has a numbered list "1. Plan fidelity ...
   5. Quality ..." and no Pass 5 paragraph or security pass. Should the owner's paragraph (a)
   replace item 5 "Quality" (dropping the quality checks), (b) be added as a new item 6, (c) be
   inserted as item 5 with "Quality" renumbered to 6, or (d) something else? Should the text keep
   the literal prefix "Pass 5 — " even if it is not item 5?
2. **`just check` and `just security`.** Should `check` call `security` (which changes D21's
   definition and would need a dated amendment or new row), or stay separate as the scope implies?
3. **CI and `just security`.** Should CI (T0.4) run `just security` or its parts, and should D22 or
   this chore say so? T0.4 does not exist yet.
4. **semgrep registry fetch vs D19 and "pinned".** `--config=p/security-audit` downloads rules from
   semgrep.dev on each run. Is that network call acceptable under D19 and the Pass 5 wording? And
   what does "pinned public ruleset" in D22 mean: (a) the alias `p/security-audit` as named, (b) a
   pinned semgrep version (for example in README / cloud-setup), (c) a vendored copy of the rules
   in the repo (licence terms apply), or (d) something else?
5. **`pnpm audit` network call.** `pnpm audit` sends the dependency list to the npm registry. Is
   that acceptable under D19? Same question for pip-audit in T0.3.
6. **Control flow of `security`.** If semgrep reports findings (non-zero with `--error`), should
   `security` stop there, or still run `security-py` and `security-web` and fail at the end? If
   semgrep is missing, the scope says skip and continue; confirm that `security-py` and
   `security-web` still run in that case.
7. **Failing on advisories.** Should `security` fail overall when `pnpm audit` finds advisories?
   At what level (low, moderate, high, critical), and including devDependencies or production only
   (`--prod`)?
8. **Network failure behaviour.** When semgrep or pnpm is installed but the registry cannot be
   reached (offline, sandbox), should the recipe fail, or skip with a message like the missing-tool
   case?
9. **Where D22 lives.** A new ADR file `docs/decisions/D22-<slug>.md` in D21's format (Date,
   Status, Task, Context, one-row table `ID | Decision | Choice | Why | Revisit if`,
   Consequences)? What goes in "Task" for a chore (for example `chore-security-scans`)? What is the
   "Revisit if" condition?
10. **Other files mentioning tools.** Should README (setup step 1 tool list, version table,
    security mention) and `scripts/cloud-setup.sh` (`uv tool install semgrep`) be updated, or is
    semgrep an optional tool that only the recipe message mentions? No file other than
    `codacy.yml` and the T0.2 brief/plan references Codacy; confirm the T0.2 records stay
    untouched as history.
11. **GitHub-side Codacy cleanup.** Should the owner also delete the `CODACY_PROJECT_TOKEN` secret,
    uninstall any Codacy GitHub App, and dismiss existing Codacy alerts in code scanning? These are
    outside the repo and cannot be done by a file change.
12. **`security-py` placeholder form.** Should it be (a) an unconditional placeholder like
    `gen-types` (keeps skipping after T0.3 until someone replaces it), or (b) keyed on
    `services/api/pyproject.toml` like `lint`/`migrate` (which would try to run tools as soon as
    T0.3 creates the file)? If (b), what should it run then, given bandit/pip-audit must not be
    named now? Is replacing the placeholder part of T0.3's requirements?
13. **Justfile header contracts.** Should the header's "Contracts later tasks must meet" block
    gain a line for `security-py` / T0.3 (bandit, pip-audit), or does "Do NOT add bandit or
    pip-audit anywhere now" exclude comments too?
14. **Missing pnpm.** If `pnpm` is not installed but `apps/web/package.json` exists, should
    `security-web` skip with a message (like missing semgrep) or fail (like `lint`/`test` do
    today)?
15. **semgrep scan scope.** Should the scan rely on semgrep's defaults for ignoring
    `node_modules/`, `data/`, `.venv/`, `dist/` and nested `.claude/worktrees/`, or should the repo
    carry an explicit ignore (for example `.semgrepignore`)? Is `data/` required to be excluded
    explicitly, given it holds participant data?
16. **semgrep local state.** Is it acceptable that semgrep writes `~/.semgrep/` (settings, possibly
    an anonymous id) and may run a version check, or should those be disabled too (for example via
    environment variables in the recipe)?
17. **Reviewer's Bash allow-list.** Should the sentence "Use Bash only for read-only commands: git
    diff, git log, git status, and the lint, type and test commands" be extended to allow
    `just security`, given it makes network calls and writes outside the repo? The scope only
    changes the Pass 5 text.
18. **PR template.** Should the PR template's "How I tested it" gain a `just security` checkbox, or
    stay as is?
19. **Branch.** The worktree is on `claude/chore-security-scans-e831f8`. Confirm the builder should
    create or switch to `chore-security-scans` off `main` before committing.

## Owner answers (2026-09-26)

1. Pass 5 numbering: (b) — add it as a new item 6, after the existing item 5 "Quality." Don't renumber or merge anything. Drop the literal "Pass 5 —" prefix; match the file's actual style and call it "6. Security and data handling."
2. `check` vs `security`: stay separate. `check` keeps its D21 definition (lint+types+test) unchanged. `security` is a distinct, slower, network-touching recipe you run manually or the reviewer runs — not part of the fast everyday gate.
3. CI and `just security`: not yet — T0.4 doesn't exist, and this chore shouldn't reach into a future task's scope. Add one line to this task's brief: "Note for T0.4: decide whether CI runs `just security` or its parts." Leave the actual decision to T0.4.
4. semgrep registry fetch: acceptable under D19. The distinction that matters: D19 forbids sending your code or data to a cloud service. Fetching a named public ruleset only downloads rule definitions — nothing of yours goes out. This is the same category as `pnpm install` downloading packages, not the same category as a cloud AI API call. For "pinned public ruleset" in D22, go with (b): pin the semgrep CLI version (record it in the README's version table), and reference the ruleset by its stable alias `p/security-audit`. Don't vendor the rules into the repo (c) — that adds licensing overhead and staleness for no real benefit here.
5. pnpm audit / pip-audit network calls: acceptable, same reasoning as #4 — only package names and versions are sent to check against a public vulnerability database, no code or participant data.
6. Control flow: run all three regardless of semgrep's result — don't stop early. Collect results from semgrep, security-py, and security-web, then exit non-zero at the end if any failed, with a summary of which. Confirmed: if semgrep is merely missing (not installed), security-py and security-web still run.
7. Failing on advisories: `pnpm audit --audit-level=high` (fail on high/critical only, not low/moderate — too noisy this early). Don't pass `--prod`; include dev dependencies too, since supply-chain risk in build tooling still matters.
8. Network unreachable: skip with a message ("couldn't reach the registry, skipping"), not a hard fail — same treatment as a missing tool. This is an environment issue, not a real finding.
9. D22 location: yes, `docs/decisions/D22-security-scanning.md`, matching D21's exact format (Date, Status, Task, Context, the one-row table, Consequences). Task: `chore-security-scans`. Revisit if: "a tool changes its default network or telemetry behavior, T0.4 decides CI's role for this, or the Codacy decision changes."
10. Other files: yes, update README (add semgrep to the setup tool list and version table) and `scripts/cloud-setup.sh` (add `uv tool install semgrep`, same line style as `just`/`pre-commit`). Confirmed: T0.2's brief/plan are historical record — never touch them.
11. GitHub-side Codacy cleanup: moot — per my last message, Codacy is being kept, not removed. Skip this entirely; no secret/app/alert cleanup needed. (If you meant something different by "keep the github things," tell me now before this goes further.)
12. `security-py` placeholder form: (a) — an unconditional placeholder, like `gen-types`. It always prints the skip message regardless of whether `services/api/` exists yet. T0.3 replaces the whole recipe body outright, rather than the recipe trying to auto-detect and guess what to run.
13. Justfile header contracts: yes, add a line naming bandit and pip-audit as what T0.3 must wire into `security-py`. This is documentation of a future contract, not adding the dependencies themselves — those stay banned from this task per your own scope.
14. Missing pnpm: skip with a message ("pnpm not found, run corepack enable"), not a hard fail like `lint`/`test`. Security scanning is supplementary, not foundational the way `check` is.
15. semgrep scan scope: add an explicit `.semgrepignore` excluding `node_modules/`, `.venv/`, `dist/`, `.claude/worktrees/`, and — explicitly, defensively, even though it's already gitignored — `data/`, since that's where participant data lives. Don't rely on defaults alone for that one.
16. semgrep local state: the `~/.semgrep/` local cache/config dir is fine to leave as-is (same category as `~/.cache/pnpm`, purely local). But add `SEMGREP_ENABLE_VERSION_CHECK=0` as an env var in the recipe invocation, alongside `--metrics=off`, to suppress the extra version-check network call too — keep it consistent with D19's spirit.
17. Reviewer's Bash allow-list: yes, extend that sentence to explicitly permit `just security` — note in the same sentence that it makes read-only network calls (checking, not modifying, the repo) so it doesn't conflict with the reviewer's "never edit files" rule.
18. PR template: yes, add a checkbox: `- [ ] just security passes (or reason noted if not)`, matching the existing `just check` checkbox style.
19. Branch: confirmed — the builder should `git checkout -b chore-security-scans` off `main` (or switch to it if it already exists from a prior attempt), not commit on the auto-generated `claude/chore-security-scans-e831f8` session-tracking branch. That branch is Claude Code's own bookkeeping, not your task branch.

Note for T0.4: decide whether CI runs `just security` or its parts.

Owner status: approved (2026-09-26), pending resolution of the Codacy conflict between the original scope item 1 (delete `.github/workflows/codacy.yml`) and answer 11 ("Codacy is being kept, not removed").

Codacy resolution (2026-09-26): owner answered "delete". Option (a): delete `.github/workflows/codacy.yml` as scoped; D22 records Codacy as removed. Answer 11 means only that no GitHub-side cleanup (secret, app, alerts) is part of this task.
