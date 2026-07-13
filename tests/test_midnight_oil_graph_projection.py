from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from threading import Event as ThreadEvent
from typing import Any

import pytest

from runtime.db_lock import WriteLockTimeout, connect_read, connect_write
from substrate.engagement_spine.store import InMemoryEngagementStore
from substrate.event_log import EventAppendBatch, append_event_once, prepare_typed_event
from substrate.graph import ensure_initialized
from substrate.graph.ops import content_addressed_id, insert_chunk, insert_document
from substrate.midnight_oil.contracts import (
    ResearchAcceptancePolicy,
    research_acceptance_policy_authority_fields,
)
from substrate.midnight_oil.durable_job import DurableJobStore
from substrate.midnight_oil.graph_projection import (
    GraphProjectionConflict,
    GraphProjectionNotReady,
    GraphProjectionPending,
    GraphProjectionRefused,
    project_terminal_job_to_graph,
)
from substrate.midnight_oil.job import (
    InMemoryJobStore,
    MidnightOilGraphEffectReceipt,
    MidnightOilStepEvidence,
    build_step_claim_evidence,
    create_job,
    get_job,
    put_job_state,
    source_receipt_id,
)
from substrate.midnight_oil.job_store import (
    OperationState,
    OwnerJob,
)
from substrate.midnight_oil.job_store import (
    TestOnlyInMemoryOwnerJobStore as MemoryOwnerJobStore,
)
from substrate.schemas.events import GraphNodeInsertedPayload


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
    receipt = {
        "source_id": "chunk-source",
        "document_id": "doc-source",
        "source_url": "antiek://document/doc-source#chunk=chunk-source",
        "content_hash": hashlib.sha256(b"source excerpt").hexdigest(),
        "hash_scope": "retrieval_excerpt",
        "title": "Source",
    }
    evidence = MidnightOilStepEvidence(
        step_key="op:test:0",
        spawn_id="spawn-test",
        output_text="The cited evidence supports a bounded conclusion.",
        insights=("A bounded conclusion is supported.",),
        questions=("What evidence would falsify it?",),
        route_receipt={"provider": "verified-fake", "model": "test"},
        source_receipts=(receipt,),
    )
    receipt_id = source_receipt_id(receipt)
    evidence = replace(
        evidence,
        claim_evidence_schema_version=1,
        claim_evidence=build_step_claim_evidence(
            job_id=job.job_id,
            step_key=evidence.step_key,
            output_text=evidence.output_text,
            insights=evidence.insights,
            questions=evidence.questions,
            source_receipts=evidence.source_receipts,
            supported_claims=(
                ("output_paragraph", 0, (receipt_id,)),
                ("insight", 0, (receipt_id,)),
            ),
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
            payload=research_acceptance_policy_authority_fields(ResearchAcceptancePolicy()),
        )
    )
    engagement = InMemoryEngagementStore()
    engagement.put_document(
        "doc-html",
        {
            "document_id": "doc-html",
            "doc_model": {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "exact artifact"}],
                    }
                ],
            },
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


def _expected_projection_ids(
    job_id: str,
    *,
    store: DurableJobStore,
    owner_jobs: MemoryOwnerJobStore,
    engagement: InMemoryEngagementStore,
) -> tuple[str, str]:
    import substrate.midnight_oil.graph_projection as projection

    job = get_job(job_id, store=store)
    authority = owner_jobs.get_job(owner_user_id="operator", job_id=job_id)
    assert job is not None and authority is not None and authority.operation_id is not None
    html_sha256 = projection._html_hash(projection._deposited_html(job, engagement))
    evidence_sha256 = hashlib.sha256(projection._canonical_evidence(job)).hexdigest()
    policy = ResearchAcceptancePolicy().model_dump(mode="json")
    source_sha256 = projection._projection_source_fingerprint(
        job,
        owner_user_id="operator",
        authority_operation_id=authority.operation_id,
        authority_state=authority.operation_state,
        acceptance_policy=policy,
        html_sha256=html_sha256,
        evidence_sha256=evidence_sha256,
    )
    return (
        content_addressed_id("dlv", f"midnight-oil|{job_id}|{source_sha256}"),
        content_addressed_id("node", f"midnight-oil-root|{job_id}|{source_sha256}"),
    )


@pytest.mark.parametrize("reverse", [False, True])
def test_receipt_census_uses_permanent_refusal_precedence(tmp_path: Path, reverse: bool) -> None:
    db = tmp_path / "graph.duckdb"
    _seed_source(db)
    receipts = [
        {
            "source_id": "chunk-source",
            "document_id": "doc-source",
            "content_hash": "0" * 64,
        },
        {
            "source_id": "chunk-missing",
            "document_id": "doc-missing",
            "content_hash": "1" * 64,
        },
    ]
    if reverse:
        receipts.reverse()
    import substrate.midnight_oil.graph_projection as projection

    with (
        connect_write(str(db), purpose="test/receipt-census") as con,
        pytest.raises(GraphProjectionRefused) as refusal,
    ):
        projection._validate_cited_receipts(con, tuple(receipts))
    assert refusal.value.reason == "receipt_malformed_or_forged"


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
        assert con.execute(
            "SELECT count(*) FROM nodes WHERE canonical_label = ?",
            ["What evidence would falsify it?"],
        ).fetchone() == (0,)

    restored = get_job(job_id, store=store)
    assert restored is not None
    assert restored.graph_projection_state == "complete"
    assert restored.graph_effect_receipt == first.receipt

    with pytest.raises(GraphProjectionConflict, match="durable effect receipt"):
        project_terminal_job_to_graph(
            job_id,
            owner_user_id="foreign-owner",
            owner_jobs=owner_jobs,
            store=store,
            engagement_store=engagement,
            graph_db_path=db,
            events_dir=str(tmp_path / "events"),
        )


