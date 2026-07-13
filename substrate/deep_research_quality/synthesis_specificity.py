"""Synthesis specificity — is the conclusion a concrete answer or a vague hedge?

Operator vision: *"provide the highest quality deep research product in the
world"* and *"I want to live in my research workstation ... as I interrogate,
assess, and wrestle with the information in front of me."* The synthesis is the
artifact's HEADLINE conclusion — the one sentence the operator reads first to
decide whether the research answered their question. A synthesis that hedges
("it depends on various factors and context") is unactionable: the operator
cannot act on a conclusion that refuses to commit. A synthesis that commits with
specifics ("GPT-4 costs $30/1M tokens and scores 86.4% on MMLU") is actionable
and checkable.

``synthesis_grounding`` (#1942) measures whether the synthesis RESTS on insights
(does it trace to evidence). ``evidence_specificity`` (#1955) measures per-INSIGHT
numeric density (are individual findings concrete). Neither measures whether the
SYNTHESIS TEXT ITSELF is specific vs vague. A synthesis can be fully grounded
(rests on concrete insights) yet still hedge its conclusion — "the evidence
suggests that several models may offer good performance depending on context"
paraphrases grounded insights into a vague summary. That gap — the synthesis's
own language — is this axis.

**Genuinely distinct (grounding/specificity of different objects):**

* ``synthesis_grounding`` (#1942): does the synthesis rest on insights? (structural
  link — is it EVIDENCE-BACKED?)
* ``evidence_specificity`` (#1955): are the INSIGHTS concrete? (numeric density of
  insight text — are the FINDINGS specific?)
* THIS: is the SYNTHESIS TEXT concrete? (numeric density + hedge density of the
  synthesis excerpt itself — is the CONCLUSION specific?)

The three compose: a grounded + specific-insights + vague-synthesis artifact is
"good findings, weak conclusion" — a real failure mode where the insights carry
the weight but the headline summary drops the specifics.

**The measurement (hard to vary).** Over the synthesis excerpt's tokens:

* ``numeric_ratio`` = fraction of tokens that are numeric (contain a digit, a
  percentage, a version, a magnitude — the same concrete-evidence markers as
  evidence_specificity #1955, applied to the synthesis field).
* ``hedge_ratio`` = fraction of tokens that are HEDGE WORDS (vague qualifiers:
  "generally," "various," "depends," "factors," "several," "some," "many,"
  "typically," "usually," "often," "approximately," "roughly," "may," "might,"
  "could," "likely," "seems," "appears"). A hedge is language that AVOIDS
  commitment.
* ``specificity_ratio = numeric_ratio - hedge_ratio`` clamped to ``[0, 1]`` — the
  net specificity. High = concrete, committed; low = vague, hedged.

The verdict:

* ``synthesis_withheld`` is True → ``withheld`` (the agent INTENTIONALLY did not
  produce a synthesis — honest, never fabricated as vague; the operator sees the
  agent chose to defer).
* ``synthesis_excerpt`` is None or all-glue → ``unknown`` (no synthesis to measure
  — defer, never fabricated as vague).
* ``hedge_ratio >= hedge_threshold`` (default 0.15) → ``hedging`` (the synthesis
  avoids commitment — the operator sees a conclusion that won't commit).
* ``specificity_ratio >= specificity_threshold`` (default 0.10) → ``specific``
  (the synthesis commits with concrete language).
* else → ``vague`` (neither strongly hedging nor concrete — a soft, non-committal
  summary).

**Hedge words are a DISTINCTION signal, not a truth verdict (load-bearing).**
Hedging language is not wrong — sometimes the honest answer genuinely "depends on
context." But a synthesis that hedges on a question with a clear answer is hiding
specificity the operator needs. This axis reports hedge density as a COMMITMENT
signal (how willing is the conclusion to commit), never as a correctness verdict.
``synthesis_grounding`` (#1942) carries the evidence-backing lane; this carries
the language-commitment lane.

**Honesty rules (load-bearing):**

* ``withheld`` when ``synthesis_withheld`` is True — the agent chose not to
  synthesize. Distinct from ``unknown`` (no text provided) and ``vague`` (text
  exists but is non-committal). Never fabricated as vague.
* ``unknown`` when ``synthesis_excerpt`` is None or all-glue (no measurable
  synthesis — defer, never fabricated as hedging).
* Ratios are ``None`` when unmeasurable (withheld/unknown) — defer, never ``0.0``.
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation.
* ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** Uses the canonical ``ResearchArtifactBody``
from ``substrate/research_artifact/schema.py`` (stable on origin/main).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from substrate.research_artifact.schema import ResearchArtifactBody

_DEFAULT_HEDGE_THRESHOLD: float = 0.15
_DEFAULT_SPECIFICITY_THRESHOLD: float = 0.10

_HEDGE_WORDS: frozenset[str] = frozenset(
    {
        "generally", "various", "depends", "factors", "factor", "several",
        "some", "many", "typically", "usually", "often", "frequently",
        "approximately", "roughly", "around", "about", "may", "might",
        "could", "likely", "unlikely", "seems", "appears", "apparently",
        "perhaps", "possibly", "potentially", "presumably", "supposedly",
        "somewhat", "relatively", "fairly", "quite", "rather", "mostly",
        "largely", "mainly", "primarily", "essentially", "basically",
        "overall", "broadly", "tends", "tended", "sometimes", "occasionally", "context", "circumstances",
        "depending", "vary", "varies", "varied", "range", "wide",
    }
)

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?%?")
_NUMERIC_RE = re.compile(r"\d")


@dataclass(frozen=True)
class SynthesisSpecificityReport:
    """The synthesis excerpt's specificity profile. Advisory, pure."""

    artifact_id: str
    numeric_ratio: float | None  # numeric tokens / total; None if unmeasurable
    hedge_ratio: float | None  # hedge tokens / total; None if unmeasurable
    specificity_ratio: float | None  # numeric - hedge clamped [0,1]; None if unmeasurable
    token_count: int  # total tokens measured (0 if withheld/unknown)
    hedge_token_count: int
    numeric_token_count: int
    hedge_threshold: float
    specificity_threshold: float
    verdict: str  # specific | vague | hedging | withheld | unknown
    notes: tuple[str, ...]
    authority: str = "advisory"


