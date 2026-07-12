from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from runtime.db_lock import connect_read, connect_write
from substrate.engagement_spine import project_to_html
from substrate.engagement_spine.store import InMemoryEngagementStore
from substrate.graph import ensure_initialized
from substrate.graph.ops import insert_chunk, insert_document
from substrate.midnight_oil.durable_job import DurableJobStore
from substrate.midnight_oil.graph_projection import (
    GraphProjectionNotReady,
    project_terminal_job_to_graph,
)
from substrate.midnight_oil.job import (
    InMemoryJobStore,
    MidnightOilStepEvidence,
    create_job,
    get_job,
    put_job_state,
)
from substrate.midnight_oil.job_store import (
    OperationState,
    OwnerJob,
)
from substrate.midnight_oil.job_store import (
    TestOnlyInMemoryOwnerJobStore as MemoryOwnerJobStore,
)

_DOC_MODEL = {
    "type": "doc",
    "content": [
        {
            "type": "paragraph",
            "content": [{"type": "text", "text": "exact artifact"}],
        }
    ],
}
_DOC_HTML_HASH = hashlib.sha256(
    project_to_html(_DOC_MODEL, document_id="doc-html", creator="midnight_oil").encode()
).hexdigest()


def _terminal_job(
    store: DurableJobStore,
    *,
    goal: str = "What changed in the operator corpus?",
) -> str:
    job = create_job(
        [goal],
        30,
        store=store,
        job_id="moil_graph_test",
    )
    evidence = MidnightOilStepEvidence(
        step_key="op:test:0",
        spawn_id="spawn-test",
        output_text="The cited evidence supports a bounded conclusion.",
        insights=("A bounded conclusion is supported.",),
        questions=("What evidence would falsify it?",),
        route_receipt={"provider": "verified-fake", "model": "test"},
        source_receipts=(
            {
                "source_id": "chunk-source",
                "document_id": "doc-source",
                "source_url": "antiek://document/doc-source#chunk=chunk-source",
                "content_hash": hashlib.sha256(b"source excerpt").hexdigest(),
                "hash_scope": "retrieval_excerpt",
                "title": "Source",
            },
        ),
    )
    put_job_state(
        replace(
            job,
            status="complete",
            step_evidence=(evidence,),
            returned_step_keys=(evidence.step_key,),
            completed_step_keys=(evidence.step_key,),
            deposit_state="complete",
            deposit_document_id="doc-html",
            deposit_html_sha256=_DOC_HTML_HASH,
        ),
        store=store,
    )
    return job.job_id


def _projection_dependencies(
    job_id: str, *, owner: str = "operator"
) -> tuple[MemoryOwnerJobStore, InMemoryEngagementStore]:
    owner_jobs = MemoryOwnerJobStore()
    owner_jobs.put_job(
        OwnerJob(
            owner_user_id=owner,
            job_id=job_id,
            state_version=4,
            approved_ceiling_cents=100,
            consent_receipt_id="receipt",
            consent_config_hash="b" * 64,
            consent_issued_at_ms=1,
            consent_expires_at_ms=100,
            consent_claimed_at_ms=2,
            operation_id="operation",
            operation_state=OperationState.COMPLETE,
            dispatch_started_at_ms=3,
            dispatched_at_ms=4,
            completed_at_ms=5,
            payload={},
        )
    )
    engagement = InMemoryEngagementStore()
    engagement.put_document(
        "doc-html",
        {
            "document_id": "doc-html",
            "doc_model": _DOC_MODEL,
        },
    )
    return owner_jobs, engagement


def _seed_source(db: Path) -> None:
    ensure_initialized(str(db))
    with connect_write(str(db), purpose="test/seed-midnight-oil-source") as con:
        insert_document(
            con,
            document_id="doc-source",
            source_tier=1,
            document_type="paper",
            title="Source",
        )
        insert_chunk(
            con,
            document_id="doc-source",
            chunk_index=0,
            text="source excerpt",
            chunk_id="chunk-source",
        )


def _event_line_count(root: Path) -> int:
    return sum(
        len(path.read_text(encoding="utf-8").splitlines())
        for path in root.rglob("*")
        if path.is_file()
    )


def test_projection_requires_terminal_deposit_and_exact_evidence(tmp_path: Path) -> None:
    store = DurableJobStore(tmp_path / "jobs.sqlite3")
    job = create_job(["goal"], 10, store=store, job_id="moil_not_ready")
    db = tmp_path / "graph.duckdb"
    owner_jobs, engagement = _projection_dependencies(job.job_id)

    with pytest.raises(GraphProjectionNotReady, match="terminal"):
        project_terminal_job_to_graph(
            job.job_id,
            owner_user_id="operator",
            owner_jobs=owner_jobs,
            store=store,
            engagement_store=engagement,
            graph_db_path=db,
            events_dir=str(tmp_path / "events"),
        )
    if db.exists():
        with connect_read(str(db)) as con:
            assert con.execute("SELECT count(*) FROM deliverables").fetchone() == (0,)


