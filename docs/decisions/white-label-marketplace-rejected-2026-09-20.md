# Decision — No white-label digital marketplace is worth buying

**Date:** 2026-09-20 (recon), recorded 2026-09-22
**Status:** accepted
**Cite:** `docs/decisions/tollbit-rejected-2026-09-20.md`;
`substrate/rights/ad_eligibility.py` (T1-only ad gate);
`substrate/ad_inventory/payout.py` (`RevShareKind`, 70/30 split);
`substrate/ad_inventory/attribution.py`, `frame_attention.py`,
`fill_settlement.py`, `auction_ranker.py`, `decisions_log.py`,
`advertiser_onboarding.py` (the in-tree payout substrate);
`substrate/rights/register.py` (pre-onboarded escrow).

## Context

The question "should Antiek buy a white-label marketplace instead of building
the publisher-facing surface" was asked during the SPR-10 recon and will be
asked again unless the negative is written down. The market scan returned
generic multi-vendor e-commerce skins. None of them does the hard part.

## The candidates, and why each fails

The hard part of Antiek's publisher surface is three things: rights clearance
(who may be paid, under which licence, with which body-serving posture),
per-chunk attribution (which asset earned which second of attention), and
AI-access licensing (machine-readable terms a crawler can read and honour).
Twenty-seven files under `substrate/ad_inventory/` plus `substrate/rights/`
already implement more of this than any candidate ships. Against that bar:

- Yo!Kart (from $1,249): a multi-vendor e-commerce storefront — catalogue, cart, vendor dashboards, commissions on physical or digital SKUs. No rights clearance, no per-chunk attribution, no AI-access licensing. The commission engine is per-order, not per-second-of-attention.
- Vendasta: an agency-facing white-label SaaS reseller marketplace — bundles third-party SaaS under a partner brand. It resells software; it has no concept of a licensed text corpus, attribution or crawler terms.
- RapidDev: a custom-build agency that assembles marketplaces to order; buying it is buying engineering hours, not a product, and the hours would be spent reimplementing what `substrate/ad_inventory/` already has.
- Kitaboo / MagicBox: white-label eBook and LMS delivery platforms — DRM-wrapped reader, course packaging, institutional licensing. Closest in domain and still wrong: DRM at the reader is the opposite posture from an ad-funded open corpus, there is no attribution-weighted payout, and no machine-readable AI-access terms.

## Decision

Buy nothing in this category. The only bought component in the publisher
payout path is Stripe Connect, for payouts, KYC and 1099 reporting — which
was already the plan (`docs/specs/tollbit-bridge-2026-08-12.md` §3.2 named
it as the rail under `publisher.antiek.ai`, and the rejected TollBit rail was
itself Stripe Connect under the hood).

The pre-publisher revenue surface does not wait on any marketplace: T1 open
content (CC0 / CC-BY / CC-BY-SA) is already ad-eligible under
`substrate/rights/ad_eligibility.py`, so the ad border earns on the open
corpus today, and licensed-publisher content joins through the §9.10 opt-in
flow and the pre-onboarded escrow in `substrate/rights/register.py` — not
through a storefront.

## The one metric that would justify revisiting

Publisher onboarding throughput. If, once counsel clears the escrow
notification, the bottleneck to signing publishers is measurably the
self-serve dashboard (claim flow, rate visibility, payout statements) rather
than legal or the revenue number — concretely, more than half of contacted
holders stall at the claim step for a product reason — then a bought
dashboard shell becomes worth pricing. A bought shell would still sit on top
of Antiek's rights, attribution and escrow substrate; it would never replace
it.
