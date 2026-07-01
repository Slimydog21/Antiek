# G2 Counsel Packet - Publisher Notification Review

**Status:** operator-support packet; **does not close G2**.
**Gate:** G2 / OA-001 lawyer review of the Kalshi-pattern publisher
notification template.
**Prepared:** 2026-07-01.

This packet gathers the source material the operator sends to counsel
before the first publisher notification email. It is not legal advice,
not counsel signoff, and not the closure artifact. G2 closes only when
`docs/decisions/g2-lawyer-review.md` records the lawyer, firm, date, and
verdict.

## Review Ask

Please review whether Antiek's publisher notification template and
pre-onboarded escrow posture are defensible under current US copyright
and commercial-speech doctrine before any first-cohort publisher email
is sent.

Counsel should specifically review:

1. Whether the template wording avoids framing Antiek as admitting
   infringement or restitution liability.
2. Whether the opt-in-only payout gate is sufficient to support the
   posture that Antiek is voluntarily sharing future revenue rather
   than paying damages.
3. Whether the 30-day costless opt-out commitment is adequate for
   first-contact publisher outreach.
4. Whether the phrase "segregated escrow" may be used before OA-014
   regulated escrow accounts are opened, or whether the copy must say
   "accrual ledger" until bank setup is complete.
5. Whether the Trust Center compliance copy needs wording changes
   before publication at `antiek.ai/trust`.

## Architecture Summary

Antiek uses published works for AI-mediated research synthesis and
discussion. The platform's stated posture is that it is not republishing
books and is not giving users cover-to-cover reading access. It uses
chunks of text for attribution-bearing synthesis while routing revenue
share back to IP holders in good faith from day one.

The implementation creates an `ip_holders` row in `pre_onboarded`
status, accrues attribution-linked revenue to that holder, and refuses
money movement until the publisher affirmatively claims the account.
The state machine is:

```text
pre_onboarded -> invited -> claimed | opted_out
```

Important constraints already represented in code and docs:

- The notification email goes to the publisher's legal department, not
  marketing.
- No notification email is sent before lawyer review.
- Claiming must happen through a documented process before any payout
  route opens.
- Opt-out records the publisher's removal request and the platform
  commits to removal within 30 days.
- Accrual and disbursement are separate. Accrual can exist before G2/G3;
  disbursement remains gated on G2 lawyer review plus G3 publisher opt-in.

Primary source files:

- `substrate/ip_holders/__init__.py`
- `docs/master-product-spec.md` section 9.10
- `docs/operator_gate_actions.md` section G2
- `docs/OPERATOR_ACTIONS.md` section OA-001
- `docs/trust_center_public.md`

## Current Template

Render the current canonical template with:

```bash
./.venv/bin/python -c "
from substrate.ip_holders import IpHolder, render_notification_email
from datetime import datetime, timezone
from decimal import Decimal
h = IpHolder(
  ip_holder_id='mit-press',
  display_name='MIT Press',
  legal_contact_email='legal@mitpress.mit.edu',
  status='pre_onboarded',
  escrow_balance_usd=Decimal('0.00'),
  escrow_account_ref=None,
  notification_sent_at=None,
  claimed_at=None,
  opted_out_at=None,
  created_at=datetime.now(timezone.utc).isoformat(),
)
print(render_notification_email(h))
"
```

The rendered template should include:

- The phrase "transformative under fair use".
- Explicit denials that Antiek is republishing books or enabling
  cover-to-cover reading.
- A claim invitation.
- A no-payment-until-claim statement.
- A costless opt-out path.
- The `legal@antiek.ai` reply contact.

## Legal Context To Review

The operator's working assumption is that pre-onboarded accounts cut both
ways:

- Helpful: timestamped notice, claimable account, and accruing publisher
  ledger support a good-faith revenue-share posture.
- Harmful: the ledger may be framed as documenting use of unlicensed
  content and an admission that value is owed.

Counsel should review that tradeoff against at least:

- Bartz v. Anthropic settlement context, including the risk that
  procurement or content-source facts matter more than training theory.
- Hachette v. Internet Archive, including the Second Circuit rejection of
  the controlled-digital-lending fair-use theory.
- Google Books opt-out reasoning, especially whether a voluntary,
  publisher-claim flow plus costless opt-out avoids the most dangerous
  opt-out-by-default framing.

## Trust Center Copy

`docs/trust_center_public.md` is currently counsel-pending. Before public
publication, counsel should review the placeholders it names:

- GDPR Article 13/14 wording.
- CCPA notice wording.
- Legal entity name and jurisdiction.
- Data processor list and transfer mechanism.
- Incident-disclosure thresholds.

This packet does not ask counsel to approve production publication unless
those placeholders are filled in or explicitly accepted as temporary copy.

## Closure Artifact

If counsel approves, the operator should commit
`docs/decisions/g2-lawyer-review.md` with:

- Review date.
- Lawyer name and firm.
- Exact template version reviewed.
- Verdict: approved, approved with changes, or rejected.
- Any required edits before first publisher email.

Only then should OA-001/G2 be marked closed and Sprint 19 first-cohort
publisher outreach proceed.
