"""Document-level rights schema: the arXiv OAI-PMH record + the rights-tier
census taxonomy.

This module is additive to ``substrate.schemas`` and is the source of truth
for two things SPR-01 needs that the existing event/book schemas do not carry:

1. ``ArxivOaiRecord`` — one harvested OAI-PMH record. Its ``license_uri`` is
   the AUTHORITATIVE rights anchor: the value of the
   ``{http://arxiv.org/OAI/arXiv/}license`` element, which only the
   OAI-PMH ``arXiv`` metadata format carries. This is deliberately a distinct
   field from any OpenAlex-derived license — the OAI element is arXiv's own
   declaration and is what the payout business case is allowed to rely on.
   OpenAlex has no equivalent element; see the census doc / SPR-01 packet for
   why we do not source the license from it.

2. ``RightsTier`` + ``classify_tier`` — the three-tier taxonomy the corpus
   census is measured against. The entire downstream payout case rides on how
   large T1 is, so the taxonomy is a closed, exhaustive partition with a
   deny-by-default floor:

     T1  redistributable open    — CC0 / CC-BY / CC-BY-SA
     T2  non-commercial          — CC-BY-NC*
     T3  default / unknown / none — arXiv-default-distrib, all-rights-reserved,
                                    unrecognised URIs, AND absent licenses

   T3 is the catch-all: an absent or ambiguous license is COUNTED in T3, never
   silently dropped and never optimistically promoted to T1. The boundary is a
   pure function of the resolved license (``acquisition.arxiv.licenses``) so the
   census is reproducible and one reviewer reads one mapping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

# NOTE: ``resolve_license`` is imported LAZILY inside ``classify_tier`` rather
# than at module top. ``substrate.schemas`` sits at the BOTTOM of the
# dependency stack (see schemas/events.py); importing ``acquisition`` here at
# module load both inverts that layering and creates an import cycle
# (acquisition.arxiv.__init__ re-exports the harvester, which imports this
# module). The lazy import keeps the legal mapping as the one home for CC
# semantics without dragging acquisition into substrate's import graph.


class RightsTier(str, Enum):
    """The three rights tiers the census partitions arXiv into.

    ``str`` mixin so a tier serialises to its value in JSON/CSV census output
    without a custom encoder. The values are the report column keys.
    """

    T1_REDISTRIBUTABLE = "T1"  # CC0 / CC-BY / CC-BY-SA — servable open
    T2_NON_COMMERCIAL = "T2"   # CC-BY-NC* — gated (NC bars ad-funded serving)
    T3_DEFAULT_UNKNOWN = "T3"  # arXiv-default / unknown / absent — gated floor


@dataclass(frozen=True)
class EnrichedAuthor:
    """One author of an arXiv paper, as disambiguated by OpenAlex (SPR-03 M2).

    This is the typed shape stored under ``documents.metadata["openalex_enrichment"]
    ["authors"]`` — it is ADDITIVE enrichment, never a rights or identity anchor
    the payout case relies on. The arXiv OAI-PMH record stays authoritative for
    license + tier; OpenAlex only contributes citation graph + author identity.

    Fields:

      * ``orcid`` — the author's ORCID identifier (e.g.
        ``https://orcid.org/0000-0002-1825-0097``) when OpenAlex carries one,
        else ``None``. NEVER invented: an absent ORCID stays ``None`` so SPR-07's
        claim flow can tell "OpenAlex disambiguated this author to a real ORCID"
        apart from "no identity was found." ORCID is the only stable cross-source
        author key OpenAlex exposes.
      * ``author_position`` — the author's 0-based index in the byline, preserving
        the OpenAlex/arXiv ordering (first / middle / last authorship carries
        meaning in academic credit). Derived from the authorship's position in the
        ``authorships`` list, NOT re-sorted.
      * ``display_name`` — the author's display name as OpenAlex records it. A
        best-effort label, not an identity key (the ORCID is the key).

    A plain frozen dataclass (not a Pydantic event payload), so it is NOT part of
    the TypeScript codegen surface (``tools/codegen/emit_types.py`` reads only
    ``substrate.schemas.events`` Pydantic models). It rides inside the metadata
    JSON blob, which the reading UI reads as untyped JSON.
    """

    orcid: str | None
    author_position: int
    display_name: str


@dataclass(frozen=True)
class ArxivOaiRecord:
    """One OAI-PMH ``<record>`` (metadataPrefix=arXiv), parsed.

    Carries only the load-bearing rights + identity fields; the full raw XML is
    out of scope here (the harvester streams it). ``license_uri`` is ``None``
    when the record's ``<license>`` element is absent or empty — the
    deny-by-default input that ``classify_tier`` lands in T3.

    ``deleted`` flags an OAI tombstone (``<header status="deleted">``): such
    records carry no metadata and are excluded from the census denominator
    rather than miscounted as unknown-license live papers.
    """

    arxiv_id: str
    datestamp: str  # OAI header datestamp (YYYY-MM-DD), the harvest cursor
    license_uri: str | None = None
    title: str | None = None
    categories: tuple[str, ...] = ()
    deleted: bool = False

    @property
    def tier(self) -> RightsTier:
        """This record's census tier — deny-by-default via ``classify_tier``."""
        return classify_tier(self.license_uri)