class SynthesisSpecificityError(ValueError):
    """A synthesis-specificity input violates a load-bearing invariant."""


def measure_synthesis_specificity(
    artifact: ResearchArtifactBody,
    *,
    hedge_threshold: float = _DEFAULT_HEDGE_THRESHOLD,
    specificity_threshold: float = _DEFAULT_SPECIFICITY_THRESHOLD,
) -> SynthesisSpecificityReport:
    """Measure whether the synthesis excerpt is specific or a vague hedge.

    ``artifact`` is the research artifact whose synthesis is being measured.
    Returns a :class:`SynthesisSpecificityReport` with numeric/hedge/specificity
    ratios + the verdict.

    Pure: no DB, no LLM, no clock, no mutation.
    """
    if not 0.0 <= hedge_threshold <= 1.0:
        raise SynthesisSpecificityError(
            f"hedge_threshold must be in [0,1], got {hedge_threshold!r}"
        )
    if not 0.0 <= specificity_threshold <= 1.0:
        raise SynthesisSpecificityError(
            f"specificity_threshold must be in [0,1], got {specificity_threshold!r}"
        )

    if artifact.synthesis_withheld:
        return _withheld_report(
            artifact.investigation_id, hedge_threshold, specificity_threshold
        )

    excerpt = artifact.synthesis_excerpt
    if not excerpt or not excerpt.strip():
        return _unknown_report(
            artifact.investigation_id, hedge_threshold, specificity_threshold
        )

    tokens = _TOKEN_RE.findall(excerpt.lower())
    if not tokens:
        return _unknown_report(
            artifact.investigation_id, hedge_threshold, specificity_threshold
        )

    token_count = len(tokens)
    numeric_count = sum(1 for t in tokens if _NUMERIC_RE.search(t))
    hedge_count = sum(1 for t in tokens if t in _HEDGE_WORDS)

    numeric_ratio = numeric_count / token_count
    hedge_ratio = hedge_count / token_count
    specificity_ratio = max(0.0, numeric_ratio - hedge_ratio)

    if hedge_ratio >= hedge_threshold:
        verdict = "hedging"
    elif specificity_ratio >= specificity_threshold:
        verdict = "specific"
    else:
        verdict = "vague"

    notes: list[str] = [
        "synthesis specificity measures whether the synthesis excerpt commits with "
        "concrete language or hedges — the CONCLUSION's commitment signal; "
        "synthesis_grounding #1942 checks whether it rests on insights (evidence-backed), "
        "evidence_specificity #1955 checks whether INSIGHTS are concrete (finding-level); "
        "THIS checks whether the SYNTHESIS TEXT is specific (conclusion-level)",
        "numeric_ratio = numeric tokens / total (digits, percentages, versions); "
        "hedge_ratio = hedge tokens / total (vague qualifiers: generally, various, "
        "depends, factors, several, may, might, could, seems, appears); "
        "specificity_ratio = numeric_ratio - hedge_ratio clamped [0,1]",
        "verdict: hedging (hedge_ratio >= threshold — the synthesis avoids commitment), "
        "specific (specificity_ratio >= threshold — commits with concrete language), "
        "vague (neither — a soft non-committal summary)",
        "hedge words are a COMMITMENT signal, not a truth verdict — sometimes the honest "
        "answer genuinely 'depends on context', but a synthesis that hedges on a question "
        "with a clear answer hides specificity the operator needs; synthesis_grounding "
        "carries the evidence-backing lane, this carries the language-commitment lane",
        "withheld when synthesis_withheld=True (agent intentionally deferred — honest, "
        "never fabricated as vague); unknown when no measurable synthesis text (defer, "
        "never fabricated as hedging); ratios None when unmeasurable (never 0.0)",
    ]
    notes.append(
        f"verdict {verdict}: numeric_ratio {numeric_ratio:.0%}, "
        f"hedge_ratio {hedge_ratio:.0%}, specificity_ratio "
        f"{specificity_ratio:.0%} over {token_count} token(s) "
        f"({numeric_count} numeric, {hedge_count} hedge); "
        f"hedge_threshold {hedge_threshold:.0%}, "
        f"specificity_threshold {specificity_threshold:.0%}"
    )

    return SynthesisSpecificityReport(
        artifact_id=artifact.investigation_id,
        numeric_ratio=numeric_ratio,
        hedge_ratio=hedge_ratio,
        specificity_ratio=specificity_ratio,
        token_count=token_count,
        hedge_token_count=hedge_count,
        numeric_token_count=numeric_count,
        hedge_threshold=hedge_threshold,
        specificity_threshold=specificity_threshold,
        verdict=verdict,
        notes=tuple(notes),
    )


