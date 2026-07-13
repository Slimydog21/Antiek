"""Annotation interrogative-density axis — does the reader's annotation pose questions?

The operator's reading vision is to *interrogate, assess, and wrestle with the information*. The
reader's WRITTEN annotations are where that interrogation lives — an annotation phrased as a
question ("why does the model collapse here?") is a different engagement signal from one phrased
as a declarative note ("key finding: X causes Y"). THIS axis measures the INTERROGATIVE
character of the annotation set: what fraction of annotations pose a question?

It is the complement of ``annotation_substantiveness`` (#1978), not a duplicate. Substantiveness
measures INFORMATION CONTENT by **stripping** interrogatives (stop-word + interrogative removed)
and counting distinctive content terms — it deliberately discards the questioning mode to measure
the declarative payload. THIS axis measures exactly what substantiveness throws away: the
QUESTIONING mode. A terse "why?" is low-substantiveness (no content terms) yet maximally
interrogative; a dense declarative summary is high-substantiveness yet zero-interrogative. The two
axes are orthogonal and disagree by construction.

It is also distinct from every other reading axis (density=marks per content; coverage=spatial
breadth; continuity=step direction; distribution=section spread; re-engagement=cross-session
return; topology=spatial contiguity; cadence=temporal rhythm; substantiveness=content depth) and
from the research-artifact question axes (#1997 question-specificity, #1980 question-redundancy,
#1959 twin-question-support) which operate on ARTIFACT questions, not READING annotations.

**Measured fields:**

* ``annotation_count`` — number of written annotations.
* ``interrogative_count`` — annotations containing a ``?`` (the lexical interrogative signal; a
  ``?`` anywhere in the annotation marks it as question-posing).
* ``interrogative_fraction`` = ``interrogative_count / annotation_count`` (``0.0`` = all
  declarative, ``1.0`` = all questioning; ``None`` only for ``unknown``).
* ``interrogative_opener_count`` — annotations that BEGIN with an interrogative word
  (why/what/how/when/where/who/whom/whose/which + auxiliary can/could/would/should/do/does/did/
  is/are/was/were/will/shall/may/might/must/has/have/had) even WITHOUT a ``?`` (auditable: the
  question-posing mode that lacks punctuation — a softer interrogative signal).
* ``interrogative_opener_fraction`` — the opener-only share (``None`` for ``unknown``).
* ``non_interrogative_count`` — declarative annotations (``annotation_count − interrogative_count``).

**Verdict (distinct honest states, never collapsed, DESCRIPTIVE not normative):**

* zero annotations -> ``unknown`` (no annotation mode to measure — defer, never fabricated).
* ``interrogative_fraction >= interrogative_threshold`` (default ``0.40``) -> ``questioning``
  (the annotation set is dominated by questions — the reader is in interrogate/wrestle mode).
* ``interrogative_fraction <= declarative_threshold`` (default ``0.10``) -> ``declarative``
  (annotations are assertions/notes — the reader is in synthesis/capture mode).
* otherwise -> ``mixed_mode`` (a blend of questions and notes).

**DESCRIPTIVE NOT NORMATIVE:** ``questioning`` does NOT mean "good" — a flood of unfocused
questions can signal confusion rather than depth. ``declarative`` does NOT mean "bad" — confident
synthesis and crisp capture are valuable. The operator judges whether the engagement MODE matches
reading INTENT (exploratory interrogation vs consolidating synthesis). This axis surfaces the FACT
of interrogative character; it does not prescribe the right mode.

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates when zero annotations are supplied.
* A single annotation HAS a definitive interrogative status (it either contains ``?`` or not) — so
  there is NO ``single_annotation`` defer state; ``interrogative_fraction`` is an honest ``0.0`` or
  ``1.0`` for one annotation (unlike cluster-topology where one mark is neither clustered nor
  scattered, one annotation genuinely is or is not a question).
* ``interrogative_fraction`` is ``None`` only for ``unknown``; for any ``>= 1`` annotation it is a
  measured value in ``[0, 1]``.
* thresholds are absolute fractions (scale-free: 40% questions means 40% whether there are 5 or
  500 annotations).
* the primary signal is lexical (``?`` presence); the opener set is a documented, auditable
  supplement (no semantic question-detection — lexical floor, not LLM judgment).
* ``authority = "advisory"`` — pure layer proposes; operator consent executes.
* deterministic + immutable (frozen dataclasses; reproducible output).
* import-free of off-main siblings (plain ``str`` annotation inputs; route layer adapts 1:1 from
  the reading annotation-text log).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "AnnotationInterrogativeDensityReport",
    "measure_annotation_interrogative_density",
]

_DEFAULT_INTERROGATIVE_THRESHOLD = 0.40
_DEFAULT_DECLARATIVE_THRESHOLD = 0.10

_INTERROGATIVE_OPENERS = frozenset(
    {
        "what", "why", "how", "when", "where", "who", "whom", "whose", "which",
        "can", "could", "would", "should", "do", "does", "did",
        "is", "are", "was", "were", "will", "shall", "may", "might", "must",
        "has", "have", "had",
    }
)


@dataclass(frozen=True)
class AnnotationInterrogativeDensityReport:
    """The interrogative-character surface for one reading session's annotations. Advisory, pure."""

    annotation_count: int
    interrogative_count: int
    interrogative_fraction: float | None
    interrogative_opener_count: int
    interrogative_opener_fraction: float | None
    non_interrogative_count: int
    interrogative_threshold: float
    declarative_threshold: float
    verdict: str
    notes: tuple[str, ...]
    authority: str = "advisory"


