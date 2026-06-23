#!/usr/bin/env bash
# ATSB SPR-01 — operator preflight (read-only). Does not create secrets or deploy.
set -euo pipefail

echo "=== TileRT Modal preflight (OA-022) ==="
echo "Profile: ${MODAL_PROFILE:-slimydog21}"
echo

_fail=0

if ! command -v modal >/dev/null 2>&1; then
  echo "FAIL: modal CLI not installed"
  exit 2
fi

echo "--- Secrets (need: antiek-tilert-auth) ---"
if modal secret list 2>/dev/null | grep -q 'antiek-tilert-auth'; then
  echo "OK: antiek-tilert-auth present"
else
  echo "MISSING: antiek-tilert-auth (see infrastructure/modal/tilert_glm5/README.md §1)"
  _fail=1
fi
if modal secret list 2>/dev/null | grep -qE 'hf-token|antiek-hf-hub'; then
  echo "OK: HF hub secret present (hf-token or antiek-hf-hub)"
else
  echo "WARN: no HF secret — gated weights need hf-token or antiek-hf-hub for prep_weights"
fi

echo
echo "--- Volume antiek-tilert-glm5-weights ---"
_vol_out="$(modal volume ls antiek-tilert-glm5-weights 2>&1 || true)"
if [[ -z "${_vol_out// }" ]]; then
  echo "EMPTY or unreadable: run prep_weights before deploy"
  _fail=1
else
  echo "${_vol_out}" | head -20
  if echo "${_vol_out}" | grep -q 'glm5-tilert'; then
    echo "OK: glm5-tilert path seen"
  else
    echo "WARN: glm5-tilert shards not listed — prep_weights may be incomplete"
    _fail=1
  fi
fi

echo
echo "--- App antiek-tilert-glm5 ---"
_app_json="$(modal app list --json 2>/dev/null || echo '[]')"
_tilert_state="$(echo "${_app_json}" | python3 -c "
import json,sys
apps=json.load(sys.stdin)
for a in apps:
    if a.get('description')=='antiek-tilert-glm5':
        print(a.get('state','unknown'), a.get('tasks','?'))
        break
else:
    print('missing', '')
" 2>/dev/null || echo "missing ?")"
if [[ "${_tilert_state%% *}" != "missing" ]]; then
  echo "antiek-tilert-glm5: state=${_tilert_state}"
  if [[ "${_tilert_state%% *}" == "deployed" ]]; then
    echo "OK: app deployed (idle tasks=0 is normal)"
  else
    echo "NOT SERVING: state is not deployed — fix secret/weights then modal deploy"
    _fail=1
  fi
else
  echo "MISSING: app not in list — modal deploy infrastructure/modal/tilert_glm5/app.py"
  _fail=1
fi

echo
echo "--- Gateway (local check only) ---"
if [[ -n "${ANTIEK_TILERT_API_KEY:-}" && -n "${ANTIEK_TILERT_BASE_URL:-}" ]]; then
  echo "OK: ANTIEK_TILERT_API_KEY and ANTIEK_TILERT_BASE_URL set in shell"
else
  echo "MISSING: set ANTIEK_TILERT_* on VM after deploy (README §5)"
  _fail=1
fi

echo
if [[ $_fail -eq 0 ]]; then
  echo "PREFLIGHT OK — run scripts/smoke_tilert_modal.sh then smoke_dispatch.py --tier speed"
  exit 0
fi
echo "PREFLIGHT INCOMPLETE — fix items above (operator-only)"
exit 1