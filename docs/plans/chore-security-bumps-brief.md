# chore-security-bumps brief: bump certifi and vite so `just security` passes on main

Analyst: phase 1 (Understand). This brief records facts only. It does not design a solution.
Sources: CLAUDE.md; the orchestrator's task message; `justfile` (`security`, `security-py`,
`security-web`, `check`, `check-web`, `check-api`); `apps/web/package.json`;
`apps/web/pnpm-lock.yaml`; `services/api/pyproject.toml`; `services/api/uv.lock`;
`.github/workflows/audit.yml` and `ci.yml`; `docs/decisions/D22-security-scanning.md`;
`docs/plans/chore-source-map-js-brief.md` and `-plan.md` (format precedent and verified pnpm
12.6.0 semantics); `docs/plans/chore-codeql-brief.md` (format precedent).

Unlike the two precedent chore briefs, this analysis **was run with the network and a live repo**.
The failing advisories, fixed versions, dependency parents and version lists below were observed
directly on `main` at `c23982b` (not scaffolded-off, not relayed). Tooling observed: `uv 0.12.18`,
`pnpm 12.6.0`, `just`, `gh`, `curl`, `python3`. The macOS `timeout` binary is absent (irrelevant).

Limits of this analysis:
- This is a chore, not a design-doc section-16 task. There are no design-doc acceptance criteria.
- Advisory data can change between this run (2026-10-21) and the owner's fix run; "latest" numbers
  below are snapshots.
- There is no `.npmrc`, no `pnpm-workspace.yaml`, and `apps/web/package.json` has no `pnpm` field.
  pnpm runs with defaults. `certifi` is a leaf package with no dependencies of its own.

---

## 1. Task

- **ID:** `chore-security-bumps` (not from design doc section 16)
- **Title:** none in the design doc. Working description: make `just security` pass again on `main`
  by bumping the two dependencies whose advisories currently fail it, with the smallest deliberate
  change and no unintended upgrades.
- **Acceptance criteria:** the design doc has none. Agreed goal, as passed on by the orchestrator:
  1. `just security` passes on `main` (today it fails on two parts, see section 4).
  2. Python side: `certifi` in `services/api/uv.lock` moves to the advisory's fixed version
     (`2026.10.19` per PYSEC-2026-4320), so `security-py` (pip-audit) passes.
  3. Web side: `vite` in `apps/web` moves to the advisory's fixed version (`>=8.3.3` per
     GHSA-587h-7wmj-h5pm), so `security-web` (`pnpm audit --audit-level=high`) passes.
  4. No other package version changes unintentionally.
  5. Open PR #23 (`t1-7-attribution`) stays green after this lands.
- Branch: `chore-security-bumps` off `main` (HEAD `c23982b`, `T1.6 ... (#22)`), working tree clean.

---

## 2. Why it matters

What this enables:
- `just security` goes green again. The reviewer (pipeline phase 4) runs it on every task and the
  PR template asks for it (D22 consequences), so every PR until this is fixed carries a known red
  result that must be explained.
- The weekly, non-required `audit.yml` job (`just security-py` + `just security-web`) stops failing
  on `main`.

What breaks if it is wrong:
- If either change pulls in other upgrades (a broad `pnpm update` / `uv lock --upgrade`), core tools
  (Vite, Vitest, Tailwind, Biome; or FastAPI/SQLModel/Alembic transitive deps) could move. That is
  the section-18 risk "Library changes mid-project / Behaviour drift" that exact pinning exists to
  prevent, and it could change telemetry or test behaviour without anyone deciding it.
- If a lockfile and its manifest disagree, the required CI jobs fail: `web` runs
  `pnpm install --frozen-lockfile` (`ci.yml` line 60); `api` runs `uv sync --locked` (`ci.yml`
  line 108). Every PR is then blocked.
- If the fix only silences the audit (an exception) the vulnerable version stays installed and must
  be remembered and removed later.
- If the certifi/vite lock changes conflict with or regress PR #23, that attribution PR (currently
  `MERGEABLE`) breaks and must be rebased.

---

## 3. Governing decisions

