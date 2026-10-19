# chore-source-map-js plan: lockfile-only bump of source-map-js to >=1.2.2 (GHSA-68fv-2mgg-jv7q)

Architect: phase 2 (Blueprint). Source: `docs/plans/chore-source-map-js-brief.md`, including
"## Owner answers" (2026-10-19, all defaults), which are binding.
Also read: CLAUDE.md, `docs/plans/chore-codeql-plan.md` (format precedent),
`apps/web/pnpm-lock.yaml` (every `source-map-js` line).
Branch: `chore-source-map-js` (already checked out, off `main`).

## Revisions

- 2026-10-19: the owner approved the plan with one change. The main session checked the change
  against the help text of the installed pnpm 12.6.0 (`pnpm update --help`, run from `apps/web`):
  - `--depth <DEPTH>`: "How deep to inspect dependencies. `0` means top-level dependencies only.
    Defaults to unlimited". So the default already reaches non-direct packages.
  - `-L, --latest`: "Ignore version ranges in package.json: bump the matched packages to their
    latest version and rewrite the manifest ranges". So without `--latest`, package.json is not
    rewritten.
  - `pnpm view` exists (aliases `info`, `show`, `v`).

  The changes that follow from this:
  - The main command is now `pnpm update source-map-js`, without `--depth`. The
    `--depth Infinity` form is removed: it is redundant, and pnpm may reject it as a non-integer.
  - The old fallback F1 is removed, because it is now the main command.
  - F2 is the only fallback.
- Flag status after this revision:
  - **Verified** from the 12.6.0 help text above: `--depth` semantics, `--latest` behaviour, and
    that `pnpm view` exists.
  - **Still unverified:** that `source-map-js@1.2.2` is published (and its `engines` field), and
    whether pnpm 12 applies a minimum-release-age delay by default.

---

## 1. Summary

When this plan is done:
- `apps/web/pnpm-lock.yaml` locks exactly one `source-map-js`, a `1.x` at or above `1.2.2`, and
  both dependents (`@tailwindcss/node@4.3.3`, `postcss@8.5.28`) point to it.
- Nothing else in the repo changes: no `package.json` edit, no overrides, no other package moves.
- `just security` passes (`security-web` no longer fails on GHSA-68fv-2mgg-jv7q), and `just check`
  passes. One commit `fix(deps): bump source-map-js to <version> (GHSA-68fv-2mgg-jv7q)`, no ADR.

## 2. Design

- **Targeted update by name (owner answer 1, approach (a)).** `source-map-js` is transitive, and
  both parents declare `^1.2.1`, so any `1.x >= 1.2.2` resolves without moving a parent.
  - Main command, from `apps/web`: `pnpm update source-map-js`.
  - Naming the package limits re-resolution to that package.
  - pnpm 12.6.0's default `--depth` is unlimited, so the command reaches a non-direct dependency.
  - There is no `--latest`, so `package.json` ranges are not rewritten.
  - Rejected: bare `pnpm update` (re-resolves every range), and `pnpm audit --fix` and
    `pnpm.overrides` (both write overrides, which owner answer 1 forbids).
- **One fallback, decided by the verify script, not by judgement.**
  - F2 applies if the main command moves another package, edits `package.json`, or changes
    nothing.
  - The owner reverts. The builder then hand-edits the five `source-map-js` lines in the
    lockfile, using the version and `dist.integrity` the owner reads from the registry.
  - `pnpm install --frozen-lockfile` then downloads the tarball and checks it against that
    integrity, so a wrong hash fails loudly.
- **Deterministic check.** A POSIX shell script in `.git/chore-source-map-js/verify.sh` compares
  the lockfile diff with the exact set of removed `1.2.1` lines (known from the current file) and
  the matching added lines. Anything else fails it.
- **The owner runs everything that needs the network, plus the commit** (owner answer 3;
  sandbox). The builder writes the script and message files and runs the offline verification.

## 3. File map

| File | Change |
|---|---|
| `apps/web/pnpm-lock.yaml` | Five `source-map-js` lines change from `1.2.1` to the new version, including the integrity hash (six lines if the `engines` line also changes). Changed by the owner's pnpm command, or by the builder in fallback F2. |
| `.git/chore-source-map-js/verify.sh` | Verification script (inside `.git/`, never committed, never `/tmp`). |
| `.git/chore-source-map-js/commit-msg.txt` | Commit message for the owner. |
| `.git/chore-source-map-js/pr-body.md` | PR body for phase 5 (names the advisory, lists the changed lockfile lines). |

No other file is created or modified. In particular: no `apps/web/package.json` change, no
`pnpm-workspace.yaml`, no `.npmrc`, no ADR, no test file.

---

## 4. Steps

