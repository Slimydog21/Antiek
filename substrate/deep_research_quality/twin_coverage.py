"""Twin coverage — did the twin CAPTURE the source's content (recall)?

Operator vision (ask #4): *"every information asset created on my platform has a
twin document with all the insights and questions proposed by that information
document written by an LLM as LLMs perfect note takers, then that substrate of
information can be merged, referenced, and leveraged in combining contexts or
doing intelligent search over my dream of an infinite information platform."* The
twin is the platform's note-taker; the operator's "infinite information platform"
is BUILT ON the twin substrate — search (#1844), merge (#1835), cross-reference
(#1945), and the knowledge graph all read the twin's insights and questions as the
asset's extractable content. A twin that drops the source's content silently
SHRINKS the platform's memory: the operator believes the twin carries everything
the source said, when it does not.

``twin_fidelity`` (#1954) measures PRECISION — for each TWIN insight, is it
supported by the source (does the twin HALLUCINATE / invent content the source
does not contain?). It is a false-positive detector: it catches twin claims that
are not grounded. But a perfectly faithful twin (zero hallucinations) that
captures only 2 of the source's 10 insights is SAFE-LOOKING but useless — it
passes fidelity yet drops 80% of the information. Nothing measures RECALL — for
each SOURCE insight, did the twin CAPTURE it? That is the false-negative
detector: it catches source content the twin silently dropped. THIS is that axis.

**Genuinely distinct (precision vs recall — the load-bearing split).** The
fidelity/coverage duality is the SAME axis-space distinction as
synthesis_grounding (#1942, ← conclusions rest on insights) vs insight_novelty
(#1958, → insights add value beyond synthesis), and the merge_integrity (#1962)
preservation check. Fidelity asks "don't add what isn't there"; coverage asks
"don't drop what is there." A twin can pass one and fail the other:
hallucination-free-but-incomplete (high fidelity, low coverage) is a different
failure from complete-but-fabricated (low fidelity, high coverage). The operator
needs BOTH to trust the twin substrate.

**The measurement (hard to vary).** For each insight on the SOURCE artifact:

* Extract its distinctive content terms (glue + interrogatives stripped — the
  lexical floor shared across all cross-reference/quality modules).
* Find the best overlap-coefficient ``|source_terms ∩ twin_terms| /``
  ``min(|source_terms|, |twin_terms|)`` against ANY twin insight. Overlap-
  coefficient (not Jaccard) so a rich source insight that contains a captured
  twin insight (subset) scores 1.0 rather than being penalised for the source's
  own length.
* The source insight is ``captured`` if its best overlap >= ``capture_threshold``
  (default 0.50); otherwise ``dropped`` (the twin failed to surface it).

``insight_coverage = captured / measurable`` (``None`` when the source has zero
measurable insights). The SAME measure runs over questions:
``question_coverage``. (``twin_question_support`` #1959 is the precision side of
questions — are the twin's questions grounded; this is the recall side — are the
source's questions captured.)

All-glue items (zero distinctive terms) are NOT measurable and are excluded from
both numerator and denominator, carried as ``unmeasurable_*`` counts for honesty
(never fabricated as dropped).

The overall verdict:

* both ``insight_coverage`` and ``question_coverage`` ``None`` → ``unknown`` (the
  source carried no measurable content — defer, never fabricated).
* ``insight_coverage < capture_threshold`` → ``insight_loss`` (the twin dropped
  source findings).
* ``question_coverage < capture_threshold`` → ``question_loss`` (the twin dropped
  source questions).
* both coverage ``>= capture_threshold`` but not both ``1.0`` → ``partial``
  (most captured, some dropped).
* both coverage ``== 1.0`` → ``complete`` (every measurable item captured — the
  ideal the operator's "infinite information platform" requires).

**Lexical floor, not semantic (load-bearing).** No stemming, no synonymy. A
source insight rephrased by the twin (same meaning, different words) may score
low — that is the SAME conservative direction as twin_fidelity (#1954),
merge_integrity (#1962), and recursion_closure (#1961): this detector prefers
flagging a rephrase (false positive — the operator confirms downstream) over
certifying a complete twin that silently dropped a source finding (false negative
— that hides real information loss behind a phony all-clear). The two directions
bound the twin from opposite sides: fidelity flags twin claims not in the source
(false positives on hallucination), coverage flags source content not in the twin
(false positives on paraphrase). Together they bracket the true fidelity.

**Honesty rules (load-bearing):**

* ``insight_coverage`` / ``question_coverage`` are ``None`` when the source has
  zero measurable items of that type (defer — never ``0.0`` or ``1.0``).
* All-glue items excluded from coverage ratios (carried as ``unmeasurable_*``
  counts) — fabricating a dropped item from glue would conflate "unmeasurable"
  with "dropped."
* Coverage ratios are in ``[0.0, 1.0]``; per-item matched evidence (the best
  overlap ratio + the twin node it matched) is recorded (auditable — exactly
  which source items the twin failed to surface).
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation.
* ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** Uses the canonical ``ResearchArtifactBody``
from ``substrate/research_artifact/schema.py`` (stable on origin/main). The
source and twin are ordinary ``ResearchArtifactBody`` instances (the route layer
reads them by following the twin-generation edge in the graph DB).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from substrate.research_artifact.schema import ResearchArtifactBody

_DEFAULT_CAPTURE_THRESHOLD: float = 0.50

_STOP_WORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "this", "that", "these", "those",
        "is", "are", "was", "were", "be", "been", "being", "am",
        "of", "to", "in", "on", "at", "by", "for", "with", "from",
        "into", "onto", "upon", "over", "under", "between", "through",
        "during", "before", "after", "above", "below", "up", "down",
        "out", "off", "about", "against", "as", "than", "then",
        "and", "or", "but", "nor", "so", "yet", "if", "because",
        "while", "where", "when", "how", "what", "which", "who", "whom",
        "why", "will", "would", "shall", "should", "can", "could", "may",
        "might", "must", "not", "no", "yes", "also", "very", "just",
        "only", "more", "most", "some", "any", "all", "each", "every",
        "other", "such", "own", "same", "too", "do", "does", "did",
        "it", "its", "they", "them", "their", "we", "us", "our",
        "you", "your", "he", "she", "his", "her", "i", "me", "my", "s",
    }
)

_WORD_RE = re.compile(r"[a-z0-9]+")


def _distinctive_terms(text: str) -> frozenset[str]:
    """Lowercase content words (glue + interrogatives stripped). Lexical floor."""
    return frozenset(
        tok for tok in _WORD_RE.findall(text.lower()) if tok not in _STOP_WORDS
    )


def _overlap_coefficient(a: frozenset[str], b: frozenset[str]) -> float:
    """|a ∩ b| / min(|a|, |b|); 0.0 when either set is empty."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


class TwinCoverageError(ValueError):
    """A twin-coverage input violates a load-bearing invariant."""


@dataclass(frozen=True)
class SourceItemCoverage:
    """One source item's capture verdict against the twin. Advisory, pure."""

    source_node_id: str
    best_overlap: float | None  # None if no measurable twin content to match against
    matched_twin_node_id: str | None  # the twin node with the best overlap (None if none)
    verdict: str  # captured | dropped | unmeasurable


@dataclass(frozen=True)
class TwinCoverageReport:
    """The twin's recall over its source. Advisory, pure."""

    source_id: str
    twin_id: str
    insight_coverage: float | None  # captured/measurable; None if zero measurable
    question_coverage: float | None
    captured_insights: int
    dropped_insights: int
    unmeasurable_insights: int
    captured_questions: int
    dropped_questions: int
    unmeasurable_questions: int
    insight_captures: tuple[SourceItemCoverage, ...]
    question_captures: tuple[SourceItemCoverage, ...]
    capture_threshold: float
    verdict: str  # complete | partial | insight_loss | question_loss | unknown
    notes: tuple[str, ...]
    authority: str = "advisory"


def _measure_items(
    source_texts_and_ids: list[tuple[str, str]],
    twin_item_sets: list[tuple[str, frozenset[str]]],
    *,
    threshold: float,
) -> tuple[
    float | None,
    int,
    int,
    int,
    list[SourceItemCoverage],
]:
    """Return (coverage, captured, dropped, unmeasurable, per_item).

    ``coverage`` is ``None`` when zero source items are measurable.
    """
    per_item: list[SourceItemCoverage] = []
    captured = 0
    measurable = 0
    unmeasurable = 0

    for source_text, source_node_id in source_texts_and_ids:
        source_terms = _distinctive_terms(source_text)
        if not source_terms:
            per_item.append(
                SourceItemCoverage(
                    source_node_id=source_node_id,
                    best_overlap=None,
                    matched_twin_node_id=None,
                    verdict="unmeasurable",
                )
            )
            unmeasurable += 1
            continue

        measurable += 1
        best = 0.0
        best_twin_id: str | None = None
        for twin_node_id, twin_terms in twin_item_sets:
            score = _overlap_coefficient(source_terms, twin_terms)
            if score > best:
                best = score
                best_twin_id = twin_node_id
                if best >= 1.0:
                    break

        verdict = "captured" if best >= threshold else "dropped"
        if verdict == "captured":
            captured += 1
        per_item.append(
            SourceItemCoverage(
                source_node_id=source_node_id,
                best_overlap=best,
                matched_twin_node_id=best_twin_id,
                verdict=verdict,
            )
        )

    dropped = measurable - captured
    coverage = captured / measurable if measurable else None
    return coverage, captured, dropped, unmeasurable, per_item


