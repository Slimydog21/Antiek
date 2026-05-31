"""Monitoring mode tests (Personal-Reading Lane SPR-09).

Covers the four milestones + the verification gates:

* Monitor CRUD round-trips (idempotent re-create).
* Resumable refresh — surfaced once, no duplicates; checkpoint advances.
* Lane isolation — refresh returns only personal_reading.
* Puttering feed — full body on owner path, every item non-attributable.
* Body invisible to the public search gate.

No live network; temp DuckDB + a deterministic stub EmbeddingModel,
mirroring tests/test_personal_lane_read_side.py and
tests/test_continuous_daemon.py.

Connection discipline: monitor calls are made with ``con=None, path=temp_db``
so each call opens (and closes) its OWN short-lived connection. We never hold
a read connection open across a write to the same DuckDB file in one process
(that can make the writer attach a fresh empty catalog).
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import inspect
import os
import uuid

import pytest

from runtime.db_lock import connect_write
from substrate.graph.schema import init_database_at_path
from substrate.graph import ops
from substrate.graph.search import search
from substrate.collective_graph.eligibility import (
    CollectiveGraphDocument,
    is_attribution_eligible,
)
from orchestration.monitoring import monitor as mon


class _StubEmbedding:
    """Deterministic stub: hashes tokens into a fixed-dim vector via a STABLE
    hash (sha256), so the embedding is reproducible across processes (unlike
    builtin hash(), which is salted per-process)."""

    dimension = 8

    def encode(self, text: str) -> list[float]:
        vec = [0.0] * self.dimension
        for i, tok in enumerate(text.lower().split()):
            h = int(hashlib.sha256(tok.encode()).hexdigest(), 16)
            vec[i % self.dimension] += (h % 1000) / 1000.0
        return vec


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "g.duckdb")
    events_dir = str(tmp_path / "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    init_database_at_path(db_path)
    yield db_path


def _seed_doc(
    db_path,
    *,
    content_class,
    acquired_at,
    text="alpha beta gamma",
    title="A thread doc",
    with_chunk=True,
):
    """Insert one document (and optionally an embedded chunk) at a given
    acquired_at. Returns the document_id. Opens and closes its own writer."""
    doc_id = str(uuid.uuid4())
    model = _StubEmbedding()
    with connect_write(db_path) as con:
        # insert_document does not expose acquired_at (the schema DEFAULTs it to
        # CURRENT_TIMESTAMP); set it explicitly so the since-checkpoint boundary
        # is deterministic.
        ops.insert_document(
            con,
            document_id=doc_id,
            source_tier=4,
            title=title,
            document_type="web_article",
            raw_text=text,
            content_class=content_class,
        )
        con.execute(
            "UPDATE documents SET acquired_at = ? WHERE document_id = ?",
            [acquired_at, doc_id],
        )
        if with_chunk:
            ops.insert_chunk(
                con,
                document_id=doc_id,
                chunk_index=0,
                text=text,
                embedding=model.encode(text),
            )
    return doc_id


def _ts(offset_seconds: int) -> str:
    """A deterministic ISO timestamp relative to a fixed base (in the past)."""
    base = _dt.datetime(2026, 1, 1, 0, 0, 0, tzinfo=_dt.timezone.utc)
    return (base + _dt.timedelta(seconds=offset_seconds)).isoformat()


def _future(offset_seconds: int = 0) -> str:
    """A timestamp guaranteed to be AFTER a just-created monitor's checkpoint."""
    base = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(hours=1)
    return (base + _dt.timedelta(seconds=offset_seconds)).isoformat()


# ---------------------------------------------------------------------------
# Milestone 1 — Monitor CRUD
# ---------------------------------------------------------------------------


def test_monitor_create_list_delete(temp_db):
    model = _StubEmbedding()
    d1 = _seed_doc(temp_db, content_class="personal_reading", acquired_at=_ts(0),
                   text="quantum computing photonics", title="Quantum photonics")
    d2 = _seed_doc(temp_db, content_class="personal_reading", acquired_at=_ts(1),
                   text="error correction qubits", title="Error correction")

    m = mon.create_monitor(
        None, investigation_id="inv-1", model=model,
        document_ids=[d1, d2], title="My thread", path=temp_db,
    )
    assert m.monitor_id.startswith("monitor-")
    assert m.centroid is not None and m.centroid_dim == model.dimension
    assert m.query_terms  # salient title tokens

    monitors = mon.list_monitors(path=temp_db)
    assert len(monitors) == 1
    assert monitors[0].monitor_id == m.monitor_id

    # Idempotent re-create: same investigation -> same id -> still ONE row.
    m2 = mon.create_monitor(
        None, investigation_id="inv-1", model=model,
        document_ids=[d1, d2], title="My thread", path=temp_db,
    )
    assert m2.monitor_id == m.monitor_id
    assert len(mon.list_monitors(path=temp_db)) == 1

    # Delete -> list is empty.
    assert mon.delete_monitor(None, m.monitor_id, path=temp_db) is True
    assert mon.list_monitors(path=temp_db) == []
    # Deleting again returns False.
    assert mon.delete_monitor(None, m.monitor_id, path=temp_db) is False


