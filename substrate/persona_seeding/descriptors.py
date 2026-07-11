"""Immutable, process-safe descriptors for isolated persona gathering lanes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, cast

from substrate.research_budget import TierBudget

from .derive import Persona
from .questions import PersonaQuestions


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{field} must be a non-empty string")
    return value.strip()


def _integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field} must be an integer (bool is forbidden)")
    if value < 0:
        raise ValueError(f"{field} must be non-negative")
    return value


@dataclass(frozen=True, slots=True)
class BudgetSlice:
    breadth: int
    depth: int
    token_budget: int
    max_tool_calls: int

    def __post_init__(self) -> None:
        for field in ("breadth", "depth", "token_budget", "max_tool_calls"):
            object.__setattr__(self, field, _integer(getattr(self, field), field))

    def to_payload(self) -> dict[str, int]:
        return {field: getattr(self, field) for field in ("breadth", "depth", "token_budget", "max_tool_calls")}


@dataclass(frozen=True, slots=True)
class SubRunDescriptor:
    run_id: str
    parent_run_id: str
    persona: Persona
    questions: tuple[str, ...]
    budget: BudgetSlice
    corpus_refs: tuple[str, ...]
    visible_persona_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _string(self.run_id, "run_id"))
        object.__setattr__(self, "parent_run_id", _string(self.parent_run_id, "parent_run_id"))
        if not isinstance(self.persona, Persona) or not isinstance(self.budget, BudgetSlice):
            raise TypeError("persona and budget must use canonical contract types")
        questions = tuple(_string(item, "question") for item in self.questions)
        refs = tuple(_string(item, "corpus_ref") for item in self.corpus_refs)
        visible = tuple(_string(item, "visible_persona_id") for item in self.visible_persona_ids)
        if not questions or len(questions) != len(set(questions)):
            raise ValueError("questions must be non-empty and unique")
        if len(refs) != len(set(refs)) or len(visible) != len(set(visible)):
            raise ValueError("duplicate descriptor identity")
        if self.run_id != f"{self.parent_run_id}/{self.persona.persona_id}":
            raise ValueError("conflicting run/persona identity")
        if visible != (self.persona.persona_id,):
            raise ValueError("descriptor violates persona context isolation")
        if sum(
            getattr(self.budget, field)
            for field in ("breadth", "depth", "token_budget", "max_tool_calls")
        ) == 0:
            raise ValueError("descriptor budget slice cannot be entirely zero")
        object.__setattr__(self, "questions", questions)
        object.__setattr__(self, "corpus_refs", refs)
        object.__setattr__(self, "visible_persona_ids", visible)

    def to_payload(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id, "parent_run_id": self.parent_run_id,
            "persona": self.persona.to_payload(), "questions": list(self.questions),
            "budget": self.budget.to_payload(), "corpus_refs": list(self.corpus_refs),
            "visible_persona_ids": list(self.visible_persona_ids),
        }


def _split(total: int, count: int) -> tuple[int, ...]:
    base, remainder = divmod(total, count)
    return tuple(base + (index < remainder) for index in range(count))


def build_sub_run_descriptors(
    parent_run_id: str,
    persona_questions: Sequence[PersonaQuestions | tuple[Persona, tuple[str, ...]]],
    *,
    parent_budget: TierBudget,
    corpus_refs: Sequence[str] = (),
    budget_slices: Sequence[BudgetSlice] | None = None,
) -> tuple[SubRunDescriptor, ...]:
    parent = _string(parent_run_id, "parent_run_id")
    for field in ("breadth", "depth", "token_budget", "max_tool_calls"):
        value = getattr(parent_budget, field)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise TypeError(f"parent budget {field} must be a positive integer")
    if not persona_questions:
        raise ValueError("persona questions cannot be empty")
    pairs = tuple((item.persona, item.questions) if isinstance(item, PersonaQuestions) else item for item in persona_questions)
    if any(not isinstance(persona, Persona) for persona, _ in pairs):
        raise TypeError("invalid persona")
    identities = [persona.persona_id for persona, _ in pairs]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate persona identity")
    refs = tuple(_string(ref, "corpus_ref") for ref in corpus_refs)
    if len(refs) != len(set(refs)):
        raise ValueError("duplicate corpus identity")
    if budget_slices is None:
        fields = tuple(_split(getattr(parent_budget, field), len(pairs)) for field in ("breadth", "depth", "token_budget", "max_tool_calls"))
        slices = tuple(BudgetSlice(*(values[index] for values in fields)) for index in range(len(pairs)))
    else:
        slices = tuple(budget_slices)
        if len(slices) != len(pairs) or any(not isinstance(item, BudgetSlice) for item in slices):
            raise ValueError("one valid budget slice is required per persona")
    _assert_within_parent(slices, parent_budget)
    output: list[SubRunDescriptor] = []
    for (persona, raw_questions), budget in zip(pairs, slices, strict=True):
        questions = tuple(_string(question, "question") for question in raw_questions)
        if not questions or len(questions) != len(set(questions)):
            raise ValueError("questions must be non-empty and unique")
        output.append(SubRunDescriptor(
            f"{parent}/{persona.persona_id}", parent, persona, questions, budget, refs, (persona.persona_id,)
        ))
    return tuple(output)


def _assert_within_parent(slices: Sequence[BudgetSlice], parent: TierBudget) -> None:
    for field in ("breadth", "depth", "token_budget", "max_tool_calls"):
        if sum(getattr(item, field) for item in slices) > getattr(parent, field):
            raise ValueError(f"budget slices exceed parent {field}")


def parse_sub_run_descriptor(payload: object) -> SubRunDescriptor:
    if not isinstance(payload, Mapping):
        raise TypeError("descriptor payload must be a mapping")
    persona_raw = payload.get("persona")
    budget_raw = payload.get("budget")
    if not isinstance(persona_raw, Mapping) or not isinstance(budget_raw, Mapping):
        raise TypeError("persona and budget must be mappings")
    ids_raw = persona_raw.get("grounding_ids")
    questions_raw = payload.get("questions")
    refs_raw = payload.get("corpus_refs")
    visible_raw = payload.get("visible_persona_ids")
    for value, field in ((ids_raw, "grounding_ids"), (questions_raw, "questions"), (refs_raw, "corpus_refs"), (visible_raw, "visible_persona_ids")):
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            raise TypeError(f"{field} must be a sequence")
    ids = cast(Sequence[object], ids_raw)
    questions = cast(Sequence[object], questions_raw)
    refs = cast(Sequence[object], refs_raw)
    visible = cast(Sequence[object], visible_raw)
    provenance_raw = _string(persona_raw.get("provenance"), "provenance")
    if provenance_raw not in ("grounded", "generic"):
        raise ValueError("invalid persona provenance")
    provenance = cast(Literal["grounded", "generic"], provenance_raw)
    persona = Persona(
        _string(persona_raw.get("persona_id"), "persona_id"), _string(persona_raw.get("name"), "name"),
        _string(persona_raw.get("stance"), "stance"), provenance,
        tuple(_string(item, "grounding_id") for item in ids),
    )
    budget = BudgetSlice(*(_integer(budget_raw.get(field), field) for field in ("breadth", "depth", "token_budget", "max_tool_calls")))
    return SubRunDescriptor(
        _string(payload.get("run_id"), "run_id"), _string(payload.get("parent_run_id"), "parent_run_id"), persona,
        tuple(_string(item, "question") for item in questions), budget,
        tuple(_string(item, "corpus_ref") for item in refs),
        tuple(_string(item, "visible_persona_id") for item in visible),
    )
