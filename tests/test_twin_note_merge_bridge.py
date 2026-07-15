from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from runtime.db_lock import connect_read, connect_write
from substrate.contracts.html_projection import HtmlProjectionContract, derive_projection_id
from substrate.graph.schema import init_database_at_path
from substrate.research_artifact.merge_draft import MergeDraftError, MergeDraftRepository
from substrate.twin_note_taker.compression import DurableTwinNoteCompression
from substrate.twin_note_taker.merge_bridge import (
    MergeBridgeConflict,
    MergeBridgeIntegrity,
    MergeBridgeUnavailable,
    SelectedNote,
    TwinNoteMergeBridge,
)
from substrate.twin_note_taker.serving import TwinNoteServingService


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha(value: str | bytes) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


@pytest.fixture
def bridge_fixture(tmp_path: Path):
    db = str(tmp_path / "graph.duckdb")
    root = tmp_path / "objects"
    root.mkdir()
    init_database_at_path(db)
    for window_id, investigation_id, text in (
        ("w-a", "inv-a", "Alpha <verified>"),
        ("w-b", "inv-b", "Beta"),
    ):
        sources = [f"evt-{investigation_id}"]
        source_json = _json(sources)
        request = _json({"investigation_id": investigation_id, "source_event_ids": sources})
        raw = _json({"notes": [{"text": text, "confidence": "high", "source_event_ids": sources}]})
        with connect_write(db, purpose="bridge-test-seed") as con:
            con.execute(
                "INSERT INTO note_taker_windows (window_id,consumer_version,investigation_id,"
                "threshold,ordinal,first_event_id,last_event_id,source_event_ids_json,source_digest,"
                "request_json,request_sha256,provider_idempotency_key,state,raw_result,raw_result_sha256) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [window_id, 2, investigation_id, 5, 0, sources[0], sources[0], source_json,
                 _sha(source_json), request, _sha(request), window_id, "completed", raw, _sha(raw)],
            )
    events = tmp_path / "events"
    events.mkdir()
    compressor = DurableTwinNoteCompression(
        lambda *_: True, db_path=db, publication_root=root, events_dir=str(events)
    )
    first = compressor.compress(account_id="owner-a", asset_id="asset", window_ids=("w-a",))
    second = compressor.compress(
        account_id="owner-a", asset_id="asset", window_ids=("w-b",),
        expected_predecessor=first.revision_id,
    )
    source_bytes = b"<article><h1>Source</h1></article>"
    (root / "source.html").write_bytes(source_bytes)
    identity = {
        "source_asset_id": "asset",
        "source_document_id": "document-a",
        "source_sha256": "a" * 64,
        "converter_id": "test",
        "converter_version": "1",
        "sanitizer_policy": "test",
        "sanitizer_version": "1",
    }
    projection = HtmlProjectionContract(
        **identity, projection_id=derive_projection_id(**identity), status="ready",
        hosted_html_locator="source.html", hosted_html_sha256=_sha(source_bytes),
    )
    with connect_write(db, purpose="bridge-test-source") as con:
        con.execute(
            "INSERT INTO documents (document_id,source_tier,document_type,owner_user_id) "
            "VALUES ('document-a',1,'html','owner-a')"
        )
        con.execute(
            "INSERT INTO html_projections VALUES (?,?,?)",
            [projection.projection_id, _json(projection.identity()), projection.model_dump_json()],
        )
    return db, root, projection, first, second


def test_revision_bridge_is_deterministic_script_free_and_replayable(bridge_fixture) -> None:
    db, root, source, first, _second = bridge_fixture
    service = TwinNoteMergeBridge(db_path=db, publication_root=root)
    with connect_read(db) as con:
        immutable_before = (
            con.execute("SELECT projection_json FROM html_projections WHERE projection_id=?", [source.projection_id]).fetchone(),
            tuple(con.execute("SELECT * FROM twin_note_revisions ORDER BY revision_id").fetchall()),
            tuple(con.execute("SELECT * FROM twin_note_revision_members ORDER BY ALL").fetchall()),
            tuple(con.execute("SELECT * FROM note_taker_windows ORDER BY window_id").fetchall()),
        )
    command = dict(
        owner_user_id="owner-a", source_projection_id=source.projection_id,
        source_kind="revision", source_id=first.revision_id,
        selected_notes=[SelectedNote(first.revision_id, 0)], idempotency_key="key-revision-0001",
    )
    result = service.create(**command)
    assert service.create(**command) == result
    payload = next(root.glob("*/tmb_*/appendix.html")).read_bytes()
    assert b"Alpha &lt;verified&gt;" in payload and b"<script" not in payload
    assert b"inv-a" not in payload and b"evt-inv-a" not in payload
    assert result.response()["merge_draft_input"]["projection_ids"] == [
        source.projection_id, result.projection_id
    ]
    draft = MergeDraftRepository(db_path=db, projection_root=root).create_draft(
        owner_user_id="owner-a",
        projection_ids=(source.projection_id, result.projection_id),
        intent="create",
        title="Source with twin-note appendix",
        asset_kind="analysis",
    )
    assert "Advisory machine-authored twin-note appendix" in draft.canonical_html
    with connect_read(db) as con:
        assert con.execute("SELECT object_state FROM twin_note_merge_bridges").fetchone() == ("published",)
        immutable_after = (
            con.execute("SELECT projection_json FROM html_projections WHERE projection_id=?", [source.projection_id]).fetchone(),
            tuple(con.execute("SELECT * FROM twin_note_revisions ORDER BY revision_id").fetchall()),
            tuple(con.execute("SELECT * FROM twin_note_revision_members ORDER BY ALL").fetchall()),
            tuple(con.execute("SELECT * FROM note_taker_windows ORDER BY window_id").fetchall()),
        )
    assert immutable_after == immutable_before


