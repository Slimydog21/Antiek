#!/usr/bin/env bash
# Bridge + substrate health probe.
#
# Three checks per run:
#  1. ``hermes-bridge.antiek.ai/health`` — confirms the Cloudflare
#     Tunnel + local proxy + xAI OAuth resolution are all alive.
#  2. ``api.antiek.ai/ops/provider-ratio?window_minutes=15`` —
#     confirms Hermes is actually taking traffic (not silently
#     dropping to OpenRouter).
#  3. ``api.antiek.ai/health`` write verdict and refusal-rate alert —
#     the frame-telemetry write-path refusal rate over a rolling
#     15-minute window (the 2026-10-02/03 incident class: 84.6% of
#     writes refused for 28h while every liveness check stayed green).
#
# When any check trips, posts to ``ANTIEK_ALERT_WEBHOOK`` (Slack-
# compatible JSON ``{"text": "..."}``). When the env var is unset,
# prints the alert to stderr instead.
#
# Idempotent. Designed for a 5-minute cron. State-free — does not
# remember prior alert state; the operator's webhook sink (Slack,
# Discord, Zapier, PagerDuty) handles deduplication.
#
# Exit codes:
#   0  all checks passed
#   1  bridge unhealthy, provider-ratio alert recommended, or write-path
#      refusal-rate alert recommended or sensor unreadable
#   3  bad invocation (missing curl/jq)
#
# Required env (defaults shown):
#   ANTIEK_API_URL=https://api.antiek.ai
#   ANTIEK_BRIDGE_URL=https://hermes-bridge.antiek.ai
#   ANTIEK_ALERT_WEBHOOK=<unset>
#   PROVIDER_RATIO_WINDOW_MIN=15
#
# Delivery honesty (2026-10-03, audit .audit/2026-10-01-anatomy/
# LITERAL-STATUS-AUDIT.md section 1.9): the alert POST below is checked,
# not ``|| true``. Exit code 1 means the alert was DELIVERED to the
# configured webhook (or the webhook is unset and the alert went to
# stderr, the documented fallback). When a configured webhook POST fails
# after one bounded retry, the probe exits 2 and emits a greppable
# ``ALERT DELIVERY FAILED`` journal line — so a failed alert can never
# look like a delivered one. systemd records it as ExecMainStatus=2.

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
ratio_body=$(curl -fsS --max-time 8 ${API_AUTH_HEADER[@]+"${API_AUTH_HEADER[@]}"} \
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
# shape as the provider-ratio alert. An explicit unreadable sensor verdict
# also alerts, even when its details are empty. /health needs no auth. An empty body is
# NOT alerted on here: check (2) already reports API DOWN in that case.
health_body=$(curl -fsS --max-time 8 "$API_URL/health" 2>/dev/null || true)
if [ -n "$health_body" ]; then
  write_alert=$(echo "$health_body" | jq -r '.frame_write.alert_recommended // false')
  write_check=$(echo "$health_body" | jq -r '.status_checks.frame_write // "not_measured"')
  if [ "$write_alert" = "true" ] || [ "$write_check" = "error" ] || [ "$write_check" = "degraded" ]; then
    reason=$(echo "$health_body" | jq -r '.frame_write.alert_reason // .status_detail // "write-path sensor reports degradation"')
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

# ── Deliver ──
# A webhook POST is not delivery. Port of the backup-freshness probe's
# honesty contract (infrastructure/ansible/templates/
# antiek-backup-freshness-probe.sh.j2): ``curl -f`` so an HTTP error from
# the sink counts as failure, ``--max-time`` so a sink that accepts and
# never answers cannot hang the unit past its TimeoutStartSec, one bounded
# retry for transient sink hiccups, and on failure a distinct greppable
# journal line plus a distinct exit code — so a failed alert can never
# look like a delivered one. Only the URL origin is printed: Slack-style
# webhook paths carry a secret. No email fallback here on purpose: this
# probe is state-free and refires every 5 minutes (BRIDGE UNAUTH fired 5x
# in one audit hour), so a naive fallback would storm the fallback channel;
# that needs a rate-limited design of its own.
delivered=0
post_rc=0
if [ -n "$WEBHOOK" ]; then
  case "$WEBHOOK" in
    *://*/*) webhook_origin=$(printf '%s' "$WEBHOOK" | sed -E 's#^([a-zA-Z][a-zA-Z0-9+.-]*://[^/]+)/.*#\1#') ;;
    *://*)   webhook_origin="$WEBHOOK" ;;
    *)       webhook_origin="(unparseable webhook URL)" ;;
  esac
  payload=$(jq -nc --arg t "$message" '{text: $t}')
  for attempt in 1 2; do
    if [ "$attempt" -gt 1 ]; then
      sleep "${ANTIEK_ALERT_RETRY_DELAY:-10}"
    fi
    if curl -fsS --max-time 15 -X POST "$WEBHOOK" \
        -H 'Content-Type: application/json' \
        -d "$payload" >/dev/null; then
      delivered=1
      break
    else
      post_rc=$?
    fi
  done
  if [ "$delivered" -eq 0 ]; then
    echo "ALERT DELIVERY FAILED: webhook POST to ${webhook_origin} failed (last curl exit ${post_rc}, 2 attempts); the alert below was NOT delivered to the configured sink and exists only in this journal" >&2
  fi
fi

echo "$message" >&2
if [ -n "$WEBHOOK" ] && [ "$delivered" -eq 0 ]; then
  exit 2
fi
exit 1
