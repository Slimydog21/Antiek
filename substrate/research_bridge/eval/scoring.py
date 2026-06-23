"""Precision/recall scoring of LLM extractions against operator labels."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

SemanticJudge = Callable[[str, str], bool]


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def SubstringJudge(extracted: str, labelled: str) -> bool:
    """Deterministic baseline judge — substring either direction."""
    a = _normalize(extracted)
    b = _normalize(labelled)
    if not a or not b:
        return False
    return a in b or b in a


@dataclass(frozen=True)
class EvalReportRow:
    document_id: str
    operator_label: str | None
    insight_precision: float
    insight_recall: float
    insight_matched: int
    insight_extracted: int
    insight_labelled: int
    question_precision: float
    question_recall: float
    question_matched: int
    question_extracted: int
    question_labelled: int


@dataclass(frozen=True)
class EvalReport:
    rows: tuple[EvalReportRow, ...]
    insight_precision: float
    insight_recall: float
    question_precision: float
    question_recall: float

    def s3_gate_passed(self, floor: float = 0.5) -> bool:
        return self.question_precision >= floor


def _match_items(
    extracted: list[str], labelled: list[str], judge: SemanticJudge
) -> tuple[int, int, int]:
    n_ext = len(extracted)
    n_lab = len(labelled)
    used = [False] * n_lab
    matched = 0
    for e in extracted:
        for i, lab in enumerate(labelled):
            if used[i]:
                continue
            if judge(e, lab):
                used[i] = True
                matched += 1
                break
    return matched, n_ext, n_lab


def _safe_div(num: int, denom: int) -> float:
    return (num / denom) if denom > 0 else 0.0


def score_against_labels(
    labelled_pastes,  # Iterable[LabelledPaste]
    *,
    extracted_for_doc,  # Callable[[str], tuple[list[str], list[str]]]
    judge: SemanticJudge,
) -> EvalReport:
    rows: list[EvalReportRow] = []
    ins_m_tot = 0
    ins_e_tot = 0
    ins_l_tot = 0
    q_m_tot = 0
    q_e_tot = 0
    q_l_tot = 0
    for lp in labelled_pastes:
        ext_ins, ext_q = extracted_for_doc(lp.document_id)
        ins_m, ins_e, ins_l = _match_items(
            list(ext_ins), list(lp.expected_insights), judge,
        )
        q_m, q_e, q_l = _match_items(
            list(ext_q), list(lp.expected_open_questions), judge,
        )
        rows.append(EvalReportRow(
            document_id=lp.document_id,
            operator_label=lp.operator_label,
            insight_precision=_safe_div(ins_m, ins_e),
            insight_recall=_safe_div(ins_m, ins_l),
            insight_matched=ins_m, insight_extracted=ins_e, insight_labelled=ins_l,
            question_precision=_safe_div(q_m, q_e),
            question_recall=_safe_div(q_m, q_l),
            question_matched=q_m, question_extracted=q_e, question_labelled=q_l,
        ))
        ins_m_tot += ins_m
        ins_e_tot += ins_e
        ins_l_tot += ins_l
        q_m_tot += q_m
        q_e_tot += q_e
        q_l_tot += q_l
    return EvalReport(
        rows=tuple(rows),
        insight_precision=_safe_div(ins_m_tot, ins_e_tot),
        insight_recall=_safe_div(ins_m_tot, ins_l_tot),
        question_precision=_safe_div(q_m_tot, q_e_tot),
        question_recall=_safe_div(q_m_tot, q_l_tot),
    )
