#!/usr/bin/env bash
# Create the GitHub repo, set merge settings, push main, and protect it.
# Usage: scripts/bootstrap-github.sh [repo-name] [private|public]
# Run from inside this starter folder, after `gh auth login`.
set -euo pipefail

REPO="${1:-typist-ml}"
VISIBILITY="${2:-private}"

gh auth status >/dev/null 2>&1 || { echo "Run: gh auth login"; exit 1; }
OWNER="$(gh api user --jq .login)"

# 1. Local repo with main as the default branch
if [ ! -d .git ]; then
  git init -b main
  git add .
  git commit -m "chore: project skeleton, CI, PR template, agent instructions"
fi

# 2. Create the GitHub repo and push
gh repo create "$REPO" "--$VISIBILITY" --source . --remote origin --push \
  --description "Typing coach experiment: do targeted drills work, and does a local LLM help?"

# 3. Merge settings: squash only, auto-delete merged branches, allow auto-merge
gh repo edit "$OWNER/$REPO" \
  --enable-squash-merge \
  --enable-merge-commit=false \
  --enable-rebase-merge=false \
  --delete-branch-on-merge \
  --enable-auto-merge

# 4. Protect main: PR required, CI (web + api) must pass, no force-push or deletion.
#    Approvals are 0 because GitHub does not let you approve your own PR.
if gh api --method POST "repos/$OWNER/$REPO/rulesets" --input - <<'JSON'
{
  "name": "protect-main",
  "target": "branch",
  "enforcement": "active",
  "conditions": { "ref_name": { "include": ["~DEFAULT_BRANCH"], "exclude": [] } },
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    { "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 0,
        "dismiss_stale_reviews_on_push": false,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": true
      } },
    { "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "required_status_checks": [ { "context": "web" }, { "context": "api" } ]
      } }
  ]
}
JSON
then
  echo "Ruleset created: main is protected."
else
  echo "Could not create the ruleset. Private repos need GitHub Pro (free with the"
  echo "GitHub Student Developer Pack); otherwise make the repo public."
fi

echo "Done: https://github.com/$OWNER/$REPO"
