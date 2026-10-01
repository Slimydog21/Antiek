"""Takedown remains authoritative for highlight and fresh companion reads."""

from __future__ import annotations

from pathlib import Path

import pytest

from runtime.db_lock import connect_read, connect_write
from substrate.books.highlights.resolve import document_servable, resolve_pin
from substrate.books.highlights.schema import init_highlights_schema
from substrate.books.highlights.store import (
    CreatePinCommand,
    HighlightSource,
    HighlightsStore,
)
from substrate.companions.projector import (
    document_companion_payload,
    project_document,
)
from substrate.graph.ops import insert_document
from substrate.graph.schema import init_database_at_path

BODY = "A distinctive sentence for checking takedown admission."


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    path = str(tmp_path / "rights.duckdb")
    init_database_at_path(path)
    with connect_write(path, purpose="test/highlight-takedown-schema") as con:
        init_highlights_schema(con)
    return path


def _seed_document(db_path: str, document_id: str, *, content_class: str) -> None:
    with connect_write(db_path, purpose="test/highlight-takedown-seed") as con:
        insert_document(
            con,
            document_id=document_id,
            source_tier=2,
            document_type="book",
            title="Synthetic source",
            raw_text=BODY,
            content_class=content_class,
            on_conflict="ignore",
        )
        con.execute(
            "INSERT INTO chunks (chunk_id, document_id, chunk_index, text, token_count) "
            "VALUES (?, ?, 0, ?, 9)",
            [f"chunk-{document_id}", document_id, BODY],
        )


def _set_takedown(db_path: str, document_id: str, taken_down: bool) -> None:
    with connect_write(db_path, purpose="test/highlight-takedown-state") as con:
        con.execute(
            "INSERT INTO book_assets (document_id, taken_down) VALUES (?, ?) "
            "ON CONFLICT (document_id) DO UPDATE SET taken_down = excluded.taken_down",
            [document_id, taken_down],
        )


def test_document_servable_uses_asset_override_and_legacy_left_join(db_path: str) -> None:
    _seed_document(db_path, "public", content_class="public_domain")
    _seed_document(db_path, "down", content_class="public_domain")
    _seed_document(db_path, "personal", content_class="personal_reading")
    _seed_document(db_path, "restricted", content_class="restricted_pending_opt_in")
    _set_takedown(db_path, "down", True)

    with connect_read(db_path) as con:
        assert document_servable(con, "public") is True  # no book_assets row
        assert document_servable(con, "down") is False  # allowlisted class loses
        assert document_servable(con, "personal") is False
        assert document_servable(con, "restricted") is False
        assert document_servable(con, "missing") is False

    # Reclassification cannot override the orthogonal flag; reinstatement
    # restores the original allowlisted projection without changing policy.
    with connect_write(db_path, purpose="test/highlight-takedown-reclass") as con:
        con.execute(
            "UPDATE documents SET content_class = 'source_declared_open' "
            "WHERE document_id = 'down'"
        )
    with connect_read(db_path) as con:
        assert document_servable(con, "down") is False
    _set_takedown(db_path, "down", False)
    with connect_read(db_path) as con:
        assert document_servable(con, "down") is True


def test_taken_down_document_creates_metadata_only_pin(db_path: str) -> None:
    _seed_document(db_path, "pin", content_class="public_domain")
    _set_takedown(db_path, "pin", True)

    with connect_write(db_path, purpose="test/highlight-takedown-pin") as con:
        resolved = resolve_pin(
            con,
            document_id="pin",
            quote="distinctive sentence",
            prefix="A ",
            suffix=" for checking",
        )
        row = HighlightsStore().create_pin(
            con,
            CreatePinCommand(
                owner_user_id="synthetic-owner",
                document_id="pin",
                anchor=resolved.anchor,
                servable_at_pin=document_servable(con, "pin"),
                source=HighlightSource.PIN,
                page_index_hint=resolved.page_index_hint,
            ),
        )

    assert row.servable_at_pin is False
    assert row.anchor.quote == ""
    assert row.anchor.prefix == ""
    assert row.anchor.suffix == ""


@pytest.mark.parametrize("taken_down", [False, True])
def test_fresh_companion_projection_obeys_current_takedown(
    db_path: str, taken_down: bool
) -> None:
    document_id = f"companion-{taken_down}"
    _seed_document(db_path, document_id, content_class="public_domain")
    if taken_down:
        _set_takedown(db_path, document_id, True)
    with connect_write(db_path, purpose="test/highlight-takedown-claim") as con:
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope) "
            "VALUES (?, ?, 'insight', 'depth')",
            [f"node-{document_id}", "Synthetic source-grounded claim"],
        )
        con.execute(
            "INSERT INTO edges (edge_id, source_node_id, target_node_id, relation, "
            "chunk_id, source_document_id, source_tier, extraction_confidence, "
            "investigation_id, graph_scope) "
            "VALUES (?, ?, ?, 'supported_by', ?, ?, 2, 0.9, 'synthetic', 'depth')",
            [
                f"edge-{document_id}",
                f"node-{document_id}",
                f"node-{document_id}",
                f"chunk-{document_id}",
                document_id,
            ],
        )

    con = connect_read(db_path)
    try:
        _, view = project_document(
            con,
            owner_user_id="synthetic-owner",
            document_id=document_id,
            events_dir=str(Path(db_path).parent / "events"),
        )
    finally:
        con.close()
    payload = document_companion_payload(view)
    assert payload["servable"] is (not taken_down)
    assert len(payload["claims"]) == 1
    assert payload["claims"][0]["text"] == (
        "Synthetic source-grounded claim" if not taken_down else None
    )
