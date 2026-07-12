"""Twin fidelity — does an LLM-generated twin faithfully reflect its source?

Operator vision (ask #4): *"every information asset created on my platform has a
twin document with all the insights and questions proposed by that information
document written by an LLM as LLMs are perfect note takers, then that substrate
of information can be merged, referenced, and leveraged."* The twin is generated
by an LLM from the source content. But LLMs are NOT perfect note takers — they
hallucinate. A twin that proposes an insight the source does not support is a
CONTENT-POISONING surface: that fabricated insight flows into search (#1844),
merge (#1835), cross-reference (#1945), and the knowledge graph — each one
treating the hallucination as a real finding. The operator's "infinite
information platform" is only trustworthy if its twin substrate is faithful.

No current axis measures this. citation_grounding (#1848) checks whether an
artifact's insights carry ``source_document_id`` (structural provenance). The
twin's insights DON'T carry per-insight source ids (the whole artifact is the
source). provenance_coverage (#1940) checks source provenance metadata.
Neither checks whether the twin's proposed CONTENT is actually supported by the
source TEXT. gap_detection/unsupported.py checks graph-level edge support (needs
the graph DB). THIS is the lexical-support check: does each twin insight have
term overlap with the source it was generated from?

**The measurement (hard to vary).** For each twin insight:
* Extract its distinctive terms (content words, glue stripped — the lexical floor
  shared across all cross-reference/quality modules).
* Compute ``support_ratio = |insight_terms ∩ source_terms| / |insight_terms|`` —
  the fraction of the insight's distinctive vocabulary present in the source.
* An insight with ``support_ratio >= support_threshold`` (default 0.50) is
  ``supported``; below is ``unsupported`` (the twin invented vocabulary the source
  doesn't contain — a hallucination signal).

The module reports:
* ``supported_count`` / ``unsupported_count`` / ``unmeasurable_count`` (insights
  with no distinctive terms — can't measure).
* ``fidelity_rate = supported / measurable`` — the overall faithfulness.
* ``unsupported_terms`` per insight (the auditable evidence — exactly which terms
  the source lacks).

**Lexical floor, not semantic (load-bearing).** Distinctive terms are content
words (grammatical glue stripped). NO stemming, NO synonymy. This means a
PARAPHRASED insight (same meaning, different words) may score low — that is the
precision/recall tradeoff: this detector prefers flagging a paraphrase (false
positive) over missing a hallucination (false negative). A paraphrase flagged as
"unsupported" is a minor inconvenience; a hallucination accepted as "supported"
is content poisoning. The operator can always confirm with a semantic check
downstream.

**Honesty rules (load-bearing):**
* An insight with NO distinctive terms (empty or all-glue text) is
  ``unmeasurable`` — excluded from the fidelity rate (never fabricated as
  supported or unsupported). ``unmeasurable_count`` carried through.
* ``fidelity_rate`` is ``None`` when zero measurable insights (defer).
* The source text's own distinctive terms are the ground truth — if the source
  is empty or all-glue, every insight is ``unmeasurable``.
* ``support_ratio`` is in ``[0.0, 1.0]``; ``unsupported_terms`` is the set
  difference (auditable).
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation.
* ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** Uses the canonical ``ResearchArtifactBody``
from ``substrate/research_artifact/schema.py`` (stable on origin/main). The
source text is a plain ``str`` input (the route layer reads it from the asset
store).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from substrate.research_artifact.schema import ResearchArtifactBody

_DEFAULT_SUPPORT_THRESHOLD: float = 0.50

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
        "it", "its", "they", "them", "their", "we", "us", "our",
        "you", "your", "he", "she", "his", "her", "i", "me", "my",
        "do", "does", "did", "doing", "have", "has", "had", "having",
        "will", "would", "shall", "should", "can", "could", "may",
        "might", "must", "not", "no", "yes", "also", "very", "just",
        "only", "more", "most", "some", "any", "all", "each", "every",
        "such", "there", "here", "now",
    }
)

_WORD_RE = re.compile(r"[a-z0-9]+")


def _distinctive_terms(text: str) -> frozenset[str]:
    """Lowercase content words (grammatical glue stripped). Lexical floor."""
    return frozenset(
        tok for tok in _WORD_RE.findall(text.lower()) if tok not in _STOP_WORDS
    )


class TwinFidelityError(ValueError):
    """A twin-fidelity input violates a load-bearing invariant."""


@dataclass(frozen=True)
class InsightFidelity:
    """One twin insight's support against the source text."""

    node_id: str
    support_ratio: float | None  # None if unmeasurable (no distinctive terms)
    verdict: str  # supported | unsupported | unmeasurable
    unsupported_terms: tuple[str, ...]  # terms missing from source (auditable)


