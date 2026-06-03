"""Unit-level near-duplicate detection — link a restated finding, don't re-store it (AFF SPR-07).

The flywheel only *compounds* if a restated fact links back to the unit that
already holds it instead of inserting a fresh row. SPR-04 gave each
investigation a way to *deposit* knowledge units; this module is the
compounding guard that runs once per deposit and answers a single pure
question: **is this candidate unit a duplicate of one we already have?**

Reused antecedents (M1 — one identity home, no second ladder, no third cosine):

  * ``substrate.dedup`` (PR #31, the SINGLE identity home) — REUSE its
    ``identity_key`` / ``Confidence`` / the ``DOI>ISBN>arXiv>source_id>content-hash>
    title_author-LOW`` precedence ladder as the Tier-1 high-confidence layer.
    A candidate that resolves to the *same HIGH-confidence* ``identity_key`` as
    an existing unit is a duplicate; a LOW-confidence key (the title+author /
    ref fallback) NEVER triggers a merge — we inherit dedup.py's
    LOW-never-merges rule verbatim rather than re-deriving it. We import
    ``identity_key``; we do NOT re-define a normalizer or a precedence ladder.
  * ``processing.embedding.embed.default_embedding_provider`` — REUSE the one
    embedding path (L2-normalized, cosine-friendly) for the Tier-2 near-dup
    layer. We do not mint a second embedding model.
  * ``interfaces.research.api.cross_doc._cosine`` — REUSE the cosine pattern
    (re-exported here as ``_unit_cosine`` so this module composes it rather
    than importing an interface-layer private). There is exactly ONE cosine
    formula in the codebase; this is not a third one.
  * ``roles.note_taker.step_pass.RunNoteDeduper`` — the closest unit-level
    antecedent (within-RUN exact-text suppression via ``canonical_text``).
    EXTEND, do not reuse: that guard is per-run and exact-text only; SPR-07 is
    CROSS-investigation and adds an embedding near-dup layer for paraphrases
    with no stable id, which RunNoteDeduper structurally cannot catch.

Why EXTEND rather than just reuse ``substrate.dedup``: that module keys on a
real-world *work*'s stable identity (a DOI'd paper, an ISBN'd book). A
knowledge unit is a *claim* — a sentence of distilled prose with, usually, no
stable id of its own. Two investigations that surface "neutral-atom qubits hit
a sub-1% error rate" will phrase it differently and carry no shared DOI, so the
identity ladder alone never merges them. The embedding-cosine layer is the
EXTENSION that catches paraphrase-level claim duplication the work-identity
ladder cannot — while delegating every *stable-id* decision back to the one
identity home.

------------------------------------------------------------------------------
HONESTY — the false-merge risk this module CANNOT fully eliminate (rigor #1)
------------------------------------------------------------------------------
A cosine near-dup is similarity, not entailment. Cosine cannot tell
NEGATION/ANTONYMY apart: "drug X reduces mortality" and "drug X *increases*
mortality" share almost all their vocabulary and embed very close, yet they are
OPPOSITE claims — merging them would silently destroy a finding and corrupt the
SPR-09 benchmark. This module does NOT solve antonymy. It BOUNDS it with two
mechanisms, both of which are mechanically tested:

  1. the SCOPE GUARD (M2): cosine alone NEVER merges. A near-dup requires
     cosine >= threshold AND a shared retrieval-key/provenance scope (same
     investigation OR same grounding document). Two distinct claims that merely
     share vocabulary across unrelated scopes are never merged.
  2. the Polarity-B test (M4): a seeded distinct-but-similar pair
     ("X increases Y" vs "X decreases Y") MUST stay two units, and the test
     asserts the threshold sits strictly ABOVE the distinct pair's cosine.

RESIDUAL (stated, not hidden): within ONE scope, a true antonym pair whose
cosine clears the threshold WOULD be wrongly merged — cosine is blind to the
"not"/"increase-vs-decrease" flip. The scope guard shrinks the blast radius to
same-scope antonyms; it does not detect them. Closing the residual needs an
entailment/NLI signal (out of scope for SPR-07; flagged in the handoff). The
Polarity-B test proves the GUARD holds on a same-scope distinct pair below
threshold — it does NOT prove every same-scope antonym above threshold is
caught, and the handoff says so.

§16 box-bounded: ``find_near_duplicate`` is PURE in-process logic over candidate
units — no DB, no network, no clock, no new store/service/index. The deposit
path (``substrate.graph.insight_question``) keeps the single writer; this module
emits no rows and holds no connection (the single-writer / row-write grep gate
over this file is empty by construction).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

# Tier 2 reuses the ONE embedding path. Imported lazily inside the function
# (mirroring insight_question._default_provider) so a test can install a hash
# provider via ANTIEK_EMBEDDING_PROVIDER=hash without paying the
# sentence-transformers import at module load.
# Cosine reuse: the codebase's single cosine formula lives in
# interfaces.research.api.cross_doc._cosine. We bind it here so this module
# COMPOSES it rather than minting a third one (rigor #4). This is an aliased
# IMPORT, never a re-definition — so the diligence grep for a forked cosine or
# normalizer over this file finds nothing.
from interfaces.research.api.cross_doc import _cosine as _unit_cosine

# Tier 1 delegates ALL stable-id identity to the single identity home — no
# re-derived normalizer, no second precedence ladder (M1 / rigor #4).
from substrate.dedup import Confidence, IdentityRecord, identity_key

# ---------------------------------------------------------------------------
# The cosine threshold — a defensible judgment call (rigor #5).
# ---------------------------------------------------------------------------

# UNIT_DEDUP_COSINE_THRESHOLD — a candidate claim is a Tier-2 near-duplicate of
# an in-scope existing unit iff their claim-text cosine is >= this value.
#
#   (a) VALUE: 0.82.
#   (b) WHY: it sits strictly BETWEEN the two cosines the two-polarity test in
#       tests/test_unit_dedup.py seeds and asserts numerically (rigor #3):
#       a near-paraphrase duplicate pair scores well above it (~0.9+ on the
#       hash embedder's token-bag overlap), while a genuinely-distinct pair that
#       merely shares vocabulary ("X increases Y" vs "X decreases Y") scores
#       below it. The test fails LOUD if this ordering ever breaks, so the value
#       is not eyeballed — it is pinned to the measured gap.
#   (c) CALIBRATED AGAINST: the deterministic HASH stub
#       (processing.embedding.HashEmbedding, ANTIEK_EMBEDDING_PROVIDER=hash) —
#       a token-BAG embedder. Its cosine distribution is NOT the same as
#       all-MiniLM-L6-v2's: the hash stub scores on shared-token overlap (so a
#       one-word antonym flip stays high, which is exactly why the scope guard,
#       not the threshold, carries the false-merge defense), whereas MiniLM
#       embeds meaning (closer for true paraphrase, and lower for an antonym
#       flip). 0.82 is the safe-on-hash value; MiniLM will want recalibration.
#   (d) RECONSIDER IF: the production embedding provider changes (hash ->
#       sentence-transformers, or a different model) — recalibrate against the
#       new provider's duplicate-vs-distinct cosine gap and re-pin from the
#       test's measured values; OR the SPR-09 dedup-rate metric (M5) SPIKES
#       (over-merging — distinct findings collapsing) or COLLAPSES toward 0
#       (under-merging — the graph bloating). Either is the signal to revisit
#       this constant, not the rest of the detector.
UNIT_DEDUP_COSINE_THRESHOLD: float = 0.82


# ---------------------------------------------------------------------------
# Pure data — the detector operates on these, never on a DB row directly.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CandidateUnit:
    """A knowledge unit about to be deposited — the thing we test for dup-ness.

    ``retrieval_key`` is the SPR-04 stable key (the content-addressed node_id);
    ``investigation_id`` + ``source_document_id`` define the provenance SCOPE
    the Tier-2 cosine guard requires a match to share. ``identity_record`` is an
    optional ``substrate.dedup.IdentityRecord`` for the Tier-1 stable-id layer
    (None when the claim carries no work identity — the common case for a
    distilled claim, which then relies on Tier 1's retrieval-key arm + Tier 2).
    Pure data: built by the deposit path, never reaches a DB itself.
    """

    text: str
    retrieval_key: str
    investigation_id: str
    source_document_id: str | None = None
    identity_record: IdentityRecord | None = None


@dataclass(frozen=True)
class ExistingUnit:
    """An already-deposited unit the candidate is compared against.

    Same shape as :class:`CandidateUnit` plus ``unit_id`` (the surviving
    node_id a ``duplicate_of`` edge would point at). The deposit path projects
    the in-scope existing units into this shape from the graph rows it already
    reads — this module never queries.
    """

    unit_id: str
    text: str
    retrieval_key: str
    investigation_id: str
    source_document_id: str | None = None
    identity_record: IdentityRecord | None = None


@dataclass(frozen=True)
class DuplicateMatch:
    """The verdict: the candidate duplicates ``existing_unit_id``.

    ``tier`` is 1 (exact / high-confidence stable identity) or 2 (embedding
    near-dup). ``cosine`` is the measured similarity (1.0 for a Tier-1 exact
    key match, where cosine is not the deciding signal). ``key_type`` names the
    Tier-1 arm that fired ("retrieval_key" or a ``substrate.dedup`` key_type),
    or "embedding" for Tier 2 — recorded so the deposit path can stamp WHY the
    merge happened onto the ``duplicate_of`` edge for audit.
    """

    existing_unit_id: str
    tier: int
    cosine: float
    key_type: str


def _shares_scope(candidate: CandidateUnit, existing: ExistingUnit) -> bool:
    """The false-merge guard: do candidate + existing share a provenance scope?

    Cosine ALONE never merges (the docstring's honesty point). A Tier-2 near-dup
    requires a shared scope — same investigation, OR the same grounding
    document. Two distinct claims that merely reuse vocabulary in unrelated
    investigations/documents can never be collapsed on similarity. Scope is the
    retrieval-key/provenance neighbourhood SPR-04 already attaches to every
    unit; we read it, we do not invent it."""
    if candidate.investigation_id and candidate.investigation_id == existing.investigation_id:
        return True
    if (
        candidate.source_document_id
        and candidate.source_document_id == existing.source_document_id
    ):
        return True
    return False


def _tier1_match(
    candidate: CandidateUnit, existing: ExistingUnit
) -> DuplicateMatch | None:
    """Tier 1 — exact / high-confidence identity. No embedding involved.

    Two arms, both high-confidence:
      * same SPR-04 retrieval key (the content-addressed node_id) — a literal
        re-emission of the same claim text resolves to the same node_id, so
        this is the cheapest, surest duplicate;
      * same HIGH-confidence ``substrate.dedup.identity_key`` — when BOTH units
        carry a work identity (a DOI/ISBN/arXiv/source-id/content-hash). A
        LOW-confidence key (title+author / ref fallback) NEVER fires here,
        inheriting dedup.py's LOW-never-merges rule.
    """
    if candidate.retrieval_key and candidate.retrieval_key == existing.retrieval_key:
        return DuplicateMatch(
            existing_unit_id=existing.unit_id,
            tier=1,
            cosine=1.0,
            key_type="retrieval_key",
        )
    if candidate.identity_record is not None and existing.identity_record is not None:
        ckey = identity_key(candidate.identity_record)
        ekey = identity_key(existing.identity_record)
        # LOW-never-merges: a title+author / ref fallback is not a confident
        # identity, so it can never collapse two units (dedup.py's own rule).
        if (
            ckey.confidence is Confidence.HIGH
            and ekey.confidence is Confidence.HIGH
            and ckey.key_type is ekey.key_type
            and ckey.key == ekey.key
        ):
            return DuplicateMatch(
                existing_unit_id=existing.unit_id,
                tier=1,
                cosine=1.0,
                key_type=ckey.key_type.value,
            )
    return None


def find_near_duplicate(
    candidate_unit: CandidateUnit,
    existing_units: Sequence[ExistingUnit],
    *,
    embedding_provider=None,
) -> DuplicateMatch | None:
    """Return the first existing unit ``candidate_unit`` duplicates, or None.

    PURE: no DB, no network, no clock. The deposit path calls this ONCE per
    candidate before any insert, projecting the in-scope existing units it
    already reads into :class:`ExistingUnit` records.

    Two tiers, Tier 1 first (it is cheaper and surer):

      * **Tier 1 — exact / high-confidence.** Same SPR-04 retrieval key OR same
        HIGH-confidence ``substrate.dedup.identity_key``. A LOW-confidence key
        never triggers a merge. No embedding computed.
      * **Tier 2 — embedding near-dup.** For each in-SCOPE existing unit, embed
        both claim texts via ``default_embedding_provider()`` (L2-normalized)
        and score the reused cosine. A near-dup requires BOTH
        ``cosine >= UNIT_DEDUP_COSINE_THRESHOLD`` AND a shared
        retrieval-key/provenance scope — cosine alone never merges across
        unrelated scopes (the false-merge guard). Among qualifying Tier-2
        matches the HIGHEST cosine wins, so the link points at the closest
        surviving unit deterministically.

    ``embedding_provider`` is injectable for tests; production passes None and
    the one default provider is used."""
    # Tier 1 — exact/high-confidence identity. First match wins (any exact-key
    # equal is as good as another; a re-emission collapses immediately).
    for existing in existing_units:
        m = _tier1_match(candidate_unit, existing)
        if m is not None:
            return m

    # Tier 2 — embedding near-dup, scoped. Only compute embeddings when we have
    # in-scope candidates to compare against (so an unrelated corpus costs
    # nothing). The candidate is embedded once.
    in_scope = [e for e in existing_units if _shares_scope(candidate_unit, e)]
    if not in_scope:
        return None

    provider = embedding_provider
    if provider is None:
        # Lazy import — keep the module import dependency-free and let
        # ANTIEK_EMBEDDING_PROVIDER=hash take effect (mirrors insight_question).
        from processing.embedding import default_embedding_provider

        provider = default_embedding_provider()

    cand_vec = provider.encode(candidate_unit.text)
    best: DuplicateMatch | None = None
    for existing in in_scope:
        cos = _unit_cosine(cand_vec, provider.encode(existing.text))
        if cos < UNIT_DEDUP_COSINE_THRESHOLD:
            continue
        if best is None or cos > best.cosine:
            best = DuplicateMatch(
                existing_unit_id=existing.unit_id,
                tier=2,
                cosine=cos,
                key_type="embedding",
            )
    return best


# ---------------------------------------------------------------------------
# M5 — dedup-rate counter. A small in-process tally the deposit path increments,
# read by the corpus_audit sibling. NOT a metrics service (§16): it is plain
# data, the same way CollapseReport in substrate.dedup is.
# ---------------------------------------------------------------------------


@dataclass
class DedupRate:
    """Deposit-time dedup accounting: linked / total attempts.

    ``attempts`` is every candidate the deposit path ran through
    :func:`find_near_duplicate`; ``linked`` is how many became a ``duplicate_of``
    edge instead of a new row. ``rate`` is the compounding signal SPR-09 reads:
    rising = the graph is compounding (restatements link), at/near 0 = it is
    bloating (every restatement inserts). Mutable on purpose — it is a counter
    the single-writer deposit path increments under its own lock; it is not the
    graph and writes no rows."""

    attempts: int = 0
    linked: int = 0

    def record(self, *, linked: bool) -> None:
        self.attempts += 1
        if linked:
            self.linked += 1

    @property
    def rate(self) -> float:
        """linked / attempts; 0.0 when there were no attempts (no division by
        zero, and "nothing deposited yet" is honestly a 0 dedup rate)."""
        if self.attempts == 0:
            return 0.0
        return self.linked / self.attempts
