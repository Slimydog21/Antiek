# Runbook · magic-link auth

**Owner:** auth
**Last verified:** 2026-05-24

## Symptom

- User clicks a magic-link email; the API returns 401 instead of a
  session.
- The token query param "looks right" but validation fails.
- A second click on the same link returns "already used" — sometimes
  even on the first click.

## Likely cause

Antiek uses magic-link auth via AgentMail (per `docs/decisions/
agentmail-custom-domain-deferral.md`; provider configured via
`ANTIEK_EMAIL_PROVIDER`). Tokens are single-use and short-lived (15
min TTL). Common failure modes:

1. **TTL expired.** User clicked an old link. The 15-min window is
   short for a reason — replay defense.
2. **Email-client prefetch.** Some mail clients fetch links to check
   for malware, which consumes the token. By the time the user clicks,
   it's "already used."
3. **Clock skew between origin and Cloudflare.** Rare, but a 1-minute
   skew on either side near the TTL boundary can shave the window.

## Quick diagnostics

```bash
# From the Hetzner host: look at the magic-link service logs.
journalctl -u antiek -n 200 --no-pager | grep -i magic

# Is the token literally in the DB?
.venv/bin/python -c "
from runtime.db_lock import connect_read
with connect_read('~/.antiek/antiek.duckdb') as con:
    rows = con.execute('SELECT token_hash, used_at, expires_at FROM magic_links ORDER BY issued_at DESC LIMIT 5').fetchall()
    for r in rows:
        print(r)
"

# What's the host's clock vs Cloudflare's view?
date -u
curl -sI https://www.cloudflare.com | grep -i date
```

## Root-cause path

Magic-link flow:

1. User enters email.
2. Antiek issues a token (random + signed), stores its hash in
   `magic_links` table with `expires_at = now + 15min`.
3. AgentMail sends the email containing the token.
4. User clicks; browser hits Antiek; Antiek validates the token
   against `expires_at` AND `used_at IS NULL`, sets `used_at`, issues
   a session.

Failure modes map to this flow:

- **TTL expired** → `expires_at < now()` on validation. Logs say
  "expired" not "invalid."
- **Email-client prefetch** → `used_at IS NOT NULL` when the user
  clicks. Logs say "already used." The fix: emit two clicks per
  token (the prefetch consumes one, the real click consumes the
  other). Antiek does NOT do this today; it's the operator's
  call whether to add it.
- **Clock skew** → `expires_at - now()` is tiny but negative. Rare;
  surfaces near the TTL boundary.

## Mitigation

| Cause | Mitigation |
|---|---|
| Expired token | Re-issue: user requests a new magic link. |
| Email-client prefetch | Tell the user to copy-paste the link from the email instead of clicking. Long-term: add prefetch-resistance (operator decision). |
| Clock skew | `chrony` / `systemd-timesyncd` on the Hetzner host. |
| AgentMail outage | Switch `ANTIEK_EMAIL_PROVIDER` to a backup; see operator gate actions doc. |

## Reference

- Code: `substrate/auth/`
- Email provider config: `infrastructure/runbooks/agentmail-setup.md`
- Magic-link details: `infrastructure/runbooks/magic-link-auth.md`
- Decision: `docs/decisions/agentmail-custom-domain-deferral.md`
- Operator status: `docs/operator_gate_actions.md`

## Worked example

```
2026-05-24T15:30:00Z user@example.com requested magic link
2026-05-24T15:30:01Z AgentMail accepted message id mb_xyz
2026-05-24T15:30:42Z magic_links.lookup: token=abc... expired_at=2026-05-24T15:45:00Z used_at=2026-05-24T15:30:05Z
2026-05-24T15:30:42Z 401 "already used"
```

Trace:

1. Token was issued at 15:30:00, used at 15:30:05 (5 seconds later).
2. The user's click came at 15:30:42 — 37s after the apparent first use.
3. Cause: email-client prefetch consumed the token at 15:30:05.
4. Mitigation: tell the user to copy-paste the URL instead of clicking.
   Long-term: add a "click to confirm" landing page so the prefetch
   doesn't consume the token (operator decision; tracked in operator
   gate actions).
