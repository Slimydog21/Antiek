"""Anchor-first SPR-01 proofs — anchored highlights: model + persistence.

Each test names the spec proof it lands. Fixtures are REAL: a DuckDB file
(init_database_at_path for the graph schema; init_highlights_schema via the
store's entry points) and a real events dir for the audit JSONL. Nothing is
asserted by code review — every claim is a DB row or an event line.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest

from interfaces.research.api.agent_work_routes import _lease_payload
from runtime.db_lock import connect_write
from substrate.agent_work.store import WorkLease
from substrate.books.highlights.resolve import (
    PinResolutionError,
    document_servable,
    reanchor_document,
    resolve_pin,
)
from substrate.books.highlights.store import (
    CreatePinCommand,
    HighlightSource,
    HighlightsStore,
    HighlightStatus,
)
from substrate.feedback.domain import ArtifactVersionRef
from substrate.graph.insight_question import promote_insight
from substrate.graph.ops import insert_document
from substrate.graph.schema import init_database_at_path

CHUNK_TEXT = "Alpha beta gamma delta epsilon zeta omega."
DOC = "doc-hl"


@pytest.fixture
def env(tmp_path, monkeypatch):
    db_path = str(tmp_path / "graph.duckdb")
    events_dir = str(tmp_path / "events")
    artifacts_dir = str(tmp_path / "artifacts")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", artifacts_dir)
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    init_database_at_path(db_path)
    return {"db": db_path, "events": events_dir, "arts": artifacts_dir}


def _seed_document(
    db_path: str,
    *,
    document_id: str = DOC,
    content_class: str | None = "public_domain",
    chunks: list[tuple[str, str, str | None]],
) -> None:
    with connect_write(db_path, purpose="test/seed-highlights") as con:
        insert_document(
            con,
            document_id=document_id,
            source_tier=2,
            document_type="book",
            title="Highlight Book",
            raw_text=" ".join(text for _, text, _ in chunks),
            content_class=content_class,
            on_conflict="ignore",
        )
        for index, (chunk_id, text, section_path) in enumerate(chunks):
            con.execute(
                "INSERT INTO chunks (chunk_id, document_id, chunk_index, "
                "section_path, text, token_count) VALUES (?, ?, ?, ?, ?, ?)",
                [chunk_id, document_id, index, section_path, text, len(text.split())],
            )


def _pin(
    db_path: str,
    *,
    document_id: str = DOC,
    quote: str,
    prefix: str,
    suffix: str,
    owner: str = "owner-1",
) -> str:
    """Resolve + persist a pin the way the server will: resolution first,
    the servability decision from the server's own rights rows."""
    with connect_write(db_path, purpose="test/pin") as con:
        resolution = resolve_pin(
            con, document_id=document_id, quote=quote, prefix=prefix, suffix=suffix
        )
        servable = document_servable(con, document_id)
        row = HighlightsStore().create_pin(
            con,
            CreatePinCommand(
                owner_user_id=owner,
                document_id=document_id,
                anchor=resolution.anchor,
                servable_at_pin=servable,
                source=HighlightSource.PIN,
                page_index_hint=resolution.page_index_hint,
            ),
        )
        return row.anchor_id


def _update_chunk_text(db_path: str, chunk_id: str, text: str) -> None:
    with connect_write(db_path, purpose="test/edit-chunk") as con:
        con.execute("UPDATE chunks SET text = ? WHERE chunk_id = ?", [text, chunk_id])


def _delete_chunk(db_path: str, chunk_id: str) -> None:
    with connect_write(db_path, purpose="test/delete-chunk") as con:
        con.execute("DELETE FROM chunks WHERE chunk_id = ?", [chunk_id])


def _events(env: dict, document_id: str) -> list[dict]:
    path = Path(env["events"]) / f"read-{document_id}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# ── Proof 1: pin → reload active; edit → fuzzy drifted; delete → orphaned ──


