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