def measure_twin_coverage(
    source: ResearchArtifactBody,
    twin: ResearchArtifactBody,
    *,
    capture_threshold: float = _DEFAULT_CAPTURE_THRESHOLD,
) -> TwinCoverageReport:
    """Measure whether the twin captured the source's insights and questions.

    ``source`` is the original artifact the twin was generated from. ``twin`` is
    the LLM-generated twin :class:`ResearchArtifactBody`. Returns a
    :class:`TwinCoverageReport` with per-item capture + per-type coverage ratios
    + the overall verdict.

    Pure: no DB, no LLM, no clock, no mutation.
    """
    if not 0.0 <= capture_threshold <= 1.0:
        raise TwinCoverageError(
            f"capture_threshold must be in [0,1], got {capture_threshold!r}"
        )

    twin_insight_sets = [
        (ins.node_id, terms)
        for ins in twin.insights
        if (terms := _distinctive_terms(ins.text))
    ]
    twin_question_sets = [
        (q.node_id, terms)
        for q in twin.open_questions
        if (terms := _distinctive_terms(q.text))
    ]

    (
        insight_coverage,
        captured_insights,
        dropped_insights,
        unmeasurable_insights,
        insight_captures,
    ) = _measure_items(
        [(ins.text, ins.node_id) for ins in source.insights],
        twin_insight_sets,
        threshold=capture_threshold,
    )
    (
        question_coverage,
        captured_questions,
        dropped_questions,
        unmeasurable_questions,
        question_captures,
    ) = _measure_items(
        [(q.text, q.node_id) for q in source.open_questions],
        twin_question_sets,
        threshold=capture_threshold,
    )

    if insight_coverage is None and question_coverage is None:
        verdict = "unknown"
    elif (
        insight_coverage is not None
        and insight_coverage < capture_threshold
        and question_coverage is not None
        and question_coverage < capture_threshold
    ):
        verdict = "loss"
    elif insight_coverage is not None and insight_coverage < capture_threshold:
        verdict = "insight_loss"
    elif question_coverage is not None and question_coverage < capture_threshold:
        verdict = "question_loss"
    elif (
        insight_coverage is None or insight_coverage == 1.0
    ) and (question_coverage is None or question_coverage == 1.0):
        # reached only when at least one side is measurable (both-None handled
        # first) and nothing is below threshold -> complete iff something was
        # fully captured
        verdict = "complete"
    else:
        verdict = "partial"

    notes: list[str] = [
        "twin coverage measures RECALL — for each SOURCE insight/question, did the "
        "twin CAPTURE it? The precision/recall complement to twin_fidelity #1954 "
        "(which measures PRECISION — for each twin claim, is it grounded in the "
        "source). A faithful-but-incomplete twin passes fidelity yet drops the "
        "platform's memory; this catches that silent shrinkage",
        "capture uses overlap-coefficient (intersection over the smaller set) >= "
        "threshold so a rich source insight containing a captured twin insight "
        "(subset) scores 1.0 rather than being penalised for the source's length",
        "verdict: complete (everything measurable captured), partial (most "
        "captured, some dropped), insight_loss/question_loss (the twin dropped "
        "below-threshold findings/questions), unknown (source carried no "
        "measurable content); all-glue items excluded from ratios and carried as "
        "unmeasurable counts (never fabricated as dropped)",
        "the two directions bound the twin from opposite sides: fidelity flags "
        "twin claims not in the source (false positive on hallucination), coverage "
        "flags source content not in the twin (false positive on paraphrase) — "
        "together they bracket the true fidelity; the operator confirms downstream",
        "lexical floor (no stemming/synonymy): a source insight rephrased by the "
        "twin may score low — prefers a false positive (flag rephrase) over "
        "certifying a complete twin that silently dropped a finding (false "
        "negative); a semantic check confirms downstream",
    ]
    i_str = (
        f"{insight_coverage:.0%}" if insight_coverage is not None else "n/a"
    )
    q_str = (
        f"{question_coverage:.0%}" if question_coverage is not None else "n/a"
    )
    notes.append(
        f"verdict {verdict}: insight coverage {i_str} "
        f"({captured_insights}/{captured_insights + dropped_insights} captured), "
        f"question coverage {q_str} "
        f"({captured_questions}/{captured_questions + dropped_questions} captured), "
        f"threshold {capture_threshold:.0%}"
    )

    return TwinCoverageReport(
        source_id=source.investigation_id,
        twin_id=twin.investigation_id,
        insight_coverage=insight_coverage,
        question_coverage=question_coverage,
        captured_insights=captured_insights,
        dropped_insights=dropped_insights,
        unmeasurable_insights=unmeasurable_insights,
        captured_questions=captured_questions,
        dropped_questions=dropped_questions,
        unmeasurable_questions=unmeasurable_questions,
        insight_captures=tuple(insight_captures),
        question_captures=tuple(question_captures),
        capture_threshold=capture_threshold,
        verdict=verdict,
        notes=tuple(notes),
    )
