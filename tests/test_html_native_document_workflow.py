from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from runtime.db_lock import connect_read, connect_write
from substrate.contracts.html_projection import HtmlProjectionContract, derive_projection_id
from substrate.event_log import emit_typed
from substrate.graph.ops import insert_deliverable, insert_section
from substrate.graph.schema import init_database
from substrate.notebooks import append_block, create_notebook
from substrate.reading.projection.pipeline import (
    finalize_projection,
    persist_prepared_projection,
    prepare_projection,
)
from substrate.reading.projection.store import ProjectionStore
from substrate.reading.projection.workflow_lineage import (
    LineageConflict,
    LineageValidationError,
    WorkflowLineageRegistry,
)
from substrate.reading.regions import CanonicalDocumentRegion, RegionStore, derive_region_id
from substrate.schemas.events import (
    InvestigationStartRequestedPayload,
    NoteEmergedPayload,
    SeamReadToResearchPayload,
)
from substrate.write.outline_block import place_node_block


def _pdf(text: str) -> bytes:
    buffer = io.BytesIO()
    output = canvas.Canvas(buffer, pagesize=letter, invariant=True)
    output.drawString(72, 720, text)
    output.showPage()
    output.save()
    return buffer.getvalue()


def _persist_html_and_region(db: Path, asset: str = "asset-1", document: str = "doc-1"):
    source = _pdf("An authoritative source region")
    identity = {
        "source_asset_id": asset,
        "source_document_id": document,
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "converter_id": "pypdf",
        "converter_version": "1",
        "sanitizer_policy": "born-antiek",
        "sanitizer_version": "1",
    }
    queued = HtmlProjectionContract(
        **identity, projection_id=derive_projection_id(**identity), status="queued"
    )
    prepared = finalize_projection(prepare_projection(queued, source), f"objects/{document}.html")
    with connect_write(str(db), purpose="test/persist-ready-html") as con:
        init_database(con)
        con.execute("BEGIN TRANSACTION")
        ready = persist_prepared_projection(ProjectionStore(con), queued, prepared)
        locator = ready.anchor_mappings[0].source_locator
        region_identity = {
            "document_id": document,
            "projection_id": ready.projection_id,
            "source_locator": locator.model_dump(exclude_none=True),
            "html_anchor_id": ready.anchor_mappings[0].html_anchor_id,
            "char_start": None,
            "char_end": None,
            "exact_text_sha256": None,
        }
        region = CanonicalDocumentRegion(
            **region_identity, region_id=derive_region_id(**region_identity)
        )
        RegionStore(con).claim(region)
        con.execute("COMMIT")
    return ready, region


def _emit_investigation(
    events_dir: Path,
    investigation_id: str,
    note_id: str,
    *,
    document_id: str = "doc-1",
    region_id: str,
) -> None:
    start_id = emit_typed(
        investigation_id,
        InvestigationStartRequestedPayload(question="What does the source establish?"),
        events_dir=str(events_dir),
    )
    assert start_id is not None
    emit_typed(
        investigation_id,
        SeamReadToResearchPayload(
            entity_id=region_id,
            provenance_ref=start_id,
            document_id=document_id,
            launched_investigation_id=investigation_id,
        ),
        parent_event_id=start_id,
        document_id=document_id,
        events_dir=str(events_dir),
    )
    emit_typed(
        investigation_id,
        NoteEmergedPayload(
            note_id=note_id,
            note_text="A real typed twin note",
            source_event_ids=[start_id],
        ),
        document_id=document_id,
        events_dir=str(events_dir),
    )


def _create_notebook_terminal(
    db: Path,
    ready,
    region,
    *,
    investigation_id: str = "investigation-7",
    note_id: str = "external-twin-note-9",
) -> str:
    with connect_write(str(db), purpose="test/create-lineage-notebook") as con:
        notebook_id = create_notebook(
            con,
            title="Lineage terminal",
            investigation_id=investigation_id,
            document_id=ready.source_document_id,
        )
        append_block(
            con, notebook_id, block_type="region_embed", content={}, ref_id=region.region_id
        )
        append_block(con, notebook_id, block_type="note", content={}, ref_id=note_id)
    return notebook_id


def _create_write_terminal(
    db: Path,
    *,
    investigation_id: str,
    note_id: str,
) -> str:
    with connect_write(str(db), purpose="test/create-lineage-write-output") as con:
        deliverable_id = insert_deliverable(
            con,
            title="Sibling output",
            deliverable_kind="research_memo",
            investigation_root_id=investigation_id,
        )
        section_id = insert_section(con, deliverable_id=deliverable_id, section_index=0)
        return place_node_block(
            con,
            section_id=section_id,
            node_id=note_id,
            block_kind="insight",
            block_index=0,
            investigation_id=investigation_id,
        )


def _registration(ready, region, *, terminal_output_id: str, **changes):
    values = {
        "source_asset_id": ready.source_asset_id,
        "projection_id": ready.projection_id,
        "document_id": ready.source_document_id,
        "region_id": region.region_id,
        "investigation_id": "investigation-7",
        "twin_note_id": "external-twin-note-9",
        "terminal_kind": "notebook",
        "terminal_output_id": terminal_output_id,
        "metadata": {"workflow_version": "2", "reason_code": "user-started"},
    }
    values.update(changes)
    return values