def test_projection_classifies_malformed_durable_metadata_as_conflict(
    tmp_path: Path,
) -> None:
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
    )
    with connect_write(str(db), purpose="test/corrupt-graph-metadata") as con:
        con.execute(
            "UPDATE deliverables SET metadata = ? WHERE deliverable_id = ?",
            ["{not-json", first.receipt.deliverable_id],
        )

    with pytest.raises(GraphProjectionConflict, match="durable effect receipt"):
        project_terminal_job_to_graph(
            job_id,
            owner_user_id="operator-1",
            owner_jobs=owner_jobs,
            store=store,
            engagement_store=engagement,
            graph_db_path=db,
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

    original_compare = store.compare_and_put_graph
    calls = 0

    def crash_once(*args: Any, **kwargs: Any) -> bool:
        nonlocal calls
        calls += 1
        if calls == 2:
            assert original_compare(*args, **kwargs) is True
            raise RuntimeError("checkpoint crash")
        return original_compare(*args, **kwargs)

    monkeypatch.setattr(store, "compare_and_put_graph", crash_once)
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
    completed = get_job(job_id, store=store)
    assert completed is not None and completed.graph_projection_state == "complete"
    assert completed.graph_effect_receipt is not None
    assert completed.graph_projection_source_sha256 is not None
    assert _event_line_count(events) == 5
    with connect_read(str(db)) as con:
        assert con.execute("SELECT count(*) FROM deliverables").fetchone() == (1,)

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


def test_event_append_before_graph_commit_failure_replays_cleanly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = DurableJobStore(tmp_path / "jobs.sqlite3")
    job_id = _terminal_job(store)
    db = tmp_path / "graph.duckdb"
    events = tmp_path / "events"
    _seed_source(db)
    owner_jobs, engagement = _projection_dependencies(job_id)
    import substrate.midnight_oil.graph_projection as projection

    real_connect_write = projection.connect_write

    class CommitCrashConnection:
        def __init__(self, connection: Any) -> None:
            self.connection = connection

        def __getattr__(self, name: str) -> Any:
            return getattr(self.connection, name)

        def execute(self, query: str, *args: Any, **kwargs: Any) -> Any:
            if query == "COMMIT":
                raise OSError("graph commit unavailable")
            return self.connection.execute(query, *args, **kwargs)

    @contextmanager
    def connect_with_commit_crash(*args: Any, **kwargs: Any):  # type: ignore[no-untyped-def]
        with real_connect_write(*args, **kwargs) as con:
            yield CommitCrashConnection(con)

    monkeypatch.setattr(projection, "connect_write", connect_with_commit_crash)
    with pytest.raises(OSError, match="graph commit unavailable"):
        project_terminal_job_to_graph(
            job_id,
            owner_user_id="operator",
            owner_jobs=owner_jobs,
            store=store,
            engagement_store=engagement,
            graph_db_path=db,
            events_dir=str(events),
        )
    assert _event_line_count(events) == 5
    with connect_read(str(db)) as con:
        assert con.execute("SELECT count(*) FROM deliverables").fetchone() == (0,)

    monkeypatch.setattr(projection, "connect_write", real_connect_write)
    result = project_terminal_job_to_graph(
        job_id,
        owner_user_id="operator",
        owner_jobs=owner_jobs,
        store=store,
        engagement_store=engagement,
        graph_db_path=db,
        events_dir=str(events),
    )
    assert result.job.graph_projection_state == "complete"
    assert _event_line_count(events) == 5


def test_deposit_writer_is_blocked_through_event_commit_and_receipt_cas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = DurableJobStore(tmp_path / "jobs.sqlite3")
    job_id = _terminal_job(store)
    db = tmp_path / "graph.duckdb"
    _seed_source(db)
    owner_jobs, engagement = _projection_dependencies(job_id)
    attempted = ThreadEvent()
    futures: list[Any] = []
    original_append = EventAppendBatch.append

    def overwrite_deposit() -> None:
        attempted.set()
        engagement.put_document(
            "doc-html",
            {
                "document_id": "doc-html",
                "doc_model": {
                    "type": "doc",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "later version"}],
                        }
                    ],
                },
            },
        )

    with ThreadPoolExecutor(max_workers=1) as pool:

        def append_with_contender(batch: EventAppendBatch, event_batch: tuple[Any, ...]) -> None:
            future = pool.submit(overwrite_deposit)
            futures.append(future)
            assert attempted.wait(timeout=1)
            assert future.done() is False
            original_append(batch, event_batch)

        monkeypatch.setattr(EventAppendBatch, "append", append_with_contender)
        result = project_terminal_job_to_graph(
            job_id,
            owner_user_id="operator",
            owner_jobs=owner_jobs,
            store=store,
            engagement_store=engagement,
            graph_db_path=db,
        )
        futures[0].result(timeout=1)

    assert result.job.graph_projection_state == "complete"
    stored = engagement.get_document("doc-html")
    assert stored is not None
    assert stored["doc_model"]["content"][0]["content"][0]["text"] == "later version"


