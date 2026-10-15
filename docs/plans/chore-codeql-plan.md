# chore-codeql plan: CodeQL init and analyze to 4.38.3, one weekly grouped Dependabot PR

Architect: phase 2 (Blueprint). Source: `docs/plans/chore-codeql-brief.md`, including
"## Owner answers" (2026-10-15), which are binding and override the brief's suggested defaults.
Also read: CLAUDE.md, `.github/workflows/codeql.yml`, `.github/dependabot.yml`,
`.pre-commit-config.yaml`, `scripts/pre-commit-actionlint.sh`.
Branch: `chore-codeql-4-38-3` (already checked out, off `main`).

---

## 1. Summary

When this plan is done:
- `.github/workflows/codeql.yml` pins both `github/codeql-action/init` and
  `github/codeql-action/analyze` to `24c54180a607b1449ed407dd24f251e4e9147c8d # v4.38.3`
  (owner-verified SHA). Nothing else in that file changes.
- `.github/dependabot.yml` runs weekly on Sunday and bundles every GitHub Actions update into one
  PR through a single `groups` entry with `patterns: ["*"]`, with a comment saying why.
- After merge, the owner closes Dependabot PRs #14 and #16 with a comment. No ADR (owner answer 2).

## 2. Design

- **Bump both CodeQL lines in one edit, to one SHA.** CodeQL requires `init` and `analyze` to run
  the same version; the SHA is the one the owner verified (owner answer 3), never retyped from
  memory. Rejected: merging #14 and #16 in turn (either alone breaks CodeQL on `main`).
- **Dependabot does the weekly bundling itself** (owner answer 1): `schedule.interval: weekly`,
  `schedule.day: sunday`, and one group `github-actions` with `patterns: ["*"]`. No
  `update-types`, `exclude-patterns`, `applies-to` or `dependency-type` keys: the owner wants all
  updates (major, minor, patch) bundled, and the documented defaults already do that for version
  updates. Rejected: a CodeQL-only group (`github/codeql-action*`), which the owner overrode.
- **Schema used (Dependabot `dependabot.yml` reference, from documented options):**
  `updates[].schedule.day` accepts `monday` to `sunday` when `interval` is `weekly`;
  `updates[].groups.<group-name>` takes `patterns` (list of name globs, `*` matches every
  dependency), and optionally `exclude-patterns`, `update-types` (`major`/`minor`/`patch`),
  `applies-to` (`version-updates` default, or `security-updates`), `dependency-type`, `group-by`.
  Only `patterns` is used. The architect could not open the live docs from this session (no
  network); see Flags in the hand-off. The PR's Dependabot config check on GitHub (the repo's
  Dependabot tab / "Check for updates") is the final proof that the file is valid.
- **Header comments.** `dependabot.yml` keeps its two existing header lines verbatim (T0.4 owner
  answer 11, design doc section 18) and adds three lines for the grouping. `codeql.yml` header line
  3 stays true and is not touched.
- **Two commits**, one per file, so each is verifiable alone. The owner runs commits (sandbox);
  message files go in `.git/chore-codeql/`.

## 3. File map

| File | Change |
|---|---|
| `.github/workflows/codeql.yml` | Lines 40 and 46: SHA and version comment to 4.38.3. Nothing else. |
| `.github/dependabot.yml` | Add `day: sunday`, a `groups` entry for all actions, and a 3-line comment. |
| `.git/chore-codeql/commit-1.txt`, `.git/chore-codeql/commit-2.txt` | Commit message files for the owner (inside `.git/`, never committed, never `/tmp`). |

No other file is created or modified. No ADR, no README change, no test file.

---

## 4. Steps

### Step 1. Bump CodeQL init and analyze to 4.38.3

- **File:** `.github/workflows/codeql.yml`.
- **Exact change** (two lines; indentation is 8 spaces before `uses:`, unchanged):

```diff
       - name: Initialize CodeQL
-        uses: github/codeql-action/init@2892aa5e19bbd11bc0cff5427e3b750a04d9e3c2 # v4.38.2
+        uses: github/codeql-action/init@24c54180a607b1449ed407dd24f251e4e9147c8d # v4.38.3
         with:
...
       - name: Perform CodeQL analysis
-        uses: github/codeql-action/analyze@2892aa5e19bbd11bc0cff5427e3b750a04d9e3c2 # v4.38.2
+        uses: github/codeql-action/analyze@24c54180a607b1449ed407dd24f251e4e9147c8d # v4.38.3
         with:
```

  Copy the SHA from this plan with copy and paste; do not retype it. Do not touch the
  `actions/checkout` pin, the header, triggers, permissions, matrix, `queries`, or `timeout-minutes`.

