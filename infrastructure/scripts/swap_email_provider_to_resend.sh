#!/usr/bin/env bash
# Swap ANTIEK_EMAIL_PROVIDER from mock → resend on the production VM.
#
# Idempotent. Safe to run multiple times: only modifies /etc/antiek/secrets.env
# if (a) the provider is currently set to something other than 'resend', AND
# (b) RESEND_API_KEY is supplied as the first argument.
#
# Usage (from the operator's machine):
#   ./infrastructure/scripts/swap_email_provider_to_resend.sh re_your_key_here
#
# Or, if already SSH'd to the VM:
#   sudo RESEND_API_KEY=re_your_key_here \
#     /opt/antiek/infrastructure/scripts/swap_email_provider_to_resend.sh

set -euo pipefail

SECRETS_FILE="/etc/antiek/secrets.env"
RESEND_KEY="${1:-${RESEND_API_KEY:-}}"

if [[ -z "$RESEND_KEY" ]]; then
  echo "ERROR: RESEND_API_KEY is required."
  echo
  echo "Usage:"
  echo "  $0 re_your_resend_key_here"
  echo
  echo "Get your key at https://resend.com → API Keys."
  echo "Verify your antiek.ai domain (SPF + DKIM) before sending real users."
  exit 1
fi

if [[ "$RESEND_KEY" != re_* ]]; then
  echo "WARNING: key doesn't start with 're_'; Resend keys typically do."
  echo "  Got: ${RESEND_KEY:0:5}…"
  echo "  Continuing anyway. Cancel with Ctrl+C if this is wrong."
  sleep 3
fi

# If we're running locally, ssh into the VM and re-invoke ourselves.
if [[ "$(hostname)" != "antiek-prod-fsn1" ]]; then
  echo "Not on the VM — ssh'ing in to apply remotely."
  SSH_KEY="${SSH_KEY:-$HOME/.ssh/antiek_ed25519}"
  ssh -i "$SSH_KEY" -o BatchMode=yes \
    "root@167.235.202.98" \
    "RESEND_API_KEY='$RESEND_KEY' bash -s" \
    < "$0"
  exit $?
fi

# ── From here on, we're on the VM ────────────────────────────────────

if [[ ! -f "$SECRETS_FILE" ]]; then
  echo "ERROR: $SECRETS_FILE not found. Is this the production VM?"
  exit 2
fi

# Update or insert ANTIEK_EMAIL_PROVIDER
if grep -q "^ANTIEK_EMAIL_PROVIDER=" "$SECRETS_FILE"; then
  CURRENT=$(grep "^ANTIEK_EMAIL_PROVIDER=" "$SECRETS_FILE" | head -1 | cut -d= -f2)
  if [[ "$CURRENT" == "resend" ]]; then
    echo "ANTIEK_EMAIL_PROVIDER is already 'resend'. No provider change needed."
  else
    sed -i "s|^ANTIEK_EMAIL_PROVIDER=.*$|ANTIEK_EMAIL_PROVIDER=resend|" "$SECRETS_FILE"
    echo "Updated ANTIEK_EMAIL_PROVIDER: $CURRENT → resend"
  fi
else
  echo "ANTIEK_EMAIL_PROVIDER=resend" >> "$SECRETS_FILE"
  echo "Set ANTIEK_EMAIL_PROVIDER=resend (was unset)"
fi

# Update or insert RESEND_API_KEY (without echoing the value)
if grep -q "^RESEND_API_KEY=" "$SECRETS_FILE"; then
  sed -i "s|^RESEND_API_KEY=.*$|RESEND_API_KEY=$RESEND_KEY|" "$SECRETS_FILE"
  echo "Updated RESEND_API_KEY (key value not echoed)"
else
  echo "RESEND_API_KEY=$RESEND_KEY" >> "$SECRETS_FILE"
  echo "Set RESEND_API_KEY (key value not echoed)"
fi

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

# Smoke test: request a magic link for a non-allowlisted email; should
# get 200 sent:true and the journal should NOT show a MockEmailProvider line.
echo
echo "Smoke test: requesting a magic link for a non-allowlisted email…"
SMOKE_RESP=$(curl -sS -X POST http://127.0.0.1:8001/auth/request \
  -H "Content-Type: application/json" \
  -d '{"email":"smoke-test@example.com"}' || echo '{"error":"curl failed"}')
echo "  Response: $SMOKE_RESP"

echo
echo "Done. Magic links to the operator email will now flow through Resend."
echo
echo "Next: open https://antiek.ai/login in an incognito window and request a"
echo "sign-in link to your operator email. The link should arrive in your inbox"
echo "within seconds (assuming the antiek.ai domain SPF + DKIM are verified at"
echo "https://resend.com/domains)."
