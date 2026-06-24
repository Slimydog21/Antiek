#!/usr/bin/env bash
# Live smoke for Deep Research Workflow #1 (SPR-LEDGER-05 / SPR-DRL-09).
#
# Exercises: plan → approve → launch → poll until parent deep_research_complete.
# Requires ANTIEK_OPERATOR_TOKEN (and optional CF Access headers) in env.
#
# Exit codes:
#   0  deep_research_complete=true, synthesis_tail_error=null
#   1  API or terminal failure
#   2  timeout
#   3  missing deps
set -euo pipefail

API_URL="${ANTIEK_API_URL:-https://api.antiek.ai}"
SMOKE_TIMEOUT_S="${SMOKE_TIMEOUT_S:-900}"
POLL_S="${SMOKE_POLL_S:-8}"

OP_TOKEN="${ANTIEK_OPERATOR_TOKEN:-}"
CF_CLIENT_ID="${CF_ACCESS_CLIENT_ID:-}"
CF_CLIENT_SECRET="${CF_ACCESS_CLIENT_SECRET:-}"

AUTH=()
if [[ -n "$CF_CLIENT_ID" && -n "$CF_CLIENT_SECRET" ]]; then
  AUTH+=(-H "CF-Access-Client-Id: $CF_CLIENT_ID" -H "CF-Access-Client-Secret: $CF_CLIENT_SECRET")
fi
if [[ -n "$OP_TOKEN" ]]; then
  AUTH+=(-H "Authorization: Bearer $OP_TOKEN")
fi

for cmd in curl jq; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "smoke_drw_1: missing $cmd" >&2; exit 3; }
done

if [[ -z "$OP_TOKEN" ]]; then
  echo "smoke_drw_1: ANTIEK_OPERATOR_TOKEN unset" >&2
  exit 3
fi

PROBLEM="${SMOKE_DRW_PROBLEM:-Will high-bandwidth memory supply constraints meaningfully limit datacenter GPU deployments through 2027?}"

# Fixed sub-questions keep smoke bounded; omit SMOKE_DRW_DECOMPOSE=1 to use auto-decompose.
if [[ "${SMOKE_DRW_DECOMPOSE:-0}" == "1" ]]; then
  PLAN_BODY=$(jq -nc --arg p "$PROBLEM" '{problem: $p, max_depth: 2}')
else
  PLAN_BODY=$(jq -nc --arg p "$PROBLEM" '{
    problem: $p,
    max_depth: 2,
    sub_questions: [
      "What is current HBM production capacity versus forecast AI accelerator demand?",
      "Which vendors and packaging technologies most affect HBM supply through 2027?"
    ]
  }')
fi

echo "smoke_drw_1: POST /research/plans"
plan=$(curl -fsS -X POST "$API_URL/research/plans" \
  "${AUTH[@]}" -H 'Content-Type: application/json' -d "$PLAN_BODY") || {
  echo "smoke_drw_1: create_plan failed" >&2
  exit 1
}
root_id=$(echo "$plan" | jq -r '.root_node_id')
echo "smoke_drw_1: root_id=$root_id"

curl -fsS -X POST "$API_URL/research/plans/$root_id/approve" \
  "${AUTH[@]}" -H 'Content-Type: application/json' \
  -d '{"approver":"smoke_drw_1"}' >/dev/null

echo "smoke_drw_1: launch"
launch=$(curl -fsS -X POST "$API_URL/research/plans/$root_id/launch" \
  "${AUTH[@]}" -H 'Content-Type: application/json' \
  -d '{"per_research_budget_usd":0.35,"aggregate_budget_usd":1.0}')
session_id=$(echo "$launch" | jq -r '.session_id')
echo "smoke_drw_1: session_id=$session_id"

deadline=$(( $(date +%s) + SMOKE_TIMEOUT_S ))
last=""
while [[ $(date +%s) -lt $deadline ]]; do
  st=$(curl -fsS "$API_URL/research/sessions/$session_id" "${AUTH[@]}")
  drc=$(echo "$st" | jq -r '.deep_research_complete')
  ste=$(echo "$st" | jq -r '.synthesis_tail_error')
  live=$(echo "$st" | jq -r '.live')
  states=$(echo "$st" | jq -r '[.researches[].state] | join(",")')
  line="live=$live states=$states deep_research_complete=$drc synthesis_tail_error=$ste"
  if [[ "$line" != "$last" ]]; then
    echo "smoke_drw_1: $line"
    last=$line
  fi
  if [[ "$drc" == "true" && "$ste" == "null" ]]; then
    echo "smoke_drw_1: PASS session_id=$session_id"
    echo "$st" | jq '{session_id, deep_research_complete, synthesis_tail_error, researches, cost}'
    exit 0
  fi
  if [[ "$ste" != "null" ]]; then
    echo "smoke_drw_1: FAIL synthesis_tail_error=$ste" >&2
    echo "$st" | jq .
    exit 1
  fi
  sleep "$POLL_S"
done

echo "smoke_drw_1: TIMEOUT after ${SMOKE_TIMEOUT_S}s session_id=$session_id" >&2
exit 2