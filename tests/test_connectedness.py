"""Tests for the connectedness profile composition.

Exercises the verdict priority (unknown > conflicting > well_integrated >
partially_integrated > isolated), the honesty rules, counts, validation, and
purity/immutability.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.cross_reference.connectedness import (
    ConnectednessError,
    ConnectednessInputs,
    ConnectednessProfile,
    build_connectedness_profile,
)


def _inputs(
    *,
    focus_id: str = "inv-focus",
    priors: int = 3,
    connections: int = 0,
    connected_via: int = 0,
    contradictions: int = 0,
    compatibles: int = 0,
    candidates: int = 0,
    q_links: int = 0,
    q_clusters: int = 0,
) -> ConnectednessInputs:
    return ConnectednessInputs(
        focus_investigation_id=focus_id,
        prior_investigation_count=priors,
        connection_count=connections,
        connected_via_connections=connected_via,
        contradiction_count=contradictions,
        compatible_count=compatibles,
        resolution_candidate_count=candidates,
        question_link_count=q_links,
        question_cluster_count=q_clusters,
    )


# --- verdict: unknown (no priors) ------------------------------------------


def test_no_priors_is_unknown() -> None:
    report = build_connectedness_profile(_inputs(priors=0, connections=5))
    assert report.verdict == "unknown"
    assert any("not measurable" in n for n in report.notes)


def test_no_priors_unknown_even_with_edges() -> None:
    # Edges without priors is a data error, but the verdict is still unknown
    # (never fabricated as isolated or integrated)
    report = build_connectedness_profile(
        _inputs(priors=0, connections=5, contradictions=2)
    )
    assert report.verdict == "unknown"


# --- verdict: conflicting (contradiction priority) -------------------------


def test_contradiction_is_conflicting() -> None:
    report = build_connectedness_profile(_inputs(priors=3, contradictions=1))
    assert report.verdict == "conflicting"


def test_conflicting_takes_priority_over_integration() -> None:
    # Well-integrated (2 priors, connections) BUT has a contradiction -> conflicting
    report = build_connectedness_profile(
        _inputs(priors=3, connections=5, connected_via=2, contradictions=1, compatibles=4)
    )
    assert report.verdict == "conflicting"
    assert any("priority" in n for n in report.notes)


def test_conflicting_count_carried_through() -> None:
    report = build_connectedness_profile(_inputs(priors=3, contradictions=3))
    assert report.contradiction_count == 3


# --- verdict: well_integrated ----------------------------------------------


def test_well_integrated() -> None:
    report = build_connectedness_profile(
        _inputs(priors=3, connections=4, connected_via=2)
    )
    assert report.verdict == "well_integrated"


def test_well_integrated_boundary_floor() -> None:
    # default floor = 2; exactly 2 connected priors with connections -> integrated
    report = build_connectedness_profile(
        _inputs(priors=5, connections=3, connected_via=2)
    )
    assert report.verdict == "well_integrated"


def test_custom_integration_floor() -> None:
    # 2 connected priors; default floor 2 = integrated; floor 3 = partial
    inp = _inputs(priors=5, connections=3, connected_via=2)
    assert build_connectedness_profile(inp).verdict == "well_integrated"
    assert (
        build_connectedness_profile(inp, integration_prior_floor=3).verdict
        == "partially_integrated"
    )


# --- verdict: partially_integrated -----------------------------------------


def test_partial_integration_one_prior() -> None:
    # 1 connected prior (< floor 2) but has edges -> partial
    report = build_connectedness_profile(
        _inputs(priors=5, connections=2, connected_via=1)
    )
    assert report.verdict == "partially_integrated"


def test_partial_via_resolution_candidates_only() -> None:
    # No insight connections, but resolution candidates -> edges > 0 -> partial
    report = build_connectedness_profile(
        _inputs(priors=3, candidates=2)
    )
    assert report.verdict == "partially_integrated"


def test_partial_via_question_links_only() -> None:
    report = build_connectedness_profile(_inputs(priors=3, q_links=1, q_clusters=1))
    assert report.verdict == "partially_integrated"


# --- verdict: isolated -----------------------------------------------------


def test_isolated_zero_edges_with_priors() -> None:
    report = build_connectedness_profile(_inputs(priors=5))
    assert report.verdict == "isolated"
    assert any("island" in n for n in report.notes)


def test_isolated_not_fabricated_without_priors() -> None:
    # No priors + no edges = unknown, NOT isolated (the honesty keystone)
    report = build_connectedness_profile(_inputs(priors=0))
    assert report.verdict == "unknown"


# --- total_edges + counts --------------------------------------------------


def test_total_edges_sums_all_edge_types() -> None:
    report = build_connectedness_profile(
        _inputs(
            priors=5,
            connections=3,
            contradictions=0,  # avoid conflicting
            compatibles=2,
            candidates=1,
            q_links=2,
        )
    )
    assert report.total_edges == 3 + 0 + 2 + 1 + 2  # 8


def test_all_counts_carried_through() -> None:
    report = build_connectedness_profile(
        _inputs(
            priors=5,
            connections=3,
            connected_via=2,
            contradictions=0,
            compatibles=2,
            candidates=1,
            q_links=2,
            q_clusters=1,
        )
    )
    assert report.connection_count == 3
    assert report.compatible_count == 2
    assert report.resolution_candidate_count == 1
    assert report.question_link_count == 2
    assert report.question_cluster_count == 1
    assert report.prior_investigation_count == 5


def test_connected_prior_count_capped_at_total() -> None:
    # connected_via=10 but only 3 priors -> capped at 3
    report = build_connectedness_profile(
        _inputs(priors=3, connections=5, connected_via=10)
    )
    assert report.connected_prior_count == 3


# --- provenance / purity ---------------------------------------------------


def test_focus_id_carried_through() -> None:
    report = build_connectedness_profile(_inputs(focus_id="inv-777", priors=2))
    assert report.focus_investigation_id == "inv-777"


def test_authority_is_always_advisory() -> None:
    assert build_connectedness_profile(_inputs(priors=2)).authority == "advisory"


def test_report_is_immutable() -> None:
    report = build_connectedness_profile(_inputs(priors=2))
    assert isinstance(report, ConnectednessProfile)
    assert dataclasses.is_dataclass(report)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.verdict = "isolated"  # type: ignore[misc]


def test_inputs_is_immutable() -> None:
    inp = _inputs(priors=2)
    assert isinstance(inp, ConnectednessInputs)
    with pytest.raises(dataclasses.FrozenInstanceError):
        inp.connection_count = 5  # type: ignore[misc]


def test_determinism_same_inputs_same_report() -> None:
    inp = _inputs(priors=3, connections=2, connected_via=2)
    assert build_connectedness_profile(inp) == build_connectedness_profile(inp)


def test_notes_describe_verdict() -> None:
    report = build_connectedness_profile(_inputs(priors=5))
    joined = " | ".join(report.notes).lower()
    assert "topological" in joined
    assert "island" in joined


# --- validation ------------------------------------------------------------


@pytest.mark.parametrize("bad", [0, -1, -5])
def test_validation_rejects_bad_integration_floor(bad: int) -> None:
    with pytest.raises(ConnectednessError, match="integration_prior_floor"):
        build_connectedness_profile(_inputs(priors=2), integration_prior_floor=bad)


def test_validation_partial_floor_must_be_below_integration() -> None:
    with pytest.raises(ConnectednessError, match="partial_prior_floor"):
        build_connectedness_profile(
            _inputs(priors=2), integration_prior_floor=2, partial_prior_floor=2
        )


# --- public api exports ----------------------------------------------------


def test_public_api_exports() -> None:
    from substrate.cross_reference import connectedness as mod

    assert set(mod.__all__) == {
        "ConnectednessError",
        "ConnectednessInputs",
        "ConnectednessProfile",
        "build_connectedness_profile",
    }
    assert issubclass(mod.ConnectednessError, ValueError)
    assert dataclasses.is_dataclass(mod.ConnectednessInputs)
    assert dataclasses.is_dataclass(mod.ConnectednessProfile)
