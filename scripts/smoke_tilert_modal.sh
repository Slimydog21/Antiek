#!/usr/bin/env bash
# ATSB SPR-01 — smoke TileRT Modal OpenAI shim (operator gate).
# Requires: BASE and TOKEN from deploy output / Modal secret.
set -euo pipefail

BASE="${ANTIEK_TILERT_BASE_URL:-${BASE:-}}"
TOKEN="${ANTIEK_TILERT_API_KEY:-${TOKEN:-}}"

if [[ -z "${BASE}" || -z "${TOKEN}" ]]; then
  echo "Set ANTIEK_TILERT_BASE_URL and ANTIEK_TILERT_API_KEY (or BASE/TOKEN)." >&2
  exit 2
fi

BASE="${BASE%/}"
echo "== health =="
curl -fsS "${BASE}/health" | head -c 500
echo
echo "== models =="
curl -fsS "${BASE}/v1/models" -H "Authorization: Bearer ${TOKEN}" | head -c 500
echo
echo "== chat =="
START=$(date +%s%3N 2>/dev/null || python3 -c 'import time; print(int(time.time()*1000))')
RESP=$(curl -fsS "${BASE}/v1/chat/completions" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"model":"glm5","max_tokens":32,"messages":[{"role":"user","content":"Reply with exactly: tilert-smoke-ok"}]}')
END=$(date +%s%3N 2>/dev/null || python3 -c 'import time; print(int(time.time()*1000))')
echo "${RESP}" | head -c 800
echo
echo "latency_ms=$(( END - START ))"