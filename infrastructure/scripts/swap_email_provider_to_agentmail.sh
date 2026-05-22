#!/usr/bin/env bash
# Swap ANTIEK_EMAIL_PROVIDER → agentmail on the production VM.
#
# Idempotent. Reapplying the same values is a no-op.
#
# Usage (from the operator's machine):
#   ./infrastructure/scripts/swap_email_provider_to_agentmail.sh \
#       am_live_your_key inb_your_inbox_id
#
# Or, if already SSH'd to the VM:
#   sudo AGENTMAIL_API_KEY=am_... \
#        ANTIEK_AGENTMAIL_INBOX_ID=inb_... \
#        /opt/antiek/infrastructure/scripts/swap_email_provider_to_agentmail.sh

set -euo pipefail

SECRETS_FILE="/etc/antiek/secrets.env"
AGENTMAIL_KEY="${1:-${AGENTMAIL_API_KEY:-}}"
AGENTMAIL_INBOX_ID="${2:-${ANTIEK_AGENTMAIL_INBOX_ID:-}}"

if [[ -z "$AGENTMAIL_KEY" || -z "$AGENTMAIL_INBOX_ID" ]]; then
  echo "ERROR: AGENTMAIL_API_KEY and ANTIEK_AGENTMAIL_INBOX_ID are both required."
  echo
  echo "Usage:"
  echo "  $0 am_live_your_key inb_your_inbox_id"
  echo
  echo "Get the API key at https://agentmail.to → Settings → API Keys."
  echo "Get the inbox_id by creating an inbox first — see"
  echo "infrastructure/runbooks/agentmail-setup.md step 3."
  exit 1
fi

if [[ "$AGENTMAIL_KEY" != am_* ]]; then
  echo "WARNING: key doesn't start with 'am_'; AgentMail keys typically do."
  echo "  Got: ${AGENTMAIL_KEY:0:5}…"
  echo "  Continuing anyway. Cancel with Ctrl+C if this is wrong."
  sleep 3
fi

# If we're running locally, ssh into the VM and re-invoke ourselves.
if [[ "$(hostname)" != "antiek-prod-fsn1" ]]; then
  echo "Not on the VM — ssh'ing in to apply remotely."
  SSH_KEY="${SSH_KEY:-$HOME/.ssh/antiek_ed25519}"
  ssh -i "$SSH_KEY" -o BatchMode=yes \
    "root@167.235.202.98" \
    "AGENTMAIL_API_KEY='$AGENTMAIL_KEY' ANTIEK_AGENTMAIL_INBOX_ID='$AGENTMAIL_INBOX_ID' bash -s" \
    < "$0"
  exit $?
fi

# ── From here on, we're on the VM ────────────────────────────────────

if [[ ! -f "$SECRETS_FILE" ]]; then
  echo "ERROR: $SECRETS_FILE not found. Is this the production VM?"
  exit 2
fi

_set_env_var() {
  local key="$1"
  local val="$2"
  if grep -q "^${key}=" "$SECRETS_FILE"; then
    # Escape | in the replacement value since sed uses | as delimiter
    local escaped="${val//|/\\|}"
    sed -i "s|^${key}=.*$|${key}=${escaped}|" "$SECRETS_FILE"
    echo "  updated ${key}"
  else
    echo "${key}=${val}" >> "$SECRETS_FILE"
    echo "  set ${key} (was unset)"
  fi
}

echo "Configuring AgentMail provider in $SECRETS_FILE…"
_set_env_var "ANTIEK_EMAIL_PROVIDER" "agentmail"
_set_env_var "AGENTMAIL_API_KEY" "$AGENTMAIL_KEY"
_set_env_var "ANTIEK_AGENTMAIL_INBOX_ID" "$AGENTMAIL_INBOX_ID"

# Re-assert ownership + permissions per the cloudflare-access runbook
chown root:antiek "$SECRETS_FILE"
chmod 0640 "$SECRETS_FILE"

# Restart antiek to pick up the new env
echo "Restarting antiek service…"
systemctl restart antiek
sleep 2

# Confirm
if systemctl is-active --quiet antiek; then
  echo "antiek service is active."
else
  echo "WARNING: antiek service is not active. Check 'journalctl -u antiek -n 30'."
  exit 3
fi

# Smoke test against the in-process API — request a magic link for
# a non-allowlisted email; should get 200 sent:true even when the
# send no-ops (allowlist guard runs before the AgentMail call).
echo
echo "Smoke test: requesting a magic link for a non-allowlisted email…"
SMOKE_RESP=$(curl -sS -X POST http://127.0.0.1:8001/auth/request \
  -H "Content-Type: application/json" \
  -d '{"email":"smoke-test@example.com"}' || echo '{"error":"curl failed"}')
echo "  Response: $SMOKE_RESP"

echo
echo "Done. Magic-link emails will now flow through AgentMail."
echo
echo "Next: open https://antiek.ai/login in an incognito window and request a"
echo "sign-in link to your operator email. The link should arrive in your inbox"
echo "within seconds (assuming the antiek.ai domain SPF + DKIM are verified at"
echo "https://agentmail.to/domains)."
echo
echo "Sprint 19+ follow-on: wire the AgentMail inbound webhook into"
echo "substrate/ip_holders/ so §9.10 publisher replies route into the substrate."