- **Tests for this step:** no pytest (config-only chore). The checks below are the tests.
- **Verify** (run from any cwd; all paths absolute):

  1. Both lines carry the new pin, and the old SHA is gone:
     ```
     grep -c 'github/codeql-action/\(init\|analyze\)@24c54180a607b1449ed407dd24f251e4e9147c8d # v4.38.3$' /Users/allen/Downloads/typist-ml/.github/workflows/codeql.yml
     grep -c '2892aa5e19bbd11bc0cff5427e3b750a04d9e3c2' /Users/allen/Downloads/typist-ml/.github/workflows/codeql.yml
     ```
     Pass: first prints `2`; second prints `0` (grep exits 1 on zero matches; that is expected).
  2. Only those two lines changed:
     ```
     git -C /Users/allen/Downloads/typist-ml diff --numstat -- .github/workflows/codeql.yml
     ```
     Pass: `2	2	.github/workflows/codeql.yml`.
  3. ASCII only:
     ```
     LC_ALL=C grep -c '[^ -~]' /Users/allen/Downloads/typist-ml/.github/workflows/codeql.yml
     ```
     Pass: prints `0`.
  4. actionlint (the pre-commit hook will also run it at commit time):
     ```
     bash /Users/allen/Downloads/typist-ml/scripts/pre-commit-actionlint.sh /Users/allen/Downloads/typist-ml/.github/workflows/codeql.yml
     ```
     Pass: no output, exit 0. If it prints "actionlint not found" or a version mismatch, report it
     to the owner and continue; the owner's commit runs the hook.

- **Commit message file** `/Users/allen/Downloads/typist-ml/.git/chore-codeql/commit-1.txt`
  (create the directory if missing), exact content:

```
chore(ci): bump CodeQL init and analyze together to v4.38.3

Both steps must run the same CodeQL version. Dependabot PRs #14 and #16 each
bumped only one of them, which fails with "Loaded a configuration file for
version '4.38.3', but running version '4.38.2'". SHA verified by the owner
with gh api on 2026-10-15.
```

  Owner runs: `git add .github/workflows/codeql.yml && git commit -F .git/chore-codeql/commit-1.txt`.

### Step 2. Group all GitHub Actions updates into one Sunday PR

- **File:** `.github/dependabot.yml`.
- **Exact change:** replace the whole file with exactly this content (ASCII, 2-space indent,
  trailing newline):

```yaml
# Dependabot keeps the SHA-pinned GitHub Actions current (T0.4 owner answer 11). npm and uv
# dependencies are not updated this way: lockfiles change only on purpose (design doc section 18).
# All action updates are grouped into one PR every Sunday (chore-codeql owner answers 1 and 2):
# CodeQL init and analyze must share a version, and the owner reviews one weekly PR. One failing
# update holds back the whole bundle until it is fixed.
version: 2
updates:
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
      day: sunday
    groups:
      github-actions:
        patterns:
          - "*"
    commit-message:
      prefix: chore
      include: scope
```

- **Tests for this step:** no pytest. The parse check below is the test: it loads the file with
  PyYAML (present in `services/api/.venv` via `services/api/uv.lock`) and compares it to the exact
  expected structure.
- **Verify:**
  1. YAML parse and structure check:
     ```
     /Users/allen/Downloads/typist-ml/services/api/.venv/bin/python -I -c 'import sys, yaml; d = yaml.safe_load(open(sys.argv[1], encoding="ascii")); exp = {"version": 2, "updates": [{"package-ecosystem": "github-actions", "directory": "/", "schedule": {"interval": "weekly", "day": "sunday"}, "groups": {"github-actions": {"patterns": ["*"]}}, "commit-message": {"prefix": "chore", "include": "scope"}}]}; assert d == exp, d; print("dependabot.yml OK")' /Users/allen/Downloads/typist-ml/.github/dependabot.yml
     ```
     Pass: prints `dependabot.yml OK`, exit 0. (`encoding="ascii"` also proves the file is ASCII.)
     If `services/api/.venv/bin/python` is missing, run `uv run --project
     /Users/allen/Downloads/typist-ml/services/api python -I -c '...'` with the same code instead;
     if neither works, report it and do not install anything.
  2. Header lines kept verbatim:
     ```
     git -C /Users/allen/Downloads/typist-ml diff -U0 -- .github/dependabot.yml
     ```
     Pass: only `+` lines (3 comment lines, `day: sunday`, and the 4 `groups` lines); no `-` lines.
  3. actionlint does not cover this file (hook pattern is `^\.github/workflows/`); no step for it.

