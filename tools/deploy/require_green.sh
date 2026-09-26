#!/usr/bin/env bash
# tools/deploy/require_green.sh — the ONE required-checks gate for deploys.
#
# Called by BOTH deploy paths so they cannot drift:
#   * .github/workflows/deploy_backend.yml  (the gated CI path)
#   * infrastructure/ansible/playbooks/deploy.yml, right before `git pull`
#     (the manual / runbook path — ssh + ansible-playbook, or an agent session)
#
# Why the second caller exists: on 2026-09-22 a408d2646 reached production
# ~6 minutes after merge while 4 of its 8 branch-required contexts were still
# running.
# Both deploy_backend runs had correctly SKIPPED. The gate guarded one caller;
# the playbook guarded nothing. A gate must sit at the action, not at a caller.
#
# Exit codes — distinguished on purpose, so "could not check" never reads as
# "checked and not green" (see #3369, and test_integrity.yml's Traceback split):
#   0  every main-required context is `success` for $SHA        -> deployable
#   1  at least one required context is not `success`            -> not yet
#   3  cannot verify (no gh, not authed, bad sha, API failure)    -> REFUSE
#   4  $SHA is not main's tip or an ancestor of it                -> REFUSE
#
# Why exit 4 exists: green checks say a commit PASSED, not that it was
# MERGED. A fork PR's head commit gets the same nine contexts from its PR
# CI, and deploy-backend's workflow_run trigger matches on the triggering
# run's head_branch — which, for a fork PR, is whatever the fork named its
# branch (`main` works). Without this check that commit's own playbook would
# run as root on production with the deploy key. Only code on main ships;
# the question is answered from the repository, not from event metadata.
set -euo pipefail

REPO_IN="${1:?usage: require_green.sh <owner/repo | git url> <full 40-char sha>}"
SHA="${2:?usage: require_green.sh <owner/repo | git url> <full 40-char sha>}"

# Accept owner/repo, https://github.com/o/r(.git), git@github.com:o/r(.git).
REPO=$(printf '%s' "$REPO_IN" | sed -E 's#^(https?://github\.com/|git@github\.com:)##; s#\.git$##; s#/$##')

command -v gh >/dev/null 2>&1 || {
  echo "require_green: gh CLI not found on this host — cannot verify required checks for $SHA; REFUSING (fail-closed). Install gh, or pass antiek_force_deploy=true deliberately." >&2
  exit 3
}
gh auth status >/dev/null 2>&1 || {
  echo "require_green: gh is not authenticated — REFUSING (fail-closed)." >&2
  exit 3
}
# An abbreviated sha is an exact-match filter that silently matches NOTHING
# on the check-runs endpoint; requiring 40 chars turns that silence into a
# loud refusal.
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || {
  echo "require_green: SHA must be a FULL 40-char sha (got '$SHA'); refusing." >&2
  exit 3
}

# Is $SHA on main? compare/<sha>...main is `identical` when it IS main's tip
# and `ahead` when main has moved past it (a rollback target); `diverged` or
# `behind` means it is not main's history (a fork or unmerged commit). A SHA
# unknown to the repository is a 404: cannot verify.
if ! on_main=$(gh api "repos/$REPO/compare/$SHA...main" --jq .status); then
  echo "require_green: cannot compare $SHA against main in $REPO — REFUSING (fail-closed)." >&2
  exit 3
fi
case "$on_main" in
  identical|ahead) ;;
  *)
    echo "require_green: $REPO@${SHA:0:9} is not on main (compare status '${on_main:-empty}') — only merged code deploys; REFUSING." >&2
    exit 4
    ;;
esac

# The eight contexts main's ruleset requires, plus the deploy-only `pytest`
# rollup. Kept as a LITERAL list so a ruleset change that silently drops a
# context does not silently widen what may deploy.
REQUIRED=(
  'tsc'
  'vitest'
  'keystone'
  'mypy --strict + ruff (declared scope, baselined)'
  'pytest shard 0 of 4'
  'pytest shard 1 of 4'
  'pytest shard 2 of 4'
  'pytest shard 3 of 4'
  'pytest'
)

# One row per check run: name, status, conclusion, started_at. A context
# that was re-run has SEVERAL rows; the newest started_at decides, so a
# rerun that turned red is never masked by its earlier green (nor a rerun
# that turned green held back by its earlier red).
if ! runs=$(gh api --paginate "repos/$REPO/commits/$SHA/check-runs?per_page=100" \
              --jq '.check_runs[] | [.name, .status, (.conclusion // "pending"), (.started_at // "")] | @tsv'); then
  echo "require_green: check-runs query failed for $REPO@$SHA — REFUSING (fail-closed)." >&2
  exit 3
fi

missing=0
for ctx in "${REQUIRED[@]}"; do
  # Most recent conclusion reported for this context name.
  concl=$(printf '%s\n' "$runs" | awk -F'\t' -v c="$ctx" '$1==c && ($4 > t || t == "") {t=$4; v=$3} END {print v}')
  if [ "${concl:-}" != "success" ]; then
    echo "NOT GREEN: '$ctx' => ${concl:-absent}"
    missing=1
  else
    echo "green: '$ctx'"
  fi
done

if [ "$missing" -ne 0 ]; then
  echo "require_green: $REPO@${SHA:0:9} is NOT deployable — a required context is not success."
  exit 1
fi
echo "require_green: $REPO@${SHA:0:9} — all ${#REQUIRED[@]} required contexts are success."
