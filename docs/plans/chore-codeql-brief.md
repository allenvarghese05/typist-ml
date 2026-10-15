# chore-codeql brief: bump CodeQL init and analyze together to 4.38.3, group CodeQL Dependabot updates

Analyst: phase 1 (Understand). This brief records facts only. It does not design a solution.
Sources: CLAUDE.md; the task message from the orchestrator (CI facts it verified from the owner's
logs); `.github/dependabot.yml`; `.github/workflows/codeql.yml`, `ci.yml`, `audit.yml`;
`.pre-commit-config.yaml`; `README.md` (CI section); `docs/decisions/D22-security-scanning.md`
(the only ADR that mentions CI or CodeQL; no ADR covers Dependabot or SHA pinning);
`docs/plans/T0.4-brief.md` (owner answers 11, 18, 19), `docs/plans/T0.4-plan.md` (pinning,
Check W, step 6); `docs/plans/chore-security-scans-brief.md` (format precedent).

Limits of this analysis:
- This is a chore, not a section-16 task. There are no design-doc acceptance criteria.
- No shell and no network. The new SHA, the Dependabot error text and the PR contents come from the
  orchestrator's message (taken from the owner's CI logs and PR #16's commit message), not from
  GitHub. Statements about Dependabot behaviour marked "(verify)" come from general knowledge.
- Branch at the time of writing: `chore-codeql-4-38-3` (off `main`, clean). HEAD is `1f62a6b`.

---

## 1. Task

- **ID:** `chore-codeql` (not from design doc section 16)
- **Title:** none in the design doc. Working description: bump `github/codeql-action/init` and
  `github/codeql-action/analyze` together from 4.38.2 to 4.38.3, and group future
  `github/codeql-action` updates into one Dependabot PR.
