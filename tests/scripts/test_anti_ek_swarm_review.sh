#!/bin/bash
# Honesty smoke for anti-ek-swarm-review.sh (no model tokens, no network).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

bash -n scripts/anti-ek-swarm-review.sh
bash -n scripts/swarm-review-pr.sh

# Wrapper must delegate (not keep the old homebrew-first / exec path).
grep -q 'anti-ek-swarm-review.sh' scripts/swarm-review-pr.sh
grep -q 'exec ' scripts/swarm-review-pr.sh
! grep -q 'glmf-codex exec' scripts/swarm-review-pr.sh

# Canonical script carries tip-sync probe + w7 tab inventory + PATH discipline.
grep -q '/private/tmp/antiek-main-probe' scripts/anti-ek-swarm-review.sh
grep -q 'w7_tab_labels' scripts/anti-ek-swarm-review.sh
grep -q 'PATH_local_before_brew' scripts/anti-ek-swarm-review.sh
grep -q '\.local/bin' scripts/anti-ek-swarm-review.sh

# Dry-run must not invoke models (exit 0 with DRY-RUN banner).
OUT=$(mktemp -d)
trap 'rm -rf "$OUT"' EXIT
export ANTIEK_SWARM_OUT="$OUT"
export ANTIEK_SWARM_DIFF="$OUT/diff.txt"
export ANTIEK_SWARM_CHECK="$OUT/check.txt"
# Ensure we have a base for dry-run even on shallow clones
git rev-parse HEAD >/dev/null
set +e
scripts/anti-ek-swarm-review.sh --dry-run HEAD 2>&1 | tee "$OUT/dry.txt"
rc=${PIPESTATUS[0]}
set -e
[[ $rc -eq 0 ]]
grep -q 'DRY-RUN' "$OUT/dry.txt"

# --check should at least emit RESULT line (may be core_ready false off Mini).
set +e
scripts/anti-ek-swarm-review.sh --check >"$OUT/check-run.txt" 2>&1
crc=$?
set -e
grep -q 'RESULT core_ready=' "$OUT/check-run.txt"
grep -q 'Dogfood worktrees' "$OUT/check-run.txt"
grep -q 'Herdr Antiek w7' "$OUT/check-run.txt"
# Wrapper alias (avoid pipefail masking: capture then grep)
set +e
wrap_out=$(scripts/swarm-review-pr.sh --dry-run HEAD 2>&1)
wrap_rc=$?
set -e
[[ $wrap_rc -eq 0 ]]
grep -q 'DRY-RUN' <<<"$wrap_out"

echo "OK tests/scripts/test_anti_ek_swarm_review.sh"