def _first_token(text: str) -> str:
    """Lowercase first whitespace-delimited token, stripped of leading punctuation."""
    stripped = text.strip().lower()
    if not stripped:
        return ""
    # drop a leading quote/punctuation char so '"why...' still matches 'why'
    first = stripped.split(None, 1)[0]
    return first.lstrip("\"'([{“‘")


def measure_annotation_interrogative_density(
    annotations: Sequence[str],
    *,
    interrogative_threshold: float = _DEFAULT_INTERROGATIVE_THRESHOLD,
    declarative_threshold: float = _DEFAULT_DECLARATIVE_THRESHOLD,
) -> AnnotationInterrogativeDensityReport:
    r"""Measure the interrogative character of a reading session's annotations.

    ``annotations`` are the reader's written annotation texts (the route layer supplies these from
    the reading annotation-text log). Returns an :class:`AnnotationInterrogativeDensityReport`.

    Raises:
        ValueError: if thresholds are out of their valid ranges.
    """
    if not 0.0 <= declarative_threshold <= 1.0:
        raise ValueError(
            f"declarative_threshold must be in [0.0, 1.0]; got {declarative_threshold}"
        )
    if not 0.0 <= interrogative_threshold <= 1.0:
        raise ValueError(
            f"interrogative_threshold must be in [0.0, 1.0]; got {interrogative_threshold}"
        )
    if not declarative_threshold <= interrogative_threshold <= 1.0:
        raise ValueError(
            f"interrogative_threshold ({interrogative_threshold}) must be in "
            f"[declarative_threshold ({declarative_threshold}), 1.0]"
        )

    annotation_count = len(annotations)

    if annotation_count == 0:
        return AnnotationInterrogativeDensityReport(
            annotation_count=0,
            interrogative_count=0,
            interrogative_fraction=None,
            interrogative_opener_count=0,
            interrogative_opener_fraction=None,
            non_interrogative_count=0,
            interrogative_threshold=interrogative_threshold,
            declarative_threshold=declarative_threshold,
            verdict="unknown",
            notes=("no annotations — interrogative character unmeasurable",),
        )

    interrogative_count = sum(1 for a in annotations if "?" in a)
    opener_count = sum(
        1 for a in annotations if _first_token(a) in _INTERROGATIVE_OPENERS
    )
    interrogative_fraction = interrogative_count / annotation_count
    opener_fraction = opener_count / annotation_count
    non_interrogative_count = annotation_count - interrogative_count

    if interrogative_fraction >= interrogative_threshold:
        verdict = "questioning"
        notes = (
            f"interrogative_fraction {interrogative_fraction:.4f} >= interrogative_threshold "
            f"{interrogative_threshold:.2f} — annotations dominated by questions "
            "(interrogate/wrestle mode)",
        )
    elif interrogative_fraction <= declarative_threshold:
        verdict = "declarative"
        notes = (
            f"interrogative_fraction {interrogative_fraction:.4f} <= declarative_threshold "
            f"{declarative_threshold:.2f} — annotations are assertions/notes "
            "(synthesis/capture mode)",
        )
    else:
        verdict = "mixed_mode"
        notes = (
            f"interrogative_fraction {interrogative_fraction:.4f} between thresholds — "
            "a blend of questions and notes",
        )

    return AnnotationInterrogativeDensityReport(
        annotation_count=annotation_count,
        interrogative_count=interrogative_count,
        interrogative_fraction=interrogative_fraction,
        interrogative_opener_count=opener_count,
        interrogative_opener_fraction=opener_fraction,
        non_interrogative_count=non_interrogative_count,
        interrogative_threshold=interrogative_threshold,
        declarative_threshold=declarative_threshold,
        verdict=verdict,
        notes=tuple(notes),
    )