def test_pin_reload_active__edit_fuzzy_drifted__delete_orphaned(env) -> None:
    db = env["db"]
    _seed_document(db, chunks=[("c-1", CHUNK_TEXT, None)])
    anchor_id = _pin(db, quote="gamma delta", prefix="Alpha beta ", suffix=" epsilon")

    # Pin → reload: the row reads back active with the resolved location.
    with connect_write(db, purpose="test/reload") as con:
        row = HighlightsStore().get(con, anchor_id)
    assert row is not None
    assert row.status is HighlightStatus.ACTIVE
    assert row.anchor.node_id == "c-1"
    assert row.anchor.quote == "gamma delta"
    assert row.servable_at_pin is True

    # Edit the chunk text in place so the passage MOVES (hash changes): the
    # fuzzy step re-anchors by quote+prefix+suffix → drifted, offsets
    # rewritten, quote preserved.
    moved = "Alpha beta CHANGED-INSERTION gamma delta epsilon zeta omega."
    _update_chunk_text(db, "c-1", moved)
    with connect_write(db, purpose="test/reanchor-drift") as con:
        report = reanchor_document(con, document_id=DOC, events_dir=env["events"])
    assert report.evaluated == 1
    assert report.drifted == 1
    with connect_write(db, purpose="test/read-drifted") as con:
        row = HighlightsStore().get(con, anchor_id)
    assert row is not None
    assert row.status is HighlightStatus.DRIFTED
    assert row.anchor.quote == "gamma delta"  # quote kept
    new_text = moved
    assert new_text[row.anchor.start_scalar : row.anchor.end_scalar] == "gamma delta"
    assert row.anchor.start_scalar > 0  # the passage moved — offsets rewritten

    # Delete the passage entirely: no fuzzy match exists → orphaned, and the
    # row is STILL returned (kept, listed, never deleted).
    _update_chunk_text(db, "c-1", "Alpha beta epsilon zeta omega only.")
    with connect_write(db, purpose="test/reanchor-orphan") as con:
        report = reanchor_document(con, document_id=DOC, events_dir=env["events"])
    assert report.orphaned == 1
    with connect_write(db, purpose="test/read-orphaned") as con:
        row = HighlightsStore().get(con, anchor_id)
        listed = HighlightsStore().list_for_document(con, DOC)
    assert row is not None
    assert row.status is HighlightStatus.ORPHANED
    assert [r.anchor_id for r in listed] == [anchor_id]


# ── Proof 2: re-chunk remint → migrate, stays active, quote-free event ─────


def test_rechunk_remint_migrates_node_id_and_stays_active(env) -> None:
    db = env["db"]
    _seed_document(db, chunks=[("c-1", CHUNK_TEXT, None)])
    anchor_id = _pin(db, quote="gamma delta", prefix="Alpha beta ", suffix=" epsilon")

    # Re-chunk: the SAME text under a reminted chunk id.
    _delete_chunk(db, "c-1")
    with connect_write(db, purpose="test/rechunk") as con:
        con.execute(
            "INSERT INTO chunks (chunk_id, document_id, chunk_index, "
            "section_path, text, token_count) VALUES (?, ?, ?, ?, ?, ?)",
            ["c-9", DOC, 0, None, CHUNK_TEXT, len(CHUNK_TEXT.split())],
        )
    with connect_write(db, purpose="test/reanchor-migrate") as con:
        report = reanchor_document(con, document_id=DOC, events_dir=env["events"])
    assert report.migrated == 1
    with connect_write(db, purpose="test/read-migrated") as con:
        row = HighlightsStore().get(con, anchor_id)
    assert row is not None
    assert row.status is HighlightStatus.ACTIVE
    assert row.anchor.node_id == "c-9"

    # The migration audit event exists and carries NO quote text anywhere.
    events = _events(env, DOC)
    assert events, "a migration audit event must have been emitted"
    migration = [e for e in events if e["action_type"] == "anchor.migrated"]
    assert len(migration) == 1
    event_line = json.dumps(migration[0])
    assert "gamma delta" not in event_line
    assert migration[0]["payload"]["from_node_id"] == "c-1"
    assert migration[0]["payload"]["node_id"] == "c-9"


# ── Proof 3: a non-servable pin persists no quote/prefix/suffix ────────────


def test_pin_on_non_servable_document_persists_no_quote(env) -> None:
    db = env["db"]
    _seed_document(
        db,
        document_id="doc-private",
        content_class="personal_reading",
        chunks=[("p-1", CHUNK_TEXT, None)],
    )
    anchor_id = _pin(
        db,
        document_id="doc-private",
        quote="gamma delta",
        prefix="Alpha beta ",
        suffix=" epsilon",
    )
    with connect_write(db, purpose="test/read-private") as con:
        raw = con.execute(
            "SELECT servable_at_pin, anchor_quote, anchor_prefix, anchor_suffix, "
            "selection_text_sha256 FROM anchored_highlights WHERE anchor_id = ?",
            [anchor_id],
        ).fetchone()
    assert raw is not None
    assert raw[0] is False
    # The rights truth at rest — NULLs asserted as a test, not a code review.
    assert raw[1] is None and raw[2] is None and raw[3] is None
    assert raw[4]  # the one-way selection hash is lawful and present

    # Metadata-only ladder: steps 1 and 4 ONLY (the spec's carve-out). A
    # re-chunk remint with identical text orphans a metadata-only anchor —
    # the spec's stated, accepted trade-off (no content-based re-anchor
    # without stored text).
    _delete_chunk(db, "p-1")
    with connect_write(db, purpose="test/rechunk-private") as con:
        con.execute(
            "INSERT INTO chunks (chunk_id, document_id, chunk_index, "
            "section_path, text, token_count) VALUES (?, ?, ?, ?, ?, ?)",
            ["p-9", "doc-private", 0, None, CHUNK_TEXT, len(CHUNK_TEXT.split())],
        )
    with connect_write(db, purpose="test/reanchor-private") as con:
        report = reanchor_document(con, document_id="doc-private", events_dir=env["events"])
    assert report.orphaned == 1
    with connect_write(db, purpose="test/read-private-orphan") as con:
        raw = con.execute(
            "SELECT status, anchor_quote FROM anchored_highlights WHERE anchor_id = ?",
            [anchor_id],
        ).fetchone()
    assert raw is not None
    assert raw[0] == "orphaned"
    assert raw[1] is None  # the row never gains a quote during re-resolution


def test_check_constraint_ties_null_quote_to_servable_flag(env) -> None:
    db = env["db"]
    with connect_write(db, purpose="test/check") as con:
        from substrate.books.highlights.schema import init_highlights_schema

        init_highlights_schema(con)
        base = {
            "anchor_id": "ahl-check",
            "owner_user_id": "owner-1",
            "document_id": DOC,
            "normalization": "unicode-nfc-v1",
            "anchor_node_id": "c-1",
            "anchor_node_text_sha256": "h",
            "anchor_start_scalar": 0,
            "anchor_end_scalar": 1,
            "selection_text_sha256": "s",
            "source": "pin",
            "status": "active",
        }
        # servable_at_pin=FALSE with a quote present → the DB refuses.
        with pytest.raises(duckdb.ConstraintException):
            con.execute(
                "INSERT INTO anchored_highlights (anchor_id, owner_user_id, "
                "document_id, normalization, anchor_node_id, "
                "anchor_node_text_sha256, anchor_start_scalar, anchor_end_scalar, "
                "servable_at_pin, anchor_quote, selection_text_sha256, source, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    base["anchor_id"],
                    base["owner_user_id"],
                    base["document_id"],
                    base["normalization"],
                    base["anchor_node_id"],
                    base["anchor_node_text_sha256"],
                    base["anchor_start_scalar"],
                    base["anchor_end_scalar"],
                    False,
                    "quote text",
                    base["selection_text_sha256"],
                    base["source"],
                    base["status"],
                ],
            )
        # servable_at_pin=TRUE with a NULL quote → the DB refuses.
        with pytest.raises(duckdb.ConstraintException):
            con.execute(
                "INSERT INTO anchored_highlights (anchor_id, owner_user_id, "
                "document_id, normalization, anchor_node_id, "
                "anchor_node_text_sha256, anchor_start_scalar, anchor_end_scalar, "
                "servable_at_pin, anchor_quote, anchor_prefix, anchor_suffix, "
                "selection_text_sha256, source, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    "ahl-check-2",
                    base["owner_user_id"],
                    base["document_id"],
                    base["normalization"],
                    base["anchor_node_id"],
                    base["anchor_node_text_sha256"],
                    base["anchor_start_scalar"],
                    base["anchor_end_scalar"],
                    True,
                    None,
                    None,
                    None,
                    base["selection_text_sha256"],
                    base["source"],
                    base["status"],
                ],
            )


