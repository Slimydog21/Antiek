#!/usr/bin/env bash
# spr07_named_gates.sh — the SPR-07 named vitest gate set with REPRODUCIBLE
# counts (repair C11): prints the exact file list and one line per file with
# its pass/fail/skip counts, then the totals, from vitest's JSON reporter.
# Run from apps/reading. Env per the sprint page (Node 25 + jsdom storage).
set -u
cd "$(dirname "$0")/.." || exit 2
export NODE_OPTIONS="${NODE_OPTIONS:---no-network-family-autoselection --no-experimental-webstorage}"
NAMED=(
  src/workspace/agent
  "src/components/ai/aiActions*.test.ts"
  src/workspace/companionPane.test.tsx
  src/workspace/contracts
  src/components/hotkeys/keymap.test.ts
  src/workspace/windowKeyListenerCensus.test.ts
)
OUT="${SPR07_GATES_JSON:-${TMPDIR:-/tmp}/spr07-named-gates.$$.json}"
echo "head: $(git rev-parse --short HEAD)  named set: ${NAMED[*]}"
# shellcheck disable=SC2068
npx vitest run --maxWorkers=1 --testTimeout=30000 --reporter=json --outputFile="$OUT" ${NAMED[@]} >/dev/null 2>&1
STATUS=$?
python3 - "$OUT" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
rows = sorted(r["testResults"], key=lambda t: t["name"])
root = None
import os
for t in rows:
    name = t["name"]
    i = name.find("apps/reading/")
    rel = name[i + len("apps/reading/"):] if i >= 0 else name
    p = sum(1 for a in t["assertionResults"] if a["status"] == "passed")
    f = sum(1 for a in t["assertionResults"] if a["status"] == "failed")
    s = sum(1 for a in t["assertionResults"] if a["status"] in ("skipped", "pending", "todo"))
    print(f"{p:4d} pass {f:3d} fail {s:3d} skip  {rel}  [{t['status']}]")
print(f"files {len(rows)}  suites {r['numTotalTestSuites']}  tests {r['numTotalTests']}  passed {r['numPassedTests']}  failed {r['numFailedTests']}  pending {r['numPendingTests']}")
PY
echo "vitest exit: $STATUS"
exit $STATUS
