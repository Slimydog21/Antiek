from __future__ import annotations

# ruff: noqa: F811 - imported fixture names are intentionally injected by pytest.
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from test_canonical_aggregate_projection import completed_parent  # noqa: F401

from runtime.db_lock import connect_write
from substrate.graph.ops import insert_document
from substrate.graph.schema import init_database
from substrate.graph.search import search
from substrate.twin_recursion import (
    CanonicalTwinPublicationError,
    SourceRevision,
    TwinRecursionLedger,
    TwinSourceEnvelope,
    project_twin_sources,
    publish_canonical_twin,
)
from substrate.twin_recursion.segmentation_ledger import TwinSegmentationLedger


def _ready_parent(completed_parent):
    asset, manifest, registry, completions, _, _, _, tmp_path = completed_parent
    ledger = TwinRecursionLedger(tmp_path / "canonical-twins.sqlite3")
    snapshot = ledger.apply_paid_aggregate(
        SourceRevision("acct", asset),
        manifest=manifest,
        completions=completions,
        registry=registry,
    )
    return ledger, snapshot, tmp_path


def _graph(path):
    con = connect_write(str(path), purpose="test_canonical_twin_publication")
    init_database(con)
    return con


class _Embedding:
    dimension = 3

    def encode(self, text: str) -> list[float]:
        return [0.4, 0.5, 0.6]


def test_publication_is_one_html_document_one_advisory_chunk_and_no_claims(
    completed_parent,
) -> None:
    ledger, snapshot, tmp_path = _ready_parent(completed_parent)
    graph = _graph(tmp_path / "graph.duckdb")
    try:
        first = publish_canonical_twin(graph, ledger, binding_id=snapshot.binding_id)
        replay = publish_canonical_twin(graph, ledger, binding_id=snapshot.binding_id)
        assert first == replay
        document = graph.execute(
            "SELECT document_id,raw_text,metadata,content_class,owner_user_id,"
            "twin_source_envelope FROM documents WHERE document_id=?",
            [first.document_id],
        ).fetchone()
        chunk = graph.execute(
            "SELECT document_id,text,embedding FROM chunks WHERE chunk_id=?",
            [first.chunk_id],
        ).fetchone()
        assert document[1].startswith("<!doctype html>")
        assert document[3:5] == ("personal_reading", "acct")
        metadata = json.loads(document[2])
        assert metadata["binding_id"] == snapshot.binding_id
        assert metadata["authority"] == "advisory_twin_v1"
        envelope = TwinSourceEnvelope.from_json(document[5])
        assert envelope.status == "requires_binding"
        assert envelope.reason == "canonical_twin_is_derived"
        assert chunk[0] == first.document_id and "Insight parent" in chunk[1]
        assert chunk[2] is None
        assert graph.execute("SELECT count(*) FROM nodes").fetchone() == (0,)
        assert graph.execute("SELECT count(*) FROM edges").fetchone() == (0,)
        coverage = project_twin_sources(
            graph,
            ledger,
            TwinSegmentationLedger(tmp_path / "coverage-segments.sqlite3"),
            account_id="acct",
        )
        assert coverage.requires_binding == 0 and coverage.verdict == "unknown"
        graph.execute(
            "UPDATE chunks SET embedding=? WHERE chunk_id=?",
            [[0.4, 0.5, 0.6], first.chunk_id],
        )
        public = search(
            graph, "parent insight", model=_Embedding(), policy_tag="attribution_eligible"
        )
        owner = search(
            graph,
            "parent insight",
            model=_Embedding(),
            policy_tag="private_research",
            owner_user_id="acct",
        )
        assert public["results"] == []
        assert [row["document_id"] for row in owner["results"]] == [first.document_id]
        assert publish_canonical_twin(graph, ledger, binding_id=snapshot.binding_id) == first
    finally:
        graph.close()


