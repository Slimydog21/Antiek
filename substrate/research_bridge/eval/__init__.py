"""Eval-precision tooling for the extractor (SPR-02 milestone 5)."""

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
