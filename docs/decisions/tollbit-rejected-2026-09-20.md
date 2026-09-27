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
   inference product.** Its homepage [S1] lists Licensed RAG access, bot and
   agent paywall, content controls, Agent Site, MCP, NLWeb, portfolio
   analytics, TollBit Analytics, scraper audit and agent apps (coming soon),
   and names no ad revenue share, attribution-based payment or
   pay-per-inference product. (That absence is what the homepage and the
   rates page [S2] say; TollBit's full documentation was not audited.) Its
   unit is a rate "per 1000 pages accessed" [S2]. The
   model the operator wants publishers to end up on (ad-revenue share,
   attribution-weighted, `RevShareKind.PUBLISHER` at 70/30) cannot be
   expressed on TollBit at all, so it cannot be a bridge *to* that model; it
   is a bridge to per-fetch licensing.

2. **Antiek is the fee-paying AI buyer in every option the spec describes.**
   In §3.1 Antiek mints the Licensing Token and fetches; in §3.2 Antiek is the
   "AI buyer" the publisher sets rates for; in §3.3 Antiek pays "during the
   bridge period". The 2026-08-12 spec also quotes TollBit's docs as
   charging "AI customers a small transaction fee on top of the rates you
   set"; that sentence was not in the text retrieved from the cited page on
   2026-09-24 and is NOT MEASURED here. The disqualifier does not need it:
   the spec's own §3.1-§3.3 make Antiek the payer. TollBit is a cost line
   on Antiek's P&L, never a revenue line, and it sits between Antiek and
   the publisher relationship the entire §9.10 strategy depends on owning.

3. **Per-fetch pricing raises the price of the eventual ad-revshare ask.**
   A publisher who has been paid per fetch (the 2026-08-12 spec gives
   $0.001-$0.20 as "typical April 2026 rates" without a source:
   NOT MEASURED) has a per-fetch anchor. The migration pitch in the old
   spec's §4.3 ("if you switch to our
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
  no-training), so a site or CDN can allow one use and refuse another.
  Cloudflare's 2026-09-15 post [S3] describes per-purpose controls whose
  presets, for domains onboarded from that date, allow Search, block Agent
  "on pages with ads" and publish a no-training preference for ad-supported
  sites; existing domains keep their settings. The post does not require
  separate user agents, and whether Cloudflare would classify Antiek's
  agents by purpose at all is NOT MEASURED. Implemented in
  `acquisition/urls/client.py`.
- **The pre-onboarded escrow** (`substrate/rights/register.py`) as the lure —
  "you already have N dollars waiting" — gated on counsel (§9.10 G2), which
  is the one operator gate in this lane and is recorded as such in
  `specs/antiek-v1-connect/SPR-10-tollbit.md` task 7.

## What this does not decide

- Cloudflare Pay Per Crawl / Pay Per Use posture. The 2026-08-12 spec's "not
  worth the integration tax" ruling predates Cloudflare's 2026-09-15
  per-purpose presets [S3] and should be re-read against them; that is a
  separate decision.
- Whether to join the RSL Collective as a *licensee*. Reading RSL terms is
  free and needs no membership; paying for RSL-licensed content is a later
  call.

## Revisit trigger

Reopen only if TollBit ships an ad-revenue-share or attribution-based payment
product in which the publisher, not the AI buyer, is the paying side. A new
per-fetch rate card, however low, does not reopen this.

## Sources (retrieved 2026-09-24)

- [S1] TollBit homepage, https://tollbit.com/ — product list; no ad,
  attribution or pay-per-inference product named.
- [S2] TollBit docs, "Enabling Monetization",
  https://docs.tollbit.com/docs/setting-rates — "Set your rate per 1000
  pages accessed and click activate".
- [S3] Cloudflare blog, "accountable mixed-use AI crawlers", published
  2026-09-15, https://blog.cloudflare.com/accountable-mixed-use-ai-crawlers/
  — new-domain presets (ad-supported: Search allow, Agent block on pages
  with ads, Disallow AI Training); "Your current settings carry over on
  their own" for existing domains.
- RSL 1.0 specification, https://rslstandard.org/rsl — `License:`
  directive (s4.4), `<content url>` scope (s3.3) and precedence (s3.1.1),
  payment types.