- **Acceptance criteria:** the design doc has none. Agreed scope, as passed on by the orchestrator:
  1. One PR that bumps `init` and `analyze` together to 4.38.3: the same SHA on both lines, version
     comment updated.
  2. Add a Dependabot `groups` entry to `.github/dependabot.yml` "so that all
     github/codeql-action/* updates come in one PR in future".
  3. Afterwards the owner closes Dependabot PRs #14 and #16 (owner action, not a file change).
- Files to change: `.github/workflows/codeql.yml` and `.github/dependabot.yml` (a 2-file change).

---

## 2. Why it matters

What this enables:
- The CodeQL workflow runs again. Today it is broken only on the Dependabot branches, but merging
  either #14 or #16 alone would break it on `main`.
- Future CodeQL bumps arrive as one PR, so a split-version state cannot be produced by merging a
  single Dependabot PR.

What breaks if it is wrong:
- If `init` and `analyze` end up on different versions (or the same version comment on different
  SHAs), CodeQL fails with the error the owner saw (section 4). CodeQL is not a required check
  (`codeql.yml` header, README line 122), so the failure does not block merges and can go
  unnoticed. Code scanning for `actions`, `javascript-typescript` and `python` stops.
- If the SHA is wrong (typo, or not the commit the v4.38.3 tag points to), the run fails to
  resolve the action, or worse, runs a commit that is not the release. SHA pinning exists to
  prevent exactly that (T0.4 owner answer 11).
- If the `groups` entry does not match how Dependabot names these dependencies, Dependabot keeps
  opening split PRs and the problem recurs on the next CodeQL release.
- If the `groups` entry is malformed, Dependabot may stop updating every pinned action (verify:
  an invalid `dependabot.yml` is reported in the repo's Dependabot tab and no updates run).

---

## 3. Governing decisions

| Source | Decision | What it forces here |
|---|---|---|
| T0.4 owner answer 11 | "Action pinning: full commit SHAs with a tag comment (`actions/checkout@<sha> # vX.Y.Z`). Update `codeql.yml` to match. Add Dependabot for GitHub Actions only (not npm/uv)." | Both lines stay `@<40-hex SHA> # vX.Y.Z`. Dependabot stays `github-actions` only. This is an owner answer recorded in the T0.4 brief, not a D-row or ADR. `dependabot.yml` line 1 cites it. |
| T0.4 plan, "Pinning" | "The SHAs and tags come only from the owner's preflight (RESUME A); the builder never guesses one." "`.github/dependabot.yml` updates `github-actions` only, weekly, with `chore(deps)` commit messages." Publishers limited to `actions`, `github`, `astral-sh`. | The new SHA must come from a verified source, not be guessed (see section 6). |
| T0.4 owner answers 18, 19 | CodeQL languages `actions`, `javascript-typescript`, `python`; weekly schedule kept; suite `security-extended`. | Nothing else in `codeql.yml` changes. |
| D22 (and its T0.4 amendment) | CodeQL is allowed "because it runs inside GitHub, where the code already lives"; CodeQL "is not a required check". | No change to D22's content. The bump does not touch what CodeQL analyses. |
| D19 (via D22) | No third-party upload services. | Dependabot and CodeQL are GitHub-native; no new service is added. |
| Design doc section 2 / 17.3 (as quoted in earlier briefs) | "Changing a decision means adding a row with the new choice and the date, not editing the old row." "Any change to a decision gets a short ADR in docs/decisions/." | Whether grouping is a change to a decision is open (Open question 2). |
| CLAUDE.md | Conventional commits; one task per PR; `just check` before pushing; never push to `main`; never merge PRs. | Commit type `chore:` (T0.4 used `chore(ci): ...` for the same files). The owner closes #14 and #16; no agent does. |

---

## 4. Current state

### `.github/workflows/codeql.yml` on `main` (relevant lines, verbatim)
```yaml
      - name: Initialize CodeQL
        uses: github/codeql-action/init@2892aa5e19bbd11bc0cff5427e3b750a04d9e3c2 # v4.38.2
        with:
          languages: ${{ matrix.language }}
          build-mode: ${{ matrix.build-mode }}
          queries: security-extended
      - name: Perform CodeQL analysis
        uses: github/codeql-action/analyze@2892aa5e19bbd11bc0cff5427e3b750a04d9e3c2 # v4.38.2
        with:
          category: "/language:${{ matrix.language }}"
```
- Line 40 is `init`, line 46 is `analyze`. Both are `2892aa5e19bbd11bc0cff5427e3b750a04d9e3c2 # v4.38.2`.
- Header comment line 3: "Actions are pinned to commit SHAs; Dependabot updates them
  (.github/dependabot.yml)."
- Other `uses:` in the file: `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1`
  (line 36). Not in scope.
- Triggers: `push` and `pull_request` to `main`, `schedule: "20 3 * * 3"`.
- No other workflow uses `github/codeql-action` (`ci.yml` and `audit.yml` use only
  `actions/checkout`, `actions/setup-node`, `actions/cache`, `astral-sh/setup-uv`).

### `.github/dependabot.yml` on `main` (whole file, verbatim)
```yaml
# Dependabot keeps the SHA-pinned GitHub Actions current (T0.4 owner answer 11). npm and uv
# dependencies are not updated this way: lockfiles change only on purpose (design doc section 18).
version: 2
updates:
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
    commit-message:
      prefix: chore
      include: scope
```
- No `groups`, no `labels`, no `open-pull-requests-limit`, no `ignore`.
- `commit-message: prefix: chore, include: scope` yields titles like `chore(deps): bump ...`
  (seen in recent commits `1f62a6b`, `bfba499`).

### Open Dependabot PRs (from the orchestrator, verified from the owner's CI logs)
- **#16**: bumps only `github/codeql-action/init` 4.38.2 -> 4.38.3.
- **#14**: bumps only `github/codeql-action/analyze` 4.38.2 -> 4.38.3.
- Each leaves `codeql.yml` with `init` and `analyze` on different versions.
- CodeQL on those branches fails with:
  `##[error]Loaded a configuration file for version '4.38.3', but running version '4.38.2'`
  and the warning "Not all workflow steps that use `github/codeql-action` actions use the same
  version". Job status: "configuration error".
- Already merged: #13 (setup-uv to v10.3.0), #15 (setup-node to v7.1.0).
- The fact that Dependabot opened two PRs for one release shows it treats `.../init` and
  `.../analyze` as separate dependencies in this config (verify the exact dependency names it
  uses; the PR titles would show them).

### SHAs
- Old (4.38.2): `2892aa5e19bbd11bc0cff5427e3b750a04d9e3c2`.
- New (4.38.3): `24c54180a607b1449ed407dd24f251e4e9147c8d`. **Source: the compare range in PR
  #16's commit message, as relayed by the orchestrator. Not verified against the `v4.38.3` tag.**
  The builder or reviewer should verify it where possible (for example the T0.4 RESUME A method:
  `gh api repos/github/codeql-action/commits/v4.38.3 --jq .sha`), and check that PR #14 uses the
  same SHA. The sandbox blocks network, so this needs the owner (Open question 3).

### Checks that touch these files
- `.pre-commit-config.yaml` hook `actionlint` runs on `files: ^\.github/workflows/.*\.ya?ml$`
  (`scripts/pre-commit-actionlint.sh`, pinned actionlint). It covers `codeql.yml`, not
  `dependabot.yml`.
- T0.4 plan "Check W" (never saved to a file) required `dependabot.yml` to equal an exact dict with
  no `groups`, and every `uses:` to match `@[0-9a-f]{40}` with a ` # vX.Y.Z` comment and a
  publisher in `{actions, github, astral-sh}`. It is a historical verification tool; its exact
  `DEPENDABOT` match would no longer hold after this chore.
- `just check` covers apps only; it does not lint workflow or Dependabot files.

### Documentation that describes this
- README line 125: "Dependabot proposes updates for the pinned GitHub Actions weekly." Remains
  true with a group; not in the 2-file scope.
- README lines 121-122 describe CodeQL; no version is mentioned.
- No ADR covers Dependabot or SHA pinning; D22 mentions `codeql.yml` only for what it analyses.

---

## 5. Inputs and outputs

Inputs:
- `.github/workflows/codeql.yml`, `.github/dependabot.yml` (section 4).
- The 4.38.3 SHA (section 4; unverified).

Outputs (repo changes):
- `.github/workflows/codeql.yml`: lines 40 and 46 point at the 4.38.3 SHA with `# v4.38.3`.
- `.github/dependabot.yml`: a `groups` entry under the single `github-actions` update.

Outputs (GitHub side, not file changes):
- CodeQL runs on this PR's `pull_request` event using the PR's own `codeql.yml`, so the PR run is
  the first proof the bump works (three matrix jobs: `actions`, `javascript-typescript`, `python`).
- After merge, Dependabot re-reads `dependabot.yml` on `main` (verify timing: on the next scheduled
  run or on a config change).
- The owner closes #14 and #16. Dependabot may also close them itself once `main` already has
  4.38.3 (verify).

---

## 6. Constraints

- **Pin format** (T0.4 answer 11): `owner/repo/path@<40 lowercase hex> # vX.Y.Z`. Both lines must
  use the identical SHA and identical comment `# v4.38.3`.
- **No guessed SHAs** (T0.4 plan). The SHA comes from PR #16's text; verification against the tag
  needs network, which the sandbox blocks (owner memory: never disable the sandbox without owner
  approval).
- **Scope**: two files. Nothing else in `codeql.yml` changes (checkout pin, languages, suite,
  permissions, schedule, timeout). Dependabot stays `github-actions` only, `directory: /`,
  `commit-message` unchanged.
- **ASCII only** in workflow files (T0.4 plan Check W rule; the files are ASCII today).
- **actionlint** must pass on `codeql.yml` at commit time (pre-commit hook).
- **Workflow**: branch `chore-codeql-4-38-3`, conventional commit (`chore:`), one PR, `just check`
  before pushing, never merge. Commits and pushes are owner-run under the sandbox (precedent
  T0.2-T0.4).
- **Platform**: CodeQL runs on `ubuntu-latest` on GitHub. Nothing runs locally; mlx-lm not involved.

---

## 7. Edge cases

1. **Bumping only one line.** Exactly the #14/#16 failure: `init` at 4.38.3, `analyze` at 4.38.2
   gives "Loaded a configuration file for version '4.38.3', but running version '4.38.2'".
2. **Same version comment, different SHAs** (for example a copy-paste of the old SHA on one line
   with `# v4.38.3` on both). The comment is not what GitHub runs; the SHA is. The mismatch would
   reproduce Edge case 1 while looking correct in review.
3. **SHA is the tag object, not the commit.** For annotated tags, `git ls-remote` shows the tag
   object SHA and a `^{}` commit SHA; `uses:` needs the commit (verify which form PR #16's compare
   range shows; Dependabot normally writes the commit SHA).
4. **Group pattern does not match the dependency names.** If Dependabot names them
   `github/codeql-action/init` and `github/codeql-action/analyze`, a pattern of exactly
   `github/codeql-action` may not match either (verify Dependabot's matching for action subpaths
   and wildcard `*` behaviour). Example: the next release again opens two PRs.
5. **Group too wide.** A pattern like `*` groups every action (checkout, setup-node, cache,
   setup-uv) into one PR. One bad bump (for example a new major of `setup-uv` that needs config
   changes) then holds back all others. This is a scope choice (Open question 1).
6. **Major-version bumps inside a group.** A group by default includes major, minor and patch
   updates (verify). A future `github/codeql-action` v5 would arrive grouped; that is still
   consistent (both steps move together).
7. **Security updates vs version updates.** `groups` apply to version updates by default; security
   updates may still arrive ungrouped unless `applies-to` says otherwise (verify). Low risk for
   actions.
8. **Open #14 and #16 after merge.** Once `main` has 4.38.3, Dependabot should detect the
   dependency is up to date and close or mark them obsolete (verify). If the owner closes them
   first, Dependabot may treat a closed PR as "ignore this version" for that dependency (verify:
   closing a Dependabot PR without merging can cause it not to reopen that version). Harmless here
   because `main` already has the version.
9. **A newer CodeQL release (4.38.4+) lands before this PR merges.** Dependabot would then propose
   versions past 4.38.3; this PR is still valid but immediately out of date.
10. **Header comments become stale.** `dependabot.yml` line 1 and `codeql.yml` line 3 describe
    Dependabot behaviour. Neither mentions grouping; neither becomes false with a group.
11. **`upload-sarif` or other codeql-action subpaths.** Not used in this repo today, but a pattern
    covering `github/codeql-action/*` would include them if added later.
12. **CodeQL is not a required check.** A red CodeQL run on this PR does not block merging, so the
    owner must look at it explicitly to confirm the fix.

---

## 8. Risks

1. **Unverified SHA.** The only source for `24c54180...` is PR text relayed second-hand. A one
   character error is invisible in review and only shows up as a failed run.
2. **Ineffective group.** A pattern that does not match Dependabot's dependency names gives no
   error; the problem only reappears on the next CodeQL release.
3. **Decision-log drift.** Grouping changes how T0.4 answer 11's Dependabot behaves. If it needs a
   record and none is made, or a full ADR is made where a comment would do, the log becomes
   inconsistent (Open question 2).
4. **Closing #14/#16 in the wrong order.** Closing them before this PR merges leaves `main` on
   4.38.2 (still working); closing is safe in either order, but merging either one alone breaks
   CodeQL on `main`.

---

## 9. Scope boundaries (facts, not decisions)

- In scope: lines 40 and 46 of `codeql.yml`; a `groups` entry in `dependabot.yml`.
- Out of scope: README, ADRs (unless Open question 2 says otherwise), `ci.yml`, `audit.yml`,
  `actions/checkout` pin, Dependabot schedule and commit-message settings, closing #14/#16
  (owner).

---

## 10. Open questions

1. **What should the Dependabot group cover?** Only `github/codeql-action` (its `init` and
   `analyze` steps, and any other subpath added later), or every GitHub Action in one weekly PR?
   - In plain terms: should Dependabot bundle just the two CodeQL pieces that must always move
     together, or bundle all action updates into one PR each week?
   - Suggested default: CodeQL only. Other actions (checkout, setup-node, cache, setup-uv) keep
     arriving as separate PRs, so one bad update does not hold back the rest, which matches the
     task goal.

2. **Does grouping need a decision record?** The Dependabot setup comes from T0.4 owner answer 11
   ("Add Dependabot for GitHub Actions only"), which is not a D-row or ADR. Grouping does not
   change what is updated or how often, only how PRs are bundled.
   - In plain terms: is this a change to an earlier decision that needs writing up in
     `docs/decisions/`, or just a config tweak explained in a comment in `dependabot.yml`?
   - Suggested default: no ADR or amendment; a short comment in `dependabot.yml` saying why
     CodeQL updates are grouped (init and analyze must share a version). The schedule stays
     weekly.

3. **Who verifies the 4.38.3 SHA, and how?** The SHA `24c54180a607b1449ed407dd24f251e4e9147c8d`
   comes from PR #16's commit message. Subagents cannot reach GitHub from the sandbox.
   - In plain terms: someone with network access needs to confirm that this long code really is
     the official 4.38.3 release before it goes in.
   - Suggested default: the owner runs
     `gh api repos/github/codeql-action/commits/v4.38.3 --jq .sha` (the T0.4 method) and pastes
     the output before the commit; the builder uses the SHA only if it matches. The green CodeQL
     run on the PR is the final proof.

## Owner answers

Date: 2026-10-15

1. Group ALL GitHub Actions updates into one Dependabot PR per week, not only codeql-action. Owner's words: "bundle all actions into one PR every week, and i want you to do that automatically every week on sundays, i want you to update and make a PR and then i can review it". Implementation reading (main session, to be confirmed at the plan gate): Dependabot itself does this, with `schedule.interval: weekly` and `schedule.day: sunday`, plus a `groups` entry matching every action (`patterns: ["*"]`). It opens one PR each Sunday for the owner to review. No Claude-side scheduled job is needed. The owner reviews and merges, as now. Accepted trade-off: one failing update holds back the whole weekly bundle until it is fixed.
2. Suggested default accepted: no ADR or amendment. Add a short comment in `dependabot.yml` saying why updates are grouped (CodeQL init and analyze must share a version, and the owner wants one weekly PR). Answer 1 moves the schedule day to Sunday.
3. SHA verified by the owner on 2026-10-15: `gh api repos/github/codeql-action/commits/v4.38.3 --jq .sha` printed `24c54180a607b1449ed407dd24f251e4e9147c8d`, which matches PR #16. The builder uses exactly this SHA, with the comment `# v4.38.3`.
