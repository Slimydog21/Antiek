"""Tests for the twin-internal-coherence axis (ask #4).

Measures the INTERNAL structural coherence of a twin's insights — do they connect
into a subject graph (coherent), form isolated islands (fragmented), or something
in between. Distinct from the 4 external-grounding twin axes. Exercises all
verdicts, union-find connectivity, component counting, the coherent-vs-unknown
distinction, all-glue exclusion, min_overlap, validation, purity/immutability.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.twin_internal_coherence import (
    TwinInsightText,
    measure_twin_internal_coherence,
)


def ins(rows: list[tuple[str, str | None]]) -> list[TwinInsightText]:
    return [TwinInsightText(insight_id=i, text=t) for i, t in rows]


# --- unknown --------------------------------------------------------------


def test_unknown_when_no_insights() -> None:
    r = measure_twin_internal_coherence([])
    assert r.verdict == "unknown"
    assert r.insight_count == 0
    assert r.connected_component_count is None
    assert r.coherence_ratio is None
    assert r.max_component_size is None
    assert r.authority == "advisory"


def test_unknown_when_single_insight() -> None:
    r = measure_twin_internal_coherence(ins([("i1", "alpha beta")]))
    assert r.verdict == "unknown"
    assert r.insight_count == 1
    assert r.connected_component_count is None


def test_unknown_when_all_glue_excluded() -> None:
    # All insights are only stop-words -> excluded -> fewer than 2 measurable.
    r = measure_twin_internal_coherence(
        ins([("i1", "the and of"), ("i2", "is was been")])
    )
    assert r.verdict == "unknown"
    assert r.insight_count == 0
    assert r.unmeasurable_count == 2


# --- coherent -------------------------------------------------------------


def test_coherent_two_insights_shared_subject() -> None:
    r = measure_twin_internal_coherence(
        ins([("i1", "alpha beta"), ("i2", "beta gamma")])
    )
    assert r.verdict == "coherent"
    assert r.connected_component_count == 1
    assert r.edge_count == 1
    assert r.max_component_size == 2
    assert len(r.connected_pairs) == 1
    assert r.connected_pairs[0].shared_terms == ("beta",)


def test_coherent_chain_all_connected() -> None:
    # i1-i2 share beta, i2-i3 share gamma -> one connected component of 3.
    r = measure_twin_internal_coherence(
        ins([("i1", "alpha beta"), ("i2", "beta gamma"), ("i3", "gamma delta")])
    )
    assert r.verdict == "coherent"
    assert r.connected_component_count == 1
    assert r.max_component_size == 3
    assert r.edge_count == 2  # i1-i2, i2-i3 (i1-i3 share nothing)


def test_coherent_star_topology() -> None:
    # i1 shares with i2, i3, i4 (hub) -> one component of 4.
    r = measure_twin_internal_coherence(
        ins(
            [
                ("i1", "alpha beta"),
                ("i2", "alpha gamma"),
                ("i3", "alpha delta"),
                ("i4", "alpha echo"),
            ]
        )
    )
    assert r.verdict == "coherent"
    assert r.connected_component_count == 1
    assert r.max_component_size == 4


# --- fragmented -----------------------------------------------------------


def test_fragmented_all_islands() -> None:
    # No two insights share a term -> 3 components (islands).
    r = measure_twin_internal_coherence(
        ins([("i1", "alpha"), ("i2", "beta"), ("i3", "gamma")])
    )
    assert r.verdict == "fragmented"
    assert r.connected_component_count == 3
    assert r.edge_count == 0
    assert r.max_component_size == 1
    assert r.coherence_ratio == 0.0


def test_fragmented_distinct_from_unknown() -> None:
    # Fewer than 2 = unknown; 2+ with no connections = fragmented. Never collapsed.
    r_unknown = measure_twin_internal_coherence(ins([("i1", "alpha")]))
    r_fragmented = measure_twin_internal_coherence(
        ins([("i1", "alpha"), ("i2", "beta")])
    )
    assert r_unknown.verdict == "unknown"
    assert r_fragmented.verdict == "fragmented"


# --- partially_connected --------------------------------------------------


def test_partially_connected_two_islands() -> None:
    # i1-i2 connected (beta), i3-i4 connected (delta) -> 2 components of 2.
    r = measure_twin_internal_coherence(
        ins(
            [
                ("i1", "alpha beta"),
                ("i2", "beta gamma"),
                ("i3", "delta echo"),
                ("i4", "delta foxtrot"),
            ]
        )
    )
    assert r.verdict == "partially_connected"
    assert r.connected_component_count == 2
    assert r.max_component_size == 2
    assert r.edge_count == 2


def test_partially_connected_one_pair_two_singletons() -> None:
    # i1-i2 connected, i3, i4 isolated -> 3 components (one of 2, two of 1).
    r = measure_twin_internal_coherence(
        ins(
            [
                ("i1", "alpha beta"),
                ("i2", "alpha gamma"),
                ("i3", "delta"),
                ("i4", "echo"),
            ]
        )
    )
    assert r.verdict == "partially_connected"
    assert r.connected_component_count == 3
    assert r.max_component_size == 2


# --- coherence_ratio ------------------------------------------------------


def test_coherence_ratio_density() -> None:
    # 4 insights, 2 edges -> possible 6 -> ratio 2/6.
    r = measure_twin_internal_coherence(
        ins(
            [
                ("i1", "alpha beta"),
                ("i2", "beta gamma"),
                ("i3", "delta echo"),
                ("i4", "delta foxtrot"),
            ]
        )
    )
    assert r.coherence_ratio == pytest.approx(2 / 6)


def test_coherence_ratio_zero_when_fragmented() -> None:
    r = measure_twin_internal_coherence(
        ins([("i1", "alpha"), ("i2", "beta"), ("i3", "gamma")])
    )
    assert r.coherence_ratio == 0.0  # real measured 0.0


# --- min_overlap ----------------------------------------------------------


def test_min_overlap_gates_connections() -> None:
    # i1-i2 share 1 term (beta); min_overlap 2 -> not connected -> fragmented.
    r_default = measure_twin_internal_coherence(
        ins([("i1", "alpha beta"), ("i2", "beta gamma")])
    )
    assert r_default.verdict == "coherent"
    r_strict = measure_twin_internal_coherence(
        ins([("i1", "alpha beta"), ("i2", "beta gamma")]), min_overlap=2
    )
    assert r_strict.verdict == "fragmented"
    assert r_strict.min_overlap == 2


def test_min_overlap_two_allows_two_shared() -> None:
    # i1-i2 share 2 terms (beta gamma); min_overlap 2 -> connected.
    r = measure_twin_internal_coherence(
        ins([("i1", "alpha beta gamma"), ("i2", "beta gamma delta")]),
        min_overlap=2,
    )
    assert r.verdict == "coherent"


# --- all-glue exclusion ---------------------------------------------------


def test_all_glue_insights_excluded() -> None:
    # i2 is all stop-words -> excluded; only i1, i3 measurable, no overlap.
    r = measure_twin_internal_coherence(
        ins([("i1", "alpha"), ("i2", "the of and"), ("i3", "beta")])
    )
    assert r.unmeasurable_count == 1
    assert r.insight_count == 2
    assert r.verdict == "fragmented"


# --- shared_terms auditable -----------------------------------------------


def test_shared_terms_sorted_in_connected_pair() -> None:
    r = measure_twin_internal_coherence(
        ins([("i1", "zebra alpha"), ("i2", "zebra mango")])
    )
    assert r.edge_count == 1
    assert r.connected_pairs[0].shared_terms == ("zebra",)


# --- validation -----------------------------------------------------------


def test_invalid_min_overlap_raises() -> None:
    with pytest.raises(ValueError):
        measure_twin_internal_coherence([], min_overlap=0)
    with pytest.raises(ValueError):
        measure_twin_internal_coherence([], min_overlap=-1)


# --- purity / determinism / immutability ---------------------------------


def test_deterministic_same_inputs_same_report() -> None:
    insights = ins([("i1", "alpha beta"), ("i2", "beta gamma"), ("i3", "delta")])
    assert measure_twin_internal_coherence(insights) == \
        measure_twin_internal_coherence(insights)


def test_report_is_frozen_immutable() -> None:
    r = measure_twin_internal_coherence(ins([("i1", "alpha"), ("i2", "beta")]))
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.verdict = "coherent"  # type: ignore[misc]


def test_none_text_treated_as_glue() -> None:
    # None text -> no distinctive terms -> excluded as unmeasurable.
    r = measure_twin_internal_coherence(
        ins([("i1", "alpha"), ("i2", None), ("i3", "beta")])
    )
    assert r.unmeasurable_count == 1
    assert r.insight_count == 2


def test_notes_carry_context() -> None:
    r = measure_twin_internal_coherence(
        ins([("i1", "alpha beta"), ("i2", "beta gamma")])
    )
    assert any("component" in note for note in r.notes)