def test_projection_row_key_substitution_refuses_bridge_and_draft(bridge_fixture) -> None:
    db, root, source, first, _second = bridge_fixture
    replacement_identity = {**source.identity(), "source_sha256": "b" * 64}
    replacement = HtmlProjectionContract(
        **replacement_identity,
        projection_id=derive_projection_id(**replacement_identity),
        status="ready",
        hosted_html_locator=source.hosted_html_locator,
        hosted_html_sha256=source.hosted_html_sha256,
    )
    with connect_write(db, purpose="bridge-row-key-substitution") as con:
        con.execute(
            "UPDATE html_projections SET identity_json=?, projection_json=? WHERE projection_id=?",
            [_json(replacement.identity()), replacement.model_dump_json(), source.projection_id],
        )
    bridge = TwinNoteMergeBridge(db_path=db, publication_root=root)
    with pytest.raises(MergeBridgeUnavailable):
        bridge.create(
            owner_user_id="owner-a",
            source_projection_id=source.projection_id,
            source_kind="revision",
            source_id=first.revision_id,
            selected_notes=[SelectedNote(first.revision_id, 0)],
            idempotency_key="row-key-substitution",
        )
    with pytest.raises(MergeDraftError):
        MergeDraftRepository(db_path=db, projection_root=root).create_draft(
            owner_user_id="owner-a",
            projection_ids=(source.projection_id,),
            intent="create",
            title="Substituted",
            asset_kind="analysis",
        )


def test_projection_row_key_substitution_after_draft_refuses_review(bridge_fixture) -> None:
    db, root, source, _first, _second = bridge_fixture
    repository = MergeDraftRepository(db_path=db, projection_root=root)
    draft = repository.create_draft(
        owner_user_id="owner-a",
        projection_ids=(source.projection_id,),
        intent="create",
        title="Review binding",
        asset_kind="analysis",
    )
    replacement_identity = {**source.identity(), "source_sha256": "b" * 64}
    replacement = HtmlProjectionContract(
        **replacement_identity,
        projection_id=derive_projection_id(**replacement_identity),
        status="ready",
        hosted_html_locator=source.hosted_html_locator,
        hosted_html_sha256=source.hosted_html_sha256,
    )
    with connect_write(db, purpose="review-row-key-substitution") as con:
        con.execute(
            "UPDATE html_projections SET identity_json=?, projection_json=? WHERE projection_id=?",
            [_json(replacement.identity()), replacement.model_dump_json(), source.projection_id],
        )
    with pytest.raises(MergeDraftError):
        repository.create_review(owner_user_id="owner-a", draft_id=draft.draft_id)


def test_composition_allows_explicit_cross_member_order_and_converges(bridge_fixture) -> None:
    db, root, source, first, second = bridge_fixture
    serving = TwinNoteServingService(db_path=db)
    composition = serving.compose("owner-a", [first.revision_id, second.revision_id])
    service = TwinNoteMergeBridge(db_path=db, publication_root=root)
    kwargs = dict(
        owner_user_id="owner-a", source_projection_id=source.projection_id,
        source_kind="composition", source_id=composition["composition_id"],
        selected_notes=[SelectedNote(second.revision_id, 0), SelectedNote(first.revision_id, 0)],
    )
    first_result = service.create(**kwargs, idempotency_key="composition-key-01")
    second_result = service.create(**kwargs, idempotency_key="composition-key-02")
    assert second_result == first_result
    payload = next(root.glob("*/tmb_*/appendix.html")).read_bytes()
    assert payload.index(b"Beta") < payload.index(b"Alpha")
    with connect_read(db) as con:
        assert con.execute("SELECT count(*) FROM twin_note_merge_bridges").fetchone() == (1,)


def test_concurrent_identical_commands_converge(bridge_fixture) -> None:
    db, root, source, first, _second = bridge_fixture
    kwargs = dict(
        owner_user_id="owner-a", source_projection_id=source.projection_id,
        source_kind="revision", source_id=first.revision_id,
        selected_notes=[SelectedNote(first.revision_id, 0)], idempotency_key="concurrent-key-001",
    )
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(
            lambda _: TwinNoteMergeBridge(db_path=db, publication_root=root).create(**kwargs),
            range(8),
        ))
    assert results == [results[0]] * 8
    with connect_read(db) as con:
        assert con.execute("SELECT count(*) FROM twin_note_merge_bridges").fetchone() == (1,)
        assert con.execute("SELECT count(*) FROM twin_note_merge_bridge_members").fetchone() == (1,)


