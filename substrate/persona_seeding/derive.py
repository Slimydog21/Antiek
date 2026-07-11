"""Pure persona derivation from injected twin-question and graph records."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

Provenance = Literal["grounded", "generic"]
GroundingKind = Literal["twin_question", "graph_neighbor"]


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{field} must be a non-empty string")
    return " ".join(value.split())


@dataclass(frozen=True, slots=True)
class GroundingFact:
    grounding_id: str
    kind: GroundingKind
    text: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "grounding_id", _text(self.grounding_id, "grounding_id"))
        object.__setattr__(self, "text", _text(self.text, "text"))
        if self.kind not in ("twin_question", "graph_neighbor"):
            raise ValueError("invalid grounding kind")

    def to_payload(self) -> dict[str, str]:
        return {"grounding_id": self.grounding_id, "kind": self.kind, "text": self.text}


@dataclass(frozen=True, slots=True)
class Persona:
    persona_id: str
    name: str
    stance: str
    provenance: Provenance
    grounding_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for field in ("persona_id", "name", "stance"):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        if "/" in self.persona_id:
            raise ValueError("persona_id must not contain '/'")
        if self.provenance not in ("grounded", "generic"):
            raise ValueError("invalid persona provenance")
        ids = tuple(_text(item, "grounding_id") for item in self.grounding_ids)
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate grounding identity")
        if self.provenance == "grounded" and not ids:
            raise ValueError("grounded persona requires grounding")
        if self.provenance == "generic" and ids:
            raise ValueError("generic persona cannot claim grounding")
        object.__setattr__(self, "grounding_ids", ids)

    def to_payload(self) -> dict[str, Any]:
        return {
            "persona_id": self.persona_id,
            "name": self.name,
            "stance": self.stance,
            "provenance": self.provenance,
            "grounding_ids": list(self.grounding_ids),
        }


_FALLBACKS = (
    ("Evidence auditor", "Generic fallback: test the strength, recency, and limits of available evidence."),
    ("Alternative examiner", "Generic fallback: compare credible alternatives and counterarguments without claiming operator grounding."),
    ("Implementation skeptic", "Generic fallback: examine constraints, failure modes, and practical adoption conditions."),
)


def derive_personas(
    asset_id: str,
    *,
    twin_question_notes: Sequence[object],
    graph_neighbors: Sequence[object],
) -> tuple[Persona, ...]:
    """Return 3--5 stable personas; readers remain outside this pure seam."""
    aid = _text(asset_id, "asset_id")
    facts = _parse_facts(aid, twin_question_notes, graph_neighbors)
    personas: list[Persona] = []
    selected = list(facts[:5])
    overflow: list[list[GroundingFact]] = [[] for _ in selected]
    for index, fact in enumerate(facts[5:]):
        overflow[index % len(selected)].append(fact)
    for index, fact in enumerate(selected):
        persona_facts = (fact, *overflow[index])
        source = "operator question" if fact.kind == "twin_question" else "graph neighbor"
        digest = hashlib.sha256(f"{aid}:{fact.kind}:{fact.grounding_id}".encode()).hexdigest()[:12]
        personas.append(Persona(
            persona_id=f"persona_{digest}",
            name=f"{source.title()} examiner — {fact.text[:48]}",
            stance=(
                f"Examine the asset through {source} evidence: "
                + "; ".join(f"`{item.text}`" for item in persona_facts)
                + "."
            ),
            provenance="grounded",
            grounding_ids=tuple(item.grounding_id for item in persona_facts),
        ))
    for index, (name, stance) in enumerate(_FALLBACKS):
        if len(personas) >= 3:
            break
        digest = hashlib.sha256(f"{aid}:generic:{index}".encode()).hexdigest()[:12]
        personas.append(Persona(f"persona_{digest}", name, stance, "generic", ()))
    return tuple(personas)


def grounding_facts(
    asset_id: str, *, twin_question_notes: Sequence[object], graph_neighbors: Sequence[object]
) -> tuple[GroundingFact, ...]:
    """Expose the canonical facts used by derivation for question conditioning."""
    return _parse_facts(_text(asset_id, "asset_id"), twin_question_notes, graph_neighbors)


def _record(value: object, context: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{context} must be a mapping")
    return value


def _parse_facts(asset_id: str, notes: Sequence[object], neighbors: Sequence[object]) -> tuple[GroundingFact, ...]:
    if isinstance(notes, (str, bytes)) or not isinstance(notes, Sequence):
        raise TypeError("twin_question_notes must be a sequence")
    if isinstance(neighbors, (str, bytes)) or not isinstance(neighbors, Sequence):
        raise TypeError("graph_neighbors must be a sequence")
    facts: list[GroundingFact] = []
    for index, raw in enumerate(notes):
        row = _record(raw, f"twin_question_notes[{index}]")
        if _text(row.get("asset_id"), "asset_id") != asset_id:
            raise ValueError("twin question belongs to a different asset")
        if row.get("kind") != "question":
            raise ValueError("only twin question notes may ground personas")
        facts.append(GroundingFact(_text(row.get("note_id"), "note_id"), "twin_question", _text(row.get("text"), "text")))
    for index, raw in enumerate(neighbors):
        row = _record(raw, f"graph_neighbors[{index}]")
        label = row.get("canonical_label", row.get("text"))
        facts.append(GroundingFact(_text(row.get("node_id"), "node_id"), "graph_neighbor", _text(label, "canonical_label")))
    by_id: dict[str, GroundingFact] = {}
    for fact in facts:
        previous = by_id.get(fact.grounding_id)
        if previous is not None:
            if previous != fact:
                raise ValueError(f"conflicting grounding identity: {fact.grounding_id}")
            raise ValueError(f"duplicate grounding identity: {fact.grounding_id}")
        by_id[fact.grounding_id] = fact
    priority = {"twin_question": 0, "graph_neighbor": 1}
    return tuple(
        sorted(
            facts,
            key=lambda fact: (priority[fact.kind], fact.grounding_id, fact.text),
        )
    )
