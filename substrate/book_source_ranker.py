r"""Book acquisition source ranker — which source should an acquisition attempt first?

Operator vision (ask #5): *"I want to read books, and I am okay with buying a digital book
if there is no pdf online so build the marketplace functionality and also the seamless port so
that book gets hosted in my account on Antiek."* The book-purchase-transport decision spec's
invariant #3 is the preference rule: *"prefer DRM-free sources (Kobo, direct-from-publisher,
Project Gutenberg for public domain, Standard Ebooks); if only DRM'd is available, surface
'DRM-locked — open in the store's reader' and DON'T port."* This module is that rule as a
deterministic, auditable ranking — the decision-independent atom the transport adapter calls
BEFORE the budget gate (``book_acquisition_budget`` #2033) to pick which source to attempt, and
before the provenance chain (``book_provenance_chain`` #2035) stamps the chosen acquisition. It
answers: given a book the operator wants and the candidate sources that carry it, in what order
should acquisition try them — and is the top of that order a clean DRM-free source, or the honest
DRM-locked fallback the spec refuses to port?

**Genuinely distinct from the acquisition surface (load-bearing):**

* ``substrate/book_acquisition_budget`` (#2033, off main): the pre-purchase AFFORDABILITY gate —
  given a BATCH of books + the operator's budget, what fits? THIS ranks the SOURCES for ONE book
  (which store/free-source to try first). Different object (a book's source options vs a batch's
  budget fit), different question (acquisition order vs spend absorption). The transport adapter
  calls the ranker to pick a source, THEN the budget gate to confirm the picked source is affordable.
* ``substrate/book_provenance_chain`` (#2035, off main): POST-ACQUISITION integrity — was the chain
  of receipts that delivered the book tampered with? THIS is PRE-ACQUISITION ranking — before any
  receipt is stamped, which source should be attempted. The ranker decides the attempt order; the
  chain verifies the outcome.
* ``acquisition/books/registry`` (on main): a fixed ENUMERATION of the five public-domain
  connectors (Standard Ebooks, HathiTrust, Internet Archive, LoC, Wikisource) — a list, not a
  ranking. THIS ranks a book's candidate sources ACROSS both PD-free AND commercial DRM-free / DRM-
  locked stores, by the spec's stated preference. The registry tells you which sources EXIST; the
  ranker tells you which to TRY FIRST for a given book.
* ``substrate/source_throttle`` (on main): per-source RATE LIMITING (don't hammer a fetcher). THIS
  is source PREFERENCE ORDERING (which to prefer, not how fast to call it).

**The ranking (hard to vary).**

Candidates are ``SourceCandidate`` records: ``source_key`` (the connector/store id), ``cost_type``
(``"free"`` public-domain / ``"purchase"`` commercial), ``price_usd_cents`` (>= 0; 0 for free),
``drm_free`` (bool — True if the file is DRM-free and thus portable to HTML), ``rights_basis`` (the
defensible record a reviewer reads later: ``"public_domain:US-pre-1929"`` / ``"purchase:owned"`` /
``"subscription:lent"`` etc.), and ``provenance_strength`` — a documented ORDINAL
(``"established"`` > ``"claimed"`` > ``"unknown"``) for how well-founded the source's rights claim
is (a Standard Ebooks PD-only publication or a store purchase receipt is ``established``; a store
that asserts rights without a receipt is ``claimed``; an unverified source is ``unknown``).

The sort key, in strict precedence (each tier fully resolved before the next, so a later tier can
never override an earlier one):

1. **DRM-free before DRM-locked** (invariant #3 HARD RULE). A DRM-free source ALWAYS precedes a
   DRM-locked one — DRM-locked files are never ported (the spec refuses), so they sort to the back
   as last-resort fallbacks. A DRM-locked source is only reached when NO DRM-free candidate exists.
2. **free before purchase** (the operator's "buy if no free PDF online" — free PD is tried before
   spending). ``cost_type == "free"`` precedes ``"purchase"``.
3. **lower price** (among same cost-type — a cheaper DRM-free purchase beats a pricier one; price is
   0 for free sources so this tier is a no-op among frees, which is correct).
4. **higher provenance_strength** (established > claimed > unknown — a source with a solid,
   receipt-backed rights basis ranks above a weaker claim at equal cost/DRM).
5. **source_key ascending** (deterministic tiebreak — identical candidates never produce a
   non-deterministic order).

**Verdict (distinct honest states, never collapsed, DESCRIPTIVE not normative):**

* no candidates -> ``no_candidates`` (``recommended_source`` is None — never fabricate a pick).
* the recommended (rank-0) source is free AND DRM-free -> ``free_drm_free_preferred`` (the cleanest
  path: PD/free, portable, no spend).
* the recommended source is a paid DRM-free purchase -> ``paid_drm_free_preferred`` (portable but
  costs money — the operator's "buy if no free PDF" case).
* EVERY candidate is DRM-locked -> ``only_drm_locked`` (the honest gap: no portable source exists;
  the recommended is a fallback the spec says to "open in store reader, DON'T port"). This is
  surfaced explicitly so the transport layer refuses the port rather than silently treating a
  DRM-locked source as a normal acquisition.

**Key properties (load-bearing):**

* The ranker PROPOSES, the operator DECIDES. ``authority = "advisory"`` — it never acquires, never
  dispatches, never charges. The transport adapter reads ``recommended_source`` and demands explicit
  operator consent (the MO #1000 recommend->approve->run pattern, applied to acquisition).
* ``only_drm_locked`` is the honest gap surface: when True, the recommended source is a DRM-locked
  fallback that the spec refuses to port. The ranker does NOT silently recommend it as a clean
  acquisition — it flags the state so the transport surfaces "DRM-locked — open in store reader."
* Deterministic + auditable. Every tiebreak is documented and positional; re-ranking identical
  candidates reproduces the identical order. The ``rank`` field makes the preference explicit.
* The free-before-purchase and price tiers are sub-rules WITHIN the DRM-free band — a DRM-locked
  FREE source still sorts AFTER a DRM-free PAID source, because portability (DRM-free) dominates
  cost in the spec's hard rule. This is correct: a free-but-locked book you cannot port is worth less
  to the HTML-native library than a paid-but-portable one.
* provenance_strength is a documented ordinal, not a magic score — the three levels map to integers
  with a clear meaning, and an unknown level raises (a programming error, not an integrity finding).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "PROVENANCE_ORDER",
    "SourceCandidate",
    "RankedSource",
    "SourceRankingReport",
    "SourceRankerError",
    "rank_book_sources",
]

# The provenance-strength ordinal: higher = more well-founded rights claim.
# Documented meaning per level — not an arbitrary score. Looked up by name; an
# unknown level is a programming error (raises), not a ranking finding.
PROVENANCE_ORDER: dict[str, int] = {
    "established": 2,
    "claimed": 1,
    "unknown": 0,
}

# Cost-type precedence used inside the DRM-free band: free precedes purchase.
_COST_ORDER: dict[str, int] = {"free": 0, "purchase": 1}

# Descriptive verdict tokens — stable strings the transport layer + tests key off.
VERDICT_NO_CANDIDATES = "no_candidates"
VERDICT_FREE_DRM_FREE = "free_drm_free_preferred"
VERDICT_PAID_DRM_FREE = "paid_drm_free_preferred"
VERDICT_ONLY_DRM_LOCKED = "only_drm_locked"


@dataclass(frozen=True)
class SourceCandidate:
    """One source that carries the target book. The ranker orders these by the
    spec's preference (invariant #3). All fields are supplied by the connector /
    store resolver; the ranker never fetches, only sorts."""

    source_key: str
    cost_type: str
    price_usd_cents: int
    drm_free: bool
    rights_basis: str
    provenance_strength: str


@dataclass(frozen=True)
class RankedSource:
    """One candidate with its computed rank (0 = the recommended attempt). The
    ``recommended`` flag is True only for rank 0 so the transport layer can find
    the pick without re-deriving the sort."""

    rank: int
    source_key: str
    cost_type: str
    price_usd_cents: int
    drm_free: bool
    rights_basis: str
    provenance_strength: str
    recommended: bool


@dataclass(frozen=True)
class SourceRankingReport:
    """The reproducible preference order for one book's candidate sources.

    ``recommended_source`` is the rank-0 pick (None only for ``no_candidates``).
    ``has_drm_free_option`` / ``has_free_option`` describe the candidate pool's
    shape; ``all_drm_locked`` surfaces the honest port-refusal gap."""

    book_id: str
    ranked_sources: tuple[RankedSource, ...]
    recommended_source: RankedSource | None
    has_drm_free_option: bool
    has_free_option: bool
    all_drm_locked: bool
    verdict: str
    notes: tuple[str, ...] = ()
    authority: str = "advisory"


class SourceRankerError(ValueError):
    """Raised when a candidate is malformed (unknown cost_type / provenance level,
    negative price, empty source_key or rights_basis) — a programming error in the
    input, distinct from a ranking finding reported in :class:`SourceRankingReport`."""


def _sort_key(candidate: SourceCandidate) -> tuple[object, ...]:
    """The deterministic precedence key (see module docstring). Each tier fully
    resolves before the next: DRM-free dominates, then free-before-purchase, then
    lower price, then higher provenance_strength, then source_key ascending."""
    return (
        0 if candidate.drm_free else 1,  # DRM-free before DRM-locked (hard rule)
        _COST_ORDER[candidate.cost_type],  # free before purchase
        candidate.price_usd_cents,  # lower price
        -PROVENANCE_ORDER[candidate.provenance_strength],  # higher strength
        candidate.source_key,  # deterministic tiebreak
    )


def _validate_candidate(candidate: SourceCandidate) -> None:
    """Reject malformed candidates before ranking. An unknown cost_type /
    provenance_strength, a negative price, or an empty key/basis is a programming
    error (raises), not a ranking finding."""
    if not candidate.source_key:
        raise SourceRankerError("SourceCandidate.source_key must be non-empty")
    if candidate.cost_type not in _COST_ORDER:
        raise SourceRankerError(
            f"SourceCandidate.cost_type {candidate.cost_type!r} is not canonical "
            f"(expected one of {tuple(_COST_ORDER)})"
        )
    if candidate.price_usd_cents < 0:
        raise SourceRankerError(
            f"SourceCandidate.price_usd_cents must be >= 0; got {candidate.price_usd_cents}"
        )
    if not candidate.rights_basis:
        raise SourceRankerError("SourceCandidate.rights_basis must be non-empty")
    if candidate.provenance_strength not in PROVENANCE_ORDER:
        raise SourceRankerError(
            f"SourceCandidate.provenance_strength {candidate.provenance_strength!r} "
            f"is not canonical (expected one of {tuple(PROVENANCE_ORDER)})"
        )


def _verdict_for(recommended: RankedSource, all_drm_locked: bool) -> str:
    """Derive the descriptive verdict from the rank-0 pick's shape. Three clean
    states plus the honest DRM-locked fallback; never collapses distinct cases."""
    if all_drm_locked:
        return VERDICT_ONLY_DRM_LOCKED
    if recommended.cost_type == "free":
        return VERDICT_FREE_DRM_FREE
    return VERDICT_PAID_DRM_FREE


def rank_book_sources(
    book_id: str,
    candidates: Sequence[SourceCandidate],
) -> SourceRankingReport:
    """Rank one book's candidate sources by the spec's preference (invariant #3).

    Returns a :class:`SourceRankingReport` with the deterministic preference order
    and the descriptive verdict. ``recommended_source`` is the rank-0 pick the
    transport adapter should attempt first (after the budget gate confirms it is
    affordable and the operator consents). See the module docstring for the full
    precedence semantics.

    A malformed candidate raises :class:`SourceRankerError`. An empty candidate
    set is a valid (if failed) ranking: verdict ``no_candidates``,
    ``recommended_source`` None.
    """
    if not book_id:
        raise SourceRankerError("book_id must be non-empty")

    for candidate in candidates:
        _validate_candidate(candidate)

    if not candidates:
        return SourceRankingReport(
            book_id=book_id,
            ranked_sources=(),
            recommended_source=None,
            has_drm_free_option=False,
            has_free_option=False,
            all_drm_locked=False,
            verdict=VERDICT_NO_CANDIDATES,
            notes=("no candidate sources resolved for this book",),
        )

    ordered = sorted(candidates, key=_sort_key)
    ranked_sources = tuple(
        RankedSource(
            rank=index,
            source_key=c.source_key,
            cost_type=c.cost_type,
            price_usd_cents=c.price_usd_cents,
            drm_free=c.drm_free,
            rights_basis=c.rights_basis,
            provenance_strength=c.provenance_strength,
            recommended=(index == 0),
        )
        for index, c in enumerate(ordered)
    )

    has_drm_free_option = any(c.drm_free for c in ordered)
    has_free_option = any(c.cost_type == "free" for c in ordered)
    all_drm_locked = not has_drm_free_option

    recommended = ranked_sources[0]
    verdict = _verdict_for(recommended, all_drm_locked)

    notes: list[str] = []
    if all_drm_locked:
        notes.append(
            "no DRM-free source exists: recommended is a DRM-locked fallback the "
            "spec refuses to port (surface 'open in store reader', do not port)"
        )
    elif recommended.cost_type == "purchase":
        notes.append(
            f"recommended source {recommended.source_key!r} is a paid DRM-free "
            f"purchase ({recommended.price_usd_cents / 100:.2f} USD) — the budget "
            "gate must confirm affordability before acquisition"
        )
    else:
        notes.append(
            f"recommended source {recommended.source_key!r} is a free DRM-free "
            "source — the cleanest path (portable, no spend)"
        )

    return SourceRankingReport(
        book_id=book_id,
        ranked_sources=ranked_sources,
        recommended_source=recommended,
        has_drm_free_option=has_drm_free_option,
        has_free_option=has_free_option,
        all_drm_locked=all_drm_locked,
        verdict=verdict,
        notes=tuple(notes),
    )