- **Commit message file** `/Users/allen/Downloads/typist-ml/.git/chore-codeql/commit-2.txt`,
  exact content:

```
chore(deps): group all GitHub Actions updates into one Sunday PR

Dependabot opened separate PRs for CodeQL init and analyze, and merging either
alone breaks CodeQL. One group with pattern "*" bundles every action update
into a single PR, opened weekly on Sunday for the owner to review.
```

  Owner runs: `git add .github/dependabot.yml && git commit -F .git/chore-codeql/commit-2.txt`.

### Step 3. Pre-push check and PR (owner-run)

- `just check` from the repo root (CLAUDE.md rule; it covers the apps only, so it should pass
  unchanged). Pass: exit 0.
- Push `chore-codeql-4-38-3`; open the PR (phase 5, /ship).
- On the PR, the owner confirms the **CodeQL** run is green for all three matrix jobs (`actions`,
  `javascript-typescript`, `python`). CodeQL is not a required check, so this must be looked at
  explicitly. Pass: no "configuration error" and no "Not all workflow steps that use
  `github/codeql-action` actions use the same version" warning.

### Step 4. After merge: close #14 and #16 (owner step, no file change)

- After the PR is merged to `main`, close PR #14 and PR #16 on GitHub with this comment:
  `Superseded by #<this PR>, which bumps init and analyze together to v4.38.3. Actions updates are now grouped into one weekly PR.`
- **Edge case (brief section 7, item 8): closing a Dependabot PR unmerged makes Dependabot ignore
  that version.** When a Dependabot PR is closed without merging, Dependabot stops proposing that
  exact version (4.38.3) for that dependency; it still proposes later versions (4.38.4 and up).
  Because `main` already has 4.38.3 after this merge, ignoring 4.38.3 has no effect. **The owner
  needs to do nothing about it.** Do not use `@dependabot ignore this dependency` or
  `@dependabot ignore this major version` comments, which would suppress future CodeQL updates.
- Alternative that avoids the question: wait for Dependabot's next run; it normally closes PRs
  whose update is already on `main` by itself. Either is fine.
- Optional check afterwards: the repo's Insights > Dependency graph > Dependabot tab shows the
  `github-actions` config with no error, and the next Sunday brings at most one grouped PR titled
  like `chore(deps): bump the github-actions group ...`.

---

## 5. Dependencies

None. PyYAML is used only for verification and is already in `services/api/.venv`.

## 6. Acceptance check

| Criterion (brief section 1 and owner answers) | Proven by |
|---|---|
| `init` and `analyze` on the same SHA, `24c54180...` with `# v4.38.3` | Step 1 verify 1 (count `2`, old SHA count `0`); PR CodeQL run green (Step 3) |
| Nothing else in `codeql.yml` changes | Step 1 verify 2 (`2 2` numstat) |
| All actions grouped in one PR, weekly on Sunday; ecosystem, directory, commit-message kept | Step 2 verify 1 (exact dict match) |
| Short "why" comment, existing header references kept | Step 2 verify 2 (no `-` lines) and the file content in Step 2 |
| No ADR (owner answer 2) | File map: no `docs/decisions/` change |
| Owner closes #14 and #16 after merge | Step 4 |

## 7. Out of scope

- The `actions/checkout` pin and every other line of `codeql.yml` (header, triggers, cron,
  permissions, matrix, `queries`, timeout).
- `ci.yml`, `audit.yml`, README (line 125 stays true), `docs/decisions/`, `.pre-commit-config.yaml`.
- Adding `schedule.time`, `timezone`, `labels`, `open-pull-requests-limit`, `ignore`, `reviewers`,
  `update-types`, `exclude-patterns`, `applies-to`, or npm/uv ecosystems to `dependabot.yml`.
- Adding a Claude-side scheduled job (owner answer 1: Dependabot does it).
- Closing, merging or commenting on #14/#16 (owner only).

## 8. Review focus

1. **The SHA on both `uses:` lines** is byte-identical to the owner-verified
   `24c54180a607b1449ed407dd24f251e4e9147c8d` and both comments read `# v4.38.3` (brief edge case 2:
   same comment, different SHA looks right but fails).
2. **`codeql.yml` diff is exactly two lines.** Nothing else touched.
3. **`dependabot.yml` keys:** `day: sunday` sits under `schedule`; `groups` is a sibling of
   `schedule` under the update entry (not top level); the group has `patterns: ["*"]` and no
   invented keys.
4. **Comments:** the two original header lines are unchanged; the new comment states both reasons
   (CodeQL version coupling, one weekly PR) and the accepted trade-off.
5. **Step 4 guidance** does not tell the owner to use `@dependabot ignore` commands.