def test_monitor_empty_thread_stores_null_centroid(temp_db):
    """Rigor #1: a thread with zero embedded chunks stores centroid=NULL,
    never a fabricated zero-vector."""
    model = _StubEmbedding()
    m = mon.create_monitor(
        None, investigation_id="inv-empty", model=model,
        document_ids=[], title="Empty thread", path=temp_db,
    )
    assert m.centroid is None
    assert m.centroid_dim is None


# ---------------------------------------------------------------------------
# Milestone 2 — resumable refresh
# ---------------------------------------------------------------------------


def test_refresh_no_duplicates(temp_db):
    model = _StubEmbedding()
    seed = _seed_doc(temp_db, content_class="personal_reading", acquired_at=_ts(0),
                     text="ambient research feed", title="Ambient research")
    m = mon.create_monitor(
        None, investigation_id="inv-2", model=model,
        document_ids=[seed], title="Thread", path=temp_db,
    )

    future = _future()
    fresh = _seed_doc(temp_db, content_class="personal_reading", acquired_at=future,
                      text="ambient research feed new idea", title="New idea")

    first = mon.refresh_monitor(None, m.monitor_id, model=model, path=temp_db)
    ids = {it.document_id for it in first.new_items}
    assert fresh in ids
    # The checkpoint advanced to the fresh item's acquired_at, on the module's
    # naive-UTC basis (the same normalization the refresh applies to the
    # since-checkpoint comparison).
    assert first.new_checkpoint == mon._naive_utc(future)

    # Second refresh with NO new ingest returns [] (no duplicates).
    second = mon.refresh_monitor(None, m.monitor_id, model=model, path=temp_db)
    assert second.new_items == []


def test_refresh_only_personal_lane(temp_db):
    """Lane isolation: a user_owned and a restricted_pending_opt_in doc in
    the same window are never returned; only the personal_reading item is."""
    model = _StubEmbedding()
    seed = _seed_doc(temp_db, content_class="personal_reading", acquired_at=_ts(0),
                     text="lane isolation seed", title="Seed")
    m = mon.create_monitor(
        None, investigation_id="inv-3", model=model,
        document_ids=[seed], title="Thread", path=temp_db,
    )

    personal = _seed_doc(temp_db, content_class="personal_reading",
                         acquired_at=_future(0),
                         text="lane isolation personal item", title="Personal")
    _seed_doc(temp_db, content_class="user_owned", acquired_at=_future(1),
              text="lane isolation user owned", title="UserOwned")
    _seed_doc(temp_db, content_class="restricted_pending_opt_in",
              acquired_at=_future(2),
              text="lane isolation restricted", title="Restricted")

    result = mon.refresh_monitor(None, m.monitor_id, model=model, path=temp_db)
    returned = {it.document_id for it in result.new_items}
    assert returned == {personal}
    assert all(it.content_class == "personal_reading" for it in result.new_items)


def test_refresh_chronological_fallback_when_no_centroid(temp_db):
    """A monitor with NULL centroid still refreshes — chronological order."""
    model = _StubEmbedding()
    m = mon.create_monitor(
        None, investigation_id="inv-nocent", model=model,
        document_ids=[], title="No centroid", path=temp_db,
    )
    assert m.centroid is None

    # Use fixed, far-apart future timestamps (not now()-derived) so the
    # chronological ordering assertion is deterministic — both are well after
    # the monitor's creation-time checkpoint, and 'newer' is unambiguously later.
    older_ts = "2099-01-01T00:00:00+00:00"
    newer_ts = "2099-06-01T00:00:00+00:00"
    _seed_doc(temp_db, content_class="personal_reading", acquired_at=older_ts,
              text="older", title="Older", with_chunk=False)
    newer = _seed_doc(temp_db, content_class="personal_reading",
                      acquired_at=newer_ts, text="newer", title="Newer",
                      with_chunk=False)

    result = mon.refresh_monitor(None, m.monitor_id, model=model, path=temp_db)
    assert {it.document_id for it in result.new_items} >= {newer}
    # newest-first ordering
    assert result.new_items[0].document_id == newer


# ---------------------------------------------------------------------------
# Milestone 3 — puttering feed
# ---------------------------------------------------------------------------


def test_putter_feed_body_and_non_attributable(temp_db):
    model = _StubEmbedding()
    seed = _seed_doc(temp_db, content_class="personal_reading", acquired_at=_ts(0),
                     text="putter body seed", title="Seed")
    m = mon.create_monitor(
        None, investigation_id="inv-4", model=model,
        document_ids=[seed], title="Thread", path=temp_db,
    )
    _seed_doc(temp_db, content_class="personal_reading", acquired_at=_future(),
              text="putter body full text of the essay", title="Essay")

    feed = mon.putter_feed(
        None, m.monitor_id, model=model, policy_tag="operator_only", path=temp_db
    )
    assert feed, "owner-path feed should surface the fresh item"
    for item in feed:
        assert item.body, "owner-path FeedItem must carry a non-empty body"
        assert item.content_class == "personal_reading"
        assert item.open_route == f"/read/{item.document_id}"
        doc = CollectiveGraphDocument(
            document_id=item.document_id,
            note_id="n",
            owner_user_id="owner",
            content_class=item.content_class,
            quality_gate_result=None,
        )
        assert is_attribution_eligible(doc) is False


