# chore-source-map-js brief: move source-map-js to >=1.2.2 so `just security` passes

Analyst: phase 1 (Understand). This brief records facts only. It does not design a solution.
Sources: CLAUDE.md; the task message from the orchestrator (advisory facts from the owner's
`just security` run on 2026-10-15); `apps/web/package.json`; `apps/web/pnpm-lock.yaml`; the
installed manifests under `apps/web/node_modules/.pnpm/` (for dependency ranges); `justfile`
(`security`, `security-web`); `.github/workflows/audit.yml`, `ci.yml`; `.github/dependabot.yml`
(via the chore-codeql brief and plan); `docs/decisions/D22-security-scanning.md`;
`docs/plans/T0.2-brief.md` and `-plan.md` (owner answer 11, pinning); `docs/plans/T0.4-brief.md`
(lockfile constraints, owner answer 6, edge case 7); `docs/plans/chore-security-scans-brief.md`
and `-plan.md` (owner answer 7, audit level); `docs/plans/chore-codeql-brief.md` (format).

Limits of this analysis:
- This is a chore, not a section-16 task. There are no design-doc acceptance criteria.
- No shell and no network. The advisory details (ID, title, ranges, paths) come from the owner's
  `pnpm audit` output as relayed by the orchestrator, not from the npm registry or GitHub. Whether
  `source-map-js@1.2.2` is published, its contents and its publish date are not verified here.
  Statements about pnpm 12 behaviour marked "(verify)" come from general knowledge of earlier pnpm
  versions, not from pnpm 12 docs.
- There is no `.npmrc` and no `pnpm-workspace.yaml` anywhere in the repo, and `package.json` has
  no `pnpm` field. pnpm runs with defaults.

---

## 1. Task

- **ID:** `chore-source-map-js` (not from design doc section 16)
- **Title:** none in the design doc. Working description: get `source-map-js` to `>=1.2.2` in
  `apps/web/pnpm-lock.yaml` with the smallest deliberate change, so that `just security` passes,
  without unintended upgrades.
- **Acceptance criteria:** the design doc has none. Agreed goal, as passed on by the orchestrator:
  1. `source-map-js` resolves to `>=1.2.2` in the lockfile.
  2. `just security` passes (today `security-web` fails on GHSA-68fv-2mgg-jv7q).
  3. No other package version changes unintentionally.
- Branch: `chore-source-map-js` (off `main`, which includes chore-codeql #18).

---

## 2. Why it matters

What this enables:
- `just security` goes green again. The reviewer (phase 4) runs it on every task and the PR
  template asks for it, so every PR until this is fixed carries a known red result that has
  to be explained.
- The weekly `audit.yml` job (`just security-web` step) stops failing on `main`.

What breaks if it is wrong:
- If the change pulls in other upgrades (for example a broad `pnpm update`), Vite, Tailwind,
  Vitest or Biome could move. That is the section 18 risk "Library changes mid-project /
  Behaviour drift" that exact pinning (T0.2 owner answer 11) exists to prevent, and it could
  change telemetry or test behaviour without anyone deciding it.
- If the lockfile and `package.json` disagree, CI's `pnpm install --frozen-lockfile` (`ci.yml`
  line 60; required check `web`) fails, and every PR is blocked.
- If the fix only silences the audit (an exception) the vulnerable version stays installed, and
  the exception must be remembered and removed later.

---

## 3. Governing decisions