def test_projection_is_queryable_attributed_and_idempotent(tmp_path: Path) -> None:
    store = DurableJobStore(tmp_path / "jobs.sqlite3")
    job_id = _terminal_job(store)
    db = tmp_path / "graph.duckdb"
    _seed_source(db)
    owner_jobs, engagement = _projection_dependencies(job_id, owner="operator-1")

    first = project_terminal_job_to_graph(
        job_id,
        owner_user_id="operator-1",
        owner_jobs=owner_jobs,
        store=store,
        engagement_store=engagement,
        graph_db_path=db,
        events_dir=str(tmp_path / "events"),
    )
    event_count = _event_line_count(tmp_path / "events")
    second = project_terminal_job_to_graph(
        job_id,
        owner_user_id="operator-1",
        owner_jobs=owner_jobs,
        store=store,
        engagement_store=engagement,
        graph_db_path=db,
        events_dir=str(tmp_path / "events"),
    )
    assert second.receipt == first.receipt
    assert _event_line_count(tmp_path / "events") == event_count
    assert first.receipt.owner_user_id == "operator-1"
    assert first.receipt.deep_links[0].startswith("antiek://deliverable/")

    with connect_read(str(db)) as con:
        assert con.execute(
            "SELECT owner_user_id FROM deliverables WHERE deliverable_id = ?",
            [first.receipt.deliverable_id],
        ).fetchone() == ("operator-1",)
        assert con.execute(
            "SELECT count(*) FROM deliverable_sections WHERE deliverable_id = ?",
            [first.receipt.deliverable_id],
        ).fetchone() == (1,)
        placeholders = ",".join("?" for _ in first.receipt.node_ids)
        assert con.execute(
            f"SELECT count(*) FROM nodes WHERE node_id IN ({placeholders})",
            list(first.receipt.node_ids),
        ).fetchone() == (3,)
        placeholders = ",".join("?" for _ in first.receipt.edge_ids)
        assert con.execute(
            f"SELECT count(*), min(source_document_id), min(chunk_id) FROM edges "
            f"WHERE edge_id IN ({placeholders})",
            list(first.receipt.edge_ids),
        ).fetchone() == (2, "doc-source", "chunk-source")

    restored = get_job(job_id, store=store)
    assert restored is not None
    assert restored.graph_projection_state == "complete"
    assert restored.graph_effect_receipt == first.receipt

    with pytest.raises(GraphProjectionNotReady, match="owner authority"):
        project_terminal_job_to_graph(
            job_id,
            owner_user_id="foreign-owner",
            owner_jobs=owner_jobs,
            store=store,
            engagement_store=engagement,
            graph_db_path=db,
            events_dir=str(tmp_path / "events"),
        )