### Step 1. Builder: write the verify script and prove it rejects an unchanged tree

- **File:** `/Users/allen/Downloads/typist-ml/.git/chore-source-map-js/verify.sh` (create the
  directory if missing). Exact content:

```sh
#!/bin/sh
# Verifies that the chore-source-map-js change touches only source-map-js in
# apps/web/pnpm-lock.yaml. Usage: sh verify.sh [base]   (base defaults to HEAD;
# pass main after the commit). Prints FAIL lines and exits 1 on any failure.
set -u
LC_ALL=C
export LC_ALL
repo=/Users/allen/Downloads/typist-ml
lock=apps/web/pnpm-lock.yaml
base=${1:-HEAD}
fail=0
bad() { printf 'FAIL: %s\n' "$*"; fail=1; }

old_hash='sha512-UXWMKhLOwVKb728IUtQPXxfYU+usdybtUrK/8uGE8CQMvrhOpwvzDBwj0QhSL7MQc7vIsISBG8VQ8+IDQxpfQA=='

# 1. Under apps/web only the lockfile changed, and package.json is untouched.
changed=$(git -C "$repo" diff --name-only "$base" -- apps/web)
[ "$changed" = "$lock" ] || bad "changed files under apps/web: [$changed], expected only $lock"
git -C "$repo" diff --quiet "$base" -- apps/web/package.json || bad "apps/web/package.json changed"

# 2. Removed lines are exactly the source-map-js@1.2.1 lines (optionally its engines line).
diff_out=$(git -C "$repo" diff -U0 "$base" -- "$lock")
removed=$(printf '%s\n' "$diff_out" | grep '^-' | grep -v '^--- ' | sort)
added=$(printf '%s\n' "$diff_out" | grep '^+' | grep -v '^+++ ' | sort)
exp_removed=$(printf '%s\n' \
  '-  source-map-js@1.2.1:' \
  "-    resolution: {integrity: $old_hash}" \
  '-      source-map-js: 1.2.1' \
  '-      source-map-js: 1.2.1' \
  '-  source-map-js@1.2.1: {}' | sort)
exp_removed_eng=$(printf '%s\n%s\n' "$exp_removed" "-    engines: {node: '>=0.10.0'}" | sort)
[ "$removed" = "$exp_removed" ] || [ "$removed" = "$exp_removed_eng" ] \
  || bad "removed lines are not exactly the source-map-js@1.2.1 lines:
$removed"

# 3. The new version is a single 1.x >= 1.2.2.
v=$(printf '%s\n' "$added" | sed -n 's/^+  source-map-js@\([0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*\):$/\1/p')
printf '%s\n' "$v" | awk -F. 'NR == 1 && NF == 3 { ok = ($1 == 1 && ($2 > 2 || ($2 == 2 && $3 >= 2))) } END { exit !(ok && NR == 1) }' \
  || bad "new version [$v] is not a single 1.x >= 1.2.2"

# 4. Added lines mirror the removed ones, for version $v and nothing else.
rest=$(printf '%s\n' "$added" \
  | grep -v -x -F -e "+  source-map-js@$v:" -e "+  source-map-js@$v: {}" -e "+      source-map-js: $v" \
  | grep -Ev "^\+    (resolution: \{integrity: sha512-[A-Za-z0-9+/]+=*\}|engines: \{node: '[^']*'\})$" \
  | grep .)
[ -z "$rest" ] || bad "added lines outside source-map-js:
$rest"
n_rem=$(printf '%s\n' "$removed" | grep -c .)
n_add=$(printf '%s\n' "$added" | grep -c .)
[ "$n_add" = "$n_rem" ] || bad "added $n_add lines but removed $n_rem"
[ "$(printf '%s\n' "$added" | grep -c -x -F "+  source-map-js@$v:")" = 1 ] || bad "package entry for $v missing"
[ "$(printf '%s\n' "$added" | grep -c -x -F "+  source-map-js@$v: {}")" = 1 ] || bad "snapshot entry for $v missing"
[ "$(printf '%s\n' "$added" | grep -c -x -F "+      source-map-js: $v")" = 2 ] || bad "the two dependents do not both point to $v"
[ "$(printf '%s\n' "$added" | grep -c '^+    resolution: ')" = 1 ] || bad "expected exactly one new resolution line"

# 5. Whole file: one copy only, and 1.2.1 is gone.
[ "$(grep -c '^  source-map-js@' "$repo/$lock")" = 2 ] || bad "expected one package entry and one snapshot entry for source-map-js"
grep -Eq 'source-map-js(@|: )1\.2\.1' "$repo/$lock" && bad "source-map-js 1.2.1 still referenced"

if [ "$fail" = 0 ]; then
  printf 'PASS: only source-map-js changed in %s, now %s\n' "$lock" "$v"
else
  exit 1
fi
```

  The `old_hash` value is copied from line 794 of the current lockfile. Copy and paste it; do not
  retype it.