| Source | Decision | What it forces here |
|---|---|---|
| Design doc section 18 (as quoted in T0.1/T0.4 briefs and `dependabot.yml`) | Risk "Library changes mid-project / Behaviour drift", mitigation "Lockfiles; no upgrades between freeze and retest". `dependabot.yml`: "lockfiles change only on purpose (design doc section 18)". | Any lockfile change must be deliberate and limited to what is intended. Whether the experiment freeze has happened is not stated in the files read; the project is at M1 (T1.4 just merged), which suggests it has not (verify with the owner if it matters). |
| T0.2 owner answer 11 | "exact versions (no `^`) for the core tools (Vite, React, TypeScript, Biome, Vitest, Tailwind), with the lockfile as the backstop for transitive deps. Add a `packageManager` field pinning the pnpm version". | `source-map-js` is transitive, so the lockfile is its only pin. Direct dependency pins in `package.json` must not change. pnpm stays 12.6.0. |
| T0.4 constraints (brief section 6) | "Lockfiles are the source of truth ... Installs must not rewrite them: ... `pnpm install --frozen-lockfile`." | The new lockfile must install cleanly with `--frozen-lockfile` in CI. |
| T0.4 owner answer 11 / `dependabot.yml` | Dependabot updates GitHub Actions only, "not npm/uv". | Dependabot will not open a fix PR for this; it is a manual change. |
| D22 (and T0.3/T0.4 amendments) | `security-web` is `pnpm audit --audit-level=high`, dev dependencies included. pnpm audit is not a required check; it runs in `audit.yml` weekly and by hand. | The fix must make `pnpm audit --audit-level=high` exit 0. D22 says nothing about audit exceptions, ignores or overrides. Changing the audit level or excluding dev dependencies would change D22. |
| chore-security-scans owner answer 7 | "fail on high/critical only ... Don't pass `--prod`; include dev dependencies too, since supply-chain risk in build tooling still matters." | A dev-only, build-time package is still in scope of the audit; "it is only a dev dependency" is not an exemption under this answer. |
| chore-security-scans plan, out of scope | "Do not add `nosemgrep` comments, audit ignores, pnpm overrides or dependency upgrades, whatever step 7 reports." | That was a scope limit for that chore only, not a standing rule. No document forbids or permits overrides or audit ignores going forward. |
| Design doc section 2 / 17.3 (as quoted in earlier briefs) | "Any change to a decision gets a short ADR in docs/decisions/." | Relevant only if an approach changes D22 (for example an audit exception). |
| CLAUDE.md | Conventional commits; one task per PR; `just check` before pushing; never push to `main`; never merge. | Commit type `chore:` or `fix:` (open). Owner runs network steps, commits and pushes under the sandbox. |

---

## 4. Current state

### `apps/web/package.json` (relevant lines, verbatim)
```json
  "packageManager": "pnpm@12.6.0",
  "engines": {
    "node": ">=22.12.0 <23"
  },
```
devDependencies include `"@tailwindcss/vite": "4.3.3"`, `"@vitejs/plugin-react": "6.1.1"`,
`"tailwindcss": "4.3.3"`, `"vite": "8.3.1"`, `"vitest": "4.1.11"`. No `pnpm` field (so no
`pnpm.overrides`, no `pnpm.auditConfig`). `source-map-js` is not a direct dependency.

### `apps/web/pnpm-lock.yaml`
- The file holds two YAML documents. Lines 1-157: a pnpm-12 document for
  `packageManagerDependencies` (`pnpm: specifier 12.6.0, version 12.6.0` and the `@pnpm/exe.*`
  binaries). Lines 158 onward: the project lockfile, `lockfileVersion: '9.0'`, with
  `settings: autoInstallPeers: true, excludeLinksFromLockfile: false`. No `overrides:` section.
- Exactly one `source-map-js` version is locked: `source-map-js@1.2.1` (packages line 793,
  snapshot line 1348 `source-map-js@1.2.1: {}`; it has no dependencies of its own).
- Exactly two packages depend on it directly (snapshots, verbatim):
  ```yaml
  '@tailwindcss/node@4.3.3':
    dependencies:
      ...
      source-map-js: 1.2.1
  postcss@8.5.28:
    dependencies:
      nanoid: 3.3.19
      picocolors: 1.1.1
      source-map-js: 1.2.1
  ```
- `postcss@8.5.28` is pulled in by `vite@8.3.1(@types/node@22.20.4)(jiti@2.7.0)` (`postcss: 8.5.28`).
  vite is reached through the direct `vite` dependency, `@vitejs/plugin-react`, `@tailwindcss/vite`
  and vitest, which explains the 6 paths in the audit report.