@dataclass(frozen=True)
class TwinFidelityReport:
    """The twin's faithfulness to its source. Advisory, pure."""

    artifact_id: str
    supported_count: int
    unsupported_count: int
    unmeasurable_count: int
    fidelity_rate: float | None  # supported/measurable; None if zero measurable
    insight_fidelities: tuple[InsightFidelity, ...]
    support_threshold: float
    notes: tuple[str, ...]
    authority: str = "advisory"


def measure_twin_fidelity(
    twin: ResearchArtifactBody,
    source_text: str,
    *,
    support_threshold: float = _DEFAULT_SUPPORT_THRESHOLD,
) -> TwinFidelityReport:
    """Measure whether the twin's proposed insights are supported by the source.

    ``twin`` is the LLM-generated twin (a ``ResearchArtifactBody``).
    ``source_text`` is the content the twin was generated from. Returns a
    :class:`TwinFidelityReport` with per-insight support + the overall fidelity rate.

    Pure: no DB, no LLM, no clock, no mutation.
    """
    if not 0.0 <= support_threshold <= 1.0:
        raise TwinFidelityError(
            f"support_threshold must be in [0,1], got {support_threshold!r}"
        )

    source_terms = _distinctive_terms(source_text)

    per_insight: list[InsightFidelity] = []
    supported = 0
    unsupported = 0
    unmeasurable = 0

    for ins in twin.insights:
        ins_terms = _distinctive_terms(ins.text)
        if not ins_terms or not source_terms:
            per_insight.append(
                InsightFidelity(
                    node_id=ins.node_id,
                    support_ratio=None,
                    verdict="unmeasurable",
                    unsupported_terms=(),
                )
            )
            unmeasurable += 1
            continue

        overlap = ins_terms & source_terms
        ratio = len(overlap) / len(ins_terms)
        missing = tuple(sorted(ins_terms - source_terms))

        if ratio >= support_threshold:
            verdict = "supported"
            supported += 1
        else:
            verdict = "unsupported"
            unsupported += 1

        per_insight.append(
            InsightFidelity(
                node_id=ins.node_id,
                support_ratio=ratio,
                verdict=verdict,
                unsupported_terms=missing,
            )
        )

    measurable = supported + unsupported
    fidelity_rate = (supported / measurable) if measurable else None

    notes: list[str] = [
        "twin fidelity measures whether the LLM-generated twin's proposed insights "
        "are LEXICALLY supported by the source text — a hallucinated insight "
        "(vocabulary absent from the source) is a content-poisoning surface that "
        "flows into search, merge, and cross-reference",
        "lexical floor (no stemming/synonymy): a paraphrased insight (same meaning, "
        "different words) may score low — this detector prefers flagging a paraphrase "
        "(false positive) over missing a hallucination (false negative); a semantic "
        "check can confirm downstream",
        "insights with no distinctive terms are unmeasurable (excluded from the rate, "
        "never fabricated); the unsupported_terms tuple shows exactly which vocabulary "
        "the source lacks",
    ]
    if measurable == 0:
        notes.append(
            "no measurable insights (empty twin or all-glue/source-empty); fidelity "
            "is not measurable (defer — never fabricated)"
        )
    else:
        assert fidelity_rate is not None
        notes.append(
            f"fidelity rate {fidelity_rate:.0%}: {supported} supported, "
            f"{unsupported} unsupported, {unmeasurable} unmeasurable of "
            f"{len(twin.insights)} twin insight(s) at threshold {support_threshold:.0%}"
        )

    return TwinFidelityReport(
        artifact_id=twin.investigation_id,
        supported_count=supported,
        unsupported_count=unsupported,
        unmeasurable_count=unmeasurable,
        fidelity_rate=fidelity_rate,
        insight_fidelities=tuple(per_insight),
        support_threshold=support_threshold,
        notes=tuple(notes),
        authority="advisory",
    )


__all__ = [
    "InsightFidelity",
    "TwinFidelityError",
    "TwinFidelityReport",
    "measure_twin_fidelity",
]