def test_commit_before_checkpoint_replays_without_duplicate_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = DurableJobStore(tmp_path / "jobs.sqlite3")
    job_id = _terminal_job(store)
    db = tmp_path / "graph.duckdb"
    _seed_source(db)
    events = tmp_path / "events"
    owner_jobs, engagement = _projection_dependencies(job_id)

    import substrate.midnight_oil.graph_projection as projection

    original_put = projection.put_job_state
    calls = 0

    def crash_once(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("checkpoint crash")
        return original_put(*args, **kwargs)

    monkeypatch.setattr(projection, "put_job_state", crash_once)
    with pytest.raises(RuntimeError, match="checkpoint crash"):
        project_terminal_job_to_graph(
            job_id,
            owner_user_id="operator",
            owner_jobs=owner_jobs,
            store=store,
            engagement_store=engagement,
            graph_db_path=db,
            events_dir=str(events),
        )
    pending = get_job(job_id, store=store)
    assert pending is not None and pending.graph_projection_state == "pending"

    result = project_terminal_job_to_graph(
        job_id,
        owner_user_id="operator",
        owner_jobs=owner_jobs,
        store=store,
        engagement_store=engagement,
        graph_db_path=db,
        events_dir=str(events),
    )
    with connect_read(str(db)) as con:
        assert con.execute("SELECT count(*) FROM deliverables").fetchone() == (1,)
        assert con.execute("SELECT count(*) FROM deliverable_sections").fetchone() == (1,)
        assert con.execute("SELECT count(*) FROM nodes").fetchone() == (3,)
        assert con.execute("SELECT count(*) FROM edges").fetchone() == (2,)
    assert result.job.graph_projection_state == "complete"


def test_missing_source_row_is_recorded_without_fabricating_foreign_key(
    tmp_path: Path,
) -> None:
    store = DurableJobStore(tmp_path / "jobs.sqlite3")
    job_id = _terminal_job(store)
    db = tmp_path / "graph.duckdb"
    ensure_initialized(str(db))
    owner_jobs, engagement = _projection_dependencies(job_id)

    result = project_terminal_job_to_graph(
        job_id,
        owner_user_id="operator",
        owner_jobs=owner_jobs,
        store=store,
        engagement_store=engagement,
        graph_db_path=db,
        events_dir=str(tmp_path / "events"),
    )
    with connect_read(str(db)) as con:
        rows = con.execute(
            "SELECT source_document_id, chunk_id, metadata FROM edges ORDER BY edge_id"
        ).fetchall()
    assert len(rows) == len(result.receipt.edge_ids)
    assert all(row[0] is None and row[1] is None for row in rows)
    assert all(json.loads(row[2])["source_row_present"] is False for row in rows)


def test_old_durable_rows_default_to_pending_graph_projection(tmp_path: Path) -> None:
    store = DurableJobStore(tmp_path / "jobs.sqlite3")
    job = create_job(["legacy"], 5, store=store, job_id="legacy")
    row = store.get_job(job.job_id)
    assert row is not None
    row.pop("graph_projection_state", None)
    row.pop("graph_effect_receipt", None)
    store.put_job(row)
    restored = get_job(job.job_id, store=store)
    assert restored is not None
    assert restored.graph_projection_state == "pending"
    assert restored.graph_effect_receipt is None


def test_malformed_graph_receipt_is_sanitized_to_pending() -> None:
    from substrate.midnight_oil.job import _job_from_row, _job_to_row

    store = InMemoryJobStore()
    job = create_job(["legacy"], 5, store=store, job_id="malformed")
    row = _job_to_row(job)
    row["graph_projection_state"] = "complete"
    row["graph_effect_receipt"] = {
        "schema_version": "1",
        "owner_user_id": "operator",
        "deliverable_id": "dlv-not-hex",
        "section_ids": "sec-character-iteration",
        "node_ids": [],
        "edge_ids": [],
        "html_sha256": "z" * 64,
        "evidence_sha256": "0" * 64,
        "deep_links": ["https://hostile.invalid"],
    }
    restored = _job_from_row(row)
    assert restored.graph_projection_state == "pending"
    assert restored.graph_effect_receipt is None


def test_existing_conflicting_graph_row_prevents_false_receipt(tmp_path: Path) -> None:
    store = DurableJobStore(tmp_path / "jobs.sqlite3")
    job_id = _terminal_job(store)
    owner_jobs, engagement = _projection_dependencies(job_id)
    db = tmp_path / "graph.duckdb"
    ensure_initialized(str(db))
    from substrate.graph.ops import content_addressed_id

    deliverable_id = content_addressed_id("dlv", f"midnight-oil|{job_id}")
    with connect_write(str(db), purpose="test/conflicting-deliverable") as con:
        con.execute(
            "INSERT INTO deliverables "
            "(deliverable_id, title, deliverable_kind, investigation_root_id, "
            "owner_user_id, metadata) VALUES (?, 'wrong', 'research_memo', "
            "'wrong', 'foreign', '{}')",
            [deliverable_id],
        )
    with pytest.raises(RuntimeError, match="deliverable conflicts"):
        project_terminal_job_to_graph(
            job_id,
            owner_user_id="operator",
            owner_jobs=owner_jobs,
            store=store,
            engagement_store=engagement,
            graph_db_path=db,
            events_dir=str(tmp_path / "events"),
        )
    restored = get_job(job_id, store=store)
    assert restored is not None
    assert restored.graph_projection_state == "pending"


def test_goal_secret_never_enters_graph_or_typed_events(tmp_path: Path) -> None:
    # Deliberately credential-shaped content without impersonating a real
    # provider token prefix (keeps leak scanners meaningful and quiet).
    secret = "credential-marker-supersecret123456789"
    store = DurableJobStore(tmp_path / "jobs.sqlite3")
    job_id = _terminal_job(store, goal=f"Investigate {secret}")
    owner_jobs, engagement = _projection_dependencies(job_id)
    db = tmp_path / "graph.duckdb"
    events = tmp_path / "events"
    project_terminal_job_to_graph(
        job_id,
        owner_user_id="operator",
        owner_jobs=owner_jobs,
        store=store,
        engagement_store=engagement,
        graph_db_path=db,
        events_dir=str(events),
    )
    with connect_read(str(db)) as con:
        graph_text = " ".join(
            str(value)
            for row in con.execute(
                "SELECT title, metadata FROM deliverables UNION ALL "
                "SELECT canonical_label, metadata FROM nodes"
            ).fetchall()
            for value in row
        )
    event_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in events.rglob("*")
        if path.is_file()
    )
    assert secret not in graph_text
    assert secret not in event_text


