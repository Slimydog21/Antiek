from __future__ import annotations

# ruff: noqa: F811 - pytest fixture is intentionally imported.
from dataclasses import asdict

import pytest
from test_canonical_aggregate_projection import completed_parent  # noqa: F401
from test_canonical_twin_promotion_writer import _accepted

import substrate.twin_recursion.promotion_writer as promotion_writer
from substrate.graph import schema as graph_schema
from substrate.graph.schema import SCHEMA_TABLES, init_database_at_path
from substrate.twin_recursion import (
    CanonicalTwinPromotionWriterError,
    HistoricalCanonicalTwinNodeWithheld,
    materialize_accepted_twin_promotion,
    read_current_canonical_twin_node_citations,
)


def _materialized(completed_parent):
    twins, graph, promotions, candidate = _accepted(completed_parent)
    result = materialize_accepted_twin_promotion(
        graph,
        promotions,
        twins,
        owner_id="acct",
        candidate_id=candidate.candidate_id,
    )
    return twins, graph, promotions, candidate, result


def test_pre_v21_database_and_stale_memo_upgrade_exactly(tmp_path) -> None:
    path = str(tmp_path / "pre-v21.duckdb")
    init_database_at_path(path)
    graph_schema._INITIALIZED_PATHS.discard(path)
    graph_schema._INITIALIZED_PATH_EPOCHS.pop(path, None)
    con = graph_schema.duckdb.connect(path)
    try:
        con.execute("DROP TABLE canonical_twin_node_citations")
    finally:
        con.close()
    graph_schema._INITIALIZED_PATHS.add(path)
    graph_schema._INITIALIZED_PATH_EPOCHS[path] = 20

    assert graph_schema._schema_is_present(path) is False
    init_database_at_path(path)
    assert graph_schema._schema_is_present(path) is True
    init_database_at_path(path)
    con = graph_schema.duckdb.connect(path, read_only=True)
    try:
        assert graph_schema._v21_citation_shape_is_valid(con)
    finally:
        con.close()
    assert "canonical_twin_node_citations" in SCHEMA_TABLES


def test_materialization_writes_exact_ordered_hash_only_citations_and_replays(
    completed_parent,
) -> None:
    twins, graph, promotions, candidate, result = _materialized(completed_parent)
    try:
        replay = materialize_accepted_twin_promotion(
            graph,
            promotions,
            twins,
            owner_id="acct",
            candidate_id=candidate.candidate_id,
        )
        assert replay == result
        rows = graph.execute(
            "SELECT citation_kind,ordinal,document_id,chunk_id,range_start,range_end,"
            "text_sha256,chunk_sha256,document_sha256,source_envelope_sha256,content_class "
            "FROM canonical_twin_node_citations ORDER BY ordinal"
        ).fetchall()
        assert rows[0] == (
            "canonical_twin",
            0,
            candidate.twin_document_id,
            candidate.twin_chunk_id,
            None,
            None,
            candidate.twin_chunk_sha256,
            candidate.twin_chunk_sha256,
            None,
            None,
            None,
        )
        evidence = candidate.evidence[0]
        assert rows[1] == (
            "evidence",
            1,
            evidence.document_id,
            evidence.chunk_id,
            evidence.start,
            evidence.end,
            evidence.text_sha256,
            evidence.chunk_sha256,
            evidence.document_sha256,
            evidence.source_envelope_sha256,
            evidence.content_class,
        )
        assert graph.execute("SELECT count(*) FROM canonical_twin_node_citations").fetchone() == (
            2,
        )
        stored = " ".join(str(value) for row in rows for value in row)
        assert evidence.text not in stored
    finally:
        graph.close()


