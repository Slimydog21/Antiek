# AgentMail setup — operator-owned email inboxes

**Status: ready to provision as of 2026-05-22.** The
`AgentMailEmailProvider` ships in `substrate/auth/email_provider.py`;
the production substrate routes magic-link auth, publisher
notifications (§9.10), and interview invitations (§11) through
AgentMail inboxes when configured.

For the architectural rationale see
`docs/operator_gate_actions.md` — short version: every email use
case past magic-link involves a reply, and replies must route into
the substrate, not into the operator's personal Gmail.

---

## Setup overview

1. Sign up at <https://agentmail.to> + generate an API key.
2. Verify the `antiek.ai` domain (DKIM + SPF records via Cloudflare DNS).
3. Create one inbox per purpose (notifications, interviews, outreach).
4. Set env vars + restart antiek.
5. Validate with a curl smoke test.

Steps 1-2 are AgentMail-side; 3-5 are operator commands.

---

## Step 1 — API key

Generate at <https://agentmail.to> → Settings → API Keys.

Format: `am_live_...` (or `am_test_...` for sandbox). Store
where you store other secrets; you'll paste it into the VM in
step 4.

## Step 2 — Domain verification

AgentMail's domain settings will show 2 DNS records to add:

- **SPF**: a TXT record at the apex
- **DKIM**: a TXT record at a CNAME-like name (e.g. `am._domainkey.antiek.ai`)

Add them in Cloudflare DNS:

1. Cloudflare dashboard → `antiek.ai` zone → DNS → Records
2. Add the SPF record (TXT, name `@`, value as AgentMail provides)
3. Add the DKIM record (TXT, name as AgentMail provides)
4. Back in AgentMail: click "Verify" — propagation takes 5-15 min

## Step 3 — Create the inboxes

Once the domain verifies, create the inboxes the substrate will
use. From your local machine (with the API key in your shell):

```bash
export AGENTMAIL_API_KEY=am_live_...

# Notifications inbox: magic-link auth + publisher Kalshi-pattern
# notifications (§9.10). The most important one to set up first.
curl -sS -X POST https://api.agentmail.to/inboxes \
  -H "Authorization: Bearer $AGENTMAIL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"client_id": "antiek-notifications-v1"}'
# Capture the returned inbox_id — you'll set ANTIEK_AGENTMAIL_INBOX_ID to this.

# Optional: separate inboxes per surface. Recommended once Sprint
# 19+ inbound reply routing lands.
curl -sS -X POST https://api.agentmail.to/inboxes \
  -H "Authorization: Bearer $AGENTMAIL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"client_id": "antiek-interviews-v1"}'

curl -sS -X POST https://api.agentmail.to/inboxes \
  -H "Authorization: Bearer $AGENTMAIL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"client_id": "antiek-outreach-v1"}'
```

Each call returns `{"inbox_id": "inb_...", ...}`. Save the
`notifications` inbox id for step 4.

## Step 4 — Configure the VM

```bash
ssh -i ~/.ssh/antiek_ed25519 root@167.235.202.98
```

Append to `/etc/antiek/secrets.env` (idempotent — overwrite if
already present):

```
ANTIEK_EMAIL_PROVIDER=agentmail
AGENTMAIL_API_KEY=am_live_...
ANTIEK_AGENTMAIL_INBOX_ID=inb_...   # the notifications inbox from step 3
```

Then re-chown + restart:

```bash
chown root:antiek /etc/antiek/secrets.env
chmod 0640 /etc/antiek/secrets.env
systemctl restart antiek
sleep 2
systemctl is-active antiek
```

Or use the one-command swap script (see below).

## Step 5 — Smoke test

In an incognito browser window:

1. Go to `https://antiek.ai/login`
2. Enter your operator email
3. Click "Send sign-in link"

A magic-link email should arrive in your inbox within seconds.
Click the link — you should land on `https://antiek.ai/` with the
session cookie set.

If nothing arrives:

```bash
# Check the antiek log for the actual send call:
ssh -i ~/.ssh/antiek_ed25519 root@167.235.202.98 \
  'journalctl -u antiek -n 50 --no-pager | grep -i agentmail'
```

A `EmailDeliveryFailure` with the AgentMail HTTP error body will
tell you whether the issue is auth (401), config (400 missing
`from`-equivalent), rate-limiting (429), or transport.

---

## One-command swap (alternative to step 4)

If you already have an AgentMail API key + inbox_id:

```bash
./infrastructure/scripts/swap_email_provider_to_agentmail.sh \
    am_live_your_key \
    inb_your_notifications_inbox_id
```

Same idempotency + restart semantics as the Resend equivalent.

---

## Why AgentMail over Resend

Architectural reason: every email use case in the master spec past
magic-link involves a reply that should route into the substrate.

- **§9.10 publisher notifications** — MIT Press / Cambridge UP /
  Princeton UP legal departments email back. AgentMail's inbox +
  webhook lets the substrate ingest those replies as typed events
  (`ip_holder.reply_received`); without it, replies land in the
  operator's personal Gmail and the §9.10 state machine drifts.
- **§11 interview invitations** — informants reply about timing,
  recording consent, compensation. Same shape.
- **§9.13 cross-graph "ask an expert" (Sprint 25+)** — User B's
  investigation surfaces User A; outreach is email-mediated;
  replies need to route back.

Inbound reply handling itself is Sprint 19+ work; this runbook
ships the outbound side now so the substrate is on the right
provider at the right time.

---

## Companion docs

- `substrate/auth/email_provider.py` — provider implementation
- `infrastructure/runbooks/magic-link-auth.md` — auth substrate
- `docs/operator_gate_actions.md` — the AgentMail-vs-Resend verdict
- `docs/master-product-spec.md` §9.10 + §11 — the reply-handling cases