def test_putter_feed_has_no_query_arg(temp_db):
    """Grazing, not querying: putter_feed must not take a free-text query."""
    params = set(inspect.signature(mon.putter_feed).parameters)
    assert "query" not in params


def test_putter_feed_filters_non_personal_lane(temp_db):
    """Defense-in-depth: a user_owned row in the candidate window never
    reaches putter_feed output."""
    model = _StubEmbedding()
    seed = _seed_doc(temp_db, content_class="personal_reading", acquired_at=_ts(0),
                     text="filter seed", title="Seed")
    m = mon.create_monitor(
        None, investigation_id="inv-5", model=model,
        document_ids=[seed], title="Thread", path=temp_db,
    )
    personal = _seed_doc(temp_db, content_class="personal_reading",
                         acquired_at=_future(0),
                         text="filter personal", title="Personal")
    _seed_doc(temp_db, content_class="user_owned", acquired_at=_future(1),
              text="filter user owned", title="UserOwned")

    feed = mon.putter_feed(
        None, m.monitor_id, model=model, policy_tag="operator_only", path=temp_db
    )
    ids = {it.document_id for it in feed}
    assert personal in ids
    assert all(it.content_class == "personal_reading" for it in feed)


def test_putter_feed_withholds_body_on_public_path(temp_db):
    """The body is returned only on the owner path; the public
    attribution_eligible default does NOT surface the body."""
    model = _StubEmbedding()
    seed = _seed_doc(temp_db, content_class="personal_reading", acquired_at=_ts(0),
                     text="public path seed", title="Seed")
    m = mon.create_monitor(
        None, investigation_id="inv-6", model=model,
        document_ids=[seed], title="Thread", path=temp_db,
    )
    _seed_doc(temp_db, content_class="personal_reading", acquired_at=_future(),
              text="public path full body", title="Body")

    public_feed = mon.putter_feed(
        None, m.monitor_id, model=model,
        policy_tag="attribution_eligible", path=temp_db,
    )
    for item in public_feed:
        assert item.body is None


# ---------------------------------------------------------------------------
# Milestone 3 (cont.) — body invisible to the public SEARCH gate
# ---------------------------------------------------------------------------


def test_personal_lane_hidden_from_public_search(temp_db):
    """The same monitor's personal_reading doc does not surface via search.py
    on the default attribution_eligible policy_tag, but DOES on the owner
    operator_only path."""
    model = _StubEmbedding()
    text = "hidden from public search zebra unique"
    doc_id = _seed_doc(temp_db, content_class="personal_reading",
                       acquired_at=_future(), text=text, title="Hidden")

    from runtime.db_lock import connect_read
    with connect_read(temp_db) as con:
        public = search(con, text, model=model, top_k=10)  # default gate
        owner = search(con, text, model=model, top_k=10, policy_tag="operator_only")

    public_ids = {r["document_id"] for r in public["results"]}
    owner_ids = {r["document_id"] for r in owner["results"]}
    assert doc_id not in public_ids  # public gate excludes personal_reading
    assert doc_id in owner_ids       # owner path includes it


# ---------------------------------------------------------------------------
# Milestone 2 (cont.) — audit emit carries no body
# ---------------------------------------------------------------------------


def test_refresh_emits_event_without_body(temp_db):
    model = _StubEmbedding()
    seed = _seed_doc(temp_db, content_class="personal_reading", acquired_at=_ts(0),
                     text="audit seed", title="Seed")
    m = mon.create_monitor(
        None, investigation_id="inv-audit", model=model,
        document_ids=[seed], title="Thread", path=temp_db,
    )
    secret_body = "TOP SECRET ESSAY BODY THAT MUST NOT LEAK"
    _seed_doc(temp_db, content_class="personal_reading", acquired_at=_future(),
              text=secret_body, title="Secret")

    mon.refresh_monitor(None, m.monitor_id, model=model, path=temp_db)

    from substrate.event_log.events import trajectory
    events = trajectory("inv-audit", events_dir=os.environ["ANTIEK_RESEARCH_EVENTS_DIR"])
    refresh_events = [e for e in events if e.get("action_type") == "monitor.refresh"]
    assert refresh_events, "a monitor.refresh event should be recorded"
    payload = refresh_events[-1]["payload"]
    assert payload["monitor_id"] == m.monitor_id
    assert "new_count" in payload and "new_checkpoint" in payload
    # The body never enters the event log.
    assert secret_body not in str(payload)
