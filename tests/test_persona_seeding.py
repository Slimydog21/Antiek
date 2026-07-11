from __future__ import annotations

import json
import math
from collections.abc import Sequence
from typing import Any

import pytest

from substrate.persona_seeding import (
    BudgetSlice,
    GroundingFact,
    Persona,
    SubRunDescriptor,
    build_sub_run_descriptors,
    derive_personas,
    generate_questions,
    grounding_facts,
    parse_sub_run_descriptor,
    parse_sub_run_descriptors,
)
from substrate.persona_seeding.descriptors import _split_breadth_depth
from substrate.research_budget import TierBudget

NOTES = (
    {"note_id": "note-risk", "asset_id": "asset-1", "kind": "question", "text": "What could invalidate adoption?"},
    {"note_id": "note-cost", "asset_id": "asset-1", "kind": "question", "text": "What drives lifecycle cost?"},
)
NEIGHBORS = (
    {"node_id": "node-rival", "canonical_label": "Incumbent alternative"},
    {"node_id": "node-policy", "canonical_label": "Policy constraint"},
)


def test_derivation_is_deterministic_grounded_and_resolvable() -> None:
    first = derive_personas("asset-1", twin_question_notes=NOTES, graph_neighbors=NEIGHBORS)
    second = derive_personas("asset-1", twin_question_notes=tuple(reversed(NOTES)), graph_neighbors=tuple(reversed(NEIGHBORS)))

    assert first == second
    assert 3 <= len(first) <= 5
    available = {"note-risk", "note-cost", "node-rival", "node-policy"}
    assert all(set(persona.grounding_ids) <= available for persona in first)
    assert all(persona.provenance == "grounded" for persona in first)


@pytest.mark.parametrize(
    ("notes", "neighbors", "expected_grounded"),
    [
        ((), (), 0),
        ((NOTES[0],), (), 1),
        ((), (NEIGHBORS[0],), 1),
    ],
)
def test_empty_and_thin_inputs_are_honest_fallbacks(
    notes: Sequence[object], neighbors: Sequence[object], expected_grounded: int
) -> None:
    personas = derive_personas("asset-1", twin_question_notes=notes, graph_neighbors=neighbors)

    assert len(personas) == 3
    assert sum(persona.provenance == "grounded" for persona in personas) == expected_grounded
    assert all(persona.grounding_ids == () for persona in personas if persona.provenance == "generic")
    assert all("generic fallback" in persona.stance.lower() for persona in personas if persona.provenance == "generic")


@pytest.mark.parametrize(
    ("notes", "neighbors"),
    [
        (({"note_id": "dup", "asset_id": "asset-1", "kind": "question", "text": "A?"}, {"note_id": "dup", "asset_id": "asset-1", "kind": "question", "text": "B?"}), ()),
        (({"note_id": "x", "asset_id": "other", "kind": "question", "text": "A?"},), ()),
        (({"note_id": "x", "asset_id": "asset-1", "kind": "insight", "text": "A"},), ()),
        (({"note_id": True, "asset_id": "asset-1", "kind": "question", "text": "A?"},), ()),
        ((), ({"node_id": "same", "canonical_label": "A"}, {"node_id": "same", "canonical_label": "B"})),
    ],
)
def test_derivation_fails_closed_on_hostile_or_conflicting_facts(
    notes: Sequence[object], neighbors: Sequence[object]
) -> None:
    with pytest.raises((TypeError, ValueError)):
        derive_personas("asset-1", twin_question_notes=notes, graph_neighbors=neighbors)


def test_question_counts_follow_breadth_boundaries() -> None:
    personas = derive_personas("asset-1", twin_question_notes=NOTES, graph_neighbors=NEIGHBORS)

    fast = generate_questions(personas, facts=_facts(), budget=TierBudget(2, 1, 100, 4))
    wrestle = generate_questions(personas, facts=_facts(), budget=TierBudget(10, 2, 100, 4))

    assert {len(item.questions) for item in fast} == {1}
    assert {len(item.questions) for item in wrestle} == {3}
    assert len({item.questions for item in fast}) == len(fast)


