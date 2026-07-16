from __future__ import annotations

# ruff: noqa: F811 - pytest fixture is intentionally imported.
import json
import os
import shutil

import pytest
from test_canonical_aggregate_projection import completed_parent  # noqa: F401
from test_canonical_twin_promotion_writer import _accepted

from substrate.twin_recursion import (
    HistoricalCanonicalTwinNodeWithheld,
    materialize_accepted_twin_promotion,
    read_current_canonical_twin_node,
)


def _materialized(completed_parent, *, kind: str = "insight"):
    twins, graph, promotions, candidate = _accepted(completed_parent, kind=kind)
    result = materialize_accepted_twin_promotion(
        graph,
        promotions,
        twins,
        owner_id="acct",
        candidate_id=candidate.candidate_id,
    )
    return twins, graph, promotions, candidate, result


@pytest.mark.parametrize("kind", ["insight", "question"])
def test_exact_current_node_is_owner_only_and_read_does_not_mutate(completed_parent, kind) -> None:
    twins, graph, promotions, candidate, result = _materialized(completed_parent, kind=kind)
    try:
        before = (
            graph.execute("SELECT * FROM nodes ORDER BY node_id").fetchall(),
            graph.execute("SELECT * FROM edges ORDER BY edge_id").fetchall(),
        )
        view = read_current_canonical_twin_node(
            graph,
            promotions,
            twins,
            owner_id="acct",
            candidate_id=candidate.candidate_id,
        )
        assert view.status == "current"
        assert view.node_id == result.node_id
        assert view.candidate_id == candidate.candidate_id
        assert view.review_id == result.review_id
        assert view.kind == kind
        assert view.text == candidate.text
        assert view.owner_id == "acct"
        assert (
            graph.execute("SELECT * FROM nodes ORDER BY node_id").fetchall(),
            graph.execute("SELECT * FROM edges ORDER BY edge_id").fetchall(),
        ) == before
    finally:
        graph.close()


def test_absent_and_foreign_owner_are_indistinguishable(completed_parent) -> None:
    twins, graph, promotions, candidate, _ = _materialized(completed_parent)
    try:
        absent = read_current_canonical_twin_node(
            graph, promotions, twins, owner_id="acct", candidate_id="absent"
        )
        foreign = read_current_canonical_twin_node(
            graph,
            promotions,
            twins,
            owner_id="other-owner",
            candidate_id=candidate.candidate_id,
        )
        assert absent == foreign == HistoricalCanonicalTwinNodeWithheld()
        assert vars(absent) == {"status": "historical_withheld", "authority": "unavailable"}
    finally:
        graph.close()


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("canonical_label", "changed"),
        ("node_type", "question"),
        ("embedding", [0.1]),
        ("graph_scope", "constraint"),
        ("owner_user_id", "other-owner"),
    ],
)
def test_conflicting_graph_projection_is_uniformly_withheld(
    completed_parent, column, value
) -> None:
    twins, graph, promotions, candidate, result = _materialized(completed_parent)
    try:
        graph.execute(f"UPDATE nodes SET {column}=? WHERE node_id=?", [value, result.node_id])
        view = read_current_canonical_twin_node(
            graph,
            promotions,
            twins,
            owner_id="acct",
            candidate_id=candidate.candidate_id,
        )
        assert view == HistoricalCanonicalTwinNodeWithheld()
    finally:
        graph.close()


@pytest.mark.parametrize("metadata", ["not-json", "{}"])
def test_malformed_or_incomplete_metadata_is_withheld(completed_parent, metadata) -> None:
    twins, graph, promotions, candidate, result = _materialized(completed_parent)
    try:
        graph.execute("UPDATE nodes SET metadata=? WHERE node_id=?", [metadata, result.node_id])
        assert (
            read_current_canonical_twin_node(
                graph,
                promotions,
                twins,
                owner_id="acct",
                candidate_id=candidate.candidate_id,
            )
            == HistoricalCanonicalTwinNodeWithheld()
        )
    finally:
        graph.close()


