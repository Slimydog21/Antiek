"""Antiek-bench judged: versioned blinded judge evidence journal.

Separate evidence journal for qualitative scoring with candidate blinding,
deterministic order swaps, and crash-safe claim/settle protocol.  Does not
replace the existing keyword score, dispatch authority, or model selection.

Public surface:

* **RubricVersion**, **RubricAxis** — versioned qualitative rubric definition
* **AxisScore**, **JudgeResult** — validated score output from an injected judge
* **BlindedCandidate**, **BlindedJudgeRequest** — blinded judge inputs
* **BlindingContext** — private join map (never serialized)
* **JudgeEvidenceRecord**, **JudgeEvidenceJournal** — fsync-backed JSONL journal
* **JudgeClient** — typed protocol for injected judge boundary
* **score_and_persist** — claim/score/settle orchestration
"""

from __future__ import annotations

from .blinding import (
    BlindedCandidate,
    BlindedJudgeRequest,
    BlindingContext,
    blind_candidates,
)
from .client import JudgeClient, JudgeReconciliationRequiredError, score_and_persist
from .journal import (
    JudgeEvidenceJournal,
    JudgeEvidenceRecord,
    JudgeJournalCorruptionError,
)
from .rubric import (
    AxisScore,
    JudgeResult,
    RubricAxis,
    RubricVersion,
    make_rubric,
    validate_scores,
)

__all__ = [
    "AxisScore",
    "BlindedCandidate",
    "BlindedJudgeRequest",
    "BlindingContext",
    "JudgeClient",
    "JudgeEvidenceJournal",
    "JudgeEvidenceRecord",
    "JudgeJournalCorruptionError",
    "JudgeResult",
    "JudgeReconciliationRequiredError",
    "RubricAxis",
    "RubricVersion",
    "blind_candidates",
    "make_rubric",
    "score_and_persist",
    "validate_scores",
]