def classify_tier(license_uri: str | None) -> RightsTier:
    """Map a license URI to its census tier. Deny-by-default to T3.

    RECONCILED (SPR-02): this is now a thin DELEGATION to the authoritative
    resolver ``substrate.rights.arxiv_tiers.resolve_tier`` — the ONE source of
    truth that serving, ad-eligibility, and (future) payouts also cite. SPR-01
    shipped a provisional copy of the mapping here (a redistributable->T1,
    NC-by-display-name->T2, else->T3 branch); that copy is GONE so the tier
    table cannot fork. ``RightsTier`` itself stays defined in this module (the
    schema layer) and the census types here continue to consume it; only the
    *decision* moved up to ``substrate.rights``.

    The delegation is a lazy import for the same layering reason the previous
    ``resolve_license`` import was lazy (see the module note): ``substrate``
    sits below ``acquisition``, and ``arxiv_tiers`` itself reaches into
    ``acquisition.arxiv.licenses``. Importing it at module top would invert the
    layering and risk a cycle.
    """
    from substrate.rights.arxiv_tiers import resolve_tier  # lazy: see module note

    return resolve_tier(license_uri)


@dataclass(frozen=True)
class RightsCensus:
    """The measured rights-tier distribution of a harvest.

    Reproducibility is the contract (rigor bar 3 + 5): the census records the
    exact query that produced it (``metadata_prefix`` + ``from_date`` /
    ``until_date`` window) and the wall-clock ``harvested_at``, so a reviewer
    can re-run the same ListRecords and get the same counts. ``__post_init__``
    asserts the partition is exhaustive — ``t1 + t2 + t3 == total`` — so a
    record can never be silently dropped from the denominator.

    ``ambiguous`` is the subset of T3 whose license was absent/empty (vs a
    present-but-unrecognised URI). It is reported separately so the packet can
    state the honesty number — how many papers had NO declared license — rather
    than hiding it inside the T3 total.
    """

    t1: int
    t2: int
    t3: int
    total: int
    ambiguous: int
    metadata_prefix: str
    from_date: str | None
    until_date: str | None
    harvested_at: datetime
    deleted: int = 0

    def __post_init__(self) -> None:
        partition = self.t1 + self.t2 + self.t3
        if partition != self.total:
            raise ValueError(
                f"census partition is not exhaustive: "
                f"t1({self.t1}) + t2({self.t2}) + t3({self.t3}) = {partition} "
                f"!= total({self.total})"
            )
        if not 0 <= self.ambiguous <= self.t3:
            raise ValueError(
                f"ambiguous({self.ambiguous}) must be within [0, t3({self.t3})]"
            )

    def fraction(self, count: int) -> float:
        """``count`` as a fraction of ``total`` — computed, never hand-rounded
        (rigor bar 3). Returns 0.0 for an empty census rather than dividing by
        zero."""
        return count / self.total if self.total else 0.0


@dataclass
class _TierTally:
    """Mutable accumulator the harvester folds records into; frozen into a
    ``RightsCensus`` at the end. Separate from ``RightsCensus`` so the
    immutable, self-checking report type never has to expose increment
    methods."""

    t1: int = 0
    t2: int = 0
    t3: int = 0
    ambiguous: int = 0
    deleted: int = 0
    _counts: dict = field(default_factory=dict)

    def add(self, record: ArxivOaiRecord) -> None:
        if record.deleted:
            self.deleted += 1
            return
        tier = record.tier
        if tier is RightsTier.T1_REDISTRIBUTABLE:
            self.t1 += 1
        elif tier is RightsTier.T2_NON_COMMERCIAL:
            self.t2 += 1
        else:
            self.t3 += 1
            if not record.license_uri or not record.license_uri.strip():
                self.ambiguous += 1

    @property
    def total(self) -> int:
        return self.t1 + self.t2 + self.t3

    def freeze(
        self,
        *,
        metadata_prefix: str,
        from_date: str | None,
        until_date: str | None,
        harvested_at: datetime,
    ) -> RightsCensus:
        return RightsCensus(
            t1=self.t1,
            t2=self.t2,
            t3=self.t3,
            total=self.total,
            ambiguous=self.ambiguous,
            deleted=self.deleted,
            metadata_prefix=metadata_prefix,
            from_date=from_date,
            until_date=until_date,
            harvested_at=harvested_at,
        )