def test_existing_chunk_with_wrong_hash_is_not_attributed(tmp_path: Path) -> None:
    store = DurableJobStore(tmp_path / "jobs.sqlite3")
    job_id = _terminal_job(store)
    owner_jobs, engagement = _projection_dependencies(job_id)
    db = tmp_path / "graph.duckdb"
    ensure_initialized(str(db))
    with connect_write(str(db), purpose="test/seed-wrong-source") as con:
        insert_document(
            con,
            document_id="doc-source",
            source_tier=1,
            document_type="paper",
        )
        insert_chunk(
            con,
            document_id="doc-source",
            chunk_index=0,
            text="different content",
            chunk_id="chunk-source",
        )
    project_terminal_job_to_graph(
        job_id,
        owner_user_id="operator",
        owner_jobs=owner_jobs,
        store=store,
        engagement_store=engagement,
        graph_db_path=db,
        events_dir=str(tmp_path / "events"),
    )
    with connect_read(str(db)) as con:
        rows = con.execute(
            "SELECT source_document_id, chunk_id, metadata FROM edges"
        ).fetchall()
    assert all(row[0] is None and row[1] is None for row in rows)
    assert all(json.loads(row[2])["source_row_present"] is False for row in rows)


@pytest.mark.parametrize(
    ("table", "column", "error"),
    [
        ("nodes", "metadata", "node conflicts"),
        ("edges", "relation", "edge conflicts"),
    ],
)
def test_completed_receipt_rechecks_hostile_node_and_edge_collisions(
    tmp_path: Path, table: str, column: str, error: str
) -> None:
    store = DurableJobStore(tmp_path / f"{table}-jobs.sqlite3")
    job_id = _terminal_job(store)
    owner_jobs, engagement = _projection_dependencies(job_id)
    db = tmp_path / f"{table}-graph.duckdb"
    result = project_terminal_job_to_graph(
        job_id,
        owner_user_id="operator",
        owner_jobs=owner_jobs,
        store=store,
        engagement_store=engagement,
        graph_db_path=db,
        events_dir=str(tmp_path / f"{table}-events"),
    )
    row_id = result.receipt.node_ids[0] if table == "nodes" else result.receipt.edge_ids[0]
    id_column = "node_id" if table == "nodes" else "edge_id"
    hostile = '{"hostile":true}' if column == "metadata" else "hostile_relation"
    with connect_write(str(db), purpose=f"test/hostile-{table}") as con:
        con.execute(
            f"UPDATE {table} SET {column} = ? WHERE {id_column} = ?",
            [hostile, row_id],
        )
    with pytest.raises(RuntimeError, match=error):
        project_terminal_job_to_graph(
            job_id,
            owner_user_id="operator",
            owner_jobs=owner_jobs,
            store=store,
            engagement_store=engagement,
            graph_db_path=db,
            events_dir=str(tmp_path / f"{table}-events"),
        )


@pytest.mark.parametrize(
    "receipt_patch",
    [
        {"hash_scope": "whole_document"},
        {"source_url": "antiek://document/other#chunk=chunk-source"},
    ],
)
def test_noncanonical_source_receipt_is_never_attributed(
    tmp_path: Path, receipt_patch: dict[str, str]
) -> None:
    store = DurableJobStore(tmp_path / "jobs.sqlite3")
    job_id = _terminal_job(store)
    job = get_job(job_id, store=store)
    assert job is not None
    evidence = job.step_evidence[0]
    receipt = {**evidence.source_receipts[0], **receipt_patch}
    put_job_state(
        replace(
            job,
            step_evidence=(replace(evidence, source_receipts=(receipt,)),),
        ),
        store=store,
    )
    owner_jobs, engagement = _projection_dependencies(job_id)
    db = tmp_path / "graph.duckdb"
    _seed_source(db)
    project_terminal_job_to_graph(
        job_id,
        owner_user_id="operator",
        owner_jobs=owner_jobs,
        store=store,
        engagement_store=engagement,
        graph_db_path=db,
        events_dir=str(tmp_path / "events"),
    )
    with connect_read(str(db)) as con:
        rows = con.execute("SELECT source_document_id, chunk_id FROM edges").fetchall()
    assert rows and all(row == (None, None) for row in rows)