def test_event_persistence_failure_replays_without_duplicate_or_lost_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = DurableJobStore(tmp_path / "jobs.sqlite3")
    job_id = _terminal_job(store)
    db = tmp_path / "graph.duckdb"
    events = tmp_path / "events"
    _seed_source(db)
    owner_jobs, engagement = _projection_dependencies(job_id)
    original_append = EventAppendBatch.append

    def append_then_crash(batch: EventAppendBatch, event_batch: tuple[Any, ...]) -> None:
        original_append(batch, event_batch[:1])
        raise OSError("event filesystem unavailable")

    monkeypatch.setattr(EventAppendBatch, "append", append_then_crash)
    with pytest.raises(OSError, match="event filesystem unavailable"):
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
    assert pending is not None
    assert pending.graph_projection_state == "pending"
    assert _event_line_count(events) == 1

    monkeypatch.setattr(EventAppendBatch, "append", original_append)
    result = project_terminal_job_to_graph(
        job_id,
        owner_user_id="operator",
        owner_jobs=owner_jobs,
        store=store,
        engagement_store=engagement,
        graph_db_path=db,
        events_dir=str(events),
    )
    assert result.job.graph_projection_state == "complete"
    assert _event_line_count(events) == 5


@pytest.mark.parametrize("matching_last", [False, True])
def test_conflicting_deterministic_event_refuses_before_graph_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, matching_last: bool
) -> None:
    store = DurableJobStore(tmp_path / "jobs.sqlite3")
    job_id = _terminal_job(store)
    db = tmp_path / "graph.duckdb"
    events = tmp_path / "events"
    _seed_source(db)
    owner_jobs, engagement = _projection_dependencies(job_id)
    import substrate.midnight_oil.graph_projection as projection

    original_events = projection._projection_events

    def projection_events_with_collision(plan: Any) -> tuple[Any, ...]:
        desired = original_events(plan)
        root = desired[0]
        hostile = prepare_typed_event(
            root.investigation_id,
            GraphNodeInsertedPayload(
                node_id=root.payload.node_id,
                canonical_label="hostile deterministic collision",
                node_type="entity",
                graph_scope="depth",
                has_embedding=False,
            ),
            event_id=root.event_id,
            role="connector",
            emitted_at=root.emitted_at,
        )
        first, second = (hostile, root) if matching_last else (root, hostile)
        append_event_once(first, events_dir=str(events))
        event_path = next(events.rglob("*.jsonl"))
        with event_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(second.model_dump(mode="json"), default=str) + "\n")
        return desired

    monkeypatch.setattr(projection, "_projection_events", projection_events_with_collision)

    with pytest.raises(GraphProjectionRefused) as refusal:
        project_terminal_job_to_graph(
            job_id,
            owner_user_id="operator",
            owner_jobs=owner_jobs,
            store=store,
            engagement_store=engagement,
            graph_db_path=db,
            events_dir=str(events),
        )
    assert refusal.value.reason == "deterministic_row_conflict"
    assert _event_line_count(events) == 2
    with connect_read(str(db)) as con:
        assert con.execute("SELECT count(*) FROM deliverables").fetchone() == (0,)
        assert con.execute("SELECT count(*) FROM nodes").fetchone() == (0,)
        assert con.execute("SELECT count(*) FROM edges").fetchone() == (0,)


@pytest.mark.parametrize("matching_last", [False, True])
def test_unrelated_event_collision_refuses_before_graph_writes(
    tmp_path: Path, matching_last: bool
) -> None:
    store = DurableJobStore(tmp_path / "jobs.sqlite3")
    job_id = _terminal_job(store)
    db = tmp_path / "graph.duckdb"
    events = tmp_path / "events"
    _seed_source(db)
    owner_jobs, engagement = _projection_dependencies(job_id)
    investigation_id = f"midnight-oil:{job_id}"
    matching = prepare_typed_event(
        investigation_id,
        GraphNodeInsertedPayload(
            node_id="unrelated-node",
            canonical_label="matching unrelated event",
            node_type="claim",
            graph_scope="depth",
            has_embedding=False,
        ),
        event_id="unrelated-event-id",
    )
    conflicting = matching.model_copy(
        update={
            "payload": GraphNodeInsertedPayload(
                node_id="unrelated-node",
                canonical_label="conflicting unrelated event",
                node_type="claim",
                graph_scope="depth",
                has_embedding=False,
            )
        }
    )
    first, second = (conflicting, matching) if matching_last else (matching, conflicting)
    append_event_once(first, events_dir=str(events))
    event_path = next(events.rglob("*.jsonl"))
    with event_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(second.model_dump(mode="json"), default=str) + "\n")

    with pytest.raises(GraphProjectionRefused) as refusal:
        project_terminal_job_to_graph(
            job_id,
            owner_user_id="operator",
            owner_jobs=owner_jobs,
            store=store,
            engagement_store=engagement,
            graph_db_path=db,
            events_dir=str(events),
        )
    assert refusal.value.reason == "deterministic_row_conflict"
    with connect_read(str(db)) as con:
        assert con.execute("SELECT count(*) FROM deliverables").fetchone() == (0,)


def test_malformed_event_stream_refuses_before_graph_writes(tmp_path: Path) -> None:
    store = DurableJobStore(tmp_path / "jobs.sqlite3")
    job_id = _terminal_job(store)
    db = tmp_path / "graph.duckdb"
    events = tmp_path / "events"
    _seed_source(db)
    owner_jobs, engagement = _projection_dependencies(job_id)
    append_event_once(
        prepare_typed_event(
            f"midnight-oil:{job_id}",
            GraphNodeInsertedPayload(
                node_id="unrelated-node",
                canonical_label="valid unrelated event",
                node_type="claim",
                graph_scope="depth",
                has_embedding=False,
            ),
            event_id="unrelated-event-id",
        ),
        events_dir=str(events),
    )
    event_path = next(events.rglob("*.jsonl"))
    with event_path.open("a", encoding="utf-8") as handle:
        handle.write("{malformed-json\n")

    with pytest.raises(GraphProjectionRefused) as refusal:
        project_terminal_job_to_graph(
            job_id,
            owner_user_id="operator",
            owner_jobs=owner_jobs,
            store=store,
            engagement_store=engagement,
            graph_db_path=db,
            events_dir=str(events),
        )
    assert refusal.value.reason == "deterministic_row_conflict"
    with connect_read(str(db)) as con:
        assert con.execute("SELECT count(*) FROM deliverables").fetchone() == (0,)


def test_duplicate_step_keys_refuse_before_graph_or_event_writes(tmp_path: Path) -> None:
    store = DurableJobStore(tmp_path / "jobs.sqlite3")
    job_id = _terminal_job(store)
    job = get_job(job_id, store=store)
    assert job is not None
    put_job_state(
        replace(job, step_evidence=(job.step_evidence[0], job.step_evidence[0])),
        store=store,
    )
    db = tmp_path / "graph.duckdb"
    events = tmp_path / "events"
    _seed_source(db)
    owner_jobs, engagement = _projection_dependencies(job_id)

    with pytest.raises(GraphProjectionRefused) as refusal:
        project_terminal_job_to_graph(
            job_id,
            owner_user_id="operator",
            owner_jobs=owner_jobs,
            store=store,
            engagement_store=engagement,
            graph_db_path=db,
            events_dir=str(events),
        )
    assert refusal.value.reason == "deterministic_row_conflict"
    assert _event_line_count(events) == 0
    with connect_read(str(db)) as con:
        assert con.execute("SELECT count(*) FROM deliverables").fetchone() == (0,)
        assert con.execute("SELECT count(*) FROM nodes").fetchone() == (0,)
        assert con.execute("SELECT count(*) FROM edges").fetchone() == (0,)


def test_claim_mapping_is_part_of_durable_evidence_hash(tmp_path: Path) -> None:
    store = DurableJobStore(tmp_path / "jobs.sqlite3")
    job_id = _terminal_job(store)
    db = tmp_path / "graph.duckdb"
    _seed_source(db)
    owner_jobs, engagement = _projection_dependencies(job_id)
    first = project_terminal_job_to_graph(
        job_id,
        owner_user_id="operator",
        owner_jobs=owner_jobs,
        store=store,
        engagement_store=engagement,
        graph_db_path=db,
    )
    job = get_job(job_id, store=store)
    assert job is not None
    evidence = job.step_evidence[0]
    second_receipt = {
        "source_id": "chunk-source-2",
        "document_id": "doc-source-2",
        "source_url": "antiek://document/doc-source-2#chunk=chunk-source-2",
        "content_hash": hashlib.sha256(b"second source excerpt").hexdigest(),
        "hash_scope": "retrieval_excerpt",
        "title": "Second source",
    }
    first_receipt_id = source_receipt_id(evidence.source_receipts[0])
    second_receipt_id = source_receipt_id(second_receipt)
    claims = build_step_claim_evidence(
        job_id=job.job_id,
        step_key=evidence.step_key,
        output_text=evidence.output_text,
        insights=evidence.insights,
        questions=evidence.questions,
        source_receipts=(*evidence.source_receipts, second_receipt),
        supported_claims=(
            ("output_paragraph", 0, (first_receipt_id,)),
            ("insight", 0, (second_receipt_id,)),
        ),
    )
    with pytest.raises(ValueError, match="sealed graph projection source"):
        put_job_state(
            replace(
                job,
                step_evidence=(
                    replace(
                        evidence,
                        source_receipts=(*evidence.source_receipts, second_receipt),
                        claim_evidence_schema_version=1,
                        claim_evidence=claims,
                    ),
                ),
                graph_projection_state="pending",
                graph_effect_receipt=None,
            ),
            store=store,
        )
    restored = get_job(job_id, store=store)
    assert restored is not None
    assert restored.graph_effect_receipt == first.receipt


