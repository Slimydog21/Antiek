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
"""

from __future__ import annotations

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


__all__ = ["ads_allowed"]
