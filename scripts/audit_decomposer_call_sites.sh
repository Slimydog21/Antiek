#!/usr/bin/env bash
# ANT-H2V SPR-06 — grep gate for decomposer contract drift.
# Audited paths only (not every render_full_prompt in the repo).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
FAIL=0

check_no_positional_render() {
  local file="$1"
  if rg -n 'render_full_prompt\s*\(\s*[^*]' "$file" 2>/dev/null | rg -v 'render_full_prompt\s*\(\s*$' | rg -v '^\s*#' ; then
    echo "FAIL: possible positional render_full_prompt in $file"
    FAIL=1
  fi
}

for f in \
  roles/cascade_planner/planner.py \
  interfaces/research/api/decomposer.py; do
  if [[ -f "$f" ]]; then
    check_no_positional_render "$f"
  fi
done

# dispatch must receive investigation_id= in planner production path
if ! rg -n 'dispatch\(.*investigation_id=' roles/cascade_planner/planner.py >/dev/null; then
  echo "FAIL: DispatchDecomposer missing investigation_id= on dispatch()"
  FAIL=1
fi

if [[ "$FAIL" -eq 0 ]]; then
  echo "AUDIT_OK: decomposer call sites in audited files"
fi
exit "$FAIL"