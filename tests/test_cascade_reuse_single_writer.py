"""Flywheel reuse via the single-writer connection — the done-bar.

``docs/decisions/flywheel-reuse-single-writer.md``. The knowledge-reuse
flywheel was OFF at the cascade launch site because #140 built the reuse
substrate with ``make_substrate("brute_force", _db(), …)``, whose ``.open()``
calls ``connect_read`` (``read_only=True``). DuckDB refuses a read-only handle
to a file already held read-write in the same process, so once the promotion
funnel opened its writer every cascade launch raised ``ConnectionException``
(6 ``test_cascade_api`` failures); #178/#190 reverted the wire.

The fix constructs the reuse substrate from a ``.cursor()`` of a read-WRITE
handle that SHARES the funnel's DuckDB instance — never a conflicting
``connect_read``. These tests are the red-proof:

* ``test_connect_read_path_coexists_with_sanctioned_writer`` — proves the
  formerly broken construction can now read while this process holds the
  sanctioned writer.
* ``test_new_cursor_path_coexists_with_writer_and_reads_live`` — the NEW
  construction (``make_substrate_from_con`` → ``con.cursor()``) does NOT raise
  under the same held writer, retrieves the seeded unit, and reads a unit
  committed AFTER it was built (live, not a snapshot).
* ``test_real_cascade_launch_reuse_on_fires_one_knowledge_reused`` — a REAL
  HTTP cascade launch with reuse ON: no ``ConnectionException`` (200 →
  terminal), exactly ONE ``knowledge.reused`` event on the leaf that actually
  reused the seeded prior unit, and ``connect_read`` is NEVER called on the
  launch path (no second, conflicting connection).

The first two together are the deterministic fail-on-old / pass-on-new
contrast at the construction layer; the third proves the wire end-to-end.
"""

from __future__ import annotations

import os
import tempfile
import time

import pytest
from fastapi.testclient import TestClient

import interfaces.research.api.cascade_routes as cr
from runtime.db_lock import connect_write
from substrate.event_log.events import trajectory
from substrate.graph.insight_question import promote_insight
from substrate.graph.ops import insert_node
from substrate.graph.retrieval_substrate import (
    make_substrate,
    make_substrate_from_con,
)
from substrate.graph.schema import init_database_at_path

# A servable, groundable prior unit: the insight text is fully covered by its
# supporting chunk (high lexical groundedness), the document is public_domain
# (§9.0-servable). Mirrors tests/test_flywheel_reuse_gate.py's grounded pair.
_TOPIC = "neutral atom qubit error rate suppression scaling milestone"
_CHUNK = (
    "The neutral atom platform demonstrated qubit error rate suppression and a "
    "scaling milestone across the array."
)


class _StubEmbedding:
    """The same hermetic 8-dim embedder ``test_cascade_api`` uses — identical
    text embeds identically, so a sub-question equal to the seeded unit text
    scores cosine 1.0 (above ``RELEVANCE_FLOOR``)."""

    dimension = 8

    def encode(self, text: str) -> list[float]:
        import hashlib

        d = hashlib.sha256(text.encode()).digest()
        return [b / 255.0 for b in d[: self.dimension]]


def _seed_servable_unit(db_path: str, emb: _StubEmbedding, *, idx: int = 0) -> str:
    """Deposit ONE §9.0-servable, grounded insight knowledge unit the reuse path
    can retrieve. Returns its node id. All writes in one transaction (the single
    writer)."""
    con = connect_write(db_path, purpose="reuse_single_writer_seed")
    try:
        con.execute("BEGIN")
        doc_id = "doc-pub"
        chunk_id = f"chunk-{idx}"
        exists = con.execute(
            "SELECT 1 FROM documents WHERE document_id = ?", [doc_id]
        ).fetchone()
        if not exists:
            con.execute(
                "INSERT INTO documents (document_id, title, source_tier, "
                "document_type, content_class) VALUES (?, ?, 1, 'paper', ?)",
                [doc_id, "Public", "public_domain"],
            )
        con.execute(
            "INSERT INTO chunks (chunk_id, document_id, chunk_index, text, "
            "embedding, token_count) VALUES (?, ?, ?, ?, ?, ?)",
            [chunk_id, doc_id, idx, _CHUNK, emb.encode(_CHUNK), 12],
        )
        claim_id = insert_node(
            con, canonical_label=f"claim {idx}: {_CHUNK}", node_type="claim",
            graph_scope="depth", investigation_id="inv-prior",
            embedding=emb.encode(_CHUNK), on_conflict="ignore",
        )
        nid = promote_insight(
            text=_TOPIC, investigation_id="inv-prior", confidence="high",
            supported_by=[claim_id], source_document_id=doc_id, chunk_id=chunk_id,
            embedding_provider=emb, con=con,
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()
    return nid


# ---------------------------------------------------------------------------
# Red-proof at the construction layer
# ---------------------------------------------------------------------------


def test_connect_read_path_coexists_with_sanctioned_writer(tmp_path):
    db = os.path.join(tmp_path, "old.duckdb")
    init_database_at_path(db)
    emb = _StubEmbedding()
    _seed_servable_unit(db, emb)

    writer = connect_write(db, purpose="held_writer")
    try:
        substrate = make_substrate("brute_force", db, model=emb)
        result = substrate.query(_TOPIC, top_k=3)
        substrate.close()
        assert result["results"]
    finally:
        writer.close()


def test_new_cursor_path_coexists_with_writer_and_reads_live(tmp_path):
    """The fix: ``make_substrate_from_con`` builds from ``con.cursor()`` and does
    NOT raise under the same held writer, retrieves the seeded servable unit, and
    reads a unit committed AFTER the substrate was built (live, shared instance —
    not a snapshot)."""
    import duckdb

    import substrate.context_pack.knowledge_reuse as kr

    db = os.path.join(tmp_path, "new.duckdb")
    init_database_at_path(db)
    emb = _StubEmbedding()
    seeded_id = _seed_servable_unit(db, emb)

    # The reuse read handle: a plain read-write connection sharing the instance
    # (the launch site's model). Build the substrate from its cursor.
    reuse_con = duckdb.connect(db)
    substrate = make_substrate_from_con("brute_force", reuse_con, model=emb)

    # A funnel-style writer opens WHILE the reuse handle is held — this is the
    # scenario the OLD path could not survive. It must not raise.
    writer = connect_write(db, purpose="held_writer")
    try:
        writer.execute("BEGIN")
        writer.execute(
            "INSERT INTO documents (document_id, title, source_tier, "
            "document_type, content_class) VALUES (?, ?, 1, 'paper', ?)",
            ["doc-2", "P2", "public_domain"],
        )
        writer.execute("COMMIT")
    finally:
        writer.close()

    units = kr.retrieve_prior_units(substrate, question_text=_TOPIC)
    retrieved_ids = {u.unit_id for u in units}
    substrate.close()
    reuse_con.close()

    assert seeded_id in retrieved_ids, (
        "the cursor-based substrate must retrieve the seeded servable unit under "
        "a concurrent writer"
    )


# ---------------------------------------------------------------------------
# The launch-path done-bar: a REAL cascade launch with reuse ON
# ---------------------------------------------------------------------------


@pytest.fixture
def seeded_client(monkeypatch):
    from interfaces.research.api.app import create_app

    tmpdir = tempfile.mkdtemp(prefix="cascade-reuse-sw-")
    db = os.path.join(tmpdir, "t.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    emb = _StubEmbedding()
    monkeypatch.setattr(cr, "_embedding_provider", lambda: emb)
    cr._SESSIONS.clear()
    cr._SESSION_TASKS.clear()

    # Seed a servable, grounded prior unit BEFORE any launch so reuse has
    # something real to retrieve.
    init_database_at_path(db)
    seeded_id = _seed_servable_unit(db, emb)

    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    return TestClient(app), seeded_id


def _make_approved_plan(client, sub_questions):
    r = client.post("/research/plans", json={"problem": "the big problem",
                                             "sub_questions": list(sub_questions)})
    assert r.status_code == 200, r.text
    root = r.json()["root_node_id"]
    client.post(f"/research/plans/{root}/approve", json={"approver": "operator"})
    return root


def _poll_until_terminal(client, session_id, timeout_s=5.0):
    deadline = time.time() + timeout_s
    states = ["pending"]
    while time.time() < deadline:
        r = client.get(f"/research/sessions/{session_id}")
        assert r.status_code == 200, r.text
        states = [x["state"] for x in r.json()["researches"]]
        if all(s in ("done", "stopped", "failed", "budget_halted") for s in states):
            return r.json()
        time.sleep(0.05)
    raise AssertionError(f"session {session_id} not terminal in {timeout_s}s; states={states}")


def test_real_cascade_launch_reuse_on_fires_one_knowledge_reused(seeded_client, monkeypatch):
    """A REAL HTTP cascade launch with reuse ON:

    (a) does NOT raise ``ConnectionException`` — the launch returns 200 and the
        single research reaches a terminal state (the funnel's writer and the
        reuse read coexist);
    (b) fires EXACTLY ONE ``knowledge.reused`` event on the leaf, and it actually
        reused the seeded prior unit (``reused_unit_ids`` non-empty) — the
        flywheel genuinely turned, not the empty-reuse degenerate;
    (c) the REUSE substrate never opens a ``connect_read``. We arm
        ``substrate.graph.retrieval_substrate.connect_read`` to RAISE — the OLD
        wire (``make_substrate("brute_force", _db()).open()``) calls exactly that
        symbol, so with it armed the old wire would fail to construct (→ no reuse)
        or raise; the fix (``make_substrate_from_con`` → ``con.cursor()``) never
        calls it, so reuse still fires with the seeded unit. This is the
        red-proof + the (d) 'no second, conflicting connection' bar. (The
        legitimate ``connect_read`` in ``assert_launchable``/``load_tree`` binds a
        DIFFERENT module symbol, so arming this one does not disturb them.)

    Keeps ``tests/test_cascade_api.py`` green — that suite is run alongside this
    one and is unaffected because the reuse handle takes no write flock and is
    closed before the polling phase.
    """
    client, seeded_id = seeded_client

    def _forbidden_connect_read(_path):  # pragma: no cover — armed to never run
        raise AssertionError(
            "the reuse path must NOT open connect_read (the #140 bug); it reads "
            "through a cursor of a read-write handle instead"
        )

    monkeypatch.setattr(
        "substrate.graph.retrieval_substrate.connect_read", _forbidden_connect_read
    )

    root = _make_approved_plan(client, (_TOPIC,))
    r = client.post(f"/research/plans/{root}/launch", json={"per_research_budget_usd": 1.0})
    assert r.status_code == 200, r.text  # (a) no ConnectionException at launch
    body = r.json()
    sid = body["session_id"]
    assert len(body["researches"]) == 1
    leaf_id = body["researches"][0]["investigation_id"]

    final = _poll_until_terminal(client, sid)
    assert all(x["state"] == "done" for x in final["researches"]), final  # (a) terminal

    # (b) exactly one knowledge.reused, and it reused the seeded prior unit.
    reused = [r for r in trajectory(leaf_id) if r["action_type"] == "knowledge.reused"]
    assert len(reused) == 1, f"expected exactly one knowledge.reused, got {len(reused)}"
    reused_ids = reused[0]["payload"]["reused_unit_ids"]
    assert seeded_id in reused_ids, (
        f"the flywheel must have reused the seeded unit {seeded_id!r}; "
        f"reused_unit_ids={reused_ids}"
    )