### Declared ranges of the parents (from installed manifests in `apps/web/node_modules/.pnpm/`)
- `postcss@8.5.28/node_modules/postcss/package.json` line 83: `"source-map-js": "^1.2.1"`
  (line 40, `"source-map-js": false`, is in the `browser` field, not a dependency range).
- `@tailwindcss+node@4.3.3/node_modules/@tailwindcss/node/package.json` line 41:
  `"source-map-js": "^1.2.1"`.
- **Fact: `1.2.2` satisfies `^1.2.1` for both parents.** So a newer `source-map-js` can be
  resolved without changing `postcss`, `@tailwindcss/node`, `vite` or any direct dependency.
  (The lockfile v9 format does not record transitive ranges; these come from the installed
  `node_modules`, which matches the lockfile versions.)
- `^1.2.1` also admits any later `1.x` (for example a hypothetical `1.3.0`). Whatever command is
  used, the version it picks is the registry's highest matching `1.x`, not necessarily `1.2.2`.

### History
- `source-map-js@1.2.1` has been locked since T0.2 (commit `ffd48a9`, "pin exact dependency
  versions"). `main` fails `security-web` the same way. semgrep, bandit and pip-audit pass.

### Checks that touch the lockfile
- `ci.yml` (required `web` job): `pnpm install --frozen-lockfile` (line 60), pnpm store cache keyed
  on `apps/web/pnpm-lock.yaml` (line 58), then the D21 web checks (biome, tsc, vitest, vite build).
- `audit.yml` (weekly Monday 04:40 UTC and `workflow_dispatch`, not required): `just security-web`.
- `justfile` `security-web` (verbatim core): probes `https://registry.npmjs.org/` with curl, skips
  if unreachable, else `cd apps/web` and `pnpm audit --audit-level=high`.
- `.pre-commit-config.yaml` line 2 notes tool versions come from the app lockfiles.
- `just check` does not run `pnpm audit`.

---

## 5. Inputs and outputs

Inputs:
- `apps/web/pnpm-lock.yaml`, `apps/web/package.json` (section 4).
- The npm registry (metadata and tarball for `source-map-js@1.2.2` or later; advisory database
  for `pnpm audit`). Needs network.

Outputs (repo changes, depending on the approach chosen):
- `apps/web/pnpm-lock.yaml`: the `source-map-js` package and snapshot entries, and the two
  dependent snapshot lines, move from `1.2.1` to the new version with a new integrity hash.
- Possibly `apps/web/package.json` (only for approaches (b) or (d) in section 9).
- Possibly a docs/decisions file (only if a decision changes; Open question 2).

Outputs (not file changes):
- `apps/web/node_modules` refreshed on the owner's machine.
- `just security` summary showing `security-web: passed`.
- CI `web` job green with `--frozen-lockfile`.

---

## 6. Constraints

- **Sandbox / network.** Subagents cannot reach `registry.npmjs.org` (owner memory: never disable
  the sandbox without owner approval). Every step that resolves, downloads or audits
  (`pnpm update`, `pnpm install` without `--offline`, `pnpm audit`, `just security`) is owner-run.
  The `security-web` recipe would report "couldn't reach the registry, skipping" inside the
  sandbox, which is a skip, not proof of a fix. Commits and pushes are owner-run as well
  (precedent T0.2-T0.4, chore-codeql).
- **pnpm version.** `packageManager: pnpm@12.6.0`. A different pnpm may rewrite the lockfile
  format or the first YAML document (T0.2 brief line 356; chore-security-scans brief edge case 13).
  Commands should run under 12.6.0 (corepack).
- **Exact pins stay.** No direct dependency in `package.json` changes version.
- **Frozen install must pass.** After the change, `pnpm install --frozen-lockfile` must succeed in
  CI, and `pnpm install --frozen-lockfile --offline` should succeed once the store has the new
  tarball (T0.2 plan check 7).
- **D22 stays as is** unless the owner decides otherwise: `--audit-level=high`, dev dependencies
  included, no `--prod`.
- **Platform.** Linux CI and macOS dev both use the same lockfile; `source-map-js` is pure JS
  with no platform binaries. mlx-lm is not involved.
- **Workflow.** One PR, conventional commit, `just check` before pushing, never merge.

---

## 7. Edge cases

1. **Broad update by accident.** `pnpm update` without a package name (or with `--latest`)
   re-resolves every range. With exact pins the direct deps stay, but other transitive packages
   inside their `^` ranges can move (for example `nanoid`, `picocolors`, `lightningcss`). Example:
   a diff that touches dozens of lockfile entries instead of three lines plus one package entry.
2. **`--latest` on a named package.** `pnpm update --latest <pkg>` targets direct dependencies and
   rewrites `package.json` specifiers (verify for transitive targets in pnpm 12). Not what a
   transitive fix needs.
3. **Depth semantics.** Whether `pnpm update source-map-js` alone updates a transitive package, or
   needs `--depth Infinity` / `-r`, differs between pnpm versions (verify for 12.6.0). Example: the
   command exits 0 and the lockfile is unchanged.
4. **Newer than 1.2.2.** If `1.2.3` or `1.3.0` exists by the time the owner runs the command, a
   range-based update picks it. That still satisfies `>=1.2.2` but is not exactly 1.2.2.
5. **Release-age gate.** Newer pnpm versions have a `minimumReleaseAge` setting that refuses very
   recently published versions (verify whether pnpm 12 enables it by default). If 1.2.2 was
   published days ago, resolution could silently keep 1.2.1 or fail.
6. **Overrides change the lockfile shape.** A `pnpm.overrides` entry (or `overrides` in a
   `pnpm-workspace.yaml`; which location pnpm 12 reads is a verify item) adds an `overrides:`
   block to the lockfile. A frozen install with a `package.json` override that is missing from
   the lockfile (or the other way round) fails with an outdated-lockfile error. The override then
   stays forever unless someone removes it, and it can also force the version for future parents
   whose ranges do not include it.
7. **Override location in pnpm 12.** pnpm 10 moved many settings from `package.json` `pnpm` field to
   `pnpm-workspace.yaml`. This repo deliberately has no `pnpm-workspace.yaml` (T0.2 plan: "Rejected:
   a root `pnpm-workspace.yaml`"; that rejection was about a root file, an `apps/web` one is not
   addressed). Whether `pnpm.overrides` in `package.json` still works in 12.6.0 is a verify item.
8. **`pnpm audit --fix`.** It writes overrides automatically (in some pnpm versions to
   `package.json`, in newer ones to `pnpm-workspace.yaml`; verify) and may add entries for every
   advisory, not just this one. Its output is not a minimal change by construction.
9. **Two YAML documents.** Any lockfile write also rewrites the first document
   (`packageManagerDependencies`). Under pnpm 12.6.0 it should stay identical; under another pnpm
   it may change.
10. **Stale `node_modules`.** The owner's `node_modules` holds 1.2.1. `pnpm audit` reads the
    lockfile, not `node_modules`, so audit can pass while `node_modules` is stale until the next
    `pnpm install`.
11. **Advisory drift after the fix.** A new high advisory in any other web package could appear
    before or after this PR; `just security` would fail again for a different reason. Example:
    the fix lands, and next Monday `audit.yml` is red on a different package.
12. **Upstream fix arrives later.** A future postcss or `@tailwindcss/node` release might raise
    its range to `^1.2.2`. With a lockfile-only fix nothing needs undoing; with an override, the
    override becomes redundant.
13. **CI cache.** The pnpm store cache key changes with the lockfile, so the first CI run after
    the change downloads more. Harmless.

---

## 8. Risks

1. **Unintended upgrades.** The most likely failure: a command that re-resolves more than
   `source-map-js`, producing a large lockfile diff that slips through review.
2. **pnpm 12 behaviour unknown here.** pnpm 12.6.0 is newer than anything this analysis can
   check offline. Flags (`--depth`), override location and release-age defaults may differ from
   earlier versions; the owner's first run is the real test.
3. **Silencing instead of fixing.** An audit exception leaves 1.2.1 installed and, if forgotten,
   could also hide a future advisory with the same ID scope.
4. **Owner-run steps out of order.** If the owner commits the lockfile without running
   `pnpm install --frozen-lockfile` and `just check`, CI is the first place a mismatch shows up.

---

## 9. Candidate approaches (identified, not chosen)

| | Approach | What changes | Compatible with existing decisions? |
|---|---|---|---|
| (a) | Lockfile-only targeted update (for example `pnpm update source-map-js`, possibly with `--depth`) | `pnpm-lock.yaml` only: `source-map-js` entry and the two dependent lines | Yes. 1.2.2 is inside both parents' `^1.2.1`, so no parent or direct pin moves (T0.2 answer 11). It is a deliberate, narrow lockfile change (section 18). D22 untouched. Needs network (owner-run) and care against edge cases 1-5. |
| (b) | `pnpm.overrides` entry (for example `"source-map-js": ">=1.2.2"` or an exact version) | `package.json` (or a new `pnpm-workspace.yaml`) plus a lockfile `overrides:` block | Not forbidden by any decision. Adds a permanent manifest setting no decision covers, and possibly a new file the T0.2 layout avoided. Only needed when a parent's range excludes the fix, which is not the case here. |
| (c) | Wait for upstream (vite/postcss/tailwind) releases | Later, a direct dependency bump | Leaves `just security` red now (goal not met). A later direct bump is a larger section 18 change than (a). |
| (d) | Documented audit exception (for example `pnpm.auditConfig.ignoreGhsas`, verify name in pnpm 12) | `package.json` plus a written justification | Changes how D22's `security-web` behaves, so it needs an ADR/amendment (section 2 rule). Conflicts with owner answer 7's intent (dev deps included). The vulnerable version stays. |

---

## 10. Open questions

1. **Which approach?** Facts in sections 4 and 9 show a lockfile-only update is possible without
   moving any other package.
   - In plain terms: should we just bump this one small hidden package in the lockfile, or use a
     heavier tool (a permanent override, waiting for upstream, or an audit exception)?
   - Suggested default: (a), lockfile-only. Accept any `1.x` at or above 1.2.2 that the update
     picks, and reject the result if any package other than `source-map-js` changes.

2. **Commit type and record.** No decision changes under (a).
   - In plain terms: is this a routine dependency fix that just needs a clear commit message, or
     does it need a note in `docs/decisions/`?
   - Suggested default: no ADR. One commit, `fix(deps): bump source-map-js to <version>
     (GHSA-68fv-2mgg-jv7q)` or `chore(deps): ...` as the owner prefers, with the PR body naming the
     advisory and listing the lockfile lines that changed.

3. **Who runs the network steps?** The sandbox blocks the npm registry.
   - In plain terms: you will need to run the update command and `just security` yourself, then
     paste the output so the builder can check the diff.
   - Suggested default: the owner runs, from `apps/web` with pnpm 12.6.0, the update command the
     plan specifies, then `pnpm install --frozen-lockfile`, `just check` and `just security`, and
     pastes `git diff --stat` plus the security summary. The builder then verifies that only
     `source-map-js` changed.

## Owner answers

Date: 2026-10-19

The owner accepted every suggested default ("all defaults"). Recorded explicitly:

1. Approach (a): a lockfile-only update. Accept any `1.x` at or above 1.2.2 that the update picks, and reject the result if any package other than `source-map-js` changes in `apps/web/pnpm-lock.yaml`.
2. No ADR. One commit. The main session recommended the `fix(deps):` type because it fixes a security advisory: `fix(deps): bump source-map-js to <version> (GHSA-68fv-2mgg-jv7q)`. The PR body names the advisory and lists the lockfile lines that changed.
3. The owner runs the network steps from `apps/web` with pnpm 12.6.0: the update command the plan specifies, then `pnpm install --frozen-lockfile`, `just check` and `just security`. The owner pastes `git diff --stat` and the security summary, and the builder then checks that only `source-map-js` changed.
