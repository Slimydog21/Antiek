"""Operator-labelled extraction expectations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class LabelledPaste:
    document_id: str
    operator_label: Optional[str]
    expected_insights: tuple[str, ...] = ()
    expected_open_questions: tuple[str, ...] = ()


def load_labelled_pastes(path: Path | str) -> list[LabelledPaste]:
    import yaml  # type: ignore[import]

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"labels file not found: {p}")
    with p.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    pastes_raw = raw.get("pastes", []) or []
    out: list[LabelledPaste] = []
    for p_raw in pastes_raw:
        if not isinstance(p_raw, dict):
            continue
        doc_id = p_raw.get("document_id")
        if not doc_id:
            continue
        out.append(LabelledPaste(
            document_id=str(doc_id),
            operator_label=p_raw.get("operator_label"),
            expected_insights=tuple(p_raw.get("expected_insights") or ()),
            expected_open_questions=tuple(p_raw.get("expected_open_questions") or ()),
        ))
    return out