| Source | Decision | What it forces here |
|---|---|---|
| D22 (and T0.3/T0.4 amendments) | `security-py` = bandit (`-r src -ll`) + pip-audit on `uv.lock` (`uv export --locked --no-emit-project` then `pip-audit --no-deps --disable-pip`); `security-web` = `pnpm audit --audit-level=high`, dev deps included. Both run by hand and by the reviewer; `pip-audit`/`pnpm audit` are **not** required CI checks (run weekly in `audit.yml`). Not part of `just check`. | The fix must make pip-audit and `pnpm audit --audit-level=high` exit 0. D22 says nothing about audit ignores/exceptions; adding one (or changing `--audit-level`, or `--prod`) would change D22 and needs an ADR. |
| chore-source-map-js owner answer 1 (approach (a)) | "a lockfile-only update ... reject the result if any package other than `source-map-js` changes". | Precedent for the Python side: a lockfile-only, single-package upgrade is the preferred minimal change. **Does not transfer directly to vite** (see section 7, vite is a direct exact pin). |
| T0.2 owner answer 11 | "exact versions (no `^`) for the core tools (Vite, React, TypeScript, Biome, Vitest, Tailwind), with the lockfile as the backstop for transitive deps. Add a `packageManager` field pinning the pnpm version". | `vite` is an exact pin in `package.json`; fixing it requires a deliberate `package.json` edit (not just a lockfile move). pnpm stays `12.6.0`. |
| T0.3 owner answer 14 (pyproject header) | "Exact pins ...; transitive versions live in uv.lock." | `certifi` is transitive (not in `pyproject.toml`), so the Python fix is `uv.lock`-only. No `pyproject.toml` edit needed. |
| Design doc section 18 (quoted in T0.1/T0.4 briefs, `dependabot.yml`) | "Lockfiles; no upgrades between freeze and retest"; "lockfiles change only on purpose". | Both lockfile changes must be deliberate and limited to what is intended. Whether the experiment freeze has happened is not stated (project is at M1; verify if it matters). |
| T0.4 constraints / `dependabot.yml` | Installs must not rewrite lockfiles (`--frozen-lockfile`, `--locked`). Dependabot updates GitHub Actions only, not npm/uv. | New lockfiles must install frozen/locked in CI. Dependabot will not open these fix PRs; both are manual. |
| chore-source-map-js plan (verified pnpm 12.6.0 help) | `pnpm update`'s `--depth` default is unlimited (reaches transitive deps); `-L/--latest` "Ignore version ranges in package.json: bump the matched packages to their latest version and rewrite the manifest ranges"; `pnpm view` exists. | Without `--latest`, `pnpm update vite` respects the exact `package.json` specifier and is a **no-op** for the pinned direct dep (section 7). `--latest` would rewrite `package.json` and jump to the dist-tag latest. |
| Design doc section 2 / 17.3 | "Any change to a decision gets a short ADR in docs/decisions/." | Relevant only if an approach changes D22 (an audit exception). A plain version bump needs no ADR. |
| CLAUDE.md | Conventional commits; one task per PR; `just check` before pushing; never push to `main`; never merge. Never commit under `data/`. | Commit type `fix(deps):` (fixes advisories) is the precedent (chore-source-map-js). Owner runs network/commit steps. |

---

## 4. Current state (observed on `main` @ `c23982b`)

### `just security` result (verbatim, trimmed)
Running the parts individually:

**`just security-py`** → `security-py: FAILED: pip-audit`:
```
Found 1 known vulnerability in 1 package
Name    Version   ID              Fix Versions
------- --------- --------------- ------------
certifi 2026.7.22 PYSEC-2026-4320 2026.10.19
...
  bandit: passed
  pip-audit: FAILED (exit 1, see output above)
```

**`just security-web`** → `recipe security-web failed with exit code 1`:
```
high  launch-editor: `fs.existsSync()` existence check can be bypassed on Windows
Package: vite
Vulnerable versions: >=8.3.0 <=8.3.2
Patched versions: >=8.3.3
Paths: .>@tailwindcss/vite>vite ; .>vitest>@vitest/mocker>vite ; .>vitest>vite ; ... Found 7 paths
More info: https://github.com/advisories/GHSA-587h-7wmj-h5pm
3 vulnerabilities found. Severity: 2 moderate | 1 high
```
The full `pnpm audit --json` shows **all three advisories are on `vite`**, all patched by `>=8.3.3`:
- `high`     GHSA-587h-7wmj-h5pm  (vuln `>=8.3.0 <=8.3.2`, patched `>=8.3.3`) — **this one fails the `--audit-level=high` gate.**
- `moderate` GHSA-698v-4r3x-3vcv  (same range/patch) — does not fail the gate today.
- `moderate` GHSA-r825-w8mm-5pxw  (same range/patch) — does not fail the gate today.
A single bump of `vite` to `>=8.3.3` clears all three. semgrep and bandit pass.