def test_cross_persona_literal_and_conservative_near_duplicate_dedup() -> None:
    personas = derive_personas("asset-1", twin_question_notes=NOTES, graph_neighbors=NEIGHBORS)

    def colliding(persona: Persona, facts: tuple[GroundingFact, ...], count: int) -> Sequence[str]:
        del facts, count
        return (
            "What evidence supports adoption?",
            "What evidence supports the adoption!",
            f"Which constraint matters most to {persona.persona_id}?",
            f"What would falsify the {persona.persona_id} perspective?",
        )

    generated = generate_questions(personas, facts=_facts(), budget=TierBudget(6, 1, 100, 4), generator=colliding)
    normalized = [q.casefold().rstrip("?!.") for result in generated for q in result.questions]

    assert len(normalized) == len(set(normalized))
    assert len({result.questions for result in generated}) == len(generated)
    assert all(len(result.questions) == 2 for result in generated)


def test_dedup_never_invents_questions_missing_from_generator_output() -> None:
    personas = (
        Persona("p1", "One", "Generic fallback: one", "generic", ()),
        Persona("p2", "Two", "Generic fallback: two", "generic", ()),
    )

    def collision(
        persona: Persona, facts: tuple[GroundingFact, ...], count: int
    ) -> Sequence[str]:
        del persona, facts, count
        return ("What evidence supports adoption?",)

    with pytest.raises(ValueError, match="no globally distinct"):
        generate_questions(
            personas,
            facts=(),
            budget=TierBudget(2, 1, 100, 2),
            generator=collision,
        )


@pytest.mark.parametrize("bad", [None, "question", ("ok", 3), (), (" ",)])
def test_question_generator_invalid_outputs_fail_closed(bad: object) -> None:
    personas = derive_personas("asset-1", twin_question_notes=NOTES, graph_neighbors=NEIGHBORS)

    def invalid(persona: Persona, facts: tuple[GroundingFact, ...], count: int) -> object:
        del persona, facts, count
        return bad

    with pytest.raises((TypeError, ValueError)):
        generate_questions(personas, facts=_facts(), budget=TierBudget(2, 1, 100, 4), generator=invalid)  # type: ignore[arg-type]

    def exploding(persona: Persona, facts: tuple[GroundingFact, ...], count: int) -> Sequence[str]:
        del persona, facts, count
        raise RuntimeError("generator unavailable")

    with pytest.raises(ValueError, match="generator failed"):
        generate_questions(personas, facts=_facts(), budget=TierBudget(2, 1, 100, 4), generator=exploding)


def test_descriptors_are_isolated_immutable_budgeted_and_round_trip() -> None:
    parent = TierBudget(4, 2, 80_000, 32)
    personas = derive_personas("asset-1", twin_question_notes=NOTES, graph_neighbors=NEIGHBORS)
    questions = generate_questions(personas, facts=_facts(), budget=parent)
    descriptors = build_sub_run_descriptors("run-1", questions, parent_budget=parent, corpus_refs=("asset-1",))

    assert len({d.run_id for d in descriptors}) == len(descriptors)
    assert len({d.persona.persona_id for d in descriptors}) == len(descriptors)
    assert sum(d.budget.breadth for d in descriptors) <= parent.breadth
    assert sum(d.budget.depth for d in descriptors) <= parent.depth
    assert sum(d.budget.token_budget for d in descriptors) <= parent.token_budget
    assert sum(d.budget.max_tool_calls for d in descriptors) <= parent.max_tool_calls
    assert all(d.visible_persona_ids == (d.persona.persona_id,) for d in descriptors)
    assert all(
        parse_sub_run_descriptor(
            json.loads(json.dumps(d.to_payload())),
            parent_budget=parent,
            grounding_facts=_facts(),
        )
        == d
        for d in descriptors
    )
    payloads = [json.loads(json.dumps(d.to_payload())) for d in descriptors]
    assert parse_sub_run_descriptors(
        payloads, parent_budget=parent, grounding_facts=_facts(),
    ) == descriptors
    with pytest.raises((AttributeError, TypeError)):
        descriptors[0].questions += ("mutation",)  # type: ignore[misc]