def test_current_reader_returns_exact_node_and_citations_without_mutation(
    completed_parent,
) -> None:
    twins, graph, promotions, candidate, result = _materialized(completed_parent)
    try:
        before = graph.execute(
            "SELECT * FROM canonical_twin_node_citations ORDER BY ordinal"
        ).fetchall()
        view = read_current_canonical_twin_node_citations(
            graph,
            promotions,
            twins,
            owner_id="acct",
            candidate_id=candidate.candidate_id,
        )
        assert view.status == "current"
        assert view.node.node_id == result.node_id
        assert [citation.ordinal for citation in view.citations] == [0, 1]
        assert [citation.citation_kind for citation in view.citations] == [
            "canonical_twin",
            "evidence",
        ]
        assert (
            graph.execute("SELECT * FROM canonical_twin_node_citations ORDER BY ordinal").fetchall()
            == before
        )
    finally:
        graph.close()


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("owner_id", "other-owner"),
        ("candidate_id", "other-candidate"),
        ("chunk_id", "other-chunk"),
        ("text_sha256", "0" * 64),
        ("range_end", 45),
    ],
)
def test_citation_substitution_is_uniformly_withheld(completed_parent, column, value) -> None:
    twins, graph, promotions, candidate, _ = _materialized(completed_parent)
    try:
        graph.execute(
            f"UPDATE canonical_twin_node_citations SET {column}=? WHERE ordinal=1",
            [value],
        )
        assert (
            read_current_canonical_twin_node_citations(
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


def test_absent_foreign_and_missing_projection_are_indistinguishable(completed_parent) -> None:
    twins, graph, promotions, candidate, _ = _materialized(completed_parent)
    try:
        absent = read_current_canonical_twin_node_citations(
            graph, promotions, twins, owner_id="acct", candidate_id="absent"
        )
        foreign = read_current_canonical_twin_node_citations(
            graph,
            promotions,
            twins,
            owner_id="foreign",
            candidate_id=candidate.candidate_id,
        )
        graph.execute("DELETE FROM canonical_twin_node_citations")
        missing = read_current_canonical_twin_node_citations(
            graph,
            promotions,
            twins,
            owner_id="acct",
            candidate_id=candidate.candidate_id,
        )
        assert absent == foreign == missing == HistoricalCanonicalTwinNodeWithheld()
    finally:
        graph.close()


def test_later_takedown_withholds_citations_but_retains_audit_rows(completed_parent) -> None:
    twins, graph, promotions, candidate, _ = _materialized(completed_parent)
    try:
        before = graph.execute(
            "SELECT * FROM canonical_twin_node_citations ORDER BY ordinal"
        ).fetchall()
        graph.execute(
            "INSERT INTO book_assets(document_id,taken_down) VALUES ('evidence-document',TRUE)"
        )
        assert (
            read_current_canonical_twin_node_citations(
                graph,
                promotions,
                twins,
                owner_id="acct",
                candidate_id=candidate.candidate_id,
            )
            == HistoricalCanonicalTwinNodeWithheld()
        )
        assert (
            graph.execute("SELECT * FROM canonical_twin_node_citations ORDER BY ordinal").fetchall()
            == before
        )
    finally:
        graph.close()


def test_late_citation_failure_rolls_back_node_and_projection(
    completed_parent, monkeypatch
) -> None:
    twins, graph, promotions, candidate = _accepted(completed_parent)
    original = promotion_writer._materialize_citations

    def fail_after_citations(con, authority):  # type: ignore[no-untyped-def]
        original(con, authority)
        raise RuntimeError("late citation failure")

    monkeypatch.setattr(promotion_writer, "_materialize_citations", fail_after_citations)
    try:
        with pytest.raises(RuntimeError, match="late citation failure"):
            materialize_accepted_twin_promotion(
                graph,
                promotions,
                twins,
                owner_id="acct",
                candidate_id=candidate.candidate_id,
            )
        assert graph.execute("SELECT count(*) FROM nodes").fetchone() == (0,)
        assert graph.execute("SELECT count(*) FROM canonical_twin_node_citations").fetchone() == (
            0,
        )
    finally:
        graph.close()


def test_conflicting_existing_citation_rolls_back_new_node(completed_parent) -> None:
    twins, graph, promotions, candidate = _accepted(completed_parent)
    with promotions.accepted_snapshot(
        graph, twins, owner_id="acct", candidate_id=candidate.candidate_id
    ) as snapshot:
        citation = promotion_writer.canonical_promotion_node_citations(snapshot.authority)[0]
    values = asdict(citation)
    values["chunk_id"] = "conflicting-chunk"
    graph.execute(
        f"INSERT INTO canonical_twin_node_citations ({promotion_writer._CITATION_COLUMNS}) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        list(values.values()),
    )
    try:
        with pytest.raises(
            CanonicalTwinPromotionWriterError, match="citation projection conflicts"
        ):
            materialize_accepted_twin_promotion(
                graph,
                promotions,
                twins,
                owner_id="acct",
                candidate_id=candidate.candidate_id,
            )
        assert graph.execute("SELECT count(*) FROM nodes").fetchone() == (0,)
        assert graph.execute("SELECT chunk_id FROM canonical_twin_node_citations").fetchone() == (
            "conflicting-chunk",
        )
    finally:
        graph.close()