def test_failure_after_document_insert_rolls_back_document_and_chunk(
    completed_parent,
) -> None:
    ledger, snapshot, tmp_path = _ready_parent(completed_parent)
    graph = _graph(tmp_path / "crash-graph.duckdb")

    def crash(checkpoint: str) -> None:
        if checkpoint == "after_document_insert":
            raise RuntimeError("injected publication crash")

    try:
        with pytest.raises(RuntimeError, match="injected publication crash"):
            publish_canonical_twin(
                graph,
                ledger,
                binding_id=snapshot.binding_id,
                failure_injector=crash,
            )
        assert graph.execute("SELECT count(*) FROM documents").fetchone() == (0,)
        assert graph.execute("SELECT count(*) FROM chunks").fetchone() == (0,)
        recovered = publish_canonical_twin(graph, ledger, binding_id=snapshot.binding_id)
        assert recovered.document_id == snapshot.twin_id
    finally:
        graph.close()


def test_exact_replay_rejects_graph_row_substitution(completed_parent) -> None:
    ledger, snapshot, tmp_path = _ready_parent(completed_parent)
    graph = _graph(tmp_path / "substituted-graph.duckdb")
    try:
        result = publish_canonical_twin(graph, ledger, binding_id=snapshot.binding_id)
        graph.execute(
            "UPDATE documents SET metadata=? WHERE document_id=?",
            [json.dumps({"forged": True}), result.document_id],
        )
        with pytest.raises(CanonicalTwinPublicationError, match="substitution"):
            publish_canonical_twin(graph, ledger, binding_id=snapshot.binding_id)
    finally:
        graph.close()


def test_exact_replay_rejects_extra_advisory_chunk(completed_parent) -> None:
    ledger, snapshot, tmp_path = _ready_parent(completed_parent)
    graph = _graph(tmp_path / "extra-chunk-graph.duckdb")
    try:
        result = publish_canonical_twin(graph, ledger, binding_id=snapshot.binding_id)
        graph.execute(
            "INSERT INTO chunks(chunk_id,document_id,chunk_index,text,token_count) "
            "VALUES ('forged-extra',?,1,'forged advisory claim',0)",
            [result.document_id],
        )
        coverage = project_twin_sources(
            graph,
            ledger,
            TwinSegmentationLedger(tmp_path / "extra-chunk-segments.sqlite3"),
            account_id="acct",
        )
        assert coverage.requires_binding == 1 and coverage.verdict == "partial"
        with pytest.raises(CanonicalTwinPublicationError, match="unexpected retrieval"):
            publish_canonical_twin(graph, ledger, binding_id=snapshot.binding_id)
    finally:
        graph.close()


def test_concurrent_locked_publishers_converge(completed_parent) -> None:
    ledger, snapshot, tmp_path = _ready_parent(completed_parent)
    path = tmp_path / "concurrent-graph.duckdb"
    initialized = _graph(path)
    initialized.close()

    def publish(_unused: int):
        con = connect_write(str(path), purpose="concurrent_twin_publication")
        try:
            return publish_canonical_twin(con, ledger, binding_id=snapshot.binding_id)
        finally:
            con.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.map(publish, range(2))
    assert first == second
    con = connect_write(str(path), purpose="verify_concurrent_twin_publication")
    try:
        assert con.execute("SELECT count(*) FROM documents").fetchone() == (1,)
        assert con.execute("SELECT count(*) FROM chunks").fetchone() == (1,)
    finally:
        con.close()


def test_forged_canonical_twin_label_remains_unresolved(completed_parent) -> None:
    _, _, tmp_path = _ready_parent(completed_parent)
    graph = _graph(tmp_path / "forged-label-graph.duckdb")
    try:
        insert_document(
            graph,
            document_id="forged-canonical-twin",
            source_tier=5,
            document_type="canonical_twin",
            title="Forged twin",
            raw_text="<html><body>Caller supplied advisory content.</body></html>",
            metadata={"binding_id": "forged"},
            content_class="personal_reading",
            owner_user_id="acct",
        )
        report = project_twin_sources(
            graph,
            TwinRecursionLedger(tmp_path / "forged-label-twins.sqlite3"),
            TwinSegmentationLedger(tmp_path / "forged-label-segments.sqlite3"),
            account_id="acct",
        )
        assert report.requires_binding == 1 and report.verdict == "partial"
    finally:
        graph.close()