- **Tests for this step** (no pytest; this is a config-only chore, so the script is the test):
  - `verify_rejects_clean_tree`: the input is the unchanged branch. Run
    `sh /Users/allen/Downloads/typist-ml/.git/chore-source-map-js/verify.sh`.
    Expected: exit 1, and the output includes `FAIL: changed files under apps/web: [], expected
    only apps/web/pnpm-lock.yaml` and `FAIL: source-map-js 1.2.1 still referenced`. No `PASS`
    line.
- **Also in this step (best effort, offline):** try
  `cd /Users/allen/Downloads/typist-ml/apps/web && pnpm --version && pnpm update --help`.
  - If it runs, record whether the help lists `--depth` and `--latest`, and whether `--latest`
    is off by default, and include that in the hand-off.
  - If pnpm cannot start in the sandbox (corepack download, network), say so; the owner checks
    it in Step 2.
  - Do not install or enable anything.
- **Verify:** the test above behaves as stated. `git -C /Users/allen/Downloads/typist-ml status
  --porcelain` shows no new tracked changes (`.git/` content never shows).

### Step 2. Owner: run the targeted update (network)

From `/Users/allen/Downloads/typist-ml/apps/web`:

1. `pnpm --version` must print `12.6.0`. If it does not, stop: a different pnpm may rewrite the
   lockfile.
2. Main command: `pnpm update source-map-js` (no `--latest`, no `--depth`).
3. `pnpm install --frozen-lockfile` (must exit 0; refreshes `node_modules`).
4. Paste these to the session: `git -C /Users/allen/Downloads/typist-ml diff --stat` and
   `git -C /Users/allen/Downloads/typist-ml diff -- apps/web/pnpm-lock.yaml`.

Expected stat: one file, `apps/web/pnpm-lock.yaml | 10 +++++-----` (or `12 ++++++------` if the
`engines` line changed). Any other file, a larger count, or an empty diff means go to F2.

**Fallback F2.** Use it when the main command touched `package.json`, moved another package, or
changed nothing.
- **Revert first:** `git -C /Users/allen/Downloads/typist-ml checkout -- apps/web/package.json apps/web/pnpm-lock.yaml`,
  then `pnpm install --frozen-lockfile` to put `node_modules` back.
- **Do not run more `pnpm update` variants.**
- **The owner runs and pastes:** `pnpm view source-map-js versions`,
  `pnpm view source-map-js@1.2.2 dist.integrity` and `pnpm view source-map-js@1.2.2 engines`.
  (If `pnpm view` is not available in 12.6.0, use `npm view` with the same arguments; npm ships
  with Node 22.)
- **The builder then edits `apps/web/pnpm-lock.yaml` by hand**, to version `1.2.2`, changing
  exactly these lines and nothing else:
  - line 793 `  source-map-js@1.2.1:` becomes `  source-map-js@1.2.2:`
  - line 794 `    resolution: {integrity: <old>}` becomes `    resolution: {integrity: <pasted dist.integrity>}`
  - line 795 `    engines: {node: '>=0.10.0'}` stays, unless the pasted `engines.node` differs;
    then it becomes `    engines: {node: '<pasted value>'}`
  - line 1036 and line 1314 `      source-map-js: 1.2.1` become `      source-map-js: 1.2.2`
  - line 1348 `  source-map-js@1.2.1: {}` becomes `  source-map-js@1.2.2: {}`
- **Then the owner** runs `pnpm install --frozen-lockfile` (exit 0 proves the integrity matches
  the tarball) and pastes the stat and diff as in item 4.
- **Release-age delay:** if the update keeps `1.2.1` and pnpm mentions a minimum release age, do
  not change any pnpm setting; use F2.

### Step 3. Builder: verify the lockfile diff (offline)

- **Command:** `sh /Users/allen/Downloads/typist-ml/.git/chore-source-map-js/verify.sh`
- **Pass:**
  - Exit 0 and one line: `PASS: only source-map-js changed in apps/web/pnpm-lock.yaml, now <v>`.
  - `git -C /Users/allen/Downloads/typist-ml diff --numstat` prints exactly
    `5	5	apps/web/pnpm-lock.yaml`. If it prints `6	6` because the `engines` line changed, say so
    in the hand-off.
- **Fail:** report the FAIL lines to the owner, who reverts and moves to F2 in Step 2. Never
  commit a failing result, and never weaken the script to make it pass.