def test_missing_source_row_keeps_projection_retryable_without_graph_writes(
    tmp_path: Path,
) -> None:
    store = DurableJobStore(tmp_path / "jobs.sqlite3")
    job_id = _terminal_job(store)
    db = tmp_path / "graph.duckdb"
    ensure_initialized(str(db))
    owner_jobs, engagement = _projection_dependencies(job_id)

    with pytest.raises(GraphProjectionPending) as refusal:
        project_terminal_job_to_graph(
            job_id,
            owner_user_id="operator",
            owner_jobs=owner_jobs,
            store=store,
            engagement_store=engagement,
            graph_db_path=db,
            events_dir=str(tmp_path / "events"),
        )
    assert refusal.value.reason == "internal_local_chunk_temporarily_missing"
    with connect_read(str(db)) as con:
        assert con.execute("SELECT count(*) FROM deliverables").fetchone() == (0,)
        assert con.execute("SELECT count(*) FROM nodes").fetchone() == (0,)
        assert con.execute("SELECT count(*) FROM edges").fetchone() == (0,)
    restored = get_job(job_id, store=store)
    assert restored is not None
    assert restored.graph_projection_state == "pending"
    assert restored.graph_projection_reason == "internal_local_chunk_temporarily_missing"


def test_unverified_claim_refuses_before_graph_or_event_writes(tmp_path: Path) -> None:
    store = DurableJobStore(tmp_path / "jobs.sqlite3")
    job_id = _terminal_job(store)
    job = get_job(job_id, store=store)
    assert job is not None
    evidence = job.step_evidence[0]
    receipt_id = source_receipt_id(evidence.source_receipts[0])
    put_job_state(
        replace(
            job,
            step_evidence=(
                replace(
                    evidence,
                    claim_evidence=build_step_claim_evidence(
                        job_id=job.job_id,
                        step_key=evidence.step_key,
                        output_text=evidence.output_text,
                        insights=evidence.insights,
                        questions=evidence.questions,
                        source_receipts=evidence.source_receipts,
                        supported_claims=(("output_paragraph", 0, (receipt_id,)),),
                    ),
                ),
            ),
        ),
        store=store,
    )
    db = tmp_path / "graph.duckdb"
    events = tmp_path / "events"
    _seed_source(db)
    owner_jobs, engagement = _projection_dependencies(job_id)

    with pytest.raises(GraphProjectionRefused) as refusal:
        project_terminal_job_to_graph(
            job_id,
            owner_user_id="operator",
            owner_jobs=owner_jobs,
            store=store,
            engagement_store=engagement,
            graph_db_path=db,
            events_dir=str(events),
        )

    assert refusal.value.reason == "claim_coverage_missing"
    assert _event_line_count(events) == 0
    with connect_read(str(db)) as con:
        assert con.execute("SELECT count(*) FROM deliverables").fetchone() == (0,)
        assert con.execute("SELECT count(*) FROM nodes").fetchone() == (0,)
        assert con.execute("SELECT count(*) FROM edges").fetchone() == (0,)


def test_uninitialized_graph_and_lock_contention_are_typed_retryable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = DurableJobStore(tmp_path / "jobs.sqlite3")
    job_id = _terminal_job(store)
    owner_jobs, engagement = _projection_dependencies(job_id)
    db = tmp_path / "uninitialized.duckdb"

    with pytest.raises(GraphProjectionPending) as schema_pending:
        project_terminal_job_to_graph(
            job_id,
            owner_user_id="operator",
            owner_jobs=owner_jobs,
            store=store,
            engagement_store=engagement,
            graph_db_path=db,
        )
    assert schema_pending.value.reason == "operational_artifact_pending"

    import substrate.midnight_oil.graph_projection as projection

    monkeypatch.setattr(
        projection,
        "connect_write",
        lambda *args, **kwargs: (_ for _ in ()).throw(WriteLockTimeout("busy")),
    )
    with pytest.raises(GraphProjectionPending) as lock_pending:
        project_terminal_job_to_graph(
            job_id,
            owner_user_id="operator",
            owner_jobs=owner_jobs,
            store=store,
            engagement_store=engagement,
            graph_db_path=db,
        )
    assert lock_pending.value.reason == "graph_lock_unavailable"
    restored = get_job(job_id, store=store)
    assert restored is not None
    assert restored.graph_projection_state == "pending"
    assert restored.graph_projection_reason == "graph_lock_unavailable"


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


