"""Multi-author split policy for the (arxiv_id, author_position) accrual ledger
(SPR-06 M3).

ONE place, ONE version-stamped policy. A T1 paper's attributed ad revenue is
split across the paper's OpenAlex-enriched authors. The default policy is
EQUAL: each of ``n`` authors receives an equal share, ``1/n``. The split is
expressed as WEIGHTS (a ``dict[str, float]`` keyed by the 0-based
``author_position`` as a string), which the ledger feeds to
``substrate.ad_inventory.frame_attention.apportion_cents`` — the ONE
largest-remainder rounding primitive — so the per-author integer cents always
sum back EXACTLY to the attributed total (conservation-to-the-cent). This module
therefore NEVER re-implements rounding; it only decides the weights.

Why the policy is here, version-stamped, and NOT hard-coded at the call site
-----------------------------------------------------------------------------
The split rule is a CONTESTABLE policy (equal vs. first-author-only vs.
corresponding-author-only — see
``docs/decisions/arxiv-author-split-equal-default.md``). The FINAL rule is an
operator decision. Pinning it to a single named, versioned function means:

  * "Why is author X owed $Y?" is fully answerable from the stamped
    ``SPLIT_POLICY_VERSION`` on each accrual row + the input author count
    (defensibility) — a changed policy is a NEW version, never a silent
    re-interpretation of past accruals.
  * A future operator ruling (e.g. corresponding-author-weighted) is a one-place
    edit + a version bump, not a scattered conditional across the ledger.

The default stays EQUAL because it is the only split that needs no per-paper
metadata Antiek does not reliably have (corresponding-author / contribution
order is frequently absent from OpenAlex), and it is the least-surprising,
hardest-to-game default. It is a DEFAULT, not a verdict.
"""

from __future__ import annotations

# Version stamp recorded on every accrual row this policy produces. Bump on ANY
# change to the weight semantics so historical accruals remain replayable
# against the exact policy that produced them. ``equal`` names the rule;
# ``v1`` the revision.
SPLIT_POLICY_VERSION: str = "author-split-equal-v1"


def equal_split(n: int) -> dict[str, float]:
    """Equal-weight split across ``n`` authors, keyed by 0-based author position
    (as a string, the ledger's key form).

    Returns ``{ "0": 1/n, "1": 1/n, ... }`` — weights summing to 1.0 in exact
    arithmetic (float drift is irrelevant: the ledger feeds these to the
    largest-remainder ``apportion_cents``, which conserves the integer-cent
    total regardless of float representation). ``n <= 0`` returns an empty dict
    — the ledger reads that as "no attributable author" and routes the whole
    amount to the unattributed pool rather than dividing by zero.
    """
    if n <= 0:
        return {}
    share = 1.0 / n
    return {str(i): share for i in range(n)}


__all__ = ["SPLIT_POLICY_VERSION", "equal_split"]