def test_descriptor_parser_rejects_bool_nan_duplicate_identity_and_over_budget() -> None:
    persona = Persona("persona-1", "Name", "Stance", "generic", ())
    with pytest.raises(ValueError, match="exceed"):
        build_sub_run_descriptors(
            "run", ((persona, ("Q?",)),), parent_budget=TierBudget(1, 1, 10, 1),
            budget_slices=(BudgetSlice(2, 1, 10, 1),),
        )
    payload: dict[str, Any] = {
        "run_id": "run/persona-1", "parent_run_id": "run", "persona": persona.to_payload(),
        "questions": ["Q?"], "budget": {"breadth": True, "depth": 1, "token_budget": 10, "max_tool_calls": 1},
        "corpus_refs": [], "visible_persona_ids": ["persona-1"],
    }
    with pytest.raises(TypeError):
        parse_sub_run_descriptor(
            payload, parent_budget=TierBudget(1, 1, 10, 1), grounding_facts=(),
        )
    payload["budget"]["breadth"] = math.nan
    with pytest.raises(TypeError):
        parse_sub_run_descriptor(
            payload, parent_budget=TierBudget(1, 1, 10, 1), grounding_facts=(),
        )


def test_public_descriptor_constructor_enforces_identity_and_isolation() -> None:
    persona = Persona("p1", "One", "Generic fallback: one", "generic", ())
    with pytest.raises(ValueError, match="run/persona identity"):
        SubRunDescriptor(
            "unrelated",
            "parent",
            persona,
            ("Q?",),
            BudgetSlice(1, 0, 1, 1),
            (),
            ("p1",),
        )
    with pytest.raises(ValueError, match="context isolation"):
        SubRunDescriptor(
            "parent/p1",
            "parent",
            persona,
            ("Q?",),
            BudgetSlice(1, 0, 1, 1),
            (),
            ("p2",),
        )
    with pytest.raises(ValueError, match="dispatchable"):
        BudgetSlice(0, 0, 0, 0)


def test_persona_provenance_constructor_invariants_are_red_proven() -> None:
    with pytest.raises(ValueError, match="requires grounding"):
        Persona("grounded", "Grounded", "Evidence", "grounded", ())
    with pytest.raises(ValueError, match="cannot claim grounding"):
        Persona("generic", "Generic", "Fallback", "generic", ("note-1",))


def test_operator_questions_are_prioritized_and_no_grounding_fact_is_dropped() -> None:
    neighbors = tuple(
        {"node_id": f"node-{index}", "canonical_label": f"Neighbor {index}"}
        for index in range(7)
    )
    personas = derive_personas(
        "asset-1", twin_question_notes=NOTES, graph_neighbors=neighbors,
    )
    represented = {gid for persona in personas for gid in persona.grounding_ids}
    expected = {note["note_id"] for note in NOTES} | {
        neighbor["node_id"] for neighbor in neighbors
    }
    assert len(personas) == 5
    assert personas[0].grounding_ids[0] == "note-cost"
    assert personas[1].grounding_ids[0] == "note-risk"
    assert represented == expected


@pytest.mark.parametrize(
    "budget",
    [TierBudget(2, 1, 100, 4), TierBudget(8, 2, 1000, 8), TierBudget(20, 4, 4000, 20)],
)
def test_default_generation_survives_near_duplicate_and_non_latin_grounding(
    budget: TierBudget,
) -> None:
    neighbors = (
        {"node_id": "node-a", "canonical_label": "AlphaFold-3"},
        {"node_id": "node-b", "canonical_label": "AlphaFold 3"},
        {"node_id": "node-ar", "canonical_label": "قيود السياسة"},
        {"node_id": "node-zh", "canonical_label": "政策约束"},
    )
    personas = derive_personas(
        "asset-1", twin_question_notes=(), graph_neighbors=neighbors,
    )
    generated = generate_questions(
        personas,
        facts=grounding_facts(
            "asset-1", twin_question_notes=(), graph_neighbors=neighbors,
        ),
        budget=budget,
    )
    assert len(generated) == len(personas)
    assert all(item.questions for item in generated)
    assert len({question for item in generated for question in item.questions}) == sum(
        len(item.questions) for item in generated
    )