def test_full_chain_reopens_reverse_queries_and_replays_exactly(tmp_path: Path) -> None:
    db = tmp_path / "lineage.duckdb"
    events_dir = tmp_path / "events"
    ready, region = _persist_html_and_region(db)
    _emit_investigation(
        events_dir,
        "investigation-7",
        "external-twin-note-9",
        region_id=region.region_id,
    )
    notebook_id = _create_notebook_terminal(db, ready, region)
    registry = WorkflowLineageRegistry(db, events_dir=events_dir)
    first = registry.register(**_registration(ready, region, terminal_output_id=notebook_id))
    assert first.complete and first.representation == "html"
    assert len(first.node_ids) == 6 and len(first.edge_ids) == 5
    assert first.source_asset_id == ready.source_asset_id
    assert first.projection_id == ready.projection_id
    assert first.region_id == region.region_id
    assert first.twin_note_id == "external-twin-note-9"
    assert (
        registry.register(**_registration(ready, region, terminal_output_id=notebook_id)) == first
    )

    reopened = WorkflowLineageRegistry(db, events_dir=events_dir)
    assert reopened.by_source_asset("asset-1") == (first,)
    assert reopened.by_document("doc-1") == (first,)
    assert reopened.by_terminal_output(notebook_id) == (first,)
    with connect_read(str(db)) as con:
        payload = str(
            con.execute("SELECT record_json FROM workflow_lineages").fetchone()[0]
        ).lower()
        assert "authoritative source region" not in payload
        assert "hosted_html_locator" not in payload


def test_honest_incomplete_and_missing_authorities(tmp_path: Path) -> None:
    db = tmp_path / "incomplete.duckdb"
    events_dir = tmp_path / "events"
    ready, region = _persist_html_and_region(db)
    _emit_investigation(
        events_dir,
        "investigation-7",
        "external-twin-note-9",
        region_id=region.region_id,
    )
    notebook_id = _create_notebook_terminal(db, ready, region)
    result = WorkflowLineageRegistry(db, events_dir=events_dir).by_source_asset("asset-1")
    assert len(result) == 1 and not result[0].complete
    assert result[0].missing_hops == (
        "document_region->investigation",
        "investigation->twin_note",
        "twin_note->notebook/write_output",
    )
    with pytest.raises(LineageValidationError, match="projection does not exist"):
        WorkflowLineageRegistry(db, events_dir=events_dir).register(
            **_registration(
                ready, region, terminal_output_id=notebook_id, projection_id="missing-projection"
            )
        )
    with pytest.raises(LineageValidationError, match="region does not exist"):
        WorkflowLineageRegistry(db, events_dir=events_dir).register(
            **_registration(
                ready, region, terminal_output_id=notebook_id, region_id="missing-region"
            )
        )


def test_external_authorities_fail_without_partial_lineage_rows(tmp_path: Path) -> None:
    db = tmp_path / "external-authorities.duckdb"
    events_dir = tmp_path / "events"
    ready, region = _persist_html_and_region(db)
    notebook_id = _create_notebook_terminal(db, ready, region)
    registry = WorkflowLineageRegistry(db, events_dir=events_dir)

    with pytest.raises(LineageValidationError, match="investigation does not exist"):
        registry.register(**_registration(ready, region, terminal_output_id=notebook_id))
    start_id = emit_typed(
        "investigation-7",
        InvestigationStartRequestedPayload(question="A real investigation"),
        events_dir=str(events_dir),
    )
    assert start_id is not None
    with pytest.raises(LineageValidationError, match="region-to-research seam does not exist"):
        registry.register(**_registration(ready, region, terminal_output_id=notebook_id))
    emit_typed(
        "investigation-7",
        SeamReadToResearchPayload(
            entity_id=region.region_id,
            provenance_ref=start_id,
            document_id=ready.source_document_id,
            launched_investigation_id="investigation-7",
        ),
        parent_event_id=start_id,
        document_id=ready.source_document_id,
        events_dir=str(events_dir),
    )
    with pytest.raises(LineageValidationError, match="twin note does not exist"):
        registry.register(**_registration(ready, region, terminal_output_id=notebook_id))

    with connect_read(str(db)) as con:
        for table in ("workflow_lineages", "workflow_lineage_nodes", "workflow_lineage_edges"):
            exists = con.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [table]
            ).fetchone()[0]
            assert not exists or con.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0


def test_notebook_terminal_requires_both_exact_reference_links(tmp_path: Path) -> None:
    db = tmp_path / "terminal-links.duckdb"
    events_dir = tmp_path / "events"
    ready, region = _persist_html_and_region(db)
    _emit_investigation(
        events_dir,
        "investigation-7",
        "external-twin-note-9",
        region_id=region.region_id,
    )
    with connect_write(str(db), purpose="test/create-incomplete-notebook") as con:
        notebook_id = create_notebook(
            con,
            title="Missing note link",
            investigation_id="investigation-7",
            document_id=ready.source_document_id,
        )
        append_block(
            con, notebook_id, block_type="region_embed", content={}, ref_id=region.region_id
        )
    with pytest.raises(LineageValidationError, match="missing exact region/note"):
        WorkflowLineageRegistry(db, events_dir=events_dir).register(
            **_registration(ready, region, terminal_output_id=notebook_id)
        )
    with connect_read(str(db)) as con:
        assert (
            con.execute(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_name = 'workflow_lineages'"
            ).fetchone()[0]
            == 0
        )


