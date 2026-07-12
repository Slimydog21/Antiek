"""Synthesis grounding — does the conclusion rest on the artifact's evidence?

Operator vision (asks #6/#7): every human-viewable research output is HTML, and
the product is *"the highest quality deep research product in the world."* The
canonical ``ResearchArtifactBody`` carries ``synthesis_excerpt`` — the
human-readable conclusion a person reads as *the research product* — plus the
``insights`` it was built from. The single most user-visible quality failure is a
synthesis that OVERREACHES its evidence: a conclusion that claims things none of
the insights established. A human reads the synthesis and trusts it; if it rests
on nothing, that trust is misplaced. THIS module measures whether the synthesis
actually rests on the artifact's own insights.

**Distinct from ``problem_question_coverage`` (#1929).** That module measures the
findings against the TOP-LINE ``problem_question`` (does the output answer the
stated question). This measures the SYNTHESIS against the INSIGHTS (does the
summary rest on the evidence it summarizes). Different source text
(``synthesis_excerpt``, not all findings), different reference set (the
artifact's own ``insights``, not the problem question). An artifact can answer
its top-line question perfectly while its synthesis smuggles in a claim no
insight supports — #1929 sees the first, this sees the second.

**Distinct from ``citation_grounding`` (#1848).** That audits whether a CITED
external source supports an insight (CONTENT fidelity to a source). This audits
whether the artifact's OWN insights support the synthesis (INTERNAL fidelity to
the evidence it was built from). No external source involved.

**The score (hard to vary).** Coverage is the fraction of the synthesis's
DISTINCTIVE terms (non-stop-word, de-duplicated, lowercased) that appear in the
union of the insights' distinctive terms. ``grounding = matched / total``. The
``overreach_terms`` list is the ACCOUNTABILITY SURFACE: the synthesis's signal
words that NO insight supports — the concepts the conclusion invented or imported
beyond its evidence.

**Honest scope (load-bearing).** This is a LEXICAL floor, not semantic
overreach detection — same discipline as the other lexical axes. A synthesis can
paraphrase an insight using entirely different words and score 0 (false alarm);
catching that needs an LLM judge (out of scope). NO stemming (``scale`` !=
``scales``): a stemmer would inflate grounding and mask a real overreach behind a
phony match. Stop-words are stripped from BOTH the synthesis and the insights so
grammatical glue does not inflate coverage — only signal words count.

**Honesty rules (load-bearing):**
* ``synthesis_withheld=True`` → grounding is ``None`` (the synthesis was
  explicitly withheld, e.g. because insights were incomplete; measuring an absent
  synthesis would be fabrication). NEVER coerced to 0.
* ``synthesis_excerpt`` is ``None``/empty → grounding is ``None`` (no synthesis
  to measure; defer). Same honesty.
* Synthesis with no distinctive terms (stop-words only) → grounding ``None``
  (unmeasurable, like the goal_delivery / problem_question patterns).
* Synthesis present but NO insights → grounding ``0.0`` if the synthesis has
  distinctive terms (the synthesis rests on NOTHING — full overreach). This is
  honest, not a fabrication: an empty evidence base supporting a non-empty
  conclusion is the maximal overreach.
* ``overreach_terms`` is reported sorted; each is a concept the synthesis claims
  that no insight supports.
* Deterministic and pure: same artifact -> same report. No LLM, no network, no
  clock, no mutation. ``authority`` is always ``"advisory"``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from substrate.research_artifact.schema import ResearchArtifactBody

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Stop-words stripped so coverage measures signal-word overlap, not grammatical
# glue. Documented mirror of the sets in goal_delivery / problem_question_coverage
# / redundancy: if those change, the drift is visible (all must agree on signal).
_STOP_WORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
        "of", "to", "in", "on", "for", "with", "and", "or", "but", "not",
        "this", "that", "these", "those", "it", "its", "as", "at", "by",
        "from", "into", "than", "then", "so", "such", "do", "does", "did",
        "will", "would", "can", "could", "should", "may", "might", "must",
        "what", "which", "who", "whom", "how", "when", "where", "why",
        "about", "between", "through", "during", "above", "below", "over",
        "under", "again", "further", "there", "here", "all", "any", "both",
        "each", "few", "more", "most", "other", "some", "no", "nor", "only",
        "own", "same", "very", "just", "if", "because", "while", "until",
    }
)


@dataclass(frozen=True)
class SynthesisGroundingReport:
    """The artifact's synthesis-vs-evidence grounding surface. Advisory, pure."""

    artifact_id: str  # the artifact's investigation_id (traceability)
    grounding: float | None  # matched/total in [0,1]; None if unmeasurable
    synthesis_term_count: int  # distinctive terms in the synthesis (0 if absent)
    matched_term_count: int  # synthesis distinctive terms present in the insights
    overreach_terms: tuple[str, ...]  # synthesis terms NO insight supports, sorted
    withheld: bool  # synthesis_withheld flag carried through
    notes: tuple[str, ...]
    authority: str = "advisory"


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _distinctive_terms(text: str) -> list[str]:
    seen: set[str] = set()
    terms: list[str] = []
    for tok in _tokenize(text):
        if tok in _STOP_WORDS or tok in seen:
            continue
        seen.add(tok)
        terms.append(tok)
    return terms