# ── Proof 4: payload parity with the lease anchor field set ────────────────


def test_anchor_payload_matches_lease_field_set(env) -> None:
    db = env["db"]
    _seed_document(db, chunks=[("c-1", CHUNK_TEXT, None)])
    anchor_id = _pin(db, quote="gamma delta", prefix="Alpha beta ", suffix=" epsilon")
    with connect_write(db, purpose="test/parity-read") as con:
        row = HighlightsStore().get(con, anchor_id)
    assert row is not None

    lease = WorkLease(
        work_id="w-1",
        thread_id="t-1",
        lease_id="l-1",
        attempt_no=1,
        logical_worker_id="worker-1",
        lease_expires_at=datetime(2026, 9, 24, tzinfo=UTC),
        artifact=ArtifactVersionRef("a-1", 1, "c" * 64, "d" * 64),
        anchor=row.to_node_text_anchor(),
        comment_markdown="",
        context_sha256="e" * 64,
    )
    lease_anchor = _lease_payload(lease)["anchor"]
    stored = row.to_lease_payload()
    # The stored anchor dict round-trips through EXACTLY the lease's field set.
    assert set(stored.keys()) == set(lease_anchor.keys())
    assert stored == lease_anchor


# ── Proof 5: a real source-merge commit re-resolves the document's anchors ─


def test_source_merge_commit_reruns_anchor_resolution(env) -> None:
    """The spec's hook proof, driven through the REAL substrate path (SPR-01
    has no HTTP surface — compose_artifacts → preview → commit are the real
    calls commit_source_merge_review's own tests make)."""
    from substrate.research_artifact.compose import compose_artifacts
    from substrate.research_artifact.source_merge import (
        commit_source_merge_review,
        preview_source_merge_review,
    )

    db = env["db"]
    document_id = "doc-source-merge"
    _seed_document(
        db,
        document_id=document_id,
        chunks=[
            ("sm-1", "Original source book body.", None),
            ("sm-2", "A passage the rewrite carries away.", None),
        ],
    )
    intact_id = _pin(
        db,
        document_id=document_id,
        quote="source book body",
        prefix="Original ",
        suffix=".",
    )
    lost_id = _pin(
        db,
        document_id=document_id,
        quote="carries away",
        prefix="the rewrite ",
        suffix=".",
    )

    for iid, text in [("inv-src-a", "Source merge A"), ("inv-src-b", "Source merge B")]:
        promote_insight(
            text=text,
            investigation_id=iid,
            confidence="moderate",
            source_document_id=document_id,
        )
    composed = compose_artifacts(
        ["inv-src-a", "inv-src-b"],
        db_path=db,
        events_dir=env["events"],
        write_draft_merge=True,
    )
    assert composed.draft_merge_path is not None
    member_ids = ["inv-src-a", "inv-src-b"]
    member_hashes = {m.investigation_id: m.content_hash for m in composed.members}

    # The merge-affected change lands before the commit: the second chunk is gone.
    _delete_chunk(db, "sm-2")

    with connect_write(db, purpose="test/source-merge-commit") as con:
        preview = preview_source_merge_review(
            con,
            document_id=document_id,
            draft_merge_path=str(composed.draft_merge_path),
            compose_index_path=str(composed.path),
            member_investigation_ids=member_ids,
            expected_content_hashes=member_hashes,
            hash_conflicts=[],
        )
        receipt = commit_source_merge_review(
            con,
            document_id=document_id,
            parent_reading_thread_id=f"read-{document_id}",
            draft_merge_path=str(composed.draft_merge_path),
            compose_index_path=str(composed.path),
            member_investigation_ids=member_ids,
            expected_content_hashes=member_hashes,
            hash_conflicts=[],
            expected_source_revision_id=preview.source_revision_id,
            expected_twin_revision_id=preview.twin_revision_id,
            expected_before_source_hash=preview.before_source_hash,
            expected_after_source_hash=preview.after_source_hash,
            expected_before_twin_hash=preview.before_twin_hash,
            expected_after_twin_hash=preview.after_twin_hash,
            operator_reviewer="pytest",
            events_dir=env["events"],
        )
    assert receipt.status == "committed"
    assert receipt.writes_performed is True

    # The post-commit hook ran INSIDE the commit's write-lock scope: the
    # intact anchor is still active (not stale), the lost one is orphaned,
    # and the orphaned transition was emitted during the commit.
    with connect_write(db, purpose="test/read-after-commit") as con:
        intact = HighlightsStore().get(con, intact_id)
        lost = HighlightsStore().get(con, lost_id)
    assert intact is not None and intact.status is HighlightStatus.ACTIVE
    assert lost is not None and lost.status is HighlightStatus.ORPHANED
    events = _events(env, document_id)
    assert any(e["action_type"] == "anchor.orphaned" for e in events)
    # The audit events stay metadata-only even alongside the merge's own.
    for e in events:
        assert "carries away" not in json.dumps(e)
        assert "Source merge A" not in json.dumps(e)


