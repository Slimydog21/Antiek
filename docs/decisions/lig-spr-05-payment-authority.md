# LIG-SPR-05 payment authority boundary

Status: **pre-ratification; live checkout unavailable**  
Date: 2026-07-15

## Decision

Antiek does not have authority to enable live digital-book payments yet. The
operator has not selected a payment provider, delivery partner, merchant/legal
model, refund policy, or signed-event verifier. `ANTIEK_MARKETPLACE_LIVE_PAYMENT`
plus an injected processor is therefore insufficient: the factory also requires
a `LivePaymentAuthority`, and no production authority is configured.

`LivePaymentAuthority` is an enablement tripwire, not proof of a charge. A future
provider adapter must produce verified, durable evidence through the lifecycle
specified in
`docs/htmlspec/live-integration-gates/sprint-05a-entitlement-lifecycle.html`.
Until that sprint is executed, the live adapter is test-double scaffolding only.

## Current safe product boundary

- Live checkout is NOT RUN and must remain unavailable in deployment.
- Manual opaque receipts remain the offline fallback. They store no card data,
  but they are self-attested evidence, not processor-verified entitlement.
- The current HTTP manual-receipt route is acceptable only in an operator-only
  deployment. Multi-user exposure requires an operator approval workflow or the
  ratified live lifecycle; authenticated ownership alone is not purchase proof.
- Purchased content is owner-scoped, never classified as free, and is rendered
  only through canonical HTML.
- The pure product path stages extraction and uses a transactional SQLite commit
  for receipt, document, and membership. The canonical hosted-document route
  deliberately checkpoints extraction/event state; it must not be described as
  an atomic payment transaction until the lifecycle operation store exists.

## Required ratification packet

The operator must approve all of the following as one decision:

1. provider and merchant-of-record identity;
2. supported currencies, tax/refund rules, and title/price source of truth;
3. signed webhook/session verification algorithm and secret rotation policy;
4. purchased-file delivery authority, content-type/size/digest contract, and
   publisher-rights evidence;
5. replay identity and idempotency semantics;
6. refund, dispute, revocation, re-purchase, and offline-access semantics;
7. retention/deletion policy for opaque provider and entitlement evidence.

## Reversal condition

This decision becomes superseded only when the ratification packet is recorded,
a provider-specific verifier implements the nested sprint, its adverse-path and
recovery gates pass, and an operator explicitly authorizes a paid smoke test.