def test_stale_graph_disposition_cannot_erase_newer_effect_receipt(
    tmp_path: Path,
) -> None:
    store = DurableJobStore(tmp_path / "jobs.sqlite3")
    job_id = _terminal_job(store)
    expected = get_job(job_id, store=store)
    assert expected is not None
    receipt = MidnightOilGraphEffectReceipt(
        schema_version=1,
        owner_user_id="operator",
        deliverable_id="dlv-" + "1" * 16,
        section_ids=("sec-" + "2" * 16,),
        node_ids=("node-" + "3" * 16,),
        edge_ids=("edge-" + "4" * 16,),
        html_sha256="5" * 64,
        evidence_sha256="6" * 64,
        deep_links=(
            "antiek://deliverable/dlv-" + "1" * 16,
            "antiek://node/node-" + "3" * 16,
        ),
    )
    complete = replace(
        expected,
        graph_projection_state="complete",
        graph_effect_receipt=receipt,
    )
    assert store.compare_and_put_graph(expected, complete) is True
    stale_pending = replace(
        expected,
        graph_projection_reason="graph_lock_unavailable",
    )
    assert store.compare_and_put_graph(expected, stale_pending) is False
    restored = get_job(job_id, store=store)
    assert restored is not None
    assert restored.graph_projection_state == "complete"
    assert restored.graph_effect_receipt == receipt


def test_graph_checkpoint_cas_rejects_changed_projection_source(tmp_path: Path) -> None:
    store = DurableJobStore(tmp_path / "jobs.sqlite3")
    job_id = _terminal_job(store)
    expected = get_job(job_id, store=store)
    assert expected is not None
    put_job_state(replace(expected, deposit_document_id="doc-html-new"), store=store)

    pending = replace(expected, graph_projection_reason="graph_lock_unavailable")
    assert store.compare_and_put_graph(expected, pending) is False
    restored = get_job(job_id, store=store)
    assert restored is not None
    assert restored.deposit_document_id == "doc-html-new"
    assert restored.graph_projection_reason is None


def test_graph_checkpoint_cas_preserves_unrelated_concurrent_fields(
    tmp_path: Path,
) -> None:
    store = DurableJobStore(tmp_path / "jobs.sqlite3")
    job_id = _terminal_job(store)
    expected = get_job(job_id, store=store)
    assert expected is not None
    put_job_state(replace(expected, notes="concurrent operator note"), store=store)

    pending = replace(expected, graph_projection_reason="graph_lock_unavailable")
    assert store.compare_and_put_graph(expected, pending) is True
    restored = get_job(job_id, store=store)
    assert restored is not None
    assert restored.notes == "concurrent operator note"
    assert restored.graph_projection_reason == "graph_lock_unavailable"


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
    _seed_source(db)
    deliverable_id, _ = _expected_projection_ids(
        job_id, store=store, owner_jobs=owner_jobs, engagement=engagement
    )
    with connect_write(str(db), purpose="test/conflicting-deliverable") as con:
        con.execute(
            "INSERT INTO deliverables "
            "(deliverable_id, title, deliverable_kind, investigation_root_id, "
            "owner_user_id, metadata) VALUES (?, 'wrong', 'research_memo', "
            "'wrong', 'foreign', '{}')",
            [deliverable_id],
        )
    with connect_read(str(db)) as con:
        before = con.execute(
            "SELECT * FROM deliverables WHERE deliverable_id = ?", [deliverable_id]
        ).fetchone()
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
    assert restored.graph_projection_state == "refused"
    assert restored.graph_projection_reason == "deterministic_row_conflict"
    assert _event_line_count(tmp_path / "events") == 0
    with connect_read(str(db)) as con:
        assert (
            con.execute(
                "SELECT * FROM deliverables WHERE deliverable_id = ?", [deliverable_id]
            ).fetchone()
            == before
        )


def test_section_id_owned_by_another_deliverable_refuses_before_any_new_row(
    tmp_path: Path,
) -> None:
    store = DurableJobStore(tmp_path / "jobs.sqlite3")
    job_id = _terminal_job(store)
    owner_jobs, engagement = _projection_dependencies(job_id)
    db = tmp_path / "graph.duckdb"
    _seed_source(db)
    expected_deliverable_id, _ = _expected_projection_ids(
        job_id, store=store, owner_jobs=owner_jobs, engagement=engagement
    )
    expected_section_id = content_addressed_id("sec", f"{expected_deliverable_id}|op:test:0")
    with connect_write(str(db), purpose="test/foreign-section-owner") as con:
        con.execute(
            "INSERT INTO deliverables "
            "(deliverable_id, title, deliverable_kind, investigation_root_id, "
            "owner_user_id, metadata) VALUES "
            "('foreign-deliverable', 'foreign', 'research_memo', 'foreign', "
            "'foreign', '{}')"
        )
        con.execute(
            "INSERT INTO deliverable_sections "
            "(section_id, deliverable_id, section_index, title, prose_text, "
            "prose_provenance) VALUES (?, 'foreign-deliverable', 0, 'foreign', "
            "'foreign', '{}')",
            [expected_section_id],
        )
    with connect_read(str(db)) as con:
        before = con.execute(
            "SELECT * FROM deliverable_sections WHERE section_id = ?",
            [expected_section_id],
        ).fetchone()

    with pytest.raises(GraphProjectionRefused) as refusal:
        project_terminal_job_to_graph(
            job_id,
            owner_user_id="operator",
            owner_jobs=owner_jobs,
            store=store,
            engagement_store=engagement,
            graph_db_path=db,
        )
    assert refusal.value.reason == "deterministic_row_conflict"
    with connect_read(str(db)) as con:
        assert con.execute(
            "SELECT count(*) FROM deliverables WHERE deliverable_id = ?",
            [expected_deliverable_id],
        ).fetchone() == (0,)
        assert (
            con.execute(
                "SELECT * FROM deliverable_sections WHERE section_id = ?",
                [expected_section_id],
            ).fetchone()
            == before
        )


