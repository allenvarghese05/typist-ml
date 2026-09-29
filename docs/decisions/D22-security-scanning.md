# D22: Security scanning stays local

- Date: 2026-09-26
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
- Amended 2026-09-28 by T0.3 (owner answers 19 and 20): `security-py` runs bandit on
  `services/api/src/` only (`-r src -ll`: medium severity and above fails; tests are not scanned,
  so pytest asserts (B101) do not arise). It then runs pip-audit on the dependencies pinned in
  `services/api/uv.lock`, exported with `uv export --locked --no-emit-project` (the local project
  is not audited) and checked with `--no-deps --disable-pip`, without `--strict`. pip-audit is
  skipped when a `curl` HEAD probe of `https://pypi.org/` gets no response; bandit runs
  regardless. Each tool's result is printed with a summary, and `security-py` fails if either tool
  failed. A skipped pip-audit makes `security` report `security-py` as skipped (the "skipping"
  keyword rule), with bandit's own result shown above it. bandit and pip-audit are pinned dev
  dependencies in `services/api/uv.lock`. The local pre-commit hook `bandit`
  (`scripts/pre-commit-bandit.sh`, run through `uv run --locked` from services/api) scans staged
  files under `services/api/src/` with the same threshold.
- Amended 2026-09-28 by T0.4 (owner answers 6, 7, 18 and 19): the required CI job `api` runs bandit
  (`uv run --locked bandit -q -r src -ll`) and semgrep on the whole repository
  (`p/security-audit`, `--metrics=off`, `--error`, `SEMGREP_ENABLE_VERSION_CHECK=0`), with the
  semgrep version read from the justfile (`just --evaluate semgrep_version`). CI has no skip: a
  semgrep version that differs from the pin, or a ruleset that cannot be downloaded, fails the
  job, because a skip inside a required check would pass without scanning. pip-audit and
  `pnpm audit` are not part of any required check, since advisories change without code changes:
  `.github/workflows/audit.yml` runs `just security-py` and `just security-web` weekly and by hand
  as a non-required job, where the D22 skip for an unreachable registry is accepted. `just
  security` is unchanged. CodeQL (`.github/workflows/codeql.yml`) analyses `actions`,
  `javascript-typescript` and `python` with the `security-extended` query suite and is not a
  required check.