- **Then** write `/Users/allen/Downloads/typist-ml/.git/chore-source-map-js/commit-msg.txt`, with
  `<v>` replaced by the version the script printed:

```
fix(deps): bump source-map-js to <v> (GHSA-68fv-2mgg-jv7q)

source-map-js 1.2.1 is affected by GHSA-68fv-2mgg-jv7q, which fails
`just security` (pnpm audit --audit-level=high). Lockfile-only update:
<v> is inside the ^1.2.1 range of both dependents (postcss 8.5.28 and
@tailwindcss/node 4.3.3), so package.json and every other locked package
stay as they are.
```

- And `/Users/allen/Downloads/typist-ml/.git/chore-source-map-js/pr-body.md`:

```
Fixes GHSA-68fv-2mgg-jv7q (high) in source-map-js, a transitive dev dependency
(via postcss and @tailwindcss/node), which failed `just security`.

Lockfile-only change, approach (a) in docs/plans/chore-source-map-js-brief.md:
source-map-js 1.2.1 -> <v>. No package.json change, no overrides, no other
package moved, no ADR.

Changed lines in apps/web/pnpm-lock.yaml:

<paste the output of: git diff -U0 -- apps/web/pnpm-lock.yaml | grep '^[-+]' | grep -v '^\(---\|+++\) '>

Checks: verify.sh PASS; pnpm install --frozen-lockfile, just check and just
security pass (summary below).

<security summary pasted by the owner in Step 5>
```

  Fill the first placeholder now; leave the second for Step 5.

### Step 4. Owner: commit

From the repo root:
`git add apps/web/pnpm-lock.yaml && git commit -F .git/chore-source-map-js/commit-msg.txt`

Pass: one commit, and `git show --stat HEAD` lists only `apps/web/pnpm-lock.yaml`. The builder
then re-runs `sh /Users/allen/Downloads/typist-ml/.git/chore-source-map-js/verify.sh main` and
expects the same PASS line.

### Step 5. Owner: `just check` and `just security`

From the repo root, run `just check` (exit 0), then `just security`, and paste the security
summary.
- Pass: `security-web: passed` (an "unreachable, skipping" line is not a pass), and the other
  security recipes pass as before.
- If `security-web` fails on a different advisory (brief edge case 11), stop and report it to the
  owner; do not fix it in this PR.
- The builder pastes the summary into the second placeholder of `pr-body.md`.

### Step 6. PR (phase 5, /ship)

The owner pushes `chore-source-map-js`, and the PR uses `.git/chore-source-map-js/pr-body.md`.
The required `web` CI job (`pnpm install --frozen-lockfile`) must be green.

---

## 5. Dependencies

None added. `source-map-js` moves within its existing range as a locked transitive package.

## 6. Acceptance check

| Criterion (brief section 1, owner answers) | Proven by |
|---|---|
| `source-map-js` resolves to a single `1.x >= 1.2.2` | Step 3, verify.sh checks 3 and 5 |
| No other package changes; no `package.json` change; no overrides | Step 3, verify.sh checks 1, 2 and 4 (exact removed set, no other added lines); numstat `5 5` |
| Lockfile installs frozen | Step 2 item 3; CI `web` job (Step 6) |
| `just security` passes | Step 5 pasted summary |
| `just check` passes | Step 5 |
| One `fix(deps):` commit, no ADR, PR names the advisory and lists changed lines | Steps 3 and 4 (message files, `git show --stat`) |
| Owner runs network steps and commit | Steps 2, 4, 5 |

## 7. Out of scope

- `apps/web/package.json` (including the `packageManager` field and every exact pin).
- Any other lockfile entry, including the first YAML document (`packageManagerDependencies`).
- `pnpm.overrides`, `pnpm-workspace.yaml`, `.npmrc`, audit ignores, changing `--audit-level`
  or the `justfile`, `audit.yml`, `ci.yml`, D22, `docs/decisions/`.
- Fixing any other advisory that `just security` might show.
- `services/api` and its lockfile.
- Editing `verify.sh` to accept a result it rejected.

## 8. Review focus

1. **The lockfile diff is exactly the `source-map-js` lines**: five (or six) removed, the same
   number added, both dependents updated, the first YAML document untouched. Re-run
   `verify.sh main`.
2. **`verify.sh` itself**: the `old_hash` matches the old line 794 byte for byte, the removed set
   is exact, and the version comparison accepts only `1.x >= 1.2.2`.
3. **No `package.json`, override or settings change** anywhere in the PR, whichever path (main
   command or F2) was taken.
4. **If F2 was used**: the integrity hash equals the registry's `dist.integrity` for the chosen
   version, and the owner's `pnpm install --frozen-lockfile` passed after the edit.
5. **`just security` evidence** shows `security-web: passed`, not a registry skip.