def test_goal_secret_never_enters_graph_or_typed_events(tmp_path: Path) -> None:
    secret = "sk-supersecret123456789"
    store = DurableJobStore(tmp_path / "jobs.sqlite3")
    job_id = _terminal_job(store, goal=f"Investigate {secret}")
    owner_jobs, engagement = _projection_dependencies(job_id)
    db = tmp_path / "graph.duckdb"
    events = tmp_path / "events"
    _seed_source(db)
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
        path.read_text(encoding="utf-8") for path in events.rglob("*") if path.is_file()
    )
    assert secret not in graph_text
    assert secret not in event_text


def test_existing_chunk_with_wrong_hash_refuses_without_graph_writes(tmp_path: Path) -> None:
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
    with pytest.raises(GraphProjectionRefused) as refusal:
        project_terminal_job_to_graph(
            job_id,
            owner_user_id="operator",
            owner_jobs=owner_jobs,
            store=store,
            engagement_store=engagement,
            graph_db_path=db,
            events_dir=str(tmp_path / "events"),
        )
    assert refusal.value.reason == "receipt_malformed_or_forged"
    with connect_read(str(db)) as con:
        assert con.execute("SELECT count(*) FROM deliverables").fetchone() == (0,)
        assert con.execute("SELECT count(*) FROM nodes").fetchone() == (0,)
        assert con.execute("SELECT count(*) FROM edges").fetchone() == (0,)


def test_chunk_changed_immediately_before_projection_lock_is_revalidated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = DurableJobStore(tmp_path / "jobs.sqlite3")
    job_id = _terminal_job(store)
    owner_jobs, engagement = _projection_dependencies(job_id)
    db = tmp_path / "graph.duckdb"
    _seed_source(db)
    import substrate.midnight_oil.graph_projection as projection

    real_connect_write = connect_write

    @contextmanager
    def change_then_connect(*args: Any, **kwargs: Any):  # type: ignore[no-untyped-def]
        with real_connect_write(str(db), purpose="test/change-before-lock") as con:
            con.execute(
                "UPDATE chunks SET text = ? WHERE chunk_id = ?",
                ["changed before admission", "chunk-source"],
            )
        with real_connect_write(*args, **kwargs) as con:
            yield con

    monkeypatch.setattr(projection, "connect_write", change_then_connect)
    with pytest.raises(GraphProjectionRefused) as refusal:
        project_terminal_job_to_graph(
            job_id,
            owner_user_id="operator",
            owner_jobs=owner_jobs,
            store=store,
            engagement_store=engagement,
            graph_db_path=db,
        )
    assert refusal.value.reason == "receipt_malformed_or_forged"
    with connect_read(str(db)) as con:
        assert con.execute("SELECT count(*) FROM deliverables").fetchone() == (0,)


def test_deposit_drift_during_admission_rolls_back_graph_and_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = DurableJobStore(tmp_path / "jobs.sqlite3")
    job_id = _terminal_job(store)
    owner_jobs, engagement = _projection_dependencies(job_id)
    db = tmp_path / "graph.duckdb"
    events = tmp_path / "events"
    _seed_source(db)
    import substrate.midnight_oil.graph_projection as projection

    original_census = projection._census_projection_rows

    def drift_after_write_census(*args: Any, **kwargs: Any) -> Any:
        result = original_census(*args, **kwargs)
        if kwargs.get("require_all") is True:
            engagement.put_document(
                "doc-html",
                {
                    "document_id": "doc-html",
                    "doc_model": {
                        "type": "doc",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": "drifted artifact"}],
                            }
                        ],
                    },
                },
            )
        return result

    monkeypatch.setattr(projection, "_census_projection_rows", drift_after_write_census)
    with pytest.raises(GraphProjectionPending) as pending:
        project_terminal_job_to_graph(
            job_id,
            owner_user_id="operator",
            owner_jobs=owner_jobs,
            store=store,
            engagement_store=engagement,
            graph_db_path=db,
            events_dir=str(events),
        )
    assert pending.value.reason == "operational_artifact_pending"
    assert _event_line_count(events) == 0
    with connect_read(str(db)) as con:
        assert con.execute("SELECT count(*) FROM deliverables").fetchone() == (0,)
        assert con.execute("SELECT count(*) FROM nodes").fetchone() == (0,)
        assert con.execute("SELECT count(*) FROM edges").fetchone() == (0,)


