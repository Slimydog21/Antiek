# AgentMail custom-domain — deferred (2026-05-23)

**Status:** Deferred to the day G2 (lawyer review) closes.

## What was attempted

On 2026-05-23 the operator stood up AgentMail for magic-link auth
via the default `@agentmail.to` sender (inbox
`alivetree809@agentmail.to`). End-to-end flow is working: operator
signs in via `https://antiek.ai/login`, receives the link in
`the@faisalnazer.com`, lands on the workstation with the
`ANTIEK_SESSION` cookie set.

The follow-on step in the runbook is to register `antiek.ai` as a
custom domain in AgentMail so magic-link emails come from
`notifications@antiek.ai` instead of `alivetree809@agentmail.to`.

## What was discovered

Two constraints, both surfaced from the AgentMail docs on
2026-05-23:

1. **Custom domains are dashboard-only.** No API endpoint exists
   to register a domain. The dashboard returns DNS records the
   operator adds to their DNS provider; AgentMail re-verifies via
   a dashboard button.
2. **Custom domains require a paid plan.** Free tier excludes
   them. The cheapest plan with custom-domain support is the
   Developer tier at $20/month.

## Why deferral is the right call

The custom domain matters **only when sending to external
recipients**:

- **Sprint 19 publisher cohort outreach** (§9.10) — MIT Press,
  Cambridge UP, Princeton UP legal departments will filter or
  refuse mail from `@agentmail.to`. Hard block on G3 closure.
- **Sprint 19+ first individual subscribers** — branding affects
  trust signal once any non-operator receives a magic link.
- **§11 interview invitations** — same shape.

All three are **gated by G2 (lawyer review)**, which is currently
open. The binding precondition for needing the custom domain is
itself blocked. Spending $20/month today buys nothing the
substrate currently uses.

The substrate code is ready (`AgentMailEmailProvider` accepts any
inbox_id; the swap script generalises across `inb_*` and
`user@domain` ids). The runbook step 2 in
`infrastructure/runbooks/agentmail-setup.md` documents the
dashboard path for the operator to follow when G2 closes.

## Re-open trigger

The first time the operator is ready to send a real email to a
non-operator recipient — almost certainly the first publisher
notification — they should, in this order:

1. Upgrade AgentMail to the Developer plan
2. Register `antiek.ai` in the dashboard
3. Add the returned DNS records to Cloudflare (operator can paste
   them to the engineering assistant for help if needed)
4. Wait for verification (~10 min after DNS propagates)
5. Create `notifications@antiek.ai` via
   `POST /inboxes` with `{"username": "notifications", "domain": "antiek.ai"}`
6. Swap `ANTIEK_AGENTMAIL_INBOX_ID` on the VM via the existing
   swap script (or one curl-based env-var update)
7. Send a test magic link to confirm new sender
8. Fire the publisher cohort emails

All of this is well-defined; the only blocker is the operator's
decision to commit the $20/month + complete G2 first.

## What works today, in the meantime

Personal magic-link sign-in via `alivetree809@agentmail.to`. The
domain shows up clearly as an agent identity, which is what it
actually is. No deliverability concerns for the operator's own
inbox.