def test_owner_selection_and_idempotency_fail_closed(bridge_fixture) -> None:
    db, root, source, first, second = bridge_fixture
    service = TwinNoteMergeBridge(db_path=db, publication_root=root)
    base = dict(
        owner_user_id="owner-a", source_projection_id=source.projection_id,
        source_kind="revision", source_id=first.revision_id,
        selected_notes=[SelectedNote(first.revision_id, 0)], idempotency_key="same-key-0000001",
    )
    service.create(**base)
    with pytest.raises(MergeBridgeConflict):
        service.create(**(base | {"source_id": second.revision_id}))
    with pytest.raises(MergeBridgeUnavailable):
        service.create(**(base | {"owner_user_id": "owner-b", "idempotency_key": "foreign-key-00001"}))
    with pytest.raises(MergeBridgeUnavailable):
        service.create(**(base | {"selected_notes": [SelectedNote(second.revision_id, 0)],
                                  "idempotency_key": "nonmember-key-001"}))


def test_pending_recovery_and_tamper_detection(bridge_fixture, monkeypatch) -> None:
    db, root, source, first, _second = bridge_fixture
    service = TwinNoteMergeBridge(db_path=db, publication_root=root)
    original = service.recover
    monkeypatch.setattr(service, "recover", lambda **_: [])
    with pytest.raises(MergeBridgeIntegrity):
        service.create(
            owner_user_id="owner-a", source_projection_id=source.projection_id,
            source_kind="revision", source_id=first.revision_id,
            selected_notes=[SelectedNote(first.revision_id, 0)], idempotency_key="pending-key-00001",
        )
    monkeypatch.setattr(service, "recover", original)
    same_key = service.create(
        owner_user_id="owner-a", source_projection_id=source.projection_id,
        source_kind="revision", source_id=first.revision_id,
        selected_notes=[SelectedNote(first.revision_id, 0)], idempotency_key="pending-key-00001",
    )
    with connect_read(db) as con:
        bridge_id, locator = con.execute(
            "SELECT bridge_id,object_locator FROM twin_note_merge_bridges"
        ).fetchone()
    with connect_write(db, purpose="bridge-test-pending-replay") as con:
        con.execute(
            "UPDATE twin_note_merge_bridges SET object_state='pending',published_at=NULL "
            "WHERE bridge_id=?", [bridge_id],
        )
    (root / locator).unlink()
    different_key = service.create(
        owner_user_id="owner-a", source_projection_id=source.projection_id,
        source_kind="revision", source_id=first.revision_id,
        selected_notes=[SelectedNote(first.revision_id, 0)], idempotency_key="pending-key-00002",
    )
    assert same_key == different_key == service.reopen(
        owner_user_id="owner-a", bridge_id=bridge_id
    )
    with connect_read(db) as con:
        assert con.execute("SELECT count(*) FROM twin_note_merge_bridges").fetchone() == (1,)
    with connect_write(db, purpose="bridge-test-tamper") as con:
        con.execute("UPDATE twin_note_merge_bridge_members SET canonical_note_sha256=?", ["f" * 64])
    with pytest.raises(MergeBridgeIntegrity):
        service.reopen(owner_user_id="owner-a", bridge_id=bridge_id)


@pytest.mark.parametrize("tamper", ["request", "manifest", "object", "hardlink"])
def test_receipt_and_object_tamper_fail_closed(bridge_fixture, tamper: str) -> None:
    db, root, source, first, _second = bridge_fixture
    service = TwinNoteMergeBridge(db_path=db, publication_root=root)
    service.create(
        owner_user_id="owner-a", source_projection_id=source.projection_id,
        source_kind="revision", source_id=first.revision_id,
        selected_notes=[SelectedNote(first.revision_id, 0)], idempotency_key="tamper-key-000001",
    )
    with connect_read(db) as con:
        bridge_id, locator = con.execute(
            "SELECT bridge_id,object_locator FROM twin_note_merge_bridges"
        ).fetchone()
    if tamper == "object":
        (root / locator).write_bytes(b"tampered")
    elif tamper == "hardlink":
        (root / "second-name.html").hardlink_to(root / locator)
    else:
        column = "request_json" if tamper == "request" else "manifest_json"
        digest = "request_sha256" if tamper == "request" else "manifest_sha256"
        value = '{"valid":"but inconsistent"}'
        with connect_write(db, purpose="bridge-test-receipt-tamper") as con:
            con.execute(f"UPDATE twin_note_merge_bridges SET {column}=?,{digest}=?", [value, _sha(value)])
    with pytest.raises(MergeBridgeIntegrity):
        service.reopen(owner_user_id="owner-a", bridge_id=bridge_id)