### certifi (Python) — where it is pinned
- **Not** in `services/api/pyproject.toml`. It is transitive only, locked once in
  `services/api/uv.lock`:
  ```toml
  [[package]]
  name = "certifi"
  version = "2026.7.22"
  source = { registry = "https://pypi.org/simple" }
  ```
  (`certifi` has no `dependencies` block — it is a leaf.)
- Parents that declare a dependency on `certifi` in `uv.lock`: `httpcore` (line 258), `httpx`
  (line 272), `requests` (line 735). `httpx==0.28.1` is a dev dependency (`[dependency-groups] dev`
  in `pyproject.toml`); `httpcore` is pulled by `httpx`; `requests` is pulled by the pip-audit
  chain (`pip-audit` → `cachecontrol[filecache]` → `requests`, and `pip-audit` → `requests`
  directly). So `certifi` is in scope of pip-audit via the dev toolchain. None of these parents
  constrain the `certifi` version tightly (certifi is CA data, specifier is open); `2026.10.19`
  resolves without moving any parent.

### vite (web) — where it is pinned
- `apps/web/package.json`, `devDependencies`: `"vite": "8.3.1"` — a **direct, exact pin** (no `^`).
  Also present: `"@tailwindcss/vite": "4.3.3"`, `"@vitejs/plugin-react": "6.1.1"`,
  `"vitest": "4.1.11"`, which each pull `vite` as a peer/dep (the 7 audit paths).
- `apps/web/package.json` `engines`: `"node": ">=22.12.0 <23"`; `packageManager: "pnpm@12.6.0"`.
- `apps/web/pnpm-lock.yaml`: one `vite@8.3.1` package entry (line 1090,
  `engines: {node: ^20.19.0 || >=22.12.0}`), referenced by `@tailwindcss/vite`, `@vitejs/plugin-react`,
  `vitest`/`@vitest/mocker` (lines 1432, 1497, 1514, ...). Note: `launch-editor` (the actually
  vulnerable transitive package named in the advisory) is **not present in the lockfile** — the
  audit flags `vite` itself by version range, so the fix is to move `vite`, not `launch-editor`.

### Checks that touch these lockfiles
- `ci.yml` required `web` job: `pnpm install --frozen-lockfile` (line 60); pnpm store cache keyed on
  `apps/web/pnpm-lock.yaml`.
- `ci.yml` required `api` job: `uv sync --locked` (line 108), then `ruff`/`pyright`/`pytest`/
  `bandit`/`semgrep`. **pip-audit and `pnpm audit` are not in required CI.**
- `audit.yml` (weekly Mon 04:40 UTC + `workflow_dispatch`, not required): `just security-py`,
  `just security-web`.
- `just check` does not run either audit.

### Advisory facts (fetched live)
- **PYSEC-2026-4320** (alias `GHSA-6q48-6c7w-9gw2`), via `curl https://api.osv.dev/v1/vulns/...`:
  "certifi bundles emSign root CAs with compromised intermediate CA keys." Affected range
  `introduced 2019.03.09 → fixed 2026.10.19` (so `2026.10.18` is still affected). Details:
  "Certifi 2026.10.18 removed all emSign roots ...; Certifi 2026.10.19 restored the emSign roots
  that are not affected. **Upgrade to 2026.10.19 or later.**" pip-audit's "Fix Versions" column
  also says `2026.10.19`.
  - `https://pypi.org/pypi/certifi/json`: `2026.*` releases are `2026.1.4, 2026.2.25, 2026.4.22,
    2026.5.20, 2026.6.17, 2026.7.22, 2026.10.18, 2026.10.19`; dist-tag latest `2026.10.19`.
- **GHSA-587h-7wmj-h5pm** (`CVE-2026-112942`, severity high, CVSS v4 7.5), via `gh api`:
  "launch-editor: `fs.existsSync()` existence check can be bypassed on Windows" → OS command
  injection; **"Only apps that run on Windows are affected."** For the `vite` package the entry is
  `vulnerable_version_range: ">= 8.3.0, <= 8.3.2"`, `first_patched_version: "8.3.3"`. (The advisory
  also lists other vite ranges for 6.x/7.x/8.0-8.2 and `launch-editor <= 2.14.1` → `2.14.2`.)
  - `pnpm view vite versions`: `8.3.x` published are `8.3.0, 8.3.1, 8.3.2, 8.3.3, 8.3.4`;
    `pnpm view vite version` (dist-tag latest) = `8.3.4`.

