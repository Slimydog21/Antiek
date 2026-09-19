"""SPR-DRL-05 — SessionEvidencePack schema + builder gates."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

import pytest

from orchestration.cascade_session import CascadeSession, Leaf
from orchestration.loop_one.orchestrator import _investigation_context_from_pack
from orchestration.session_evidence_pack import (
    PackChunk,
    PackDocument,
    PackGatherReport,
    PackGatherSourceReceipt,
    PackLeafReuseReport,
    PackReusedUnitQualification,
    SessionEvidencePack,
    SessionEvidencePackError,
    _load_reuse_report,
    build_session_evidence_pack,
    compute_content_hash,
    parse_session_evidence_pack,
)
from processing.embedding import _reset_default_provider, set_default_embedding_provider
from roles.cascade_planner import SubQuestion, approve_plan, build_plan, persist_tree
from roles.cascade_planner.persist import load_tree
from runtime.research_runner import HostLocalRunner, PromotionFunnel, make_contract_gather_stub
from substrate.graph.schema import init_database_at_path
from substrate.investigation_streams import initialize_composite_stream
from substrate.investigation_tenancy import InvestigationAuthority, bind_legacy_stream_lease
from substrate.multi_user.auth import operator_claims
from substrate.schemas.events import GatherReportRecordedPayload, GatherSourceReportReceipt


class _FakeEmbedding:
    dimension = 8

    def encode(self, text: str) -> list[float]:
        d = hashlib.sha256(text.encode()).digest()
        return [b / 255.0 for b in d[: self.dimension]]


class _Dec:
    def __init__(self, subs: list[str]) -> None:
        self._subs = subs

    def decompose(self, q: str, *, context: str = ""):
        return [SubQuestion(question=s) for s in self._subs]


@pytest.fixture(autouse=True)
def _emb():
    set_default_embedding_provider(_FakeEmbedding())
    yield
    _reset_default_provider()


@pytest.fixture
def env(monkeypatch):
    d = tempfile.mkdtemp()
    db = os.path.join(d, "g.duckdb")
    ev = os.path.join(d, "events")
    os.makedirs(ev, exist_ok=True)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", ev)
    import substrate.graph.insight_question as iq

    monkeypatch.setattr(iq, "graph_db_path", lambda: db)
    init_database_at_path(db)
    return {"db": db, "events": ev}


def test_invalid_pack_rejects_unknown_document():
    with pytest.raises(SessionEvidencePackError, match="unknown document"):
        parse_session_evidence_pack(
            {
                "schema_version": 1,
                "session_id": "session-1",
                "problem_question": "q",
                "chunks": [
                    {
                        "chunk_id": "c1",
                        "document_id": "missing-doc",
                        "ip_holder_id": None,
                        "text": "t",
                        "source_investigation_id": "leaf-0",
                        "sub_question": "sq",
                    }
                ],
                "documents": [],
                "leaf_investigation_ids": ["leaf-0"],
                "content_hash": "deadbeef",
            }
        )


def test_empty_pack_valid_with_zero_chunks():
    pack = SessionEvidencePack(
        session_id="session-empty",
        problem_question="the problem",
        chunks=[],
        documents=[],
        leaf_investigation_ids=[],
    )
    assert pack.content_hash
    assert pack.chunks == []


def test_content_hash_stable_across_rebuild():
    chunks = [
        PackChunk(
            chunk_id="chunk-a",
            document_id="doc-1",
            ip_holder_id=None,
            text="alpha",
            source_investigation_id="leaf-0",
            sub_question="sub a",
        ),
    ]
    docs = [PackDocument(document_id="doc-1", title="Doc 1", ip_holder_id=None)]
    h1 = compute_content_hash(
        session_id="s1",
        problem_question="problem",
        chunks=chunks,
        documents=docs,
        leaf_investigation_ids=["leaf-0"],
    )
    h2 = compute_content_hash(
        session_id="s1",
        problem_question="problem",
        chunks=chunks,
        documents=docs,
        leaf_investigation_ids=["leaf-0"],
    )
    assert h1 == h2


def _pack_report(*, partial: bool = False) -> PackGatherReport:
    statuses = ("succeeded", "succeeded", "failed", "succeeded") if partial else (
        "succeeded", "succeeded", "succeeded", "succeeded"
    )
    return PackGatherReport(
        investigation_id="leaf-0",
        launch_fingerprint="a" * 64,
        plan_fingerprint="c" * 64,
        legal_policy_snapshot_sha256="b" * 64,
        receipts=tuple(
            PackGatherSourceReceipt(
                source=source,
                status=status,
                document_ids=("doc-1",) if index == 0 else (),
                failure_code="provider_error" if status == "failed" else None,
            )
            for index, (source, status) in enumerate(zip(
                ("exa", "parallel", "arxiv", "substack"), statuses, strict=True
            ))
        ),
        document_ids=("doc-1",),
        minimum_evidence_documents=1,
        evidence_complete=True,
        partial=partial,
    )


def test_v2_multi_source_pack_binds_reports_and_changes_hash() -> None:
    document = PackDocument(document_id="doc-1", title="One")
    complete = SessionEvidencePack(
        schema_version=2,
        session_id="session",
        problem_question="question",
        documents=[document],
        leaf_investigation_ids=["leaf-0"],
        gather_mode="authorized_multi_source",
        gather_plan_fingerprint="a" * 64,
        gather_reports=[_pack_report()],
    )
    partial = SessionEvidencePack(
        schema_version=2,
        session_id="session",
        problem_question="question",
        documents=[document],
        leaf_investigation_ids=["leaf-0"],
        gather_mode="authorized_multi_source",
        gather_plan_fingerprint="a" * 64,
        gather_reports=[_pack_report(partial=True)],
    )
    assert complete.schema_version == 2
    assert complete.content_hash != partial.content_hash
    assert "provider_receipt_id" not in complete.model_dump_json()

    context = _investigation_context_from_pack(partial)
    assert "Partial coverage: leaf-0" in context.context
    assert "arxiv=0/1 succeeded" in context.context
    assert "do not infer" in context.context
    assert "provider_error" not in context.context
    assert context.archived_source_coverage == {
        "schema_version": 1,
        "pack_schema_version": 2,
        "pack_content_hash": partial.content_hash,
        "gather_plan_fingerprint": "a" * 64,
        "coverage": context.artifact_source_coverage,
    }


def test_v2_multi_source_pack_rejects_missing_leaf_or_fingerprint_mismatch() -> None:
    base = {
        "schema_version": 2,
        "session_id": "session",
        "problem_question": "question",
        "documents": [PackDocument(document_id="doc-1", title="One")],
        "leaf_investigation_ids": ["leaf-0"],
        "gather_mode": "authorized_multi_source",
        "gather_plan_fingerprint": "c" * 64,
    }
    with pytest.raises(ValueError, match="exactly one report per leaf"):
        SessionEvidencePack(**base)
    with pytest.raises(ValueError, match="launch fingerprint does not match launch"):
        SessionEvidencePack(**base, gather_reports=[_pack_report()])


def test_legacy_v1_hash_contract_remains_parseable() -> None:
    content_hash = compute_content_hash(
        schema_version=1,
        session_id="legacy",
        problem_question="question",
        chunks=[],
        documents=[],
        leaf_investigation_ids=[],
    )
    pack = parse_session_evidence_pack({
        "schema_version": 1,
        "session_id": "legacy",
        "problem_question": "question",
        "chunks": [],
        "documents": [],
        "leaf_investigation_ids": [],
        "content_hash": content_hash,
    })
    assert pack.schema_version == 1
    assert pack.gather_mode == "legacy"


def test_v3_binds_exact_leaf_reuse_truth_and_changes_hash() -> None:
    base = {
        "schema_version": 3,
        "session_id": "session-v3",
        "problem_question": "question",
        "leaf_investigation_ids": ["leaf-0"],
    }
    absent = SessionEvidencePack(
        **base,
        reuse_reports=[PackLeafReuseReport(
            investigation_id="leaf-0",
            state="not_attempted",
            injected_unit_count=0,
        )],
    )
    qualified = SessionEvidencePack(
        **base,
        reuse_reports=[PackLeafReuseReport(
            investigation_id="leaf-0",
            state="qualified",
            injected_unit_count=1,
            qualifications=(PackReusedUnitQualification(
                unit_id="unit-1",
                source_investigation_id="prior-1",
                state="partial",
                source_successes=(1, 1, 0, 1),
                total_leaves=1,
                partial_leaf_count=1,
            ),),
        )],
    )
    assert absent.schema_version == 3
    assert absent.content_hash != qualified.content_hash
    context = _investigation_context_from_pack(qualified)
    assert "Inherited knowledge reuse (separate from direct evidence)" in context.context
    assert "unit-1=partial" in context.context
    assert "Do not treat inherited qualification as direct source coverage" in context.context
    assert context.artifact_source_coverage is None
    assert context.artifact_inherited_reuse == {
        "leaves": [qualified.reuse_reports[0].model_dump(
            mode="json", exclude={"injected_unit_ids"}
        )]
    }
    assert context.archived_source_coverage == {
        "schema_version": 2,
        "pack_schema_version": 3,
        "pack_content_hash": qualified.content_hash,
        "inherited_reuse": context.artifact_inherited_reuse,
    }


def test_v3_rejects_missing_or_contradictory_reuse_truth() -> None:
    with pytest.raises(ValueError, match="exactly one reuse report per leaf"):
        SessionEvidencePack(
            session_id="session-v3",
            problem_question="question",
            leaf_investigation_ids=["leaf-0"],
        )


def test_v4_binds_chunk_to_exact_leaf_inherited_allowlist() -> None:
    document = PackDocument(document_id="doc-1", title="One")
    report = PackLeafReuseReport(
        investigation_id="leaf-0",
        state="legacy_unqualified",
        injected_unit_count=1,
        injected_unit_ids=("unit-real-legacy",),
    )
    chunk = PackChunk(
        chunk_id="chunk-1",
        document_id="doc-1",
        text="Explicitly attested dependency",
        source_investigation_id="leaf-0",
        sub_question="question",
        inherited_unit_ids=("unit-real-legacy",),
    )
    pack = SessionEvidencePack(
        session_id="session-v4",
        problem_question="question",
        chunks=[chunk],
        documents=[document],
        leaf_investigation_ids=["leaf-0"],
        reuse_reports=[report],
    )
    assert pack.schema_version == 4
    assert pack.chunks[0].inherited_unit_ids == ("unit-real-legacy",)

    with pytest.raises(ValueError, match="unavailable inherited unit"):
        SessionEvidencePack(
            session_id="session-v4",
            problem_question="question",
            chunks=[chunk.model_copy(update={"inherited_unit_ids": ("unit-dropped",)})],
            documents=[document],
            leaf_investigation_ids=["leaf-0"],
            reuse_reports=[report],
        )

    with pytest.raises(ValueError, match="duplicate chunk_id"):
        SessionEvidencePack(
            session_id="session-v4",
            problem_question="question",
            chunks=[chunk, chunk.model_copy(update={"text": "foreign leaf collision"})],
            documents=[document],
            leaf_investigation_ids=["leaf-0"],
            reuse_reports=[report],
        )


def test_v3_rejects_new_chunk_lineage_without_changing_legacy_hash_shape() -> None:
    with pytest.raises(ValueError, match="schema v1-v3"):
        SessionEvidencePack(
            schema_version=3,
            session_id="legacy-v3",
            problem_question="question",
            chunks=[PackChunk(
                chunk_id="chunk-1",
                document_id="doc-1",
                text="claim",
                source_investigation_id="leaf-0",
                sub_question="question",
                inherited_unit_ids=("unit-1",),
            )],
            documents=[PackDocument(document_id="doc-1", title="One")],
            leaf_investigation_ids=["leaf-0"],
            reuse_reports=[PackLeafReuseReport(
                investigation_id="leaf-0",
                state="qualified",
                injected_unit_count=1,
                qualifications=(PackReusedUnitQualification(
                    unit_id="unit-1",
                    source_investigation_id="prior",
                    state="unknown",
                    source_successes=(0, 0, 0, 0),
                    total_leaves=0,
                    partial_leaf_count=0,
                ),),
            )],
        )


def _reuse_events(*, qualifications=None, reused=("unit-1",)):
    return [
        {
            "event_id": "ctx-1",
            "action_type": "context_pack.assembled",
            "payload": {},
        },
        {
            "event_id": "reuse-1",
            "parent_event_id": "ctx-1",
            "action_type": "knowledge.reused",
            "payload": {
                "reused_unit_ids": list(reused),
                "scores": [0.9 for _ in reused],
                "decisions": ["injected" for _ in reused],
                "source_investigation_ids": ["prior-1" for _ in reused],
                "context_pack_event_id": "ctx-1",
                "source_qualifications": qualifications,
            },
        },
    ]


def test_leaf_reuse_report_preserves_zero_legacy_and_v44_truth() -> None:
    assert _load_reuse_report("leaf", events=[]).state == "not_attempted"
    zero = _load_reuse_report("leaf", events=_reuse_events(reused=()))
    assert zero.state == "attempted_zero"
    legacy = _load_reuse_report("leaf", events=_reuse_events())
    assert legacy.state == "legacy_unqualified"
    qualified = _load_reuse_report("leaf", events=_reuse_events(qualifications=[{
        "unit_id": "unit-1",
        "source_investigation_id": "prior-1",
        "state": "partial",
        "source_successes": [1, 1, 0, 1],
        "total_leaves": 1,
        "partial_leaf_count": 1,
    }]))
    assert qualified.state == "qualified"
    assert qualified.qualifications[0].state == "partial"


def test_leaf_reuse_report_rejects_duplicate_or_unbound_event() -> None:
    events = _reuse_events()
    with pytest.raises(SessionEvidencePackError, match="at most one"):
        _load_reuse_report("leaf", events=[*events, events[-1]])
    events[0]["event_id"] = "different-context"
    with pytest.raises(SessionEvidencePackError, match="lacks its context pack event"):
        _load_reuse_report("leaf", events=events)
    events = _reuse_events()
    events[-1]["parent_event_id"] = "different-context"
    with pytest.raises(SessionEvidencePackError, match="lacks its context pack event"):
        _load_reuse_report("leaf", events=events)
    events = list(reversed(_reuse_events()))
    with pytest.raises(SessionEvidencePackError, match="lacks its context pack event"):
        _load_reuse_report("leaf", events=events)
    with pytest.raises(ValueError, match="legacy unqualified"):
        PackLeafReuseReport(
            investigation_id="leaf-0",
            state="legacy_unqualified",
            injected_unit_count=0,
        )


def test_leaf_reuse_report_rejects_substituted_qualified_source() -> None:
    with pytest.raises(SessionEvidencePackError, match="invalid knowledge reuse event"):
        _load_reuse_report("leaf", events=_reuse_events(qualifications=[{
            "unit_id": "unit-1",
            "source_investigation_id": "substituted-prior",
            "state": "unknown",
            "source_successes": [0, 0, 0, 0],
            "total_leaves": 0,
            "partial_leaf_count": 0,
        }]))


def _emit_multi_source_fixture(
    env: dict[str, str],
    *,
    account_id: str = "alice",
    session_id: str = "session",
    leaf_id: str = "leaf-0",
    document_id: str = "doc-1",
    unknown: bool = False,
) -> None:
    from runtime.db_lock import connect_write
    from substrate.event_log import emit_typed_authorized_strict, log_event_authorized

    events = Path(env["events"])
    session = InvestigationAuthority(account_id, session_id, events)
    leaf = InvestigationAuthority(account_id, leaf_id, events)
    initialize_composite_stream(session)
    initialize_composite_stream(leaf)
    log_event_authorized(
        session,
        "cascade.launched",
        payload={
            "plan_root_node_id": "root",
            "leaf_count": 1,
            "gather_receipt": {
                "gather_mode": "authorized_multi_source",
                "reviewed_gather_plan": {"fingerprint": "a" * 64},
            },
        },
        role="orchestrator",
    )
    statuses = ("unknown", "skipped", "skipped", "skipped") if unknown else (
        "succeeded", "succeeded", "failed", "succeeded"
    )
    report = GatherReportRecordedPayload(
        launch_fingerprint="a" * 64,
        plan_fingerprint="c" * 64,
        legal_policy_snapshot_sha256="b" * 64,
        receipts=tuple(
            GatherSourceReportReceipt(
                source=source,
                status=status,
                document_ids=(document_id,) if not unknown and index == 0 else (),
                provider_receipt_id="secret-provider-receipt" if index == 0 else None,
                failure_code="provider_error" if status == "failed" else None,
            )
            for index, (source, status) in enumerate(zip(
                ("exa", "parallel", "arxiv", "substack"), statuses, strict=True
            ))
        ),
        document_ids=() if unknown else (document_id,),
        minimum_evidence_documents=1,
        evidence_complete=not unknown,
        partial=not unknown,
        unknown_outcome=unknown,
    )
    emit_typed_authorized_strict(leaf, report, role="acquisition")
    if unknown:
        return
    with connect_write(env["db"], purpose="source_aware_pack_fixture") as con:
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope, metadata) "
            "VALUES ('insight-1', 'Durable evidence', 'insight', 'depth', ?)",
            [json.dumps({"chunk_id": "chunk-1", "source_document_id": document_id})],
        )
        con.execute(
            "INSERT INTO investigation_node_memberships "
            "(account_digest, investigation_digest, node_id, role, source_row_digest) "
            "VALUES (?, ?, 'insight-1', 'insight', ?)",
            [leaf.account_digest, leaf.investigation_digest, "d" * 64],
        )
    log_event_authorized(
        leaf,
        "graph.node.inserted",
        payload={
            "node_id": "insight-1",
            "canonical_label": "Durable evidence",
            "node_type": "insight",
            "graph_scope": "depth",
            "has_embedding": False,
        },
        role="user_agent",
    )


def test_builder_binds_durable_multi_source_launch_and_redacted_report(env) -> None:
    _emit_multi_source_fixture(env)
    kwargs = dict(
        session_id="session",
        owner_user_id="alice",
        events_dir=env["events"],
        db_path=env["db"],
        researches=[("leaf-0", "question")],
    )
    live = build_session_evidence_pack(**kwargs)
    restarted = build_session_evidence_pack(**kwargs)

    assert live.content_hash == restarted.content_hash
    assert live.gather_mode == "authorized_multi_source"
    assert live.gather_reports[0].plan_fingerprint == "c" * 64
    assert live.gather_reports[0].partial is True
    assert live.gather_reports[0].document_ids == ("doc-1",)
    assert "secret-provider-receipt" not in live.model_dump_json()
    assert "provider_error" in live.model_dump_json()


def test_builder_rejects_unknown_multi_source_outcome_before_synthesis(env) -> None:
    _emit_multi_source_fixture(env, unknown=True)
    with pytest.raises(SessionEvidencePackError, match="not synthesis-safe"):
        build_session_evidence_pack(
            "session",
            owner_user_id="alice",
            events_dir=env["events"],
            db_path=env["db"],
            researches=[("leaf-0", "question")],
        )


def test_builder_rejects_report_document_missing_from_authorized_pack(env) -> None:
    _emit_multi_source_fixture(env, document_id="doc-reported")
    # Remove the graph event's authorized membership: the typed report alone
    # cannot smuggle a document into synthesis.
    from runtime.db_lock import connect_write

    with connect_write(env["db"], purpose="remove_pack_membership") as con:
        con.execute("DELETE FROM investigation_node_memberships")
    with pytest.raises(SessionEvidencePackError, match="source-aware validation"):
        build_session_evidence_pack(
            "session",
            owner_user_id="alice",
            events_dir=env["events"],
            db_path=env["db"],
            researches=[("leaf-0", "question")],
        )


def test_builder_does_not_read_same_named_foreign_leaf_report(env) -> None:
    _emit_multi_source_fixture(
        env, account_id="bob", session_id="bob-session", leaf_id="shared-leaf"
    )
    from substrate.event_log import log_event_authorized

    alice_session = InvestigationAuthority("alice", "alice-session", Path(env["events"]))
    alice_leaf = InvestigationAuthority("alice", "shared-leaf", Path(env["events"]))
    initialize_composite_stream(alice_session)
    initialize_composite_stream(alice_leaf)
    log_event_authorized(
        alice_session,
        "cascade.launched",
        payload={
            "gather_receipt": {
                "gather_mode": "authorized_multi_source",
                "reviewed_gather_plan": {"fingerprint": "a" * 64},
            }
        },
        role="orchestrator",
    )
    with pytest.raises(SessionEvidencePackError, match="exactly one gather report"):
        build_session_evidence_pack(
            "alice-session",
            owner_user_id="alice",
            events_dir=env["events"],
            db_path=env["db"],
            researches=[("shared-leaf", "question")],
        )


def test_builder_rejects_malformed_typed_report_without_validation_prose(env) -> None:
    from substrate.event_log import log_event_authorized

    events = Path(env["events"])
    session = InvestigationAuthority("alice", "session", events)
    leaf = InvestigationAuthority("alice", "leaf", events)
    initialize_composite_stream(session)
    initialize_composite_stream(leaf)
    log_event_authorized(
        session,
        "cascade.launched",
        payload={
            "gather_receipt": {
                "gather_mode": "authorized_multi_source",
                "reviewed_gather_plan": {"fingerprint": "a" * 64},
            }
        },
        role="orchestrator",
    )
    malformed = GatherReportRecordedPayload(
        launch_fingerprint="a" * 64,
        plan_fingerprint="c" * 64,
        legal_policy_snapshot_sha256="b" * 64,
        receipts=tuple(
            GatherSourceReportReceipt(source=source, status="succeeded")
            for source in ("exa", "parallel", "arxiv", "substack")
        ),
        document_ids=(),
        minimum_evidence_documents=1,
        evidence_complete=False,
        partial=False,
        unknown_outcome=False,
    ).model_dump(mode="json")
    malformed["unknown_outcome"] = True
    log_event_authorized(
        leaf,
        "gather.report_recorded",
        payload=malformed,
        role="acquisition",
    )
    with pytest.raises(SessionEvidencePackError) as caught:
        build_session_evidence_pack(
            "session",
            owner_user_id="alice",
            events_dir=env["events"],
            db_path=env["db"],
            researches=[("leaf", "question")],
        )
    assert str(caught.value) == "leaf 'leaf' has invalid gather report"


@pytest.mark.asyncio
async def test_builder_from_hermetic_jsonl(env):
    """Hermetic cascade gather → pack with provenance-linked chunks."""
    bind_legacy_stream_lease(
        InvestigationAuthority(operator_claims().user_id, "session-1", Path(env["events"])),
        provenance="test_plan_start",
    )
    tree = build_plan("the problem", decomposer=_Dec(["sub one"])).tree
    root_id = persist_tree(
        tree,
        investigation_id="session-1",
        embedding_provider=_FakeEmbedding(),
        db_path=env["db"],
    )
    approve_plan(
        root_id,
        approver="operator",
        investigation_id="session-1",
        db_path=env["db"],
    )
    loaded = load_tree(root_id, db_path=env["db"])
    leaves = [
        Leaf(
            investigation_id="leaf-0",
            sub_question=c.question,
            question_node_id=c.graph_node_id,
        )
        for c in loaded.root.children
    ]

    funnel = PromotionFunnel(db_path=env["db"], embedding_provider=_FakeEmbedding())
    runner = HostLocalRunner(
        make_contract_gather_stub(steps=1, cost_per_step=0.01),
        claims=operator_claims(),
        events_dir=env["events"],
        seal_on_complete=False,
        on_emit=funnel.submit,
    )
    session = CascadeSession(
        "session-1",
        claims=operator_claims(),
        runner=runner,
        funnel=funnel,
        events_dir=env["events"],
        db_path=env["db"],
    )
    await session.launch(root_id, leaves)
    _ = [ev async for ev in session.stream()]
    await session.join_and_merge()

    pack = session.build_evidence_pack(plan_root_node_id=root_id)
    assert pack.session_id == "session-1"
    assert pack.problem_question == "the problem"
    assert pack.leaf_investigation_ids == ["leaf-0"]
    assert len(pack.chunks) >= 1
    assert len(pack.documents) >= 1
    for chunk in pack.chunks:
        assert any(d.document_id == chunk.document_id for d in pack.documents)
        doc = next(d for d in pack.documents if d.document_id == chunk.document_id)
        assert chunk.ip_holder_id == doc.ip_holder_id

    rebuilt = build_session_evidence_pack(
        "session-1",
        owner_user_id=operator_claims().user_id,
        events_dir=env["events"],
        db_path=env["db"],
        researches=[("leaf-0", "sub one")],
        plan_root_node_id=root_id,
    )
    assert rebuilt.content_hash == pack.content_hash


def test_authorized_event_cannot_smuggle_foreign_graph_node_into_pack(env):
    from runtime.db_lock import connect_write
    from substrate.event_log import log_event_authorized

    events = Path(env["events"])
    alice_leaf = InvestigationAuthority("alice", "alice-leaf", events)
    bob_leaf = InvestigationAuthority("bob", "bob-leaf", events)
    alice_session = InvestigationAuthority("alice", "alice-session", events)
    initialize_composite_stream(alice_leaf)
    initialize_composite_stream(bob_leaf)
    initialize_composite_stream(alice_session)
    con = connect_write(env["db"], purpose="foreign_evidence_fixture")
    try:
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope) "
            "VALUES ('bob-private-node', 'Bob private evidence', 'insight', 'depth')"
        )
        con.execute(
            "INSERT INTO investigation_node_memberships "
            "(account_digest, investigation_digest, node_id, role, source_row_digest) "
            "VALUES (?, ?, 'bob-private-node', 'insight', ?)",
            [bob_leaf.account_digest, bob_leaf.investigation_digest, "a" * 64],
        )
    finally:
        con.close()
    log_event_authorized(
        alice_leaf,
        "graph.node_inserted",
        payload={
            "node_id": "bob-private-node",
            "canonical_label": "forged public label",
            "node_type": "insight",
            "graph_scope": "depth",
            "has_embedding": False,
        },
        role="user_agent",
    )

    pack = build_session_evidence_pack(
        "alice-session",
        owner_user_id="alice",
        events_dir=env["events"],
        db_path=env["db"],
        researches=[("alice-leaf", "question")],
    )

    assert pack.chunks == []
    assert "Bob private evidence" not in str(pack.model_dump())


def test_strict_pack_rejects_provenance_free_derived_node(env, monkeypatch):
    from runtime.db_lock import connect_write
    from substrate.event_log import log_event_authorized

    monkeypatch.setenv("ANTIEK_LEGAL_READ_ENFORCEMENT", "1")
    events = Path(env["events"])
    leaf = InvestigationAuthority("alice", "alice-leaf", events)
    session = InvestigationAuthority("alice", "alice-session", events)
    initialize_composite_stream(leaf)
    initialize_composite_stream(session)
    with connect_write(env["db"], purpose="ungrounded_evidence_fixture") as con:
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope) "
            "VALUES ('derived-no-source', 'Derived secret', 'insight', 'depth')"
        )
        con.execute(
            "INSERT INTO investigation_node_memberships "
            "(account_digest, investigation_digest, node_id, role, source_row_digest) "
            "VALUES (?, ?, 'derived-no-source', 'insight', ?)",
            [leaf.account_digest, leaf.investigation_digest, "b" * 64],
        )
    log_event_authorized(
        leaf,
        "graph.node_inserted",
        payload={
            "node_id": "derived-no-source",
            "canonical_label": "Derived secret",
            "node_type": "insight",
            "graph_scope": "depth",
            "has_embedding": False,
        },
        role="user_agent",
    )

    pack = build_session_evidence_pack(
        "alice-session",
        owner_user_id="alice",
        events_dir=env["events"],
        db_path=env["db"],
        researches=[("alice-leaf", "question")],
    )

    assert pack.chunks == []
    assert "Derived secret" not in str(pack.model_dump())
