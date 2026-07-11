"""Perspective-conditioned question generation with conservative dedup."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from substrate.research_budget import TierBudget

from .derive import GroundingFact, Persona

QuestionGenerator = Callable[[Persona, tuple[GroundingFact, ...], int], Sequence[str]]


@dataclass(frozen=True, slots=True)
class PersonaQuestions:
    persona: Persona
    questions: tuple[str, ...]


def _normalized(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", text.casefold())
    return " ".join(word for word in words if word not in {"a", "an", "the"})


def _default_generator(persona: Persona, facts: tuple[GroundingFact, ...], count: int) -> Sequence[str]:
    relevant = [fact.text for fact in facts if fact.grounding_id in persona.grounding_ids]
    subject = relevant[0] if relevant else persona.stance
    stems = (
        "What evidence would confirm or weaken",
        "Which competing explanation best challenges",
        "What boundary conditions materially change",
        "Which primary source could resolve uncertainty about",
        "What practical failure mode is most relevant to",
    )
    return tuple(f"{stems[index % len(stems)]} {subject}?" for index in range(count))


def generate_questions(
    personas: Sequence[Persona],
    *,
    facts: Sequence[GroundingFact],
    budget: TierBudget,
    generator: QuestionGenerator | None = None,
) -> tuple[PersonaQuestions, ...]:
    for field in ("breadth", "depth", "token_budget", "max_tool_calls"):
        value = getattr(budget, field)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise TypeError(f"budget {field} must be a positive integer")
    if isinstance(personas, (str, bytes)) or not isinstance(personas, Sequence) or not personas:
        raise TypeError("personas must be a non-empty sequence")
    if any(not isinstance(persona, Persona) for persona in personas):
        raise TypeError("personas contains an invalid value")
    if len({persona.persona_id for persona in personas}) != len(personas):
        raise ValueError("duplicate persona identity")
    canonical_facts = tuple(facts)
    if any(not isinstance(fact, GroundingFact) for fact in canonical_facts):
        raise TypeError("facts contains an invalid value")
    available = {fact.grounding_id for fact in canonical_facts}
    if len(available) != len(canonical_facts):
        raise ValueError("duplicate grounding identity")
    if any(not set(persona.grounding_ids) <= available for persona in personas):
        raise ValueError("persona grounding does not resolve from inputs")
    count = max(1, (budget.breadth + len(personas) - 1) // len(personas))
    fn = generator or _default_generator
    seen: set[str] = set()
    output: list[PersonaQuestions] = []
    for persona in personas:
        try:
            raw = fn(persona, canonical_facts, count)
        except Exception as exc:
            raise ValueError("question generator failed") from exc
        if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence) or not raw:
            raise TypeError("question generator must return a non-empty sequence")
        if any(not isinstance(item, str) or not item.strip() for item in raw):
            raise TypeError("generated questions must be non-empty strings")
        selected: list[str] = []
        for item in raw:
            cleaned = " ".join(item.split())
            key = _normalized(cleaned)
            if key and key not in seen:
                seen.add(key)
                selected.append(cleaned)
            if len(selected) == count:
                break
        if len(selected) < count:
            raise ValueError(
                "question generator did not provide enough distinct "
                f"questions for persona {persona.persona_id}"
            )
        output.append(PersonaQuestions(persona, tuple(selected)))
    if len({item.questions for item in output}) != len(output):
        raise ValueError("personas produced identical question sets")
    return tuple(output)
