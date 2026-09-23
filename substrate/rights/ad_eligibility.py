"""Ad-eligibility predicate — may Antiek run ads on a paper? (SPR-02 M3).

ONE rule, derived from the authoritative tier (``substrate.rights.arxiv_tiers``):

    ads_allowed(tier) == (tier == T1)

Only T1 (CC0 / CC-BY / CC-BY-SA — redistributable open) is ad-eligible. T2 and
T3 are NOT, and the boundary is hard.

The steelman, and why it is refused (fairness bar 2)
----------------------------------------------------
A reasonable-sounding proposal: *"Serve CC-BY-NC (T2) papers with ads, and
attribute the author — attribution honours the spirit of the license, and the
author benefits from the ad revenue."* It is refused:

  * The "NC" in CC-BY-NC is **NonCommercial**, a term of the license itself,
    not a courtesy. Creative Commons defines NonCommercial as "not primarily
    intended for or directed toward commercial advantage or monetary
    compensation." Ad-supported serving is monetary compensation directed at
    Antiek (and, under the payout model, a revenue split). It is commercial use
    on its face.
  * Attribution does NOT cure a commercial-use breach. CC-BY-NC requires BOTH
    attribution AND non-commercial use; satisfying one obligation does not
    waive the other. Attributing the author while monetizing their NC-licensed
    work is still a breach of the NC term — arguably a more visible one.
  * "The author benefits" is not the licensor's bargain to assume on their
    behalf. An NC licensor chose to withhold the commercial grant; Antiek is
    not entitled to substitute its judgment that the author would have wanted
    the money. The author can always re-license; until then NC means no ads.

So T2 papers may be DISPLAYED non-commercially (no ad border), and are never
ad-eligible. This predicate is the single gate the per-second ad border
(constants Section J) and the SPR-09 accrual ledger consult — they never
re-derive ad-eligibility from the license, only from the tier, so there is one
place this rule lives (defensibility bar 5).

That ONE rule now has ONE extension: a document with no licence tier carries
no licence signal and is decided by whether its body is publicly servable.
``substrate.books.serve_guard`` and ``substrate.payouts.ledger`` both call
``ad_eligibility()`` — serve-time and payout-time cannot re-derive it apart.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from substrate.rights.arxiv_tiers import resolve_tier
from substrate.schemas.documents import RightsTier

# The ad-eligible tiers. T1 only. A frozenset (not an ``== T1`` literal in the
# function body) so the rule is data a reviewer reads in one place, and so the
# rare future case "another tier becomes ad-eligible" is a one-line data edit
# with the rationale attached here — not a scattered conditional.
_AD_ELIGIBLE_TIERS: frozenset[RightsTier] = frozenset({RightsTier.T1_REDISTRIBUTABLE})


def ads_allowed(tier: RightsTier) -> bool:
    """Whether Antiek may run ads on a paper in this rights tier.

    True for T1 (redistributable open) ONLY. T2 (CC-BY-NC*: non-commercial
    display only) and T3 (default/unknown: link-back only) are both False —
    ad-funded serving is commercial use, which neither tier grants. Deny by
    default: any tier not explicitly ad-eligible is False.
    """
    return tier in _AD_ELIGIBLE_TIERS


@dataclass(frozen=True)
class AdEligibility:
    """One ad-eligibility decision: whether ads may run on (and ad revenue
    accrue for) a document, the licence tier it was decided on (``None`` when
    the document carries no licence signal), and a machine-readable reason."""

    eligible: bool
    tier: RightsTier | None
    reason: str


def licence_tier_of(metadata: Mapping[str, object]) -> RightsTier | None:
    """The licence tier a document's ad-eligibility is decided on, derived
    ONCE from its parsed ``documents.metadata`` for both the serve guard and
    the payouts ledger.

    - a "license_uri" key present -> resolve_tier(value if it is a str else
      None) (blank/None resolves to T3, deny-by-default);
    - no "license_uri" key but a non-empty str "arxiv_id" ->
      resolve_tier(None), i.e. T3: an arXiv paper whose immutable licence was
      never recorded is not ad-eligible. content_class is never read as a
      licence (SPR-02 anti-laundering: a stored class or rights_tier cannot
      launder revenue);
    - neither -> None: the document carries no licence signal (a book, a web
      page, a capture) and is decided by body servability.
    """
    if "license_uri" in metadata:
        value = metadata["license_uri"]
        return resolve_tier(value if isinstance(value, str) else None)
    arxiv_id = metadata.get("arxiv_id")
    if isinstance(arxiv_id, str) and arxiv_id:
        return resolve_tier(None)
    return None


def ad_eligibility(tier: RightsTier | None, *, servable: bool | None) -> AdEligibility:
    """THE ad-eligibility predicate.

    ``serve_guard.serve_full_text_guarded`` stamps
    ``ServeResult.ad_eligible`` from it, and ``payouts.ledger.accrue_paper_read``
    gates arXiv author accrual on it, so for an arXiv paper the reader cannot
    mount an ad border on a document whose revenue the ledger then refuses
    (or the reverse). The agreement is only that wide. The ledger turns any
    non-arXiv document away (``not_an_arxiv_paper``) before it consults this
    predicate, and book escrow (``book_escrow.accrue_reading_session``) does
    not consult it at all. Neither gap moves money today:
    ``accrue_reading_session`` is the only caller of ``accrue_paper_read`` and
    has no production caller, because the impressions endpoint it served
    returns 410. Whoever wires a settled-fill path to escrow must decide
    whether escrow accrual follows this predicate.

    - A licence tier decides on its own: eligible iff ``ads_allowed(tier)``
      (T1 only). servability is not consulted (a T1 paper is ad-eligible even
      while its body is gated; a T2/T3 paper never is).
    - With no licence tier the document is a book, page or capture: eligible
      iff its body is publicly servable. That covers
      ``SourceKind.LICENSED_PUBLISHER``: a §9.10 opt-in
      (``content_class opt_in_licensed``) is the commercial grant, so an
      opted-in book is ad-eligible; a gated pre-onboarded book is not (its
      escrow accrues through attribution, not the reader's ad border).

    ``servable`` must be given when tier is None; it is ignored otherwise.
    """
    if tier is not None:
        if ads_allowed(tier):
            return AdEligibility(True, tier, f"tier_ad_eligible:{tier.value}")
        return AdEligibility(False, tier, f"tier_not_ad_eligible:{tier.value}")
    if servable is None:
        raise ValueError(
            "a document with no licence tier is decided by body servability; "
            "pass servable="
        )
    if servable:
        return AdEligibility(True, None, "servable_body")
    return AdEligibility(False, None, "body_not_servable")


__all__ = ["AdEligibility", "ad_eligibility", "ads_allowed", "licence_tier_of"]
