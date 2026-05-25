"""DRW SPR-03 — the distillation seam shared by the always-on passes.

The note-taker role already knows how to turn an LLM response into typed
``ExtractedNote``s (``parser.parse_notes_response``). The Deep Research
Workspace wants that distillation run on *everything* — every document
opened and every research step — asynchronously, so the worker never
times out on lost context. That means the document pass and the step pass
need a common, swappable way to go from *source text* to *insights +
questions* without each re-implementing a dispatch call.

``Distiller`` is that seam. The production impl calls ``dispatch`` with the
note-taker prompt and parses the response; tests inject a deterministic
fake so the always-on machinery (promotion, dedup, provenance, living-note
determinism) is verified without a live model.

Honesty note (rigor #1): "LLMs are perfect note-takers" is the product's
*bet*, not a measured fact. The provenance requirement below is the guard
— a distilled insight with no source attribution is dropped, not promoted,
so a hallucinated insight cannot enter the graph unnoticed.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any, List, Optional, Protocol, Sequence

try:
    from .parser import ExtractedNote, parse_notes_response
    from .prompt import NOTE_TAKER_SYSTEM_PROMPT
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from roles.note_taker.parser import ExtractedNote, parse_notes_response  # type: ignore[no-redef]
    from roles.note_taker.prompt import NOTE_TAKER_SYSTEM_PROMPT  # type: ignore[no-redef]


@dataclass(frozen=True)
class DistilledQuestion:
    """A question surfaced during distillation. ``asks_about`` carries the
    node ids the question concerns (provenance for the SPR-01 ``asks_about``
    edge); empty is allowed but recorded so SPR-07 can still see the
    question node."""

    text: str
    asks_about: tuple[str, ...] = ()
    anchor_region_id: Optional[str] = None


@dataclass(frozen=True)
class Distillation:
    insights: List[ExtractedNote] = field(default_factory=list)
    questions: List[DistilledQuestion] = field(default_factory=list)


class Distiller(Protocol):
    """Source text → insights + questions. Implementations must never
    fabricate: an insight without source attribution is the caller's to
    drop (see ``parser`` rule 4)."""

    def distill(self, text: str, *, source_event_ids: Sequence[str] = (), context: str = "") -> Distillation: ...


class DispatchDistiller:
    """Production distiller: dispatches the note-taker role and parses.

    Imported lazily inside ``distill`` so this module (and the passes that
    use it) stay importable without the dispatch stack — tests use a fake.
    """

    def __init__(self, *, role: str = "note_taker", system_prompt: str = NOTE_TAKER_SYSTEM_PROMPT):
        self._role = role
        self._system_prompt = system_prompt

    def distill(self, text: str, *, source_event_ids: Sequence[str] = (), context: str = "") -> Distillation:
        from substrate.dispatch import dispatch  # lazy
        prompt = self._build_prompt(text, context, source_event_ids)
        result = dispatch(prompt, role=self._role)
        response_text = getattr(result, "text", None) or getattr(result, "response_text", "") or str(result)
        return self._parse(response_text)

    def _build_prompt(self, text: str, context: str, source_event_ids: Sequence[str]) -> str:
        ids = ", ".join(source_event_ids) if source_event_ids else "(none)"
        return (
            f"{self._system_prompt}\n\n"
            f"Source event ids you may attribute to: {ids}\n"
            f"{('Project context:\n' + context) if context else ''}\n\n"
            f"Distill the following into insights + questions:\n\n{text}"
        )

    @staticmethod
    def _parse(response_text: str) -> Distillation:
        notes = parse_notes_response(response_text)
        # Questions ride in the same JSON object under a "questions" key.
        questions: List[DistilledQuestion] = []
        from roles._json_decode import extract_json_object
        obj = extract_json_object(response_text) or {}
        for q in obj.get("questions", []) if isinstance(obj, dict) else []:
            if isinstance(q, dict) and isinstance(q.get("text"), str) and q["text"].strip():
                aa = q.get("asks_about", [])
                questions.append(DistilledQuestion(
                    text=q["text"].strip(),
                    asks_about=tuple(str(a) for a in aa if isinstance(a, str)),
                    anchor_region_id=q.get("anchor_region_id"),
                ))
        return Distillation(insights=notes, questions=questions)