---

## 5. Inputs and outputs

Inputs:
- `services/api/uv.lock`, `services/api/pyproject.toml`; `apps/web/package.json`,
  `apps/web/pnpm-lock.yaml` (section 4).
- PyPI (metadata + wheel/sdist + advisory data for `certifi`) and the npm registry (metadata +
  tarballs + advisory data for `vite`). Both need the network.

Outputs (repo changes):
- `services/api/uv.lock`: the `certifi` package entry (`version`, `sdist`/`wheels` urls + hashes +
  `upload-time`) moves from `2026.7.22` to the fixed version. No `pyproject.toml` edit expected.
- `apps/web/package.json`: `"vite": "8.3.1"` → the fixed version (an exact pin edit; see section 7).
- `apps/web/pnpm-lock.yaml`: the `vite` entry and its three transitive references move; the
  `rolldown` pin moves within its range (see section 7).
- Possibly a `docs/decisions/` file (only if an audit exception approach is chosen; not expected).

Outputs (not file changes):
- Refreshed `node_modules` / `.venv` on the owner's machine.
- `just security` summary showing `security-py: passed` and `security-web: passed`.
- CI `web` (frozen) and `api` (locked) jobs green.

---

## 6. Constraints

- **Network / who runs it.** The precedent chores had the owner run all network + commit steps
  under the sandbox; the same division is expected here (update/resolve/audit/commit are owner-run).
  This analyst session had network, but the plan/build should not assume the builder does.
- **Tool/version pins.** `pnpm@12.6.0` (corepack) for the web lockfile; `uv 0.12.18` for the Python
  lockfile (CI uses `0.12.18` in `audit.yml`, `ci.yml` uses setup-uv `0.12.18`). A different pnpm/uv
  may rewrite lockfile format or extra sections.
- **Exact pins stay** except the deliberate `vite` bump. No other direct dependency changes.
- **Frozen/locked installs must pass:** `pnpm install --frozen-lockfile` (web) and
  `uv sync --locked` (api) in CI after the change.
- **D22 unchanged** unless the owner decides otherwise: `--audit-level=high`, dev deps included, no
  `--prod`; no audit ignores.
- **Platform.** Linux CI and macOS dev share both lockfiles. `certifi` is pure data; `vite`
  (rolldown) has platform binaries but is resolved per-platform in the lockfile already. mlx-lm is
  not involved (certifi here comes through the dev toolchain, not the `mlx` extra).
- **Workflow.** One PR, conventional commit, `just check` before pushing, never merge.

---

## 7. Edge cases

1. **vite is a direct exact pin, unlike source-map-js.** `source-map-js` was transitive, so
   `pnpm update source-map-js` worked. `vite` is `"8.3.1"` (exact) in `package.json`. Per the
   source-map-js plan's verified pnpm 12.6.0 help, `pnpm update vite` **respects the manifest
   specifier**, so with an exact pin it is a no-op — it will not move `vite`. Fixing vite therefore
   needs either (a) edit `package.json` `"vite"` to the fixed version, then `pnpm install`, or
   (b) `pnpm update vite --latest` (which rewrites the manifest to the dist-tag latest). The task
   message's suggested `pnpm update vite` alone is insufficient for an exact pin. **Flag for the
   owner.**