def test_projection_writer_lock_blocks_concurrent_graph_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = DurableJobStore(tmp_path / "jobs.sqlite3")
    job_id = _terminal_job(store)
    owner_jobs, engagement = _projection_dependencies(job_id)
    db = tmp_path / "graph.duckdb"
    _seed_source(db)
    import substrate.midnight_oil.graph_projection as projection

    original_validate = projection._validate_cited_receipts
    contender_blocked: list[bool] = []

    def validate_with_contender(con: Any, receipts: Any) -> None:
        def contend() -> None:
            try:
                with connect_write(str(db), purpose="test/concurrent-contender", timeout_s=0.02):
                    contender_blocked.append(False)
            except WriteLockTimeout:
                contender_blocked.append(True)

        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(contend).result()
        original_validate(con, receipts)

    monkeypatch.setattr(projection, "_validate_cited_receipts", validate_with_contender)
    result = project_terminal_job_to_graph(
        job_id,
        owner_user_id="operator",
        owner_jobs=owner_jobs,
        store=store,
        engagement_store=engagement,
        graph_db_path=db,
    )
    assert contender_blocked == [True]
    assert result.job.graph_projection_state == "complete"


@pytest.mark.parametrize(
    ("table", "column"),
    [
        ("deliverable_sections", "title"),
        ("nodes", "metadata"),
        ("edges", "relation"),
    ],
)
def test_completed_receipt_rechecks_every_hostile_child_row_collision(
    tmp_path: Path, table: str, column: str
) -> None:
    store = DurableJobStore(tmp_path / f"{table}-jobs.sqlite3")
    job_id = _terminal_job(store)
    owner_jobs, engagement = _projection_dependencies(job_id)
    db = tmp_path / f"{table}-graph.duckdb"
    _seed_source(db)
    result = project_terminal_job_to_graph(
        job_id,
        owner_user_id="operator",
        owner_jobs=owner_jobs,
        store=store,
        engagement_store=engagement,
        graph_db_path=db,
        events_dir=str(tmp_path / f"{table}-events"),
    )
    event_count = _event_line_count(tmp_path / f"{table}-events")
    if table == "deliverable_sections":
        row_id = result.receipt.section_ids[0]
        id_column = "section_id"
    elif table == "nodes":
        row_id = result.receipt.node_ids[0]
        id_column = "node_id"
    else:
        row_id = result.receipt.edge_ids[0]
        id_column = "edge_id"
    hostile = '{"hostile":true}' if column == "metadata" else f"hostile_{column}"
    with connect_write(str(db), purpose=f"test/hostile-{table}") as con:
        con.execute(
            f"UPDATE {table} SET {column} = ? WHERE {id_column} = ?",
            [hostile, row_id],
        )
    with connect_read(str(db)) as con:
        before = con.execute(f"SELECT * FROM {table} WHERE {id_column} = ?", [row_id]).fetchone()
    with pytest.raises(GraphProjectionConflict, match="durable effect receipt"):
        project_terminal_job_to_graph(
            job_id,
            owner_user_id="operator",
            owner_jobs=owner_jobs,
            store=store,
            engagement_store=engagement,
            graph_db_path=db,
            events_dir=str(tmp_path / f"{table}-events"),
        )
    assert _event_line_count(tmp_path / f"{table}-events") == event_count
    with connect_read(str(db)) as con:
        assert (
            con.execute(f"SELECT * FROM {table} WHERE {id_column} = ?", [row_id]).fetchone()
            == before
        )


@pytest.mark.parametrize(
    ("receipt_patch", "expected_reason"),
    [
        ({"hash_scope": "whole_document"}, "receipt_malformed_or_forged"),
        (
            {"source_url": "antiek://document/other#chunk=chunk-source"},
            "receipt_malformed_or_forged",
        ),
        (
            {"source_url": "https://example.test/source"},
            "external_receipt_not_admissible_v1",
        ),
    ],
)
def test_noncanonical_source_receipt_is_never_attributed(
    tmp_path: Path, receipt_patch: dict[str, str], expected_reason: str
) -> None:
    store = DurableJobStore(tmp_path / "jobs.sqlite3")
    job_id = _terminal_job(store)
    job = get_job(job_id, store=store)
    assert job is not None
    evidence = job.step_evidence[0]
    receipt = {**evidence.source_receipts[0], **receipt_patch}
    receipt_id = source_receipt_id(receipt)
    claims = build_step_claim_evidence(
        job_id=job.job_id,
        step_key=evidence.step_key,
        output_text=evidence.output_text,
        insights=evidence.insights,
        questions=evidence.questions,
        source_receipts=(receipt,),
        supported_claims=(
            ("output_paragraph", 0, (receipt_id,)),
            ("insight", 0, (receipt_id,)),
        ),
    )
    put_job_state(
        replace(
            job,
            step_evidence=(
                replace(
                    evidence,
                    source_receipts=(receipt,),
                    claim_evidence=claims,
                ),
            ),
        ),
        store=store,
    )
    owner_jobs, engagement = _projection_dependencies(job_id)
    db = tmp_path / "graph.duckdb"
    _seed_source(db)
    with pytest.raises(GraphProjectionRefused) as refusal:
        project_terminal_job_to_graph(
            job_id,
            owner_user_id="operator",
            owner_jobs=owner_jobs,
            store=store,
            engagement_store=engagement,
            graph_db_path=db,
            events_dir=str(tmp_path / "events"),
        )
    assert refusal.value.reason == expected_reason
    with connect_read(str(db)) as con:
        rows = con.execute("SELECT source_document_id, chunk_id FROM edges").fetchall()
    assert rows == []
