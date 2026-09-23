#!/usr/bin/env bash
# tools/deploy/require_green.sh — the ONE required-checks gate for deploys.
#
# Called by BOTH deploy paths so they cannot drift:
#   * .github/workflows/deploy_backend.yml  (the gated CI path)
#   * infrastructure/ansible/playbooks/deploy.yml, right before `git pull`
#     (the manual / runbook path — ssh + ansible-playbook, or an agent session)
#
# Why the second caller exists: on 2026-09-22 a408d2646 reached production
# ~6 minutes after merge while 4 of its 8 required contexts were still running.
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
# Options:
#   --wait <seconds>   (default 0 — the historical behavior, unchanged for
#     the workflow gate job and the manual/runbook path) — when the verdict
#     would be exit 1 solely because some required contexts are still PENDING
#     (queued/in_progress or not yet reported), re-poll every
#     REQUIRE_GREEN_POLL_SECONDS (default 30) until all eight are success or
#     the budget expires, then exit 1 as before. A TERMINAL non-success
#     conclusion (failure, timed_out, cancelled, ...) fails fast on the first
#     poll that sees it — waiting cannot help. Exit 3 and exit 4 are always
#     immediate, with or without --wait.
#     Why the playbook wants this: deploy.yml resolves main's tip at DEPLOY
#     time, so it can race a merge that landed after the workflow's gate job
#     passed — the new tip's checks are still running and the gate used to
#     red the whole deploy run (runs 35916451078, 35920220639). The playbook
#     passes --wait 900; the workflow's gate job passes nothing and stays
#     instant (it is the decider, not the deployer).
#
# Why exit 4 exists: green checks say a commit PASSED, not that it was
# MERGED. A fork PR's head commit gets the same eight contexts from its PR
# CI, and deploy-backend's workflow_run trigger matches on the triggering
# run's head_branch — which, for a fork PR, is whatever the fork named its
# branch (`main` works). Without this check that commit's own playbook would
# run as root on production with the deploy key. Only code on main ships;
# the question is answered from the repository, not from event metadata.
set -euo pipefail

WAIT=0
POLL="${REQUIRE_GREEN_POLL_SECONDS:-30}"
REPO_IN=""
SHA=""
while [ $# -gt 0 ]; do
  case "$1" in
    --wait)
      WAIT="${2:?usage: require_green.sh [--wait <seconds>] <owner/repo | git url> <full 40-char sha>}"
      shift 2
      ;;
    --wait=*) WAIT="${1#--wait=}"; shift ;;
    -*)
      echo "require_green: unknown flag '$1' — usage: require_green.sh [--wait <seconds>] <owner/repo | git url> <full 40-char sha>" >&2
      exit 2
      ;;
    *)
      if [ -z "$REPO_IN" ]; then REPO_IN="$1"
      elif [ -z "$SHA" ]; then SHA="$1"
      else
        echo "require_green: unexpected extra argument '$1'" >&2
        exit 2
      fi
      shift
      ;;
  esac
done
if [ -z "$REPO_IN" ] || [ -z "$SHA" ]; then
  echo "usage: require_green.sh [--wait <seconds>] <owner/repo | git url> <full 40-char sha>" >&2
  exit 2
fi
[[ "$WAIT" =~ ^[0-9]+$ ]] || {
  echo "require_green: --wait must be a non-negative integer number of seconds (got '$WAIT')" >&2
  exit 2
}
[[ "$POLL" =~ ^[1-9][0-9]*$ ]] || {
  echo "require_green: REQUIRE_GREEN_POLL_SECONDS must be a positive integer (got '$POLL')" >&2
  exit 2
}

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

# The contexts main's ruleset requires. Kept as a LITERAL list so a ruleset
# change that silently drops a context does not silently widen what may deploy.
REQUIRED=(
  'tsc'
  'vitest'
  'keystone'
  'mypy --strict + ruff (declared scope, baselined)'
  'pytest shard 0 of 4'
  'pytest shard 1 of 4'
  'pytest shard 2 of 4'
  'pytest shard 3 of 4'
)

# One poll of the check-runs API. Echoes one line per required context
# ("green:" / "NOT GREEN:") and returns: 0 all eight success; 1 the only
# offenders are pending (queued/in_progress or not yet reported); 2 at least
# one context has a TERMINAL non-success conclusion (waiting cannot help);
# 3 the API could not be read.
check_once() {
  local runs ctx concl state pending=0 failed=0
  # One row per check run: name, status, conclusion, started_at. A context
  # that was re-run has SEVERAL rows; the newest started_at decides, so a
  # rerun that turned red is never masked by its earlier green (nor a rerun
  # that turned green held back by its earlier red).
  if ! runs=$(gh api --paginate "repos/$REPO/commits/$SHA/check-runs?per_page=100" \
              --jq '.check_runs[] | [.name, .status, (.conclusion // "pending"), (.started_at // "")] | @tsv'); then
    echo "require_green: check-runs query failed for $REPO@$SHA — REFUSING (fail-closed)." >&2
    return 3
  fi

  for ctx in "${REQUIRED[@]}"; do
    # Most recent conclusion reported for this context name.
    concl=$(printf '%s\n' "$runs" | awk -F'\t' -v c="$ctx" '$1==c && ($4 > t || t == "") {t=$4; v=$3} END {print v}')
    state="${concl:-absent}"
    case "$state" in
      success)
        echo "green: '$ctx'"
        ;;
      pending|absent)
        echo "NOT GREEN: '$ctx' => $state"
        pending=1
        ;;
      *)
        echo "NOT GREEN: '$ctx' => $state"
        failed=1
        ;;
    esac
  done

  if [ "$failed" -eq 1 ]; then return 2; fi
  if [ "$pending" -eq 1 ]; then return 1; fi
  return 0
}

all_green() {
  echo "require_green: $REPO@${SHA:0:9} — all ${#REQUIRED[@]} required contexts are success."
}

not_green() {
  echo "require_green: $REPO@${SHA:0:9} is NOT deployable — a required context is not success."
}

rc=0
check_once || rc=$?
if [ "$WAIT" -eq 0 ] || [ "$rc" -ne 1 ]; then
  # No wait requested, or a verdict waiting cannot change: decide NOW.
  # Exit 3 (cannot verify) and terminal-failure verdicts are immediate.
  case "$rc" in
    0) all_green; exit 0 ;;
    3) exit 3 ;;  # check_once already said why
    2)
      echo "require_green: a required context has a terminal non-success conclusion — waiting cannot help." >&2
      not_green
      exit 1
      ;;
    *) not_green; exit 1 ;;
  esac
fi

# --wait N, first poll pending: re-poll until green or the budget expires.
deadline=$(( $(date +%s) + WAIT ))
while :; do
  now=$(date +%s)
  remaining=$(( deadline - now ))
  if [ "$remaining" -le 0 ]; then
    echo "require_green: waited ${WAIT}s and required contexts are still pending — giving up." >&2
    not_green
    exit 1
  fi
  nap=$POLL
  if [ "$nap" -gt "$remaining" ]; then nap=$remaining; fi
  echo "require_green: not all green yet; re-polling in ${nap}s (wait budget ${WAIT}s)." >&2
  sleep "$nap"
  rc=0
  check_once || rc=$?
  case "$rc" in
    0) all_green; exit 0 ;;
    3) exit 3 ;;
    2)
      echo "require_green: a required context reached a terminal non-success conclusion — waiting cannot help." >&2
      not_green
      exit 1
      ;;
  esac
done