def test_metadata_addition_is_not_silently_accepted(completed_parent) -> None:
    twins, graph, promotions, candidate, result = _materialized(completed_parent)
    try:
        metadata = json.loads(
            graph.execute(
                "SELECT metadata FROM nodes WHERE node_id=?", [result.node_id]
            ).fetchone()[0]
        )
        metadata["unreviewed"] = True
        graph.execute(
            "UPDATE nodes SET metadata=? WHERE node_id=?", [json.dumps(metadata), result.node_id]
        )
        assert (
            read_current_canonical_twin_node(
                graph, promotions, twins, owner_id="acct", candidate_id=candidate.candidate_id
            )
            == HistoricalCanonicalTwinNodeWithheld()
        )
    finally:
        graph.close()


def test_later_takedown_withholds_without_deleting_history(completed_parent) -> None:
    twins, graph, promotions, candidate, result = _materialized(completed_parent)
    try:
        row_before = graph.execute(
            "SELECT * FROM nodes WHERE node_id=?", [result.node_id]
        ).fetchone()
        graph.execute(
            "INSERT INTO book_assets(document_id,taken_down) VALUES (?,TRUE)", ["evidence-document"]
        )
        assert (
            read_current_canonical_twin_node(
                graph, promotions, twins, owner_id="acct", candidate_id=candidate.candidate_id
            )
            == HistoricalCanonicalTwinNodeWithheld()
        )
        assert (
            graph.execute("SELECT * FROM nodes WHERE node_id=?", [result.node_id]).fetchone()
            == row_before
        )
    finally:
        graph.close()


def test_later_evidence_drift_withholds_historical_node(completed_parent) -> None:
    twins, graph, promotions, candidate, result = _materialized(completed_parent)
    try:
        graph.execute("UPDATE chunks SET text='changed' WHERE chunk_id='evidence-chunk'")
        assert (
            read_current_canonical_twin_node(
                graph, promotions, twins, owner_id="acct", candidate_id=candidate.candidate_id
            )
            == HistoricalCanonicalTwinNodeWithheld()
        )
        assert graph.execute(
            "SELECT count(*) FROM nodes WHERE node_id=?", [result.node_id]
        ).fetchone() == (1,)
    finally:
        graph.close()


def test_promotion_authority_path_replacement_is_withheld(
    completed_parent, monkeypatch, tmp_path
) -> None:
    twins, graph, promotions, candidate, _ = _materialized(completed_parent)
    replacement = tmp_path / "replacement.sqlite3"
    shutil.copy2(promotions.path, replacement)
    original = promotions.require_snapshot_current

    def replace_before_final_check(snapshot):  # type: ignore[no-untyped-def]
        os.replace(replacement, promotions.path)
        original(snapshot)

    monkeypatch.setattr(promotions, "require_snapshot_current", replace_before_final_check)
    try:
        assert (
            read_current_canonical_twin_node(
                graph, promotions, twins, owner_id="acct", candidate_id=candidate.candidate_id
            )
            == HistoricalCanonicalTwinNodeWithheld()
        )
        assert graph.execute("SELECT count(*) FROM nodes").fetchone() == (1,)
    finally:
        graph.close()


def test_exact_dependency_types_and_inputs_are_required(completed_parent) -> None:
    twins, graph, promotions, candidate, _ = _materialized(completed_parent)
    try:
        with pytest.raises(TypeError, match="locked graph connection"):
            read_current_canonical_twin_node(  # type: ignore[arg-type]
                object(), promotions, twins, owner_id="acct", candidate_id=candidate.candidate_id
            )
        with pytest.raises(ValueError, match="owner_id"):
            read_current_canonical_twin_node(
                graph, promotions, twins, owner_id="", candidate_id=candidate.candidate_id
            )
    finally:
        graph.close()
