#!/usr/bin/env bash
# Bridge + substrate health probe.
#
# Two checks per run:
#  1. ``hermes-bridge.antiek.ai/health`` — confirms the Cloudflare
#     Tunnel + local proxy + xAI OAuth resolution are all alive.
#  2. ``api.antiek.ai/ops/provider-ratio?window_minutes=15`` —
#     confirms Hermes is actually taking traffic (not silently
#     dropping to OpenRouter).
#
# When either check trips, posts to ``ANTIEK_ALERT_WEBHOOK`` (Slack-
# compatible JSON ``{"text": "..."}``). When the env var is unset,
# prints the alert to stderr instead.
#
# Idempotent. Designed for a 5-minute cron. State-free — does not
# remember prior alert state; the operator's webhook sink (Slack,
# Discord, Zapier, PagerDuty) handles deduplication.
#
# Exit codes:
#   0  both checks passed
#   1  bridge unhealthy or provider-ratio alert recommended
#   3  bad invocation (missing curl/jq)
#
# Required env (defaults shown):
#   ANTIEK_API_URL=https://api.antiek.ai
#   ANTIEK_BRIDGE_URL=https://hermes-bridge.antiek.ai
#   ANTIEK_ALERT_WEBHOOK=<unset>
#   PROVIDER_RATIO_WINDOW_MIN=15

set -euo pipefail

API_URL="${ANTIEK_API_URL:-https://api.antiek.ai}"
BRIDGE_URL="${ANTIEK_BRIDGE_URL:-https://hermes-bridge.antiek.ai}"
WEBHOOK="${ANTIEK_ALERT_WEBHOOK:-}"
WINDOW="${PROVIDER_RATIO_WINDOW_MIN:-15}"
# H4: operator bearer for api.antiek.ai. The bridge's /health stays
# open (probed without auth) but the substrate's /ops endpoints gate.
OP_TOKEN="${ANTIEK_OPERATOR_TOKEN:-}"
API_AUTH_HEADER=()
if [ -n "$OP_TOKEN" ]; then
  API_AUTH_HEADER=(-H "Authorization: Bearer $OP_TOKEN")
fi

for cmd in curl jq; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "probe: missing $cmd" >&2; exit 3; }
done

alerts=()

# ── (1) Bridge health ──
bridge_body=$(curl -fsS --max-time 8 "$BRIDGE_URL/health" 2>/dev/null || true)
if [ -z "$bridge_body" ]; then
  alerts+=("BRIDGE DOWN: $BRIDGE_URL/health returned nothing or non-200")
else
  bridge_auth=$(echo "$bridge_body" | jq -r '.authenticated // false')
  if [ "$bridge_auth" != "true" ]; then
    alerts+=("BRIDGE UNAUTH: $BRIDGE_URL/health returned authenticated=false (xAI OAuth refresh likely failed)")
  fi
fi

# ── (2) Provider ratio ──
ratio_body=$(curl -fsS --max-time 8 "${API_AUTH_HEADER[@]}" \
  "$API_URL/ops/provider-ratio?window_minutes=$WINDOW" 2>/dev/null || true)
if [ -z "$ratio_body" ]; then
  alerts+=("API DOWN: $API_URL/ops/provider-ratio returned nothing")
else
  ratio_alert=$(echo "$ratio_body" | jq -r '.alert_recommended // false')
  if [ "$ratio_alert" = "true" ]; then
    reason=$(echo "$ratio_body" | jq -r '.alert_reason // "(no reason)"')
    alerts+=("HERMES DEGRADED: $reason")
  fi
fi

# ── Report ──
if [ "${#alerts[@]}" -eq 0 ]; then
  exit 0
fi

joined=$(printf '%s\n' "${alerts[@]}")
host=$(hostname -s 2>/dev/null || echo unknown)
ts=$(date -u +%FT%TZ)
message="[antiek-probe@${host} ${ts}]
$joined"

if [ -n "$WEBHOOK" ]; then
  curl -sS -X POST "$WEBHOOK" \
    -H 'Content-Type: application/json' \
    -d "$(jq -nc --arg t "$message" '{text: $t}')" >/dev/null || true
fi

echo "$message" >&2
exit 1
