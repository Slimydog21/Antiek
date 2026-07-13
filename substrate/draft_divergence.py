r"""Draft-divergence — how far has the draft drifted from its parent(s)?

Operator vision (ask #3): *"maybe even I want to create a draft version with the
combined document before fully merging."* The draft is the operator's REVIEW
CHECKPOINT — a SAFER staging state where you review the combined document before
committing the merge. ``draft_divergence`` answers the question the operator
faces at that checkpoint: *"how much has this draft changed from what I started
with?"* — so they know whether to merge it cleanly (low drift, faithful
combination) or review it carefully (high drift, the draft has become its own
thing).

**Genuinely distinct (different lifecycle stage + different ratio):**

* ``merge_integrity`` (#1962): POST-merge — did the RESULT preserve its parents?
  Measures ``|parents ∩ result| / |parents|`` (the "did we lose anything" signal
  — parent SURVIVAL rate in the committed merge).
* THIS (``draft_divergence``): PRE-merge — how far has the DRAFT drifted from its
  parents while in the staging area? Measures ``|draft \ parents| / |draft|`` (the
  "how much of the draft is NEW vs inherited" signal — the NOVELTY rate of the
  uncommitted draft).

The two ratios are genuinely different numerators/denominators and serve
different decisions:

* A draft that is 100% new material (high divergence, zero parent overlap) —
  ``merge_integrity`` frames the eventual merge as a fidelity FAILURE (parents
  did not survive); ``draft_divergence`` frames the CURRENT draft as "become its
  own thing — review before merging" (an honest signal, not a failure: combining
  sources often produces new synthesis).
* A draft that is 100% parent material (zero divergence) — ``merge_integrity``
  says the merge will be faithful (good); ``draft_divergence`` says the draft
  added NOTHING (a no-op combination — why merge? just keep the parent).

``draft_divergence`` measures the DRAFT (staging); ``merge_integrity`` measures
the RESULT (committed). A high-divergence draft may still merge faithfully (the
operator deliberately added new synthesis — divergence is expected when
combining). They are complementary: divergence predicts whether the eventual
merge will surprise the operator.

**The measurement (hard to vary):**

Lexical distinctive-term floor (stop-word + interrogative stripped, NO
stemming/synonymy — pinned, same floor as the other text axes):

* ``parent_terms`` = the SET of distinctive terms across all parent texts (the
  inherited baseline)
* ``draft_terms`` = the SET of distinctive terms in the draft text
* ``inherited_terms`` = ``draft_terms ∩ parent_terms`` (terms the draft kept from
  parents)
* ``novel_terms`` = ``draft_terms \ parent_terms`` (terms the draft added that
  are NOT in any parent)
* ``divergence_ratio = |novel_terms| / |draft_terms|`` in ``[0, 1]`` — the share
  of the draft that is NEW (0 = nothing new; 1 = entirely new)

**Verdict:**

* ``unknown`` — no measurable draft text (None / all-glue — defer, never fabricate
  drift)
* ``no_drift`` — ``draft_terms`` is non-empty AND ``novel_terms`` is empty
  (divergence 0 — the draft added nothing; a no-op combination)
* ``high_drift`` — ``divergence_ratio >= high_threshold`` (default ``0.70`` — the
  draft is mostly new material; boundary inclusive)
* ``moderate_drift`` — ``0 < divergence_ratio < high_threshold`` (the draft mixed
  inherited + new — the normal combination shape)

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates a verdict when the draft has no measurable text
  (defer rather than assert drift).
* ``no_drift`` is a REAL verdict (the draft added nothing — distinct from
  ``unknown`` which means there was no draft to measure). A draft that perfectly
  echoes its parents is measured, not unknown.
* ``unknown`` when ``draft_terms`` is empty even if parent texts exist (the
  draft's distinctive-term set is what we divide by — an empty denominator
  defers, never fabricates 0.0).
* all-glue texts (only stop-words) are excluded — they contribute no distinctive
  terms (carried as ``unmeasurable_draft`` / ``unmeasurable_parent`` counts —
  never fabricated as lost material).
* ``parent_texts`` may be empty (a draft with no recorded parents — e.g., a fresh
  standalone draft); in that case ``inherited_terms`` is empty and every draft
  term is novel, so ``divergence_ratio = 1.0`` honestly (a parentless draft is
  entirely new by definition — not an error).
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation. ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** Defines its own ``DraftInput`` shape (the
route layer adapts 1:1 from the merge_lifecycle / collective_graph records, which
are NOT on frozen main). Pure-Python: stdlib only.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

_DEFAULT_HIGH_THRESHOLD: float = 0.70

# Stop-words stripped before measuring (the lexical floor — no stemming/synonymy).
_STOP_WORDS: frozenset[str] = frozenset(
    {
        "the", "a", "an", "and", "or", "but", "if", "then", "else", "when",
        "at", "by", "for", "with", "about", "against", "between", "into",
        "through", "during", "before", "after", "above", "below", "to", "from",
        "up", "down", "in", "out", "on", "off", "over", "under", "again",
        "further", "is", "are", "was", "were", "be", "been", "being", "am",
        "have", "has", "had", "do", "does", "did", "will", "would", "shall",
        "should", "may", "might", "must", "can", "could", "of", "as", "this",
        "that", "these", "those", "it", "its", "they", "them", "their", "we",
        "us", "our", "you", "your", "he", "she", "him", "her", "his", "hers",
        "i", "me", "my", "mine", "which", "who", "whom", "what", "where", "why",
        "how", "all", "each", "every", "both", "few", "more", "most", "other",
        "some", "such", "no", "not", "only", "own", "same", "so", "than", "too",
        "very", "just", "also", "there", "here", "now", "any", "because", "while",
    }
)

# Interrogatives are stop-words for drift-measuring (they are question shape, not
# content). A draft that asks "what why how" added no novel content.
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?%?")


@dataclass(frozen=True)
class DraftInput:
    """A draft and its parent texts. Pure input."""

    draft_text: str | None
    parent_texts: Sequence[str]  # may be empty (a parentless standalone draft)


@dataclass(frozen=True)
class DraftDivergenceReport:
    """The draft-divergence verdict. Advisory, pure."""

    draft_term_count: int  # distinctive terms in draft (0 if unmeasurable)
    parent_term_count: int  # union of distinctive terms across parents
    inherited_term_count: int  # draft ∩ parents
    novel_term_count: int  # draft \ parents
    divergence_ratio: float | None  # novel/draft; None when draft unmeasurable
    high_threshold: float
    verdict: str  # unknown | no_drift | high_drift | moderate_drift
    notes: tuple[str, ...]
    authority: str = "advisory"


class DraftDivergenceError(ValueError):
    """A draft-divergence input violates a load-bearing invariant."""


def measure_draft_divergence(
    draft: DraftInput,
    *,
    high_threshold: float = _DEFAULT_HIGH_THRESHOLD,
) -> DraftDivergenceReport:
    """Measure how far the draft has drifted from its parent(s).

    ``draft`` is the draft text + its parent texts.
    ``high_threshold`` is the divergence fraction above which drift is "high"
    (default 0.70).

    Pure: no DB, no LLM, no clock, no mutation.
    """
    if not 0.0 <= high_threshold <= 1.0:
        raise DraftDivergenceError(
            f"high_threshold must be in [0,1], got {high_threshold!r}"
        )

    draft_terms = _distinctive_terms(draft.draft_text)
    parent_terms: set[str] = set()
    for parent_text in draft.parent_texts:
        parent_terms |= _distinctive_terms(parent_text)

    draft_count = len(draft_terms)
    parent_count = len(parent_terms)

    # No measurable draft -> unknown (the draft's term set is the denominator;
    # an empty denominator defers, never fabricates 0.0 divergence).
    if draft_count == 0:
        return _report(
            0, parent_count, 0, 0, None, high_threshold, "unknown",
            [
                "draft-divergence measures how far the draft drifted from its "
                "parent(s) while in the staging area (PRE-merge drift); distinct "
                "from merge_integrity #1962 (POST-merge — did the RESULT preserve "
                "its parents, |parents∩result|/|parents|); THIS measures "
                "|draft\\parents|/|draft| (how much of the draft is NEW vs inherited)",
                "verdict unknown — the draft has no measurable distinctive terms "
                "(None / all-glue); divergence_ratio is None (defer, never "
                "fabricated — an empty denominator cannot be 0.0)",
            ],
        )

    inherited = draft_terms & parent_terms
    novel = draft_terms - parent_terms
    inherited_count = len(inherited)
    novel_count = len(novel)
    divergence_ratio = novel_count / draft_count

    if novel_count == 0:
        verdict = "no_drift"
    elif divergence_ratio >= high_threshold:
        verdict = "high_drift"
    else:
        verdict = "moderate_drift"

    notes: list[str] = [
        "draft-divergence measures how far the draft drifted from its parent(s) "
        "while in the staging area (PRE-merge drift); distinct from "
        "merge_integrity #1962 (POST-merge — did the RESULT preserve its parents); "
        "THIS measures |draft\\parents|/|draft| (the share of the draft that is NEW "
        "vs inherited — the NOVELTY rate of the uncommitted draft)",
        "divergence_ratio = novel_terms / draft_terms in [0,1] (0 = nothing new, a "
        "no-op combination; 1 = entirely new); lexical distinctive-term floor "
        "(stop-word + interrogative stripped, NO stemming/synonymy — pinned)",
        "verdict: no_drift (added nothing — distinct from unknown), high_drift "
        "(mostly new — review before merging), moderate_drift (mixed inherited + "
        "new — the normal combination shape)",
        "unknown when draft has no measurable distinctive terms (defer, never "
        "fabricate); a parentless draft (empty parent_texts) is entirely novel by "
        "definition (divergence 1.0 — honest, not an error)",
    ]
    notes.append(
        f"verdict {verdict}: {draft_count} draft terms, {inherited_count} "
        f"inherited, {novel_count} novel, divergence {divergence_ratio:.0%} "
        f"(parents {parent_count} terms); high_threshold {high_threshold:.0%}"
    )

    return _report(
        draft_count,
        parent_count,
        inherited_count,
        novel_count,
        divergence_ratio,
        high_threshold,
        verdict,
        notes,
    )


def _distinctive_terms(text: str | None) -> set[str]:
    """Lexical distinctive-term set for one text (stop-words + interrogatives off).

    All-glue text contributes nothing (returns empty set). Lowercased.
    """
    if not text:
        return set()
    tokens = _TOKEN_RE.findall(text.lower())
    return {t for t in tokens if t not in _STOP_WORDS}


def _report(
    draft_count: int,
    parent_count: int,
    inherited_count: int,
    novel_count: int,
    divergence_ratio: float | None,
    high_threshold: float,
    verdict: str,
    notes: list[str],
) -> DraftDivergenceReport:
    return DraftDivergenceReport(
        draft_term_count=draft_count,
        parent_term_count=parent_count,
        inherited_term_count=inherited_count,
        novel_term_count=novel_count,
        divergence_ratio=divergence_ratio,
        high_threshold=high_threshold,
        verdict=verdict,
        notes=tuple(notes),
    )
