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
# The browser installs its own cookie by submitting the token-free form.
# The curl cookie jar below is only for API smoke and is never a browser login.
if [ "${ANTIEK_OWNER_LOGIN_MODE:-open}" = "curl" ]; then
  JAR="${ANTIEK_COOKIE_JAR:-/tmp/antiek-owner.cookies}"
  umask 077
  if [ -e "$JAR" ]; then chmod 600 "$JAR"; fi
  ANTIEK_DEV_LOGIN_NEXT="$NEXT" python3 -c \
    'import os,sys,urllib.parse; sys.stdout.write(urllib.parse.urlencode({"token":os.environ["ANTIEK_DEV_LOGIN_TOKEN"],"next":os.environ["ANTIEK_DEV_LOGIN_NEXT"]}))' \
    | curl -fsS -c "$JAR" -b "$JAR" -o /dev/null \
        -w "dev-login HTTP %{http_code} jar=$JAR\n" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        --data-binary @- "${API}/auth/dev-login"
  curl -sS -b "$JAR" "$API/auth/me"; echo
else
  if command -v open >/dev/null 2>&1; then
    NEXT_ENCODED="$(ANTIEK_DEV_LOGIN_NEXT="$NEXT" python3 -c \
      'import os,urllib.parse; print(urllib.parse.quote(os.environ["ANTIEK_DEV_LOGIN_NEXT"], safe=""))')"
    open "${API}/auth/dev-login?next=${NEXT_ENCODED}"
    echo "Opened owner sign-in form. Enter the token in the browser to install its session cookie."
  else
    echo "open unavailable; run with ANTIEK_OWNER_LOGIN_MODE=curl" >&2
    exit 1
  fi
fi