def test_terminal_rejects_duplicate_links_and_cross_investigation_write(
    tmp_path: Path,
) -> None:
    db = tmp_path / "terminal-identity.duckdb"
    events_dir = tmp_path / "events"
    ready, region = _persist_html_and_region(db)
    _emit_investigation(
        events_dir,
        "investigation-7",
        "external-twin-note-9",
        region_id=region.region_id,
    )
    notebook_id = _create_notebook_terminal(db, ready, region)
    with connect_write(str(db), purpose="test/duplicate-note-link") as con:
        append_block(
            con,
            notebook_id,
            block_type="note",
            content={},
            ref_id="external-twin-note-9",
        )
    registry = WorkflowLineageRegistry(db, events_dir=events_dir)
    with pytest.raises(LineageValidationError, match="missing exact region/note"):
        registry.register(**_registration(ready, region, terminal_output_id=notebook_id))

    wrong_output_id = _create_write_terminal(
        db,
        investigation_id="different-investigation",
        note_id="external-twin-note-9",
    )
    with pytest.raises(LineageValidationError, match="write output does not reference"):
        registry.register(
            **_registration(
                ready,
                region,
                terminal_kind="write_output",
                terminal_output_id=wrong_output_id,
            )
        )


@pytest.mark.parametrize(
    "metadata",
    [
        {"body": "secret"},
        {"source_text": "secret"},
        {"research": "secret"},
        {"workflow_version": "x" * 257},
        {"unknown": "value"},
        {"workflow_version": {"nested": "body"}},
    ],
)
def test_metadata_rejects_bodies_structure_and_oversize(tmp_path: Path, metadata) -> None:
    db = tmp_path / "metadata.duckdb"
    events_dir = tmp_path / "events"
    ready, region = _persist_html_and_region(db)
    with pytest.raises(LineageValidationError):
        WorkflowLineageRegistry(db, events_dir=events_dir).register(
            **_registration(ready, region, terminal_output_id="missing", metadata=metadata)
        )


def test_conflicting_replay_rolls_back_and_sibling_is_isolated(tmp_path: Path) -> None:
    db = tmp_path / "conflict.duckdb"
    events_dir = tmp_path / "events"
    ready, region = _persist_html_and_region(db)
    _emit_investigation(
        events_dir,
        "investigation-7",
        "external-twin-note-9",
        region_id=region.region_id,
    )
    notebook_id = _create_notebook_terminal(db, ready, region)
    registry = WorkflowLineageRegistry(db, events_dir=events_dir)
    first = registry.register(**_registration(ready, region, terminal_output_id=notebook_id))
    emit_typed(
        "investigation-7",
        NoteEmergedPayload(
            note_id="different-external-note",
            note_text="A conflicting real note",
            source_event_ids=[],
        ),
        document_id=ready.source_document_id,
        events_dir=str(events_dir),
    )
    with connect_write(str(db), purpose="test/add-conflicting-note-link") as con:
        append_block(
            con, notebook_id, block_type="note", content={}, ref_id="different-external-note"
        )
    with pytest.raises(LineageConflict):
        registry.register(
            **_registration(
                ready,
                region,
                terminal_output_id=notebook_id,
                twin_note_id="different-external-note",
            )
        )
    assert registry.by_source_asset("asset-1") == (first,)
    with connect_read(str(db)) as con:
        assert con.execute("SELECT count(*) FROM workflow_lineage_nodes").fetchone()[0] == 6
        assert con.execute("SELECT count(*) FROM workflow_lineage_edges").fetchone()[0] == 5

    second_notebook_id = _create_notebook_terminal(db, ready, region)
    second_branch = registry.register(
        **_registration(ready, region, terminal_output_id=second_notebook_id)
    )
    assert second_branch.lineage_id != first.lineage_id
    assert registry.by_source_asset("asset-1") == tuple(
        sorted((first, second_branch), key=lambda item: item.lineage_id)
    )

    _emit_investigation(
        events_dir,
        "investigation-sibling",
        "external-twin-sibling",
        region_id=region.region_id,
    )
    write_output_id = _create_write_terminal(
        db, investigation_id="investigation-sibling", note_id="external-twin-sibling"
    )
    sibling = registry.register(
        **_registration(
            ready,
            region,
            investigation_id="investigation-sibling",
            twin_note_id="external-twin-sibling",
            terminal_kind="write_output",
            terminal_output_id=write_output_id,
        )
    )
    assert sibling.lineage_id != first.lineage_id
    assert registry.by_terminal_output(write_output_id) == (sibling,)
    assert registry.by_terminal_output(notebook_id) == (first,)
