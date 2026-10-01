"""Fixed-candidate composite snapshot and cleanup controls."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Event
from types import SimpleNamespace
from typing import Any

import duckdb
import pytest

from processing.embedding.embed import HashEmbedding
from runtime.db_lock import connect_write
from substrate.context_pack.knowledge_reuse import retrieve_prior_units
from substrate.graph.insight_question import promote_insight
from substrate.graph.ops import insert_chunk, insert_node
from substrate.graph.retrieval_substrate import (
    SnapshotBusyError,
    make_substrate,
)
from substrate.graph.schema import init_database


class CountingHash(HashEmbedding):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def encode(self, text: str) -> list[float]:
        self.calls += 1
        return super().encode(text)


def _seed(path: str, model: CountingHash) -> str:
    text = "neutral atom qubit error rate suppression scaling milestone"
    con = connect_write(path, purpose="composite-snapshot-seed")
    try:
        init_database(con)
        con.execute("BEGIN")
        con.execute(
            "INSERT INTO documents (document_id,title,source_tier,document_type,content_class) "
            "VALUES ('doc-public','Public',1,'paper','public_domain')"
        )
        insert_chunk(
            con, chunk_id="chunk-public", document_id="doc-public", chunk_index=0,
            text=text, embedding=model.encode(text), embedding_provider=model,
            token_count=10,
        )
        claim = insert_node(
            con, canonical_label=f"claim {text}", node_type="claim", graph_scope="depth",
            investigation_id="previous", embedding=model.encode(text), on_conflict="ignore",
        )
        node = promote_insight(
            text=text, investigation_id="previous", confidence="high",
            supported_by=[claim], source_document_id="doc-public", chunk_id="chunk-public",
            embedding_provider=model, con=con,
        )
        con.execute("COMMIT")
        return node
    finally:
        con.close()


def test_real_reuse_materializes_on_one_snapshot_and_encodes_once(tmp_path, monkeypatch):
    import substrate.context_pack.knowledge_reuse as reuse

    path = str(tmp_path / "graph.duckdb")
    model = CountingHash()
    node = _seed(path, model)
    model.calls = 0
    sub = make_substrate("brute_force", path, model=model)
    original = reuse._materialize_prior_units_from_snapshot
    seen: list[Any] = []

    def checked(snapshot: Any, **kwargs: Any):
        seen.append(snapshot.con)
        assert snapshot.query_vector is not None
        assert snapshot.con.execute("SELECT title FROM documents WHERE document_id='doc-public'").fetchone() == ("Public",)
        return original(snapshot, **kwargs)

    monkeypatch.setattr(reuse, "_materialize_prior_units_from_snapshot", checked)
    try:
        units = retrieve_prior_units(sub, question_text="neutral atom qubit error rate suppression")
        assert [unit.unit_id for unit in units] == [node]
        assert units[0].content_class == "public_domain"
        assert units[0].unit.provenance.source_document_id == "doc-public"
        assert seen == [sub._con]
        assert model.calls == 1
    finally:
        sub.close()


def test_missing_snapshot_capability_and_blank_input_do_no_work():
    class QueryOnly:
        def __getattribute__(self, name: str):
            if name in {"query", "_con", "_model"}:
                raise AssertionError(f"unexpected access: {name}")
            return object.__getattribute__(self, name)

    assert retrieve_prior_units(QueryOnly(), question_text="topic") == []
    assert retrieve_prior_units(QueryOnly(), question_text="  ") == []


@pytest.mark.parametrize("stage", ["create", "enter", "body", "exit"])
def test_entry_failure_degrades_but_entered_failure_propagates(stage, monkeypatch):
    import substrate.context_pack.knowledge_reuse as reuse

    class Fake:
        def query_snapshot(self, *_args, **_kwargs):
            if stage == "create":
                raise RuntimeError("create failed")

            @contextmanager
            def lease():
                if stage == "enter":
                    raise RuntimeError("enter failed")
                yield SimpleNamespace(query_vector=(1.0,), result={}, con=object())
                if stage == "exit":
                    raise RuntimeError("commit failed")

            return lease()

    if stage == "body":
        def fail(*_args, **_kwargs):
            raise RuntimeError("dependent SQL failed")
        monkeypatch.setattr(reuse, "_materialize_prior_units_from_snapshot", fail)
    elif stage == "exit":
        monkeypatch.setattr(reuse, "_materialize_prior_units_from_snapshot", lambda *_args, **_kwargs: [])
    if stage in {"create", "enter"}:
        assert retrieve_prior_units(Fake(), question_text="topic") == []
    else:
        with pytest.raises(RuntimeError, match="dependent SQL|commit failed"):
            retrieve_prior_units(Fake(), question_text="topic")


def test_skipped_snapshot_does_not_read_dependent_state(monkeypatch):
    import substrate.context_pack.knowledge_reuse as reuse

    @contextmanager
    def lease():
        yield SimpleNamespace(
            query_vector=None,
            result={"status": "benchmark-failed", "results": []},
            con=object(),
        )

    monkeypatch.setattr(
        reuse, "_materialize_prior_units_from_snapshot",
        lambda *_args, **_kwargs: pytest.fail("dependent read after skipped query"),
    )
    sub = SimpleNamespace(query_snapshot=lambda *_args, **_kwargs: lease())
    assert retrieve_prior_units(sub, question_text="topic") == []


def test_lazy_busy_close_retries_without_closing_parent(monkeypatch):
    import interfaces.research.api.cascade_routes as routes
    import substrate.graph.retrieval_substrate as retrieval

    calls: list[str] = []

    class Parent:
        def close(self):
            calls.append("parent")

    class Inner:
        def __init__(self):
            self.attempts = 0

        def close(self):
            self.attempts += 1
            calls.append("child")
            if self.attempts == 1:
                raise SnapshotBusyError("busy")

    parent, inner = Parent(), Inner()
    monkeypatch.setattr(duckdb, "connect", lambda _path: parent)
    monkeypatch.setattr(retrieval, "resolve_reuse_substrate_kind", lambda: "brute_force")
    monkeypatch.setattr(retrieval, "make_substrate_from_con", lambda *_args, **_kwargs: inner)
    lazy = routes._LazyReuseSubstrate("unused", object())
    assert lazy._ensure() is inner
    with pytest.raises(SnapshotBusyError):
        lazy.close()
    assert calls == ["child"]
    assert lazy._ensure() is inner
    lazy.close()
    lazy.close()
    assert calls == ["child", "child", "parent"]


def test_lazy_terminal_close_never_claims_later_noop_success(monkeypatch):
    import interfaces.research.api.cascade_routes as routes
    import substrate.graph.retrieval_substrate as retrieval

    calls: list[str] = []

    class Parent:
        def close(self):
            calls.append("parent")

    class Inner:
        def close(self):
            calls.append("child")
            raise OSError("uncertain")

    monkeypatch.setattr(duckdb, "connect", lambda _path: Parent())
    monkeypatch.setattr(retrieval, "resolve_reuse_substrate_kind", lambda: "brute_force")
    monkeypatch.setattr(retrieval, "make_substrate_from_con", lambda *_args, **_kwargs: Inner())
    lazy = routes._LazyReuseSubstrate("unused", object())
    lazy._ensure()
    with pytest.raises(OSError, match="uncertain"):
        lazy.close()
    with pytest.raises(RuntimeError, match="uncertain"):
        lazy.close()
    with pytest.raises(RuntimeError, match="uncertain"):
        lazy._ensure()
    assert calls == ["child"]


def test_throwing_snapshot_descriptor_is_pre_entry_failure():
    class Missing:
        @property
        def query_snapshot(self):
            raise RuntimeError("capability construction failed")

        @property
        def _con(self):
            pytest.fail("private handle must not be inspected")

    assert retrieve_prior_units(Missing(), question_text="topic") == []


def _flywheel_fakes(
    monkeypatch, path: str, close_errors: list[Exception],
    *, close_started: Event | None = None, close_release: Event | None = None,
    vector: tuple[float, ...] | None = None,
):
    import runtime.db_lock as db_lock
    import substrate.context_pack.knowledge_reuse as reuse
    import substrate.flywheel.investigation_start_reuse as flywheel
    import substrate.graph.retrieval_substrate as retrieval

    flywheel._PENDING_REUSE_CLEANUP.clear()
    opens: list[Any] = []
    registrations: list[str] = []

    class Parent:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    class Child:
        def __init__(self):
            self.closed = False

        @contextmanager
        def query_snapshot(self, *_args, **_kwargs):
            yield SimpleNamespace(
                query_vector=vector,
                result={"status": "benchmark-failed" if vector is None else "shadow"},
                con=object(),
            )

        def close(self):
            if close_started is not None:
                close_started.set()
                assert close_release is not None and close_release.wait(timeout=5)
            if close_errors:
                raise close_errors.pop(0)
            self.closed = True

    def connect(_path):
        pair = Parent(), Child()
        opens.append(pair)
        return pair[0]

    monkeypatch.setattr(duckdb, "connect", connect)
    monkeypatch.setattr(db_lock, "_register_local_writer", lambda db: registrations.append(db))
    monkeypatch.setattr(db_lock, "_unregister_local_writer", lambda db: registrations.remove(db))
    monkeypatch.setattr(retrieval, "resolve_reuse_substrate_kind", lambda: "brute_force")
    monkeypatch.setattr(
        retrieval, "make_substrate_from_con",
        lambda _kind, parent, **_kwargs: next(child for p, child in opens if p is parent),
    )
    monkeypatch.setattr(reuse, "assemble_context_pack_with_reuse", lambda **_kwargs: SimpleNamespace(reuse_event_id="event"))
    return flywheel, opens, registrations


def test_flywheel_busy_cleanup_is_retained_then_retried_before_new_open(tmp_path, monkeypatch):
    from substrate.graph.retrieval_substrate import SnapshotBusyError

    path = str(tmp_path / "private.duckdb")
    flywheel, opens, registrations = _flywheel_fakes(
        monkeypatch, path, [SnapshotBusyError("busy"), SnapshotBusyError("busy")]
    )
    def run():
        return flywheel.maybe_reuse_prior_knowledge_at_start(
            investigation_id="test", question_text="topic", db_path=path,
            events_dir=str(tmp_path / "events"), embedding_provider=object(),
        )

    try:
        assert run() is None
        identity = str(tmp_path / "private.duckdb")
        assert flywheel._PENDING_REUSE_CLEANUP[identity].parent is opens[0][0]
        assert registrations == [path]
        assert run() is None  # second busy retry, no second handle
        assert len(opens) == 1
        assert not opens[0][0].closed
        assert run() == "event"  # prior cleanup succeeds, then a new handle opens
        assert len(opens) == 2
        assert opens[0][0].closed and opens[1][0].closed
        assert registrations == []
        assert identity not in flywheel._PENDING_REUSE_CLEANUP
    finally:
        flywheel._PENDING_REUSE_CLEANUP.clear()


def test_flywheel_terminal_cleanup_refuses_new_work_and_retains_refs(tmp_path, monkeypatch):
    path = str(tmp_path / "private.duckdb")
    flywheel, opens, registrations = _flywheel_fakes(monkeypatch, path, [OSError("uncertain")])
    def run():
        return flywheel.maybe_reuse_prior_knowledge_at_start(
            investigation_id="test", question_text="topic", db_path=path,
            events_dir=str(tmp_path / "events"), embedding_provider=object(),
        )

    try:
        assert run() is None
        state = flywheel._PENDING_REUSE_CLEANUP[path]
        assert state.terminal
        assert state.parent is opens[0][0] and state.child is opens[0][1]
        assert run() is None
        assert len(opens) == 1 and registrations == [path]
        assert not opens[0][0].closed
    finally:
        flywheel._PENDING_REUSE_CLEANUP.clear()


def test_same_db_overlapping_reuse_cannot_drop_failed_cleanup(tmp_path, monkeypatch):
    path = str(tmp_path / "same.duckdb")
    close_started, close_release = Event(), Event()
    flywheel, opens, registrations = _flywheel_fakes(
        monkeypatch, path, [OSError("terminal close")],
        close_started=close_started, close_release=close_release,
    )
    def run():
        return flywheel.maybe_reuse_prior_knowledge_at_start(
            investigation_id="overlap", question_text="topic", db_path=path,
            events_dir=str(tmp_path / "events"), embedding_provider=object(),
        )

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(run)
            assert close_started.wait(timeout=5)
            second = pool.submit(run)
            close_release.set()
            assert first.result(timeout=5) is None
            assert second.result(timeout=5) is None
        state = flywheel._PENDING_REUSE_CLEANUP[path]
        assert state.terminal and state.parent is opens[0][0]
        assert state.child is opens[0][1]
        assert len(opens) == 1 and registrations == [path]
    finally:
        close_release.set()
        flywheel._PENDING_REUSE_CLEANUP.clear()


def test_flywheel_index_candidate_and_supplement_share_child_lease(tmp_path, monkeypatch):
    import substrate.companions.evidence_index as index
    import substrate.context_pack.knowledge_reuse as reuse
    import substrate.flywheel.investigation_start_reuse as flywheel
    import substrate.graph.retrieval_substrate as retrieval

    path = str(tmp_path / "graph.duckdb")
    model = CountingHash()
    node = _seed(path, model)
    model.calls = 0
    observed: dict[str, Any] = {}
    materialize = reuse._materialize_prior_units_from_snapshot
    supplement = flywheel._supplement_units_from_index

    def index_lookup(con, **_kwargs):
        observed["index_con"] = con
        return [node]

    def materialize_on_child(snapshot, **kwargs):
        observed["materialize_con"] = snapshot.con
        observed["vector"] = snapshot.query_vector
        units = materialize(snapshot, **kwargs)
        assert [unit.unit_id for unit in units] == [node]
        return units

    def supplement_on_child(con, vector, units, node_ids):
        assert node_ids == [node]
        observed["supplement_con"] = con
        observed["supplement_vector"] = vector
        return supplement(con, vector, units, node_ids)

    monkeypatch.setattr(retrieval, "resolve_reuse_substrate_kind", lambda: "brute_force")
    monkeypatch.setattr(index, "query_claim_node_ids", index_lookup)
    monkeypatch.setattr(reuse, "_materialize_prior_units_from_snapshot", materialize_on_child)
    monkeypatch.setattr(flywheel, "_supplement_units_from_index", supplement_on_child)
    event_id = flywheel.maybe_reuse_prior_knowledge_at_start(
        investigation_id="new", question_text="neutral atom qubit error rate suppression",
        db_path=path, events_dir=str(tmp_path / "events"), embedding_provider=model,
    )
    assert event_id
    assert observed["index_con"] is observed["materialize_con"]
    assert observed["supplement_con"] is observed["materialize_con"]
    assert observed["supplement_vector"] is observed["vector"]
    assert model.calls == 1
    assert path not in flywheel._PENDING_REUSE_CLEANUP


@pytest.mark.parametrize("kind", ["brute_force", "vss"])
def test_composite_bf_and_vss_return_actual_grounded_unit(tmp_path, kind):
    from substrate.graph.retrieval_substrate import DuckDbVssSubstrate

    path = str(tmp_path / "graph.duckdb")
    model = CountingHash()
    node = _seed(path, model)
    model.calls = 0
    sub = (
        make_substrate("brute_force", path, model=model)
        if kind == "brute_force"
        else DuckDbVssSubstrate(duckdb.connect(path), model=model, vss_active=False)
    )
    try:
        units = retrieve_prior_units(
            sub, question_text="neutral atom qubit error rate suppression",
        )
        assert [unit.unit_id for unit in units] == [node]
        assert units[0].unit.provenance.source_document_id == "doc-public"
        assert units[0].content_class == "public_domain"
        assert model.calls == 1
    finally:
        sub.close()


def test_tp_remote_and_degraded_local_both_materialize_composite_units(tmp_path):
    from substrate.graph.retrieval_adapters.turbopuffer import TurbopufferSubstrate

    path = str(tmp_path / "graph.duckdb")
    model = CountingHash()
    node = _seed(path, model)
    model.calls = 0

    class Namespace:
        def __init__(self):
            self.calls = 0
            self.error = False

        def multi_query(self, **_kwargs):
            self.calls += 1
            if self.error:
                raise RuntimeError("synthetic vendor outage")
            return SimpleNamespace(
                results=[SimpleNamespace(rows=[SimpleNamespace(id="chunk-public")])]
            )

    namespace = Namespace()
    sub = TurbopufferSubstrate.open(
        path, model=model, api_key="synthetic", namespace=namespace,
    )
    original = sub.query_snapshot
    statuses: list[str] = []

    @contextmanager
    def observed(*args, **kwargs):
        with original(*args, **kwargs) as snapshot:
            statuses.append(snapshot.result["status"])
            yield snapshot

    sub.query_snapshot = observed
    try:
        remote = retrieve_prior_units(
            sub, question_text="neutral atom qubit error rate suppression",
        )
        namespace.error = True
        degraded = retrieve_prior_units(
            sub, question_text="neutral atom qubit error rate suppression",
        )
        assert [unit.unit_id for unit in remote] == [node]
        assert [unit.unit_id for unit in degraded] == [node]
        assert all(unit.content_class == "public_domain" for unit in remote + degraded)
        assert statuses[0] in {"shadow", "servable"}
        assert statuses[1] == "degraded — brute_force"
        assert namespace.calls == 2
        assert model.calls == 2
    finally:
        sub.close()


def test_cascade_success_registers_session_despite_reuse_close_fault(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import interfaces.research.api.cascade_routes as routes
    from interfaces.research.api.app import create_app

    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "cascade.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    monkeypatch.setattr(routes, "_embedding_provider", CountingHash)
    routes._SESSIONS.clear()
    routes._SESSION_TASKS.clear()

    class Reuse:
        name = "brute_force"
        closes = 0

        @contextmanager
        def query_snapshot(self, *_args, **_kwargs):
            yield SimpleNamespace(query_vector=None, result={"status": "benchmark-failed"}, con=object())

        def close(self):
            self.closes += 1
            raise OSError("synthetic cleanup uncertainty")

    reuse = Reuse()
    monkeypatch.setattr(routes, "_reuse_substrate", lambda _model: reuse)
    client = TestClient(create_app(register_wrestling=False, register_providers=False, cors_origins=[]))
    plan = client.post("/research/plans", json={"problem": "P", "sub_questions": ["topic"]})
    assert plan.status_code == 200, plan.text
    root = plan.json()["root_node_id"]
    approved = client.post(f"/research/plans/{root}/approve", json={"approver": "operator"})
    assert approved.status_code == 200, approved.text
    response = client.post(f"/research/plans/{root}/launch", json={"per_research_budget_usd": 1.0})
    assert response.status_code == 200, response.text
    session_id = response.json()["session_id"]
    assert session_id in routes._SESSIONS
    assert session_id in routes._SESSION_TASKS
    assert session_id not in routes._HARD_CEILING_LAUNCHING
    assert reuse.closes >= 1


def test_cascade_primary_launch_error_keeps_cleanup_note_and_discards_flag(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import interfaces.research.api.cascade_routes as routes
    from interfaces.research.api.app import create_app

    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "cascade.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    monkeypatch.setattr(routes, "_embedding_provider", CountingHash)
    routes._SESSIONS.clear()
    routes._SESSION_TASKS.clear()

    class Reuse:
        name = "brute_force"

        def close(self):
            raise OSError("synthetic cleanup uncertainty")

    async def failed_launch(self, _root, _leaves):
        raise RuntimeError("primary launch failure")

    monkeypatch.setattr(routes, "_reuse_substrate", lambda _model: Reuse())
    monkeypatch.setattr(routes.CascadeSession, "launch", failed_launch)
    client = TestClient(create_app(register_wrestling=False, register_providers=False, cors_origins=[]))
    plan = client.post("/research/plans", json={"problem": "P", "sub_questions": ["topic"]})
    assert plan.status_code == 200, plan.text
    root = plan.json()["root_node_id"]
    approved = client.post(f"/research/plans/{root}/approve", json={"approver": "operator"})
    assert approved.status_code == 200, approved.text
    session_id = f"session-{root}"
    routes._HARD_CEILING_LAUNCHING.add(session_id)
    with pytest.raises(RuntimeError, match="primary launch failure") as captured:
        client.post(f"/research/plans/{root}/launch", json={"per_research_budget_usd": 1.0})
    assert any("cleanup" in note for note in captured.value.__notes__)
    assert session_id not in routes._HARD_CEILING_LAUNCHING
    assert session_id not in routes._SESSIONS


def test_flywheel_event_waits_for_confirmed_child_and_parent_close(tmp_path, monkeypatch):
    import substrate.context_pack.knowledge_reuse as reuse

    path = str(tmp_path / "ordered.duckdb")
    flywheel, opens, registrations = _flywheel_fakes(monkeypatch, path, [])
    assembled: list[str] = []

    def assemble(**_kwargs):
        assert len(opens) == 1
        assert opens[0][1].closed and opens[0][0].closed
        assert registrations == []
        assembled.append("event")
        return SimpleNamespace(reuse_event_id="ordered-event")

    monkeypatch.setattr(reuse, "assemble_context_pack_with_reuse", assemble)
    result = flywheel.maybe_reuse_prior_knowledge_at_start(
        investigation_id="ordered", question_text="topic", db_path=path,
        events_dir=str(tmp_path / "events"), embedding_provider=object(),
    )
    assert result == "ordered-event"
    assert assembled == ["event"]


def test_flywheel_entered_sql_failure_emits_no_partial_event(tmp_path, monkeypatch):
    import substrate.companions.evidence_index as index
    import substrate.context_pack.knowledge_reuse as reuse

    path = str(tmp_path / "sql-fault.duckdb")
    flywheel, opens, registrations = _flywheel_fakes(
        monkeypatch, path, [], vector=(1.0,)
    )
    monkeypatch.setattr(index, "query_claim_node_ids", lambda *_args, **_kwargs: [])

    def fail_materialize(*_args, **_kwargs):
        raise RuntimeError("dependent SQL failed")

    monkeypatch.setattr(reuse, "_materialize_prior_units_from_snapshot", fail_materialize)
    monkeypatch.setattr(
        reuse, "assemble_context_pack_with_reuse",
        lambda **_kwargs: pytest.fail("event after dependent SQL failure"),
    )
    result = flywheel.maybe_reuse_prior_knowledge_at_start(
        investigation_id="fault", question_text="topic", db_path=path,
        events_dir=str(tmp_path / "events"), embedding_provider=object(),
    )
    assert result is None
    assert opens[0][1].closed and opens[0][0].closed
    assert registrations == []
    assert path not in flywheel._PENDING_REUSE_CLEANUP


def test_cli_child_closes_before_pack_while_parent_remains_owned(tmp_path, monkeypatch):
    import substrate.context_pack.knowledge_reuse as reuse
    import substrate.graph.retrieval_substrate as retrieval
    import tools.run_investigation as cli

    path = str(tmp_path / "cli.duckdb")
    model = CountingHash()
    node = _seed(path, model)
    parent = duckdb.connect(path)
    children: list[Any] = []
    factory = retrieval.make_substrate_from_con
    assemble = reuse.assemble_context_pack_with_reuse

    def record_child(*args, **kwargs):
        child = factory(*args, **kwargs)
        children.append(child)
        return child

    def verify_assembly(**kwargs):
        assert [unit.unit_id for unit in kwargs["units"]] == [node]
        assert len(children) == 1 and children[0]._snapshot_closed
        assert parent.execute("SELECT 1").fetchone() == (1,)
        return assemble(**kwargs)

    monkeypatch.setattr(retrieval, "make_substrate_from_con", record_child)
    monkeypatch.setattr(reuse, "assemble_context_pack_with_reuse", verify_assembly)
    try:
        count, injected, _ids = cli._reuse_step(
            parent, reuse_question="neutral atom qubit error rate suppression",
            investigation_id="cli", events_dir=str(tmp_path / "events"),
            embedding_provider=model,
        )
        assert count == 1 and injected
    finally:
        parent.close()


def test_real_writer_change_between_candidate_and_projection_keeps_one_snapshot(tmp_path, monkeypatch):
    import substrate.context_pack.knowledge_reuse as reuse
    from substrate.graph.retrieval_substrate import make_substrate_from_con

    path = str(tmp_path / "interleave.duckdb")
    model = CountingHash()
    node = _seed(path, model)
    parent = duckdb.connect(path)
    sub = make_substrate_from_con("brute_force", parent, model=model)
    original = reuse._materialize_prior_units_from_snapshot
    changes: list[tuple[str, str]] = []

    def interleave(snapshot, **kwargs):
        writer = duckdb.connect(path)
        try:
            writer.execute("BEGIN")
            writer.execute(
                "UPDATE documents SET title='After', content_class='opt_in_licensed' "
                "WHERE document_id='doc-public'"
            )
            writer.execute("COMMIT")
            changes.append(writer.execute(
                "SELECT title,content_class FROM documents WHERE document_id='doc-public'"
            ).fetchone())
        finally:
            writer.close()
        assert snapshot.con.execute(
            "SELECT title,content_class FROM documents WHERE document_id='doc-public'"
        ).fetchone() == ("Public", "public_domain")
        return original(snapshot, **kwargs)

    monkeypatch.setattr(reuse, "_materialize_prior_units_from_snapshot", interleave)
    try:
        before = retrieve_prior_units(
            sub, question_text="neutral atom qubit error rate suppression",
        )
        assert changes == [("After", "opt_in_licensed")]
        assert [unit.unit_id for unit in before] == [node]
        assert before[0].content_class == "public_domain"
        monkeypatch.setattr(reuse, "_materialize_prior_units_from_snapshot", original)
        after = retrieve_prior_units(
            sub, question_text="neutral atom qubit error rate suppression",
        )
        assert [unit.unit_id for unit in after] == [node]
        assert after[0].content_class == "opt_in_licensed"
    finally:
        sub.close()
        parent.close()


class FaultingConnection:
    def __init__(self, con, needle: str):
        self.con = con
        self.needle = needle
        self.triggered = False
        self.faulted_sql: str | None = None
        self.rolled_back = False

    def execute(self, sql, *args):
        if sql == "ROLLBACK":
            self.rolled_back = True
        if self.needle in sql:
            self.triggered = True
            self.faulted_sql = sql
            raise RuntimeError("synthetic dependent SQL fault")
        return self.con.execute(sql, *args)

    def __getattr__(self, name):
        return getattr(self.con, name)


@pytest.mark.parametrize(
    ("needle", "source_document_id"),
    [
        ("AS content_class_of_unit", None),
        ("json_extract_string(metadata, '$.source_document_id')", "doc-public"),
    ],
)
def test_real_main_and_same_doc_sql_faults_rollback_without_partial_units(
    tmp_path, needle, source_document_id,
):
    from substrate.graph.retrieval_substrate import make_substrate_from_con

    path = str(tmp_path / "fault.duckdb")
    model = CountingHash()
    _seed(path, model)
    parent = duckdb.connect(path)
    sub = make_substrate_from_con("brute_force", parent, model=model)
    fault = FaultingConnection(sub._con, needle)
    sub._con = fault
    try:
        with pytest.raises(RuntimeError, match="synthetic dependent SQL fault"):
            retrieve_prior_units(
                sub, question_text="neutral atom qubit error rate suppression",
                source_document_id=source_document_id,
            )
        assert fault.triggered and fault.rolled_back
    finally:
        sub.close()
        parent.close()


def test_real_same_doc_similarity_sql_fault_is_not_score_zero_fallback(
    tmp_path, monkeypatch,
):
    import substrate.graph.insight_question as insight
    from substrate.graph.retrieval_substrate import make_substrate_from_con

    path = str(tmp_path / "similarity.duckdb")
    model = CountingHash()
    _seed(path, model)
    parent = duckdb.connect(path)
    sub = make_substrate_from_con("brute_force", parent, model=model)
    fault = FaultingConnection(sub._con, "SELECT (list_dot_product(embedding")
    sub._con = fault
    original = insight.knowledge_unit_of
    projected = 0
    completed = 0

    def first_vanishes(*args, **kwargs):
        nonlocal projected, completed
        projected += 1
        if projected == 1:
            raise ValueError("synthetic first projection vanished")
        unit = original(*args, **kwargs)
        completed += 1
        return unit

    monkeypatch.setattr(insight, "knowledge_unit_of", first_vanishes)
    try:
        with pytest.raises(RuntimeError, match="synthetic dependent SQL fault"):
            retrieve_prior_units(
                sub, question_text="neutral atom qubit error rate suppression",
                source_document_id="doc-public",
            )
        assert projected == 2 and completed == 1
        assert fault.triggered and fault.rolled_back
        assert fault.faulted_sql is not None
        assert fault.faulted_sql.startswith("SELECT (list_dot_product(embedding")
        assert "FROM nodes WHERE node_id = ?" in fault.faulted_sql
    finally:
        sub.close()
        parent.close()


def test_supplement_metadata_sql_fault_propagates_without_partial_result(tmp_path):
    from substrate.flywheel.investigation_start_reuse import _supplement_units_from_index

    path = str(tmp_path / "supplement.duckdb")
    model = CountingHash()
    node = _seed(path, model)
    con = duckdb.connect(path)
    fault = FaultingConnection(con, "SELECT d.content_class")
    try:
        with pytest.raises(RuntimeError, match="synthetic dependent SQL fault"):
            _supplement_units_from_index(
                fault, tuple(model.encode("neutral atom qubit error rate suppression")),
                [], [node],
            )
        assert fault.triggered
    finally:
        con.close()


def test_lazy_factory_failure_closes_local_parent_and_can_retry(monkeypatch):
    import interfaces.research.api.cascade_routes as routes
    import substrate.graph.retrieval_substrate as retrieval

    parents: list[Any] = []
    calls = 0

    class Parent:
        closed = False

        def close(self):
            self.closed = True

    class Child:
        def close(self):
            pass

    def connect(_path):
        parent = Parent()
        parents.append(parent)
        return parent

    def factory(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("factory failed")
        return Child()

    monkeypatch.setattr(duckdb, "connect", connect)
    monkeypatch.setattr(retrieval, "resolve_reuse_substrate_kind", lambda: "brute_force")
    monkeypatch.setattr(retrieval, "make_substrate_from_con", factory)
    lazy = routes._LazyReuseSubstrate("unused", object())
    with pytest.raises(RuntimeError, match="factory failed"):
        lazy._ensure()
    assert parents[0].closed and lazy._parent is None and lazy._inner is None
    assert isinstance(lazy._ensure(), Child)
    lazy.close()
    assert parents[1].closed


def test_lazy_factory_and_parent_cleanup_fail_keeps_primary_and_terminal_ref(monkeypatch):
    import interfaces.research.api.cascade_routes as routes
    import substrate.graph.retrieval_substrate as retrieval

    class Parent:
        def close(self):
            raise OSError("parent cleanup failed")

    parent = Parent()
    monkeypatch.setattr(duckdb, "connect", lambda _path: parent)
    monkeypatch.setattr(retrieval, "resolve_reuse_substrate_kind", lambda: "brute_force")

    def factory(*_args, **_kwargs):
        raise RuntimeError("primary factory failure")

    monkeypatch.setattr(retrieval, "make_substrate_from_con", factory)
    lazy = routes._LazyReuseSubstrate("unused", object())
    with pytest.raises(RuntimeError, match="primary factory failure") as captured:
        lazy._ensure()
    assert any("parent cleanup failed" in note for note in captured.value.__notes__)
    assert lazy._parent is parent and lazy._inner is None
    with pytest.raises(RuntimeError, match="uncertain"):
        lazy._ensure()
    with pytest.raises(RuntimeError, match="uncertain"):
        lazy.close()


def test_lazy_parent_close_failure_is_terminal_after_child_success(monkeypatch):
    import interfaces.research.api.cascade_routes as routes
    import substrate.graph.retrieval_substrate as retrieval

    child_closes = 0

    class Parent:
        def close(self):
            raise OSError("parent close uncertain")

    class Child:
        def close(self):
            nonlocal child_closes
            child_closes += 1

    parent = Parent()
    monkeypatch.setattr(duckdb, "connect", lambda _path: parent)
    monkeypatch.setattr(retrieval, "resolve_reuse_substrate_kind", lambda: "brute_force")
    monkeypatch.setattr(retrieval, "make_substrate_from_con", lambda *_args, **_kwargs: Child())
    lazy = routes._LazyReuseSubstrate("unused", object())
    lazy._ensure()
    with pytest.raises(OSError, match="parent close uncertain"):
        lazy.close()
    assert child_closes == 1 and lazy._inner is None and lazy._parent is parent
    with pytest.raises(RuntimeError, match="uncertain"):
        lazy.close()
    with pytest.raises(RuntimeError, match="uncertain"):
        lazy._ensure()
    assert child_closes == 1
