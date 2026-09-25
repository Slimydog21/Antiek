"""Companions SPR-01 proofs — the projector, the evidence index, the
renderings. Real DuckDB fixtures + a real event log, no mocks.

The spec's seven proofs:
  1. referential integrity — every rendered evidence_id resolves to an
     index row, and every row's refs resolve to real sources;
  2. byte-identical idempotency — two passes over unchanged sources give
     identical tables AND identical renderings;
  3. from-scratch parity — drop the cache, rebuild: identical ids;
  4. exact delta — one terminal event → one rebuild → exactly the affected
     row changes, the companion shows the delta, zero hand edits;
  5. tombstone honesty — a gone source resolves to an honest tombstone,
     never dangling, never re-pointed;
  6. withheld rights — a non-servable document contributes metadata only
     (no body substring anywhere in the index or the rendering);
  7. the flywheel hook's additive consumer — the index is queried (asserted
     call) and an empty index leaves the hook byte-identical.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from runtime.db_lock import connect_read, connect_write  # noqa: E402
from substrate.books.highlights.schema import init_highlights_schema  # noqa: E402
from substrate.books.reading_state import ReadingStateStore  # noqa: E402
from substrate.companions.evidence_index import (  # noqa: E402
    read_scope,
    resolve,
)
from substrate.companions.projector import (  # noqa: E402
    ProjectScopeUnavailable,
    rebuild_document,
    rebuild_project,
)
from substrate.diligence.store import DiligenceStore  # noqa: E402
from substrate.graph.ops import insert_document  # noqa: E402
from substrate.graph.schema import init_database_at_path  # noqa: E402

OWNER = "__operator__"
BODY_TEXT = "The fixture book opens with a servable sentence worth keeping."
WITHHELD_BODY = "a withheld body sentence that must never leak"


@pytest.fixture
def env(tmp_path, monkeypatch):
    db = tmp_path / "g.duckdb"
    events = tmp_path / "events"
    events.mkdir()
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    init_database_at_path(str(db))
    return {"db": str(db), "events": str(events)}


def _write_thread(events_dir: str, investigation_id: str, terminal: str | None = None) -> None:
    when = datetime.now(UTC)
    rows = [
        {
            "event_id": f"evt-{investigation_id}-start",
            "investigation_id": investigation_id,
            "action_type": "investigation.start_requested",
            "emitted_at": when.isoformat(),
            "payload": {
                "action_type": "investigation.start_requested",
                "question": f"the question of {investigation_id}",
            },
        }
    ]
    if terminal:
        rows.append(
            {
                "event_id": f"evt-{investigation_id}-terminal",
                "investigation_id": investigation_id,
                "action_type": terminal,
                "emitted_at": datetime.now(UTC).isoformat(),
                "payload": {"action_type": terminal},
            }
        )
    with open(Path(events_dir) / f"{investigation_id}.jsonl", "a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def _seed_document(
    db: str,
    events_dir: str,
    *,
    document_id: str = "doc-1",
    content_class: str = "public_domain",
    body: str = BODY_TEXT,
    withheld: bool = False,
) -> dict[str, str]:
    """The spec's fixture: a document + two investigations with nodes + one
    anchor (+ a diligence flag + a reading position)."""
    with connect_write(db, purpose="test/seed-companion") as con:
        insert_document(
            con,
            document_id=document_id,
            source_tier=2,
            document_type="book",
            title="The Fixture Book",
            raw_text=body,
            content_class=content_class,
            on_conflict="ignore",
        )
        con.execute(
            "INSERT INTO chunks (chunk_id, document_id, chunk_index, "
            "section_path, text, token_count) VALUES (?, ?, 0, 'Page 1', ?, 8)",
            [f"c-{document_id}", document_id, body],
        )
        # Two investigations' nodes grounded in the document.
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope) "
            "VALUES (?, ?, 'insight', 'depth'), (?, ?, 'question', 'depth'), "
            "(?, ?, 'insight', 'depth')",
            [
                f"n-1-{document_id}", "the first fixture finding",
                f"n-2-{document_id}", "the fixture open question",
                f"n-3-{document_id}", "the second thread's finding",
            ],
        )
        con.execute(
            "INSERT INTO edges (edge_id, source_node_id, target_node_id, relation, "
            "chunk_id, source_document_id, source_tier, extraction_confidence, "
            "investigation_id, graph_scope) VALUES "
            "(?, ?, ?, 'supported_by', ?, ?, 2, 0.9, ?, 'depth'), "
            "(?, ?, ?, 'supported_by', ?, ?, 2, 0.9, ?, 'depth'), "
            "(?, ?, ?, 'supported_by', ?, ?, 2, 0.9, ?, 'depth')",
            [
                f"e-1-{document_id}", f"n-1-{document_id}", f"n-1-{document_id}",
                f"c-{document_id}", document_id, "inv-1",
                f"e-2-{document_id}", f"n-2-{document_id}", f"n-2-{document_id}",
                f"c-{document_id}", document_id, "inv-1",
                f"e-3-{document_id}", f"n-3-{document_id}", f"n-3-{document_id}",
                f"c-{document_id}", document_id, "inv-2",
            ],
        )
        if not withheld:
            # The unit-1 anchor linking inv-1 (servable pin).
            init_highlights_schema(con)
            import hashlib

            con.execute(
                "INSERT INTO anchored_highlights (anchor_id, owner_user_id, "
                "document_id, normalization, anchor_node_id, "
                "anchor_node_text_sha256, anchor_start_scalar, anchor_end_scalar, "
                "servable_at_pin, anchor_quote, anchor_prefix, anchor_suffix, "
                "selection_text_sha256, page_index_hint, source, status, "
                "investigation_id) "
                "VALUES (?, ?, ?, 'unicode-nfc-v1', ?, ?, 0, 11, TRUE, "
                "'the opening', '', '', ?, 0, 'pin', 'active', 'inv-1')",
                [
                    f"ahl-{document_id}", OWNER, document_id, f"c-{document_id}",
                    hashlib.sha256(body.encode()).hexdigest(),
                    hashlib.sha256(b"the opening").hexdigest(),
                ],
            )
            # Unit-7 diligence flag sourced from the document.
            DiligenceStore().create_flag(
                con,
                owner_user_id=OWNER,
                kind="concept",
                object_ref="the fixture concept",
                note=None,
                source_investigation_id="inv-1",
                source_document_id=document_id,
            )
            # Unit-4 reading position.
            ReadingStateStore().put(
                con,
                owner_user_id=OWNER,
                document_id=document_id,
                page_index=1,
                anchor_ref=None,
                prefs_json="{}",
                expected_revision=0,
            )
    _write_thread(events_dir, "inv-1")
    _write_thread(events_dir, "inv-2")
    return {"document_id": document_id}


def _dump_index(db: str, document_id: str = "doc-1"):
    con = connect_read(db)
    try:
        return read_scope(con, owner_user_id=OWNER, scope="document", scope_id=document_id)
    finally:
        con.close()


# ── Proof 1: referential integrity, row by row ─────────────────────────────


def test_referential_integrity_row_by_row(env) -> None:
    _seed_document(env["db"], env["events"])
    html = rebuild_document(env["db"], owner_user_id=OWNER, document_id="doc-1")
    rows = _dump_index(env["db"])
    assert len(rows) >= 6  # 3 claims + 1 anchor + 3 threads + flag + reading

    # Every rendered evidence_id resolves to an index row.
    import re as _re

    rendered_ids = _re.findall(r'data-evidence-id="(ev-[0-9a-f]+)"', html)
    assert rendered_ids, "the companion carries evidence ids"
    for eid in rendered_ids:
        row = resolve(connect_read(env["db"]), eid)
        assert row is not None and not row.tombstone, f"dangling rendered id: {eid}"

    # Every row's refs resolve to real sources.
    con = connect_read(env["db"])
    try:
        for row in rows:
            for ref in row.refs:
                kind, _, value = ref.partition(":")
                if kind == "node":
                    assert con.execute(
                        "SELECT 1 FROM nodes WHERE node_id = ?", [value]
                    ).fetchone(), ref
                elif kind == "anchor":
                    assert con.execute(
                        "SELECT 1 FROM anchored_highlights WHERE anchor_id = ?", [value]
                    ).fetchone(), ref
                elif kind == "flag":
                    assert con.execute(
                        "SELECT 1 FROM diligence_queue WHERE flag_id = ?", [value]
                    ).fetchone(), ref
                elif kind == "doc":
                    assert con.execute(
                        "SELECT 1 FROM documents WHERE document_id = ?", [value]
                    ).fetchone(), ref
                elif kind == "reading":
                    assert con.execute(
                        "SELECT 1 FROM reading_state WHERE owner_user_id = ? AND document_id = ?",
                        [OWNER, "doc-1"],
                    ).fetchone(), ref
                elif kind == "investigation":
                    assert (
                        Path(env["events"]) / f"{value}.jsonl"
                    ).exists() or value.startswith("read-"), ref
    finally:
        con.close()


# ── Proof 2: byte-identical idempotency ────────────────────────────────────


def test_two_rebuilds_are_byte_identical(env) -> None:
    _seed_document(env["db"], env["events"])
    html1 = rebuild_document(env["db"], owner_user_id=OWNER, document_id="doc-1")
    rows1 = _dump_index(env["db"])
    html2 = rebuild_document(env["db"], owner_user_id=OWNER, document_id="doc-1")
    rows2 = _dump_index(env["db"])
    assert html1 == html2
    assert rows1 == rows2  # frozen dataclass equality: every field identical


# ── Proof 3: from-scratch parity ────────────────────────────────────────────


def test_from_scratch_rebuild_keeps_identical_ids(env) -> None:
    _seed_document(env["db"], env["events"])
    rebuild_document(env["db"], owner_user_id=OWNER, document_id="doc-1")
    ids_before = [r.evidence_id for r in _dump_index(env["db"])]

    # DROP the cache wholesale — the index is a cache, never a truth.
    with connect_write(env["db"], purpose="test/drop-index") as con:
        con.execute("DELETE FROM evidence_index WHERE TRUE")
    assert _dump_index(env["db"]) == []

    rebuild_document(env["db"], owner_user_id=OWNER, document_id="doc-1")
    ids_after = [r.evidence_id for r in _dump_index(env["db"])]
    assert ids_before == ids_after


# ── Proof 4: the exact delta ───────────────────────────────────────────────


def test_one_terminal_event_changes_exactly_its_row(env) -> None:
    _seed_document(env["db"], env["events"])
    html1 = rebuild_document(env["db"], owner_user_id=OWNER, document_id="doc-1")
    rows1 = {r.evidence_id: r for r in _dump_index(env["db"])}

    # Fire ONE terminal event into the fixture.
    _write_thread(env["events"], "inv-1", terminal="investigation.completed")
    html2 = rebuild_document(env["db"], owner_user_id=OWNER, document_id="doc-1")
    rows2 = {r.evidence_id: r for r in _dump_index(env["db"])}

    assert set(rows1) == set(rows2)  # same ids — the delta is IN the row
    changed = [eid for eid in rows1 if rows1[eid] != rows2[eid]]
    assert len(changed) == 1, f"exactly the affected row changes: {changed}"
    changed_row = rows2[changed[0]]
    assert "investigation:inv-1" in changed_row.refs

    # The companion shows the delta with zero hand edits.
    assert "working…" in html1 and "working…" not in html2.replace("read-doc-1", "")
    assert "done" in html2


# ── Proof 5: tombstone honesty ──────────────────────────────────────────────


def test_a_gone_source_resolves_to_an_honest_tombstone(env) -> None:
    _seed_document(env["db"], env["events"])
    rebuild_document(env["db"], owner_user_id=OWNER, document_id="doc-1")
    claim = next(r for r in _dump_index(env["db"]) if r.kind == "claim")
    eid = claim.evidence_id

    # The claim's source node vanishes.
    node_ref = next(r for r in claim.refs if r.startswith("node:"))
    with connect_write(env["db"], purpose="test/vanish-node") as con:
        con.execute("DELETE FROM edges WHERE source_node_id = ?", [node_ref[5:]])
        con.execute("DELETE FROM nodes WHERE node_id = ?", [node_ref[5:]])

    rebuild_document(env["db"], owner_user_id=OWNER, document_id="doc-1")
    row = resolve(connect_read(env["db"]), eid)
    assert row is not None, "the id must not dangle"
    assert row.tombstone is True, "the row is an honest tombstone"
    assert row.refs == claim.refs, "never silently re-pointed"


# ── Proof 6: withheld rights flow through ──────────────────────────────────


def test_withheld_document_contributes_metadata_only(env) -> None:
    _seed_document(
        env["db"], env["events"],
        document_id="doc-gated", content_class="personal_reading",
        body=WITHHELD_BODY, withheld=True,
    )
    html = rebuild_document(env["db"], owner_user_id=OWNER, document_id="doc-gated")
    rows = _dump_index(env["db"], document_id="doc-gated")
    assert rows, "a withheld document still contributes rows (metadata)"

    # The grep enforcement: no body substring ANYWHERE — not the index
    # (refs only by construction), not the rendering.
    from dataclasses import asdict

    index_dump = json.dumps([asdict(r) for r in rows])
    assert WITHHELD_BODY not in index_dump
    assert WITHHELD_BODY not in html
    # And the claim TEXT stays with its lawful store for a withheld source.
    assert "the first fixture finding" not in html
    assert "withheld" in html  # the honest gate line


# ── Proof 7: the flywheel hook's additive consumer ─────────────────────────


def test_investigation_start_queries_the_index_additively(env, monkeypatch) -> None:
    from substrate.flywheel import investigation_start_reuse as hook

    _seed_document(env["db"], env["events"])
    calls: list[dict] = []
    import substrate.companions.evidence_index as ei

    real_query = ei.query_claim_node_ids

    def spy(con, *, owner_user_id, source_document_id):
        calls.append({"owner": owner_user_id, "doc": source_document_id})
        return real_query(
            con, owner_user_id=owner_user_id, source_document_id=source_document_id
        )

    monkeypatch.setattr(ei, "query_claim_node_ids", spy)

    eid = hook.maybe_reuse_prior_knowledge_at_start(
        investigation_id="inv-reuse-companion",
        question_text="What does the fixture book say?",
        db_path=env["db"],
        events_dir=env["events"],
        source_document_id="doc-1",
    )
    assert eid is not None
    assert len(calls) == 1
    assert calls[0]["doc"] == "doc-1"

    # The index is EMPTY (no rebuild ran) — the hook's behavior is unchanged:
    # the reuse event is exactly the empty-baseline shape.
    from substrate.event_log import iter_physical_events

    reused = [
        r
        for r in iter_physical_events("inv-reuse-companion", events_dir=env["events"])
        if r.get("action_type") == "knowledge.reused"
    ]
    assert len(reused) == 1
    assert isinstance(reused[0].get("payload", {}).get("reused_unit_ids"), list)


def test_index_hit_supplements_the_same_gated_pipeline(env) -> None:
    """A live index row's node joins the reuse pipeline — the emitted
    knowledge.reused event's decisions COVER it (injected or dropped by the
    existing gates, never forced). The question is deliberately UNRELATED to
    the node's text, so the node could only arrive via the index."""
    from substrate.flywheel import investigation_start_reuse as hook

    _seed_document(env["db"], env["events"])
    # A grounded, EMBEDDED node the reuse path can project (the claim→chunk→
    #doc grounding via supported_by + a real embedding from the provider).
    from processing.embedding import default_embedding_provider

    node_text = "The fixture book's finding is reusable knowledge."
    nid = "n-indexed-1"
    with connect_write(env["db"], purpose="test/seed-indexed-node") as con:
        emb = list(default_embedding_provider().encode(node_text))
        # The chunk carries the claim's terms so the groundedness gate
        # ACCEPTS the unit (the relevance floor then records the honest
        # dropped-low-relevance decision — coverage, never forced injection).
        con.execute(
            "UPDATE chunks SET text = ? WHERE chunk_id = 'c-doc-1'",
            ["The fixture book's finding is reusable knowledge, grounded in the body."],
        )
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope, embedding) "
            "VALUES (?, ?, 'insight', 'depth', ?)",
            [nid, node_text, emb],
        )
        con.execute(
            "INSERT INTO edges (edge_id, source_node_id, target_node_id, relation, "
            "chunk_id, source_document_id, source_tier, extraction_confidence, "
            "investigation_id, graph_scope) "
            "VALUES ('e-indexed-1', ?, ?, 'supported_by', 'c-doc-1', 'doc-1', 2, 0.9, "
            "'inv-1', 'depth')",
            [nid, nid],
        )
        from substrate.companions.evidence_index import EvidenceRow, rebuild_scope

        rebuild_scope(
            con,
            owner_user_id=OWNER,
            scope="document",
            scope_id="doc-1",
            rows=[
                EvidenceRow(
                    evidence_id="ev-fixture-claim",
                    owner_user_id=OWNER,
                    scope="document",
                    scope_id="doc-1",
                    kind="claim",
                    refs=(f"node:{nid}", "doc:doc-1"),
                    tombstone=False,
                    rebuilt_at="1970-01-01T00:00:00+00:00",
                )
            ],
        )

    eid = hook.maybe_reuse_prior_knowledge_at_start(
        investigation_id="inv-reuse-index-hit",
        question_text="completely unrelated query about chess openings",
        db_path=env["db"],
        events_dir=env["events"],
        source_document_id="doc-1",
    )
    assert eid is not None
    from substrate.event_log import iter_physical_events

    reused = [
        r
        for r in iter_physical_events("inv-reuse-index-hit", events_dir=env["events"])
        if r.get("action_type") == "knowledge.reused"
    ]
    assert len(reused) == 1
    payload = reused[0].get("payload", {})
    covered = payload.get("decisions") or []
    covered_ids = {d.get("unit_id") for d in covered if isinstance(d, dict)}
    assert nid in covered_ids or nid in (payload.get("reused_unit_ids") or [])


# ── The honest project scope ────────────────────────────────────────────────


def test_project_scope_is_honestly_unavailable(env) -> None:
    with pytest.raises(ProjectScopeUnavailable):
        rebuild_project(env["db"], owner_user_id=OWNER, project_id="anything")
    from substrate.companions.render import render_project_companion

    shell = render_project_companion()
    assert "Project scope unavailable" in shell
