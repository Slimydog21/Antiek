#!/bin/bash
# Open a local owner session via /auth/dev-login (Mac Mini dogfood).
# Requires ANTIEK_DEV_LOGIN_TOKEN + ANTIEK_AUTH_SECRET + ANTIEK_OPERATOR_EMAIL
# in platform/.env (or the environment). Never prints the token.
set -euo pipefail
export PATH="/opt/homebrew/bin:$PATH"
PL="${ANTIEK_PLATFORM:-/Users/slimydog/Antiek/platform}"
API="${ANTIEK_API_BASE_URL:-http://127.0.0.1:8000}"
NEXT="${1:-/}"
if [ -f "$PL/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$PL/.env"
  set +a
fi
if [ -z "${ANTIEK_DEV_LOGIN_TOKEN:-}" ]; then
  echo "ANTIEK_DEV_LOGIN_TOKEN unset — add it to $PL/.env (see docs/anti-ek-mac-mini-dogfood.md)" >&2
  exit 1
fi
if [ -z "${ANTIEK_AUTH_SECRET:-}" ]; then
  echo "ANTIEK_AUTH_SECRET unset — owner cookies cannot be verified" >&2
  exit 1
fi
URL="${API}/auth/dev-login?token=${ANTIEK_DEV_LOGIN_TOKEN}&next=${NEXT}"
# Prefer curl+cookie jar for smoke; open for interactive browser.
if [ "${ANTIEK_OWNER_LOGIN_MODE:-open}" = "curl" ]; then
  JAR="${ANTIEK_COOKIE_JAR:-/tmp/antiek-owner.cookies}"
  curl -sS -c "$JAR" -b "$JAR" -o /dev/null -w "dev-login HTTP %{http_code} jar=$JAR\n" -L "$URL"
  curl -sS -b "$JAR" "$API/auth/me"; echo
else
  if command -v open >/dev/null 2>&1; then
    open "$URL"
    echo "Opened owner login in default browser (token not printed). Then visit http://127.0.0.1:5173/"
  else
    echo "open unavailable; run with ANTIEK_OWNER_LOGIN_MODE=curl" >&2
    exit 1
  fi
fi
