# ProRata / Gist — competitive read against Antiek's attribution economy

**Date:** 2026-09-20 (recon), recorded 2026-09-22
**Status:** research-complete
**Reads with:** `docs/decisions/tollbit-rejected-2026-09-20.md`,
`docs/decisions/white-label-marketplace-rejected-2026-09-20.md`,
`master-product-spec.md` §9, §9.10, §13.5, §13.9

## Why this document exists

`git grep -iln -E 'prorata|gist answers' origin/main` returned nothing before
this file. The operator was making the "drop the gate, take ad revenue"
strategy call on a map with no one standing where he wants to stand. ProRata
is standing there: it runs the same model, at scale, with a Series B behind
it.

## What ProRata / Gist is

ProRata.ai's Gist Answers is an AI answer engine (and an embeddable
publisher-site answer widget) that keeps 50% of the ad revenue shown alongside
an answer and pays the other 50% to the publishers whose content the answer
drew on. ProRata announced a $40M Series B, led by Touring Capital, on
2025-09-05 to launch Gist Answers [P1, P2]. Status of each claim, as of
2026-09-24:

- The 50% publisher share and "more than 700" participating publications
  appear in the 2025-09-05 release [P1] as quoted by search results; the
  release page itself returned HTTP 403 to a direct fetch, so its body was
  not read.
- The round size, date and lead are confirmed by a secondary report [P2].
- That the split is proportional to per-citation attribution, the
  publisher-side pitch (no per-fetch fee, no licensing negotiation), and
  the recon's "500+ deals including the Boston Globe, Vox Media, Future and
  Raptive" are NOT MEASURED: no primary page was retrieved that states
  them, and gist.ai's homepage does not.

That is the operator's endgame, shipped by someone else first.

## Head-to-head

### Split: 50/50 vs 70/30

ProRata keeps 50 and pays 50. Antiek keeps 30 and pays 70:
`substrate/ad_inventory/payout.py:29` `CREATOR_REV_SHARE = Decimal("0.70")`
and `:30` `PLATFORM_CUT = Decimal("0.30")` (recon citation; on main at
27291eb59 the same two constants sit at `payout.py:34-35`, the file grew
above them). `RevShareKind.PUBLISHER` is the pre-onboarded IP holder
recipient under §9.10, so a publisher book is paid at the same 70 as a
creator.

Antiek's number is better for the publisher by 20 points of gross. It is
also a number, and a number is the easiest thing for a funded competitor to
match. Nothing in the tree makes 70 structural; it is one `Decimal` literal.
Treat the split as table stakes, not a differentiator.

### Attribution unit: per-citation vs per-frame attention

ProRata attributes per answer: the sources an answer drew on share its
pool (the per-citation weighting is the recon's reading, NOT MEASURED
above). The unit is the answer.

Antiek attributes per second of in-frame attention:
`substrate/ad_inventory/frame_attention.py` defines the per-second telemetry
contract (`FrameAttentionSample`, `FrameSecond`, `WindowFrameBatch`) and
`weigh_second`, which drops ineligible assets, weights each eligible asset by
area × prominence × focus, and normalises the eligible weights to exactly 1.0
per second (or 0 for a house second). The unit is the second, and the asset
is whatever is visible in the window, not whatever the model chose to cite.

This is a real structural difference, and it cuts in Antiek's favour only
because Antiek owns the window. Per-frame attention requires the reading /
research / writing surface to be Antiek's own so that the frame is
observable. ProRata's surface is an answer box; it can see citations because
it produced them, and it cannot see dwell on a page it does not render. To
copy per-frame attention ProRata would have to become a reader, which is a
product change, not a parameter change.

### The asset ProRata lacks: escrow that accrues before a publisher signs

`substrate/rights/register.py` `resolve_or_create_ip_holder()` creates a
`pre_onboarded` ip_holders account by display name, idempotently, with no
notification, and `accrue_reading_session()` in
`substrate/marketplace_metrics/book_escrow.py` is written to accrue the
publisher's 70 into that account from the first paid impression on an
ad-eligible document (since the SPR-10 review fix it first asks the shared
ad-eligibility predicate, so a gated, not-yet-opted-in book earns nothing
from the reader's border; that holder's balance would come from per-second
frame attention, `frame_attention_accrual.accrue_window`, whose earn gate
admits gated-but-public assets). Nothing calls `accrue_reading_session`
in production today. The client-priced impressions endpoint it served,
`record_ad_impressions` in `interfaces/research/api/books.py`, returns 410
`client_priced_ad_impressions_disabled`, and revenue may enter accrual again
only from a future authoritative settled-fill record. So no money accrues yet.
Once a settled-fill path feeds it, the mechanism accumulates money for rights
holders who have never heard of Antiek. ProRata signs first and pays second;
Antiek would pay first and ask second. As a pitch, "you
already have N dollars waiting" beats any rate card, and it is the closest
digital analogue of the Spotify advance.

## Does the differentiator survive contact?

Verdict: no. The escrow-before-signing asset is not a moat and should not
be described as one in any operator-facing document.

Two reasons, in order of weight:

1. **It is copyable in an afternoon.** Nothing about accruing a shadow
   balance for an unsigned publisher requires Antiek's substrate. ProRata has
   the attribution data and the ad revenue; adding an unsigned-publisher
   ledger and an outreach email is a feature, not an architecture. ProRata
   lacks it today because nobody has bothered, not because they cannot.
2. **It is inert until counsel clears it.** The account is created
   `pre_onboarded` and *no notification is sent*; that gates on §9.10 G2
   lawyer review plus operator action (`register.py` docstring). Nor does any
   balance accrue today: the escrow accrual has no production caller until a
   settled-fill path is wired to it. A balance nobody is told about is not a
   lure. The differentiator exists only in the
   notified form, and the notified form does not exist yet.

What survives contact is the thing ProRata cannot buy with the Series B:
**owning the window.** Per-frame attention needs Antiek's reader, research
and write surfaces to be where the reading happens. That is the moat, and it
is the reason the 70/30 and the escrow are worth anything at all — they are
what Antiek can offer *because* it sees the second, not the citation.

## Consequences for the lane

- Stop describing pre-onboarded escrow as a differentiator in strategy docs;
  describe it as a *timing* advantage that expires the day ProRata copies it,
  and that starts only when counsel clears the notification (SPR-10 task 7,
  the lane's one operator gate).
- The publisher pitch leads with the window (per-frame attention, the reader
  as the place the reading happens) and the 70, in that order. The escrow
  balance is the closer, not the opener.
- Watch ProRata for (a) an unsigned-publisher balance feature and (b) any
  move toward rendering the page rather than the answer. (a) erases the
  timing advantage; (b) attacks the moat.

## Sources (retrieved 2026-09-24)

- [P1] Business Wire, "ProRata Closes $40 Million Series B Financing and
  Launches Gist Answers ...", 2025-09-05,
  https://www.businesswire.com/news/home/20250905771340/en/ (direct fetch
  returned HTTP 403; quoted via search results only).
- [P2] Built In LA, "ProRata Closes $40M Series B, Launches AI-Powered
  Revenue Tool", 2025-09-05,
  https://www.builtinla.com/articles/prorata-raises-40m-series-b-20250905
  — "$40 million Series B funding round led by Touring Capital".
- Gist homepage, https://gist.ai/ — names Gist GEO and Gist Answers; states
  no split, publisher count or named publishers.
