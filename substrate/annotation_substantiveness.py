r"""Annotation-substantiveness — how much information does the reader's annotation carry?

Operator vision (asks #2/#3): *"reading and research are the same thing"* and the
core reading workflow — the reader highlights a span AND writes an annotation
(a question, a note, a reaction). ``highlight_density`` (#1973) measures the
reader's SELECTION (how much of the passage was marked — the "chase it" gesture).
This axis measures the reader's WRITTEN ENGAGEMENT — how much INFORMATION the
annotation carries. A substantive annotation ("does this contradict the 2023
finding on p.47?") is high-engagement seed material for a deeper chase; a trivial
annotation ("yes", "lol", an emoji) carries no information — it is engagement
volume without engagement depth.

**Genuinely distinct (different reader behavior):**

* ``highlight_density`` (#1973): how DENSELY did the reader MARK a passage?
  (selection — the "what is valuable" gesture; spatial coverage of the source)
* THIS (``annotation_substantiveness``): how much INFORMATION does the reader's
  WRITTEN annotation carry? (written engagement — the "what I think/question"
  gesture; informational content of the reader's own words)

A reader can densely highlight a passage (high highlight-density) yet write only
"interesting" as the annotation (low substantiveness) — marked everything, said
nothing. The reverse: a reader marks one word (low density) but writes a 40-word
question off it (high substantiveness) — targeted selection, deep engagement.
Selection and written engagement are independent reader behaviors; this axis
measures the second.

**The measurement (hard to vary):**

Lexical distinctive-term floor (stop-word + interrogative stripped, NO
stemming/synonymy — pinned, the same floor as the other text axes):

* ``annotation_terms`` = the SET of distinctive terms in the annotation text
* ``annotation_token_count`` = the total token count (incl. stop-words) — the raw
  annotation length
* ``substantive_term_count = |annotation_terms|`` — distinctive terms (the
  information content)
* ``substantiveness_ratio = substantive_term_count / annotation_token_count`` in
  ``[0,1]`` — the information density of the annotation (1.0 = every token is a
  distinct content term — maximal density; 0.0 = all glue)

**Verdict:**

* ``unknown`` — no measurable annotation text (None / all-glue — defer; never
  fabricated as substantive or trivial)
* ``substantive`` — ``substantive_term_count >= substantive_floor`` (default 5 —
  the annotation carries at least 5 distinct content terms; a real note/question;
  boundary inclusive)
* ``trivial`` — ``0 < substantive_term_count < substantive_floor`` (some words
  but thin — a reaction, not a note)
* ``bare`` — ``substantive_term_count == 0`` but ``annotation_token_count > 0``
  (annotation exists but is ALL glue — "yes", "ok", emoji; a MEASURED empty
  engagement, distinct from ``unknown`` which means no annotation at all)

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates when there is no measurable annotation text — defer
  rather than assert substantive/trivial/bare.
* ``bare`` is a REAL measured verdict (the annotation exists but carries zero
  information), distinct from ``unknown`` (no annotation recorded) and ``trivial``
  (thin but non-zero). Three distinct honest states — never collapsed.
* ``substantiveness_ratio`` is ``None`` when ``unknown`` (defer, never ``0.0``).
* ``bare`` annotation: ``substantiveness_ratio == 0.0`` (a real measured value —
  every token was glue), carried honestly.
* the floor is a COUNT of distinct content terms (not a ratio threshold) because
  a single dense 5-term annotation is substantively different from five 1-term
  annotations — distinct-term COUNT captures the annotation's own information
  mass. The ratio is reported for auditability but the verdict rests on the count.
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation. ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** No reading substrate exists on frozen
``origin/main``; this defines its own input (an annotation string, the route layer
adapts 1:1 from the reading app's annotation records). Pure-Python: stdlib only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_DEFAULT_SUBSTANTIVE_FLOOR: int = 5

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
        "yes", "ok", "okay", "lol", "haha", "wow", "nice", "cool", "great",
        "interesting", "good", "bad", "yeah", "yep", "nope",
    }
)

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?%?")


@dataclass(frozen=True)
class AnnotationSubstantivenessReport:
    """The annotation-substantiveness verdict. Advisory, pure."""

    annotation_token_count: int  # total tokens (incl stop-words); 0 if unknown
    substantive_term_count: int  # distinct content terms; 0 if bare/unknown
    substantiveness_ratio: float | None  # substantive/total; None when unknown
    substantive_floor: int
    verdict: str  # unknown | bare | trivial | substantive
    notes: tuple[str, ...]
    authority: str = "advisory"


class AnnotationSubstantivenessError(ValueError):
    """An annotation-substantiveness input violates a load-bearing invariant."""


def measure_annotation_substantiveness(
    annotation: str | None,
    *,
    substantive_floor: int = _DEFAULT_SUBSTANTIVE_FLOOR,
) -> AnnotationSubstantivenessReport:
    """Measure how much information the reader's annotation carries.

    ``annotation`` is the reader's written annotation text (may be None/empty).
    ``substantive_floor`` is the distinct-content-term count at/above which the
    annotation is "substantive" (default 5).

    Pure: no DB, no LLM, no clock, no mutation.
    """
    if substantive_floor < 1:
        raise AnnotationSubstantivenessError(
            f"substantive_floor must be >= 1, got {substantive_floor!r}"
        )

    if not annotation or not annotation.strip():
        return _report(
            0, 0, None, substantive_floor, "unknown",
            [
                "annotation-substantiveness measures how much INFORMATION the "
                "reader's written annotation carries (distinct content terms); "
                "distinct from highlight_density #1973 (how much the reader MARKED "
                "— selection vs written engagement are independent reader behaviors)",
                "verdict unknown — no measurable annotation text (defer; "
                "substantiveness_ratio is None, never fabricated)",
            ],
        )

    tokens = _TOKEN_RE.findall(annotation.lower())
    if not tokens:
        return _report(
            0, 0, None, substantive_floor, "unknown",
            [
                "annotation-substantiveness measures how much INFORMATION the "
                "reader's written annotation carries; distinct from "
                "highlight_density #1973 (selection vs written engagement)",
                "verdict unknown — annotation has no measurable tokens (defer; "
                "substantiveness_ratio is None, never fabricated)",
            ],
        )

    annotation_token_count = len(tokens)
    substantive_terms = {t for t in tokens if t not in _STOP_WORDS}
    substantive_count = len(substantive_terms)
    substantiveness_ratio = substantive_count / annotation_token_count

    if substantive_count == 0:
        verdict = "bare"
    elif substantive_count >= substantive_floor:
        verdict = "substantive"
    else:
        verdict = "trivial"

    notes: list[str] = [
        "annotation-substantiveness measures how much INFORMATION the reader's "
        "written annotation carries (distinct content terms); distinct from "
        "highlight_density #1973 (how much the reader MARKED — selection). A "
        "reader can densely highlight yet write only 'interesting' (low "
        "substantiveness) — marked everything, said nothing",
        "substantiveness_ratio = substantive_term_count / annotation_token_count "
        "in [0,1] (distinct content terms / total tokens); the verdict rests on "
        "the COUNT (a single dense 5-term annotation differs from five 1-term "
        "annotations), the ratio is reported for auditability",
        "verdict: substantive (distinct content terms >= substantive_floor, "
        "boundary inclusive), trivial (thin — some words but < floor), bare "
        "(annotation exists but ALL glue — zero information; a MEASURED empty "
        "engagement), unknown (no annotation recorded)",
        "bare != trivial != unknown (three distinct honest states — never "
        "collapsed: bare = exists but empty; trivial = thin but non-zero; "
        "unknown = none recorded)",
    ]
    notes.append(
        f"verdict {verdict}: {substantive_count} substantive term(s) of "
        f"{annotation_token_count} token(s), substantiveness_ratio "
        f"{substantiveness_ratio:.0%}; substantive_floor {substantive_floor}"
    )

    return _report(
        annotation_token_count, substantive_count, substantiveness_ratio,
        substantive_floor, verdict, notes,
    )


def _report(
    annotation_token_count: int,
    substantive_term_count: int,
    substantiveness_ratio: float | None,
    substantive_floor: int,
    verdict: str,
    notes: list[str],
) -> AnnotationSubstantivenessReport:
    return AnnotationSubstantivenessReport(
        annotation_token_count=annotation_token_count,
        substantive_term_count=substantive_term_count,
        substantiveness_ratio=substantiveness_ratio,
        substantive_floor=substantive_floor,
        verdict=verdict,
        notes=tuple(notes),
    )
