#!/usr/bin/env bash
# G3.3 on Omarchy (runbook boat-backbone.md "G3.3"; owner ruling 10). Run interactively.
# Never trace this shell: it briefly holds the owner's personal Boat key in a shell variable.
set +x
set -euo pipefail
SP=/tmp/claude-1000/-home-slimydog/66b42348-5fea-4e5c-bf5b-2fc01ad6720c/scratchpad
PR="$SP/pr3826"                      # read-only source checkout
SHA="${G33_SHA:?set G33_SHA to the reviewed PR #3826 SHA that carries the launch fix}"
DRIVER="$SP/g33/g33_driver.py"
PORT="${G33_PORT:-18001}"
unset BOAT_API_KEY BOAT_BUILD_API_KEY ANTIEK_ENV_FILE ANTIEK_DRW_GATHER ANTIEK_EXEC_BACKEND || true

# 0. Scratch copy + isolated state, all under one fresh directory.
mkdir -p /home/slimydog/.cache; T=$(mktemp -d /home/slimydog/.cache/antiek-g33.XXXXXX); chmod 700 "$T"; SRC="$T/src"   # the big disk, beside uv's cache (hardlinks)
mkdir -p "$T"/{home,home-tests,tmp,state-tests,pytest,receipts}
git clone --quiet --no-hardlinks "$PR" "$SRC"
git -C "$SRC" checkout --quiet --detach "$SHA"
for f in "$SRC/.env" "$SRC/platform/.env" "$T/platform/.env"; do
  [ ! -e "$f" ] || { echo "STOP: $f exists; the app's dotenv loader would read it" >&2; exit 2; }
done
if ss -Hltn "sport = :$PORT" | grep -q .; then echo "STOP: port $PORT is busy" >&2; exit 2; fi

# 1. The service venv, as the deploy builds it (deploy_atomic.yml:282-300), plus the dev extra for step 2.
#    Network to PyPI only if the uv cache lacks a wheel; no key exists in any process yet.
( cd "$SRC" && { uv sync --offline --frozen --python 3.12 --no-dev --no-default-groups --extra pdf --extra urls \
      --extra embedding --extra docs --extra turbopuffer_shadow --extra dev \
    || uv sync --frozen --python 3.12 --no-dev --no-default-groups --extra pdf --extra urls \
      --extra embedding --extra docs --extra turbopuffer_shadow --extra dev; } )

# 2. Hermetic pre-flight (the suite never calls Boat). Must include the fix's regression test.
( cd "$SRC" && env -i PATH="$SRC/.venv/bin:/usr/bin:/bin" LANG=C.UTF-8 HOME="$T/home-tests" TMPDIR="$T/tmp" \
    PYTHONDONTWRITEBYTECODE=1 ANTIEK_HOME="$T/state-tests" ANTIEK_EMBEDDING_PROVIDER=hash HF_HUB_OFFLINE=1 \
    "$SRC/.venv/bin/python" -m pytest -q -p no:cacheprovider --basetemp "$T/pytest" \
    tests/test_exec_backend_boat.py tests/test_cascade_exec_backend_wiring.py \
    tests/test_cascade_api.py tests/test_drw_gather_mode_reported.py )

if [ "${G33_PREFLIGHT_ONLY:-}" = 1 ]; then
  echo "preflight passed at $SHA (no key was read); removing $T"; rm -rf -- "$T"; exit 0
fi

# 3. The live run. The personal key reaches the driver's environment only (prefix assignment:
#    no argv, no file, no export); the driver mints, uses and revokes the temporary product key.
if [ -n "${BOAT_OWNER_KEY:-}" ]; then K="$BOAT_OWNER_KEY"; unset BOAT_OWNER_KEY   # from the caller's process, never argv
else read -rs -p 'Owner personal Boat key (not echoed): ' K; echo; fi
rc=0
BOAT_OWNER_KEY="$K" G33_T="$T" G33_SRC="$SRC" G33_REAL_HOME="$HOME" G33_PORT="$PORT" \
  "$SRC/.venv/bin/python" -I "$DRIVER" || rc=$?
unset K

# 4. Archive the receipt (no key in it: the driver's leak scan ran last), then remove the scratch.
OUT="$SP/receipts/g33-$(date -u +%Y%m%dT%H%M%SZ)"; mkdir -p "$OUT"
cp -- "$T/receipts/g33.jsonl" "$OUT/"
for f in "$T/logs/service.log" "$T/logs/console.log" "$T/state/boat_ledger.jsonl"; do [ -e "$f" ] && cp -- "$f" "$OUT/"; done
if grep -rlE 'boat_[A-Za-z0-9_-]{24,}' -- "$OUT"; then echo "STOP: key-shaped text in $OUT" >&2; rc=3; fi
echo "rc=$rc receipt=$OUT"
if [ "$rc" = 0 ]; then rm -rf -- "$T"; else echo "kept $T for review; rm -rf -- '$T' afterwards" >&2; fi
exit "$rc"