# ── Supporting: the honest refusals + hints + the only removal path ────────


def test_ambiguous_pin_is_an_honest_refusal(env) -> None:
    db = env["db"]
    _seed_document(
        db,
        chunks=[("c-1", CHUNK_TEXT, None), ("c-2", CHUNK_TEXT, None)],
    )
    with (
        connect_write(db, purpose="test/ambiguous") as con,
        pytest.raises(PinResolutionError) as excinfo,
    ):
        resolve_pin(
            con,
            document_id=DOC,
            quote="gamma delta",
            prefix="Alpha beta ",
            suffix=" epsilon",
        )
    assert excinfo.value.reason == "ambiguous"


def test_unlocatable_pin_is_an_honest_refusal(env) -> None:
    db = env["db"]
    _seed_document(db, chunks=[("c-1", CHUNK_TEXT, None)])
    with (
        connect_write(db, purpose="test/not-found") as con,
        pytest.raises(PinResolutionError) as excinfo,
    ):
        resolve_pin(
            con,
            document_id=DOC,
            quote="no such passage anywhere",
            prefix="",
            suffix="",
        )
    assert excinfo.value.reason == "not_found"


def test_pin_page_index_hint_comes_from_the_page_marker(env) -> None:
    db = env["db"]
    _seed_document(db, chunks=[("c-1", CHUNK_TEXT, "Page 3")])
    anchor_id = _pin(db, quote="gamma delta", prefix="Alpha beta ", suffix=" epsilon")
    with connect_write(db, purpose="test/read-hint") as con:
        row = HighlightsStore().get(con, anchor_id)
    assert row is not None
    assert row.page_index_hint == 2  # "Page 3" → 0-based index 2 (page_anchor.py:36)


def test_owner_scoped_delete_is_the_only_removal(env) -> None:
    db = env["db"]
    _seed_document(db, chunks=[("c-1", CHUNK_TEXT, None)])
    anchor_id = _pin(db, quote="gamma delta", prefix="Alpha beta ", suffix=" epsilon")
    with connect_write(db, purpose="test/delete-wrong-owner") as con:
        assert HighlightsStore().delete(con, anchor_id, "someone-else") is False
    with connect_write(db, purpose="test/delete-owner") as con:
        assert HighlightsStore().delete(con, anchor_id, "owner-1") is True
        assert HighlightsStore().get(con, anchor_id) is None