def _withheld_report(
    artifact_id: str,
    hedge_threshold: float,
    specificity_threshold: float,
) -> SynthesisSpecificityReport:
    return SynthesisSpecificityReport(
        artifact_id=artifact_id,
        numeric_ratio=None,
        hedge_ratio=None,
        specificity_ratio=None,
        token_count=0,
        hedge_token_count=0,
        numeric_token_count=0,
        hedge_threshold=hedge_threshold,
        specificity_threshold=specificity_threshold,
        verdict="withheld",
        notes=(
            "synthesis withheld (synthesis_withheld=True) — the agent intentionally "
            "did not produce a synthesis; honest, never fabricated as vague; the "
            "operator sees the agent chose to defer",
            "distinct from unknown (no text provided) and vague (text exists but is "
            "non-committal); ratios None (defer, never 0.0)",
        ),
        authority="advisory",
    )


def _unknown_report(
    artifact_id: str,
    hedge_threshold: float,
    specificity_threshold: float,
) -> SynthesisSpecificityReport:
    return SynthesisSpecificityReport(
        artifact_id=artifact_id,
        numeric_ratio=None,
        hedge_ratio=None,
        specificity_ratio=None,
        token_count=0,
        hedge_token_count=0,
        numeric_token_count=0,
        hedge_threshold=hedge_threshold,
        specificity_threshold=specificity_threshold,
        verdict="unknown",
        notes=(
            "no measurable synthesis text (synthesis_excerpt is None or all-glue) — "
            "defer, never fabricated as hedging or vague; ratios None (never 0.0)",
        ),
        authority="advisory",
    )