def test_question_dedup_degrades_to_partial_distinct_output_not_crash() -> None:
    personas = (
        Persona("p1", "One", "Generic fallback one", "generic", ()),
        Persona("p2", "Two", "Generic fallback two", "generic", ()),
    )

    def partly_colliding(
        persona: Persona, facts: tuple[GroundingFact, ...], count: int,
    ) -> Sequence[str]:
        del facts, count
        return ("Shared question?", f"Unique for {persona.persona_id}?")

    generated = generate_questions(
        personas,
        facts=(),
        budget=TierBudget(4, 1, 100, 4),
        generator=partly_colliding,
    )
    assert [len(item.questions) for item in generated] == [2, 1]


def test_descriptor_floor_and_parse_boundary_revalidate_authorities() -> None:
    personas = tuple(
        Persona(f"p{index}", f"P{index}", "Generic fallback", "generic", ())
        for index in range(5)
    )
    pairs = tuple((persona, ("Q?",)) for persona in personas)
    with pytest.raises(ValueError, match="one tool call per persona"):
        build_sub_run_descriptors(
            "run", pairs, parent_budget=TierBudget(5, 1, 100, 4),
        )

    grounded = Persona("p-ground", "Ground", "Grounded", "grounded", ("note-risk",))
    descriptor = SubRunDescriptor(
        "run/p-ground", "run", grounded, ("Q?",), BudgetSlice(1, 1, 10, 1),
        (), ("p-ground",),
    )
    payload = descriptor.to_payload()
    with pytest.raises(ValueError, match="does not resolve"):
        parse_sub_run_descriptor(
            payload, parent_budget=TierBudget(1, 1, 10, 1), grounding_facts=(),
        )
    payload["budget"]["max_tool_calls"] = 1_000_000
    with pytest.raises(ValueError, match="exceed"):
        parse_sub_run_descriptor(
            payload, parent_budget=TierBudget(1, 1, 10, 1), grounding_facts=_facts(),
        )
    payload = descriptor.to_payload()
    payload["unknown"] = "smuggled"
    with pytest.raises(ValueError, match="keys mismatch"):
        parse_sub_run_descriptor(
            payload, parent_budget=TierBudget(1, 1, 10, 1), grounding_facts=_facts(),
        )
    with pytest.raises(ValueError, match="must not contain"):
        Persona("parent/child", "Bad", "Bad", "generic", ())

    with pytest.raises(ValueError, match="breadth or depth"):
        BudgetSlice(0, 0, 100, 1)

    funded = personas[:3]
    descriptors = build_sub_run_descriptors(
        "funded",
        tuple((persona, ("Q?",)) for persona in funded),
        parent_budget=TierBudget(2, 1, 30, 3),
    )
    assert all(item.budget.breadth + item.budget.depth >= 1 for item in descriptors)
    assert all(item.budget.token_budget >= 1 for item in descriptors)
    assert all(item.budget.max_tool_calls >= 1 for item in descriptors)
    with pytest.raises(ValueError, match="cannot fund"):
        _split_breadth_depth(1, 1, 3)

    first = descriptors[0].to_payload()
    second = descriptors[1].to_payload()
    first["budget"] = {"breadth": 2, "depth": 1, "token_budget": 20, "max_tool_calls": 2}
    second["budget"] = {"breadth": 2, "depth": 1, "token_budget": 20, "max_tool_calls": 2}
    with pytest.raises(ValueError, match="exceed"):
        parse_sub_run_descriptors(
            (first, second),
            parent_budget=TierBudget(2, 1, 30, 3),
            grounding_facts=(),
        )


def _facts() -> tuple[GroundingFact, ...]:
    return (
        GroundingFact("note-risk", "twin_question", "What could invalidate adoption?"),
        GroundingFact("note-cost", "twin_question", "What drives lifecycle cost?"),
        GroundingFact("node-rival", "graph_neighbor", "Incumbent alternative"),
        GroundingFact("node-policy", "graph_neighbor", "Policy constraint"),
    )