2. **Which vite version.** First-patched is `8.3.3`. Dist-tag latest is `8.3.4` (also patched).
   `--latest` would pick `8.3.4` (and could jump a minor if one shipped by the owner's run); a
   manual edit can pin exactly `8.3.3` (minimal) or `8.3.4`. Example: `--latest` run next week after
   an `8.4.0` release would silently move to `8.4.x`.
3. **vite bump drags rolldown.** `vite@8.3.1` depends on `rolldown: ~1.2.9`; `vite@8.3.3` depends on
   `rolldown: ~1.2.11`. So the lockfile will also move `rolldown` within `~1.2.x` (a byte-for-byte
   "no other package changes" rule from the source-map chore cannot hold verbatim here). Other vite
   deps (`postcss ^8.5.28`, `picomatch ^4.0.7`, `tinyglobby ^0.2.17`, `lightningcss ^1.33.0`) are
   unchanged between 8.3.1 and 8.3.3. The expected web diff is `vite` + its references + `rolldown`.
4. **certifi "fixed" is 2026.10.19, not 2026.10.18.** `2026.10.18` removed emSign roots but is still
   inside the OSV affected range (`fixed: 2026.10.19`). pip-audit expects `2026.10.19`. Do not stop
   at `2026.10.18`.
5. **certifi upgrade scope.** `uv lock --upgrade-package certifi` should move only `certifi` (a leaf
   with no deps and no tight parent constraints). Verify the `uv.lock` diff is `certifi`-only; a
   bare `uv lock --upgrade` would re-resolve everything (section-18 risk).
6. **engines/python-version compatibility.** `vite@8.3.3` `engines.node` = `^20.19.0 || >=22.12.0`,
   compatible with the repo's `">=22.12.0 <23"`. `certifi` supports the repo's `requires-python
   ">=3.12,<3.13"` (certifi targets py>=3.6). No constraint blocks either bump.
7. **Two moderate vite advisories.** They do not fail `--audit-level=high` today, but they share the
   same package/patch, so the high fix removes them too. If vite is only bumped enough to clear the
   high one, the moderates vanish anyway; no separate action.
8. **Stale node_modules / .venv.** `pnpm audit` and pip-audit read the lockfiles, not the installed
   trees, so an audit can pass while the installed packages are stale until the next
   `pnpm install` / `uv sync`.
9. **Advisory drift after the fix.** A new high advisory in any other package could appear before or
   after this PR and make `just security` red again for a different reason (as happened here after
   chore-source-map-js). Example: next Monday `audit.yml` red on a different package.
10. **PR #23 interaction.** PR #23 (`t1-7-attribution`, `services/api`) is `MERGEABLE` against
    `main`. If #23 does not touch `uv.lock`, there is no conflict and it inherits the certifi bump
    on rebase; it must still pass `uv sync --locked` + `just check`. If #23 *does* edit `uv.lock`,
    a conflict or a resurrected old certifi is possible — must be checked. `certifi` is a TLS-CA
    data package used only by the dev/test toolchain, so attribution logic/tests are not expected to
    be affected; the risk is purely lockfile-merge, not behaviour.
11. **CI cache churn.** Both lockfiles' cache keys change, so the first CI run after the change
    re-downloads. Harmless.
12. **minimum-release-age / release delay.** The source-map-js plan left "whether pnpm 12 applies a
    minimum-release-age delay by default" unverified. The fixed vite versions are weeks old, so this
    is unlikely to bite, but if `pnpm update` keeps an old version and mentions a release-age gate,
    do not change any pnpm setting (use a manual edit).

---

## 8. Risks

1. **vite bump moving more than expected.** `--latest` or a careless `pnpm update` could jump a
   minor or re-resolve unrelated packages, triggering the section-18 behaviour-drift risk. Most
   likely slip is a large `pnpm-lock.yaml` diff beyond `vite` + `rolldown`.
2. **Using the wrong "fixed" number.** Stopping certifi at `2026.10.18`, or bumping vite only to
   `8.3.2`, leaves the audit red.
3. **Frozen/locked mismatch.** Committing a lockfile without re-running `pnpm install
   --frozen-lockfile` / `uv sync --locked` surfaces as a required-CI failure, blocking all PRs.
4. **Silencing instead of fixing.** An audit exception leaves the vulnerable version installed.
5. **PR #23 regressions.** If the rebase/merge of the new lockfiles onto #23 is mishandled, #23
   goes red.
6. **pnpm/uv version drift.** Running with a pnpm ≠ 12.6.0 or uv ≠ the CI version can rewrite the
   lockfile shape and produce a noisy diff.

---

## 9. Candidate approaches (identified, not chosen)

| | Approach | What changes | Notes |
|---|---|---|---|
| Python (a) | `uv lock --upgrade-package certifi` | `uv.lock` certifi entry only | Preferred, mirrors source-map chore. Leaf package; verify diff is certifi-only. |
| Python (b) | Pin `certifi` explicitly in `pyproject.toml` | `pyproject.toml` + `uv.lock` | Adds a direct pin for a transitive package; not needed and against T0.3 "transitive versions live in uv.lock". |
| Web (a) | Edit `package.json` `"vite"` to `8.3.3` (minimal), `pnpm install` | `package.json` + `pnpm-lock.yaml` (vite refs + rolldown) | Minimal, deterministic version; keeps exact-pin discipline (T0.2 answer 11). |
| Web (b) | `pnpm update vite --latest` | `package.json` (rewritten to `8.3.4`) + `pnpm-lock.yaml` | Jumps to dist-tag latest; less controlled; can pick a future minor. |
| Web (c) | `pnpm.overrides` / audit ignore | `package.json` + lockfile override block, or ADR | Leaves vite old or changes D22; against the minimal-change precedent. |
| Scope | One PR for both, or two PRs | — | CLAUDE.md "one task per PR" — this *is* one chore (make `just security` pass); likely one PR, two commits or one. |

---

## 10. Open questions

1. **vite version target.** The exact pin must change deliberately (edge case 1). Should vite be
   pinned to `8.3.3` (minimal first-patched) or `8.3.4` (current dist-tag latest)?
   - Plain terms: bump the smallest amount that fixes it, or go to the newest 8.3 patch?
   - Suggested default: pin exactly `8.3.3` via a `package.json` edit + `pnpm install` (minimal,
     controlled; matches exact-pin discipline). Accept the `rolldown ~1.2.x` move it drags, and
     reject any change to a package other than `vite` and `rolldown`.

2. **How to apply the vite bump.** `pnpm update vite` (no `--latest`) is a no-op on an exact pin.
   - Plain terms: hand-edit `package.json` then `pnpm install`, or use `pnpm update vite --latest`?
   - Suggested default: hand-edit `package.json` to the chosen version, then `pnpm install`
     (`--frozen-lockfile` fails because the manifest changed, so a plain `pnpm install` regenerates
     the lock), then `pnpm install --frozen-lockfile` to prove it installs clean. Avoid `--latest`.

3. **certifi upgrade command.** 
   - Plain terms: bump just certifi in `uv.lock` without re-resolving everything else.
   - Suggested default: `uv lock --upgrade-package certifi` (from `services/api`), then
     `uv sync --locked`; verify the `uv.lock` diff is certifi-only and lands on `2026.10.19`.

4. **One PR or two.** Both fixes are small and both are needed for `just security` to pass.
   - Plain terms: fix certifi and vite in the same PR, or split?
   - Suggested default: one PR, `chore-security-bumps`, so `just security` can be verified green in
     a single pass; two commits (`fix(deps): bump certifi ...`, `fix(deps): bump vite ...`) or one,
     owner's preference. No ADR (no decision changes).

5. **Commit type / record.** 
   - Plain terms: routine dependency fix message, or an ADR?
   - Suggested default: `fix(deps):` commits naming the advisories (precedent chore-source-map-js);
     PR body lists the changed lockfile/manifest lines. No `docs/decisions/` entry.

6. **PR #23 coordination (sequencing).** #23 is open and `MERGEABLE`.
   - Plain terms: does this chore land before or after #23, and who rebases?
   - Suggested default: either order works since #23 is not expected to touch `uv.lock`; after this
     lands, whoever owns #23 rebases onto `main` and confirms `just check` + `just security` pass.
     Confirm #23 does not edit `uv.lock` (edge case 10). This is an owner/orchestrator sequencing
     call, not a file change in this chore.

## Owner answers

2026-10-19 — answered by the orchestrator under the autonomous pipeline rule. Sources: (c) earlier
plans (chore-source-map-js, chore-codeql), (d) repo conventions, (e) industry practice.

1. **vite `8.3.3`**, the first patched version. Source: (c) chore-source-map-js took the minimal
   fixed version; exact pins stay exact.
2. **Hand-edit `apps/web/package.json` (`"vite": "8.3.3"`) then `pnpm install`** (lockfile updates
   to match). Source: (c) the chore-source-map-js plan verified that `--latest` rewrites manifest
   ranges, which we do not want; a one-line manifest edit is explicit and reviewable.
3. **`uv lock --upgrade-package certifi` then `uv sync --locked`**; the lock diff must touch only
   `certifi` (→ `2026.10.19`). Source: (d) the justfile runs everything `--locked`.
4. **One PR, two commits** (`fix(deps): bump vite to 8.3.3 (GHSA-587h-7wmj-h5pm)` and
   `fix(deps): bump certifi to 2026.10.19 (PYSEC-2026-4320)`). Source: (c) precedent; one chore per
   PR, one commit per advisory keeps bisection clean.
5. **`fix(deps):` commits naming the advisory, no ADR.** Source: (c) precedent.
6. **This chore merges first; the orchestrator then rebases PR #23.** Correction to the brief's
   expectation: #23 *does* edit `uv.lock` (it adds `hypothesis`). After this chore lands, #23 is
   rebased onto main and `uv lock` re-run so the lock contains both changes; `just check` is
   re-confirmed before merge. Source: (d).

Branch: `chore-security-bumps`.