def _insights_vocab(insights_texts: list[str]) -> set[str]:
    vocab: set[str] = set()
    for text in insights_texts:
        for tok in _tokenize(text):
            if tok not in _STOP_WORDS:
                vocab.add(tok)
    return vocab


def measure_synthesis_grounding(
    artifact: ResearchArtifactBody,
) -> SynthesisGroundingReport:
    """Measure whether the artifact's synthesis rests on its own insights.

    ``artifact`` is the canonical knowledge-asset body. Returns a
    :class:`SynthesisGroundingReport` with the grounding coverage and the
    overreach-terms accountability surface.

    Pure: no DB, no LLM, no clock, no mutation.
    """
    notes: list[str] = [
        "synthesis grounding is a LEXICAL floor (does the synthesis's distinctive "
        "terms appear in the insights' terms); a paraphrase using different words "
        "scores 0 (false alarm); semantic overreach detection is an LLM-judge "
        "concern, out of scope",
        "grounding is distinct from problem_question_coverage (#1929, findings vs "
        "the top-line question) and citation_grounding (#1848, insight vs a cited "
        "external source) — this is the synthesis vs the artifact's OWN insights",
    ]

    if artifact.synthesis_withheld:
        notes.append(
            "synthesis_withheld=True; the synthesis was explicitly withheld (often "
            "because the insights were incomplete), so grounding is not measurable"
        )
        return SynthesisGroundingReport(
            artifact_id=artifact.investigation_id,
            grounding=None,
            synthesis_term_count=0,
            matched_term_count=0,
            overreach_terms=(),
            withheld=True,
            notes=tuple(notes),
        )

    synthesis_text = artifact.synthesis_excerpt or ""
    if not synthesis_text.strip():
        notes.append(
            "no synthesis_excerpt present; there is no conclusion to ground "
            "(defer — grounding applies once a synthesis is authored)"
        )
        return SynthesisGroundingReport(
            artifact_id=artifact.investigation_id,
            grounding=None,
            synthesis_term_count=0,
            matched_term_count=0,
            overreach_terms=(),
            withheld=False,
            notes=tuple(notes),
        )

    synth_terms = _distinctive_terms(synthesis_text)
    if not synth_terms:
        notes.append(
            "synthesis has no distinctive terms after stop-word removal; grounding "
            "is not measurable (defer to the operator's own review)"
        )
        return SynthesisGroundingReport(
            artifact_id=artifact.investigation_id,
            grounding=None,
            synthesis_term_count=0,
            matched_term_count=0,
            overreach_terms=(),
            withheld=False,
            notes=tuple(notes),
        )

    vocab = _insights_vocab([ins.text for ins in artifact.insights])
    matched = [t for t in synth_terms if t in vocab]
    overreach = sorted(t for t in synth_terms if t not in vocab)
    grounding = len(matched) / len(synth_terms)

    notes.append(
        f"synthesis grounding {grounding:.0%}: {len(matched)} of "
        f"{len(synth_terms)} distinctive synthesis term(s) supported by the "
        f"{len(artifact.insights)} insight(s)"
    )
    if overreach:
        notes.append(
            f"OVERREACH: {len(overreach)} synthesis term(s) supported by NO insight "
            "— the conclusion claims these beyond its evidence: "
            + ", ".join(overreach)
        )

    return SynthesisGroundingReport(
        artifact_id=artifact.investigation_id,
        grounding=grounding,
        synthesis_term_count=len(synth_terms),
        matched_term_count=len(matched),
        overreach_terms=tuple(overreach),
        withheld=False,
        notes=tuple(notes),
    )


__all__ = [
    "SynthesisGroundingReport",
    "measure_synthesis_grounding",
]
