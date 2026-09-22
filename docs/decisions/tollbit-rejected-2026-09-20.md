# Decision — TollBit integration REJECTED (reverses the 2026-08-12 "bridge" verdict)

**Date:** 2026-09-20 (recon), recorded 2026-09-22
**Status:** accepted
**Supersedes:** the "Verdict: Integrate TollBit as a short-to-medium-term bridge
(Sprint 18-22)" line in `docs/specs/tollbit-bridge-2026-08-12.md` §1, and the
"Integrate TollBit? Yes, as bridge" row in its §6 decision matrix.
**Cite:** `docs/specs/tollbit-bridge-2026-08-12.md` (now carries a superseded
banner); `substrate/ad_inventory/payout.py` (`CREATOR_REV_SHARE` 0.70 /
`PLATFORM_CUT` 0.30, `RevShareKind.PUBLISHER`);
`substrate/rights/register.py` (`resolve_or_create_ip_holder`, pre-onboarded
escrow); `docs/decisions/white-label-marketplace-rejected-2026-09-20.md`;
`docs/specs/prorata-competitive-2026-09-20.md`.

## Context

Main has carried a 197-line TollBit assessment since 2026-08-12 whose headline
verdict is "Yes, integrate (Sprint 18-22)". Zero TollBit code exists on main
(`git grep -iln 'tollbit' origin/main -- ':!docs/'` is empty at 27291eb59), so
the integration is one hundred percent documentation — and that document is
the artifact a fresh agent will execute against. The operator's stated position
is that TollBit is "a bridge, not the endgame" and that publishers should
eventually drop the API payment gate in favour of ad revenue inside Antiek's
attribution economy. The 2026-08-12 spec agreed with the endgame and still
recommended paying for the bridge. This record reverses that recommendation.

## Decision

Do not integrate TollBit. Do not write a TollBit client, mint TollBit
licensing tokens, adopt its Licensed Search API, or route publisher payouts
through its rail. Three disqualifiers, each sufficient on its own:

1. **TollBit's product surface carries no advertising, attribution or
   inference product.** Its live surface — Licensed RAG access, bot and agent
   paywall, content controls, Agent Site, MCP, NLWeb, portfolio analytics,
   agent apps — contains no ad revenue share, no attribution-based payment and
   no pay-per-inference. Its unit is "your rate per 1000 pages accessed". The
   model the operator wants publishers to end up on (ad-revenue share,
   attribution-weighted, `RevShareKind.PUBLISHER` at 70/30) cannot be
   expressed on TollBit at all, so it cannot be a bridge *to* that model; it
   is a bridge to per-fetch licensing.

2. **Antiek is the fee-paying AI buyer in every option the spec describes.**
   In §3.1 Antiek mints the Licensing Token and fetches; in §3.2 Antiek is the
   "AI buyer" the publisher sets rates for; in §3.3 Antiek pays "during the
   bridge period". TollBit "charges AI customers a small transaction fee on
   top of the rates you set". TollBit is a cost line on Antiek's P&L, never a
   revenue line, and it sits between Antiek and the publisher relationship the
   entire §9.10 strategy depends on owning.

3. **Per-fetch pricing raises the price of the eventual ad-revshare ask.**
   A publisher who has been paid $0.001-$0.20 per fetch has a per-fetch
   anchor. The migration pitch in the old spec's §4.3 ("if you switch to our
   native dashboard you get 70% ad rev-share on top of licensing fees")
   concedes the point: it stacks ad revenue *on top of* the fee rather than
   replacing it. Paying per fetch first makes "drop the gate" a pay cut to
   negotiate down from, not a free upgrade to offer.

## What replaces it

- **Read publishers' own machine-readable licence terms off `robots.txt`**
  (RSL `License:` directive → `/license.xml`, including the `attribution` and
  `free` payment types). This is the free bridge: it finds the publishers who
  have already dropped the gate. Implemented in `acquisition/urls/robots.py` +
  `acquisition/urls/rights_terms.py`.
- **Purpose-split crawler identity** (search / agent-retrieval / explicit
  no-training) so Cloudflare's 2026-09-15 mixed-use default block does not
  silently cost coverage. Implemented in `acquisition/urls/client.py`.
- **The pre-onboarded escrow** (`substrate/rights/register.py`) as the lure —
  "you already have N dollars waiting" — gated on counsel (§9.10 G2), which
  is the one operator gate in this lane and is recorded as such in
  `specs/antiek-v1-connect/SPR-10-tollbit.md` task 7.

## What this does not decide

- Cloudflare Pay Per Crawl / Pay Per Use posture. The 2026-08-12 spec's "not
  worth the integration tax" ruling is stale (Cloudflare now blocks mixed-use
  AI crawlers by default on ad-carrying pages); that is a separate decision.
- Whether to join the RSL Collective as a *licensee*. Reading RSL terms is
  free and needs no membership; paying for RSL-licensed content is a later
  call.

## Revisit trigger

Reopen only if TollBit ships an ad-revenue-share or attribution-based payment
product in which the publisher, not the AI buyer, is the paying side. A new
per-fetch rate card, however low, does not reopen this.
