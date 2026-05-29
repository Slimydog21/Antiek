"""Eval-precision tooling for the extractor (SPR-02 milestone 5).

NOTE FOR DELETION (Foundation v2 SPR-02, Rigor card 4): this
precision/recall extractor scorer has **zero production callers** (and no
test callers) as of 2026-05-29. The truth-axis eval substrate now lives
at ``substrate/eval/groundedness/``; this module is dead. It is NOTED for
deletion here — NOT deleted this sprint (out of scope) — so two competing
eval substrates do not silently coexist implying both are wired.
"""

from __future__ import annotations

from .labels import LabelledPaste, load_labelled_pastes
from .scoring import (
    EvalReport,
    EvalReportRow,
    SemanticJudge,
    SubstringJudge,
    score_against_labels,
)

__all__ = [
    "LabelledPaste",
    "load_labelled_pastes",
    "EvalReport",
    "EvalReportRow",
    "SemanticJudge",
    "SubstringJudge",
    "score_against_labels",
]
