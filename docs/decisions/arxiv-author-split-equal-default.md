# arXiv multi-author ad-revenue split — equal by default

**Decision date:** 2026-05-30 (SPR-06, arxiv-ingest, M3 multi-author split)
**Status:** ✅ Implemented as the DEFAULT — `equal_split(n)` in
`substrate/payouts/split.py`, version-stamped `author-split-equal-v1`. The
ledger (`substrate/payouts/ledger.py`) splits a T1 paper read's attributed ad
revenue **equally** across the paper's OpenAlex-enriched authors, keyed by
0-based `author_position`, conserved to the cent via `apportion_cents`.
**Owner:** SPR-06 internal author-attribution ledger
**Binding rule is an OPERATOR decision** — the default is deliberately the
least-contestable starting point, not a final verdict. This document records the
default, the alternatives, and the steelman so the operator can rule from the
record.

## The decision

When a T1 (ad-eligible) arXiv paper is read and earns ad revenue, the revenue
attributed to that paper is split **equally** across its authors: each of `n`
authors is owed `1/n`, apportioned to integer cents by the largest-remainder
primitive so the per-author cents sum back **exactly** to the attributed total.
The split weights live in ONE version-stamped place
(`split.SPLIT_POLICY_VERSION` + `equal_split(n)`); every accrual row records the
stamped version, so "why is author X owed $Y" is answerable from the row alone,
and a future policy change is a new version — never a silent re-interpretation of
past accruals.

This is an INTERNAL accrual only. The ledger holds OWED amounts keyed by byline
position; it writes no escrow, contacts no author, and disburses nothing
(SPR-07 claims a position to an identity; SPR-08 pays out). The split rule
therefore decides *bookkeeping*, not a payment — which is exactly why a
contestable default is acceptable now and the binding rule can be set later
without re-plumbing.

## The alternatives, and the steelman of the rejected one

Three candidate rules:

1. **Equal split** (the default). Every author position gets `1/n`.
2. **First-author-only** (or last-author / corresponding-author-only). The
   whole share goes to one byline position.
3. **Weighted by contribution / corresponding-author-weighted.** A graded split.

### Steelman of first/corresponding-author-only (the rejected alternative)

The strongest case for *not* splitting equally:

- **Academic credit is not equal.** In most fields the first author did the bulk
  of the work and the last (senior/PI) author secured the funding and direction;
  the long middle of a large collaboration contributed marginally. An equal split
  across, say, 200 authors of a physics paper gives each a rounding-error share
  while the people who actually drove the work are diluted to the same slice as a
  contributor who ran one calibration. First-author-only (or
  first+corresponding-weighted) tracks the real credit distribution far better,
  and is the convention readers and authors already understand.
- **It concentrates a claimable amount.** A per-author `1/200` of a few cents is
  below any plausible payout floor — it is effectively unclaimable, so equal
  splitting can mean *nobody* ever realizes the revenue and it sits unattributed
  forever. Concentrating on the first/corresponding author produces a share large
  enough to be worth claiming, which is the whole point of an attribution ledger.

### Why equal is the DEFAULT anyway (not why first-author is wrong)

The steelman is real, but it does not win the **default**:

- **The metadata first-author-only needs is not reliably present.** OpenAlex
  exposes byline *position*, but "corresponding author" and contribution weight
  are frequently absent or noisy. A default that depends on data Antiek does not
  reliably have would silently degrade to "first byline position gets everything"
  even when that position is not the corresponding author — a confident-looking
  but wrong attribution. Equal split needs only the author *count*, which we do
  have whenever enrichment matched.
- **Equal is the hardest-to-game, least-surprising floor.** It never over-credits
  one position on incomplete data, and it conserves exactly. The dilution
  objection is a *payout-floor* problem (SPR-08), not an *accrual* problem — the
  ledger can hold a `1/n` share truthfully even if a later payout policy rolls
  sub-threshold shares forward or concentrates them at disbursement.
- **It is a one-place, version-bumped change to revise.** If the operator rules
  for first-author-weighted, that is a new `equal_split`-shaped function + a
  `SPLIT_POLICY_VERSION` bump; historical accruals stay replayable against the
  version that produced them. Nothing about choosing equal-now forecloses
  weighted-later.

So: **equal by default; the binding rule is the operator's to set**, and the
machinery is built so setting it is a single versioned edit.

## Unattributed pool — the no-author case (M4)

OpenAlex lags recent arXiv postings, so a freshly-harvested T1 paper is commonly
ad-eligible yet has **no** `openalex_enrichment` author list at all (or an empty
one). There is then no `author_position` to split across. `documents.author` is
NOT a usable fallback — the OAI path leaves it NULL and the adapter path writes a
single non-positional comma-joined string. So the whole attributed amount routes
to an explicit **unattributed** entry (`author_position = -1`, carrying the
`UNATTRIBUTED_RIGHTS_BUCKET` semantics: held, never misattributed, never
disbursed). This is the conservation backstop: revenue is always accounted to
*something* explicit, never silently dropped and never attributed to a wrong
position.

## Reverse-if

Revisit when SPR-07/SPR-08 land a payout floor and real claim data: if equal
splitting strands a material amount of revenue below the floor, an
operator-ratified first/corresponding-author-weighted policy (a new
`SPLIT_POLICY_VERSION`) becomes the better default. Until then, equal.
