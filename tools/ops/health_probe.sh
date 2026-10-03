#!/usr/bin/env bash
# Bridge + substrate health probe.
#
# Three checks per run:
#  1. ``hermes-bridge.antiek.ai/health`` — confirms the Cloudflare
#     Tunnel + local proxy + xAI OAuth resolution are all alive.
#  2. ``api.antiek.ai/ops/provider-ratio?window_minutes=15`` —
#     confirms Hermes is actually taking traffic (not silently
#     dropping to OpenRouter).
#  3. ``api.antiek.ai/health`` ``.frame_write.alert_recommended`` —
#     the frame-telemetry write-path refusal rate over a rolling
#     15-minute window (the 2026-10-02/03 incident class: 84.6% of
#     writes refused for 28h while every liveness check stayed green).
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
#   1  bridge unhealthy, provider-ratio alert recommended, or write-path
#      refusal-rate alert recommended
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
# H4.5: auth headers for machine callers behind Cloudflare Access.
# Same shape as smoke_investigation.sh — Cf-Access-Client-Id +
# Cf-Access-Client-Secret for the edge gate, plus an
# Authorization: Bearer fallback for the substrate-level gate.
# The bridge's /health stays open (probed without auth).
OP_TOKEN="${ANTIEK_OPERATOR_TOKEN:-}"
CF_CLIENT_ID="${CF_ACCESS_CLIENT_ID:-}"
CF_CLIENT_SECRET="${CF_ACCESS_CLIENT_SECRET:-}"
API_AUTH_HEADER=()
if [ -n "$CF_CLIENT_ID" ] && [ -n "$CF_CLIENT_SECRET" ]; then
  API_AUTH_HEADER+=(-H "CF-Access-Client-Id: $CF_CLIENT_ID")
  API_AUTH_HEADER+=(-H "CF-Access-Client-Secret: $CF_CLIENT_SECRET")
fi
if [ -n "$OP_TOKEN" ]; then
  API_AUTH_HEADER+=(-H "Authorization: Bearer $OP_TOKEN")
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

# ── (3) Write-path refusal rate ──
# Prod incident 2026-10-02/03: POST /api/ad/frame-telemetry refused 84.6% of
# writes (28,562 of 33,776) for ~28h while /health said "ok" and this probe
# stayed green — both checks above measure liveness, none measured whether a
# write can land. /health now carries a rolling 15-minute refusal rate with a
# server-side threshold (derived in frame_write_health.py: measured healthy
# 3.1%, incident 84.6%, threshold 25%); this check only forwards it, the same
# shape as the provider-ratio alert. /health needs no auth. An empty body is
# NOT alerted on here: check (2) already reports API DOWN in that case.
health_body=$(curl -fsS --max-time 8 "$API_URL/health" 2>/dev/null || true)
if [ -n "$health_body" ]; then
  write_alert=$(echo "$health_body" | jq -r '.frame_write.alert_recommended // false')
  if [ "$write_alert" = "true" ]; then
    reason=$(echo "$health_body" | jq -r '.frame_write.alert_reason // "(no reason)"')
    alerts+=("WRITE PATH DEGRADED: $reason")
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
