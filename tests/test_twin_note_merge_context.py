from __future__ import annotations

import pytest

from runtime.db_lock import connect_write
from substrate.contracts.html_projection import HtmlProjectionContract, derive_projection_id
from substrate.twin_note_taker.merge_context import (
    MergeContextIntegrity,
    MergeContextUnavailable,
    TwinNoteMergeContext,
)
from substrate.twin_note_taker.serving import TwinNoteServingService

pytest_plugins = ("tests.test_twin_note_merge_bridge",)


def test_context_is_verified_bounded_and_display_only(bridge_fixture) -> None:
    db, root, source, first, second = bridge_fixture
    with connect_write(db, purpose="merge-context-title") as con:
        con.execute("UPDATE documents SET title='Flight systems' WHERE document_id='document-a'")
    composition = TwinNoteServingService(db_path=db).compose(
        "owner-a", [first.revision_id, second.revision_id]
    )
    result = TwinNoteMergeContext(db_path=db, projection_root=root).discover("owner-a")

    assert result["source_projections"] == [{
        "projection_id": source.projection_id,
        "source_asset_id": "asset",
        "source_document_id": "document-a",
        "label": "Flight systems",
        "preview_url": (
            "/research/twin-notes/merge-context/source-projections/"
            f"{source.projection_id}/preview"
        ),
    }]
    revisions = [item for item in result["twin_sources"] if item["kind"] == "revision"]
    assert {item["id"] for item in revisions} == {first.revision_id, second.revision_id}
    first_context = next(item for item in revisions if item["id"] == first.revision_id)
    assert first_context["revisions"][0]["notes"] == [
        {"note_ordinal": 0, "text": "Alpha <verified>", "source_count": 1}
    ]
    composed = next(item for item in result["twin_sources"]
                    if item["id"] == composition["composition_id"])
    assert [item["member_ordinal"] for item in composed["revisions"]] == [0, 1]
    rendered = repr(result)
    for forbidden in ("html_sha", "body_sha", "locator", "evt-inv", "inv-a", "w-a", "provider"):
        assert forbidden not in rendered


def test_context_previews_are_exact_and_owner_bound(bridge_fixture) -> None:
    db, root, source, first, _second = bridge_fixture
    service = TwinNoteMergeContext(db_path=db, projection_root=root)
    assert service.source_preview("owner-a", source.projection_id) == (
        root / "source.html"
    ).read_bytes()
    assert service.twin_preview("owner-a", "revision", first.revision_id) == first.html_bytes
    for owner in ("owner-b", "missing"):
        with pytest.raises(MergeContextUnavailable):
            service.source_preview(owner, source.projection_id)
        with pytest.raises(MergeContextUnavailable):
            service.twin_preview(owner, "revision", first.revision_id)


def test_context_rejects_object_and_twin_tamper(bridge_fixture) -> None:
    db, root, source, _first, _second = bridge_fixture
    service = TwinNoteMergeContext(db_path=db, projection_root=root)
    (root / "source.html").write_bytes(b"tampered")
    with pytest.raises(MergeContextIntegrity):
        service.discover("owner-a")
    with pytest.raises(MergeContextIntegrity):
        service.source_preview("owner-a", source.projection_id)


def test_context_rejects_owned_projection_identity_or_payload_drift(bridge_fixture) -> None:
    db, root, source, _first, _second = bridge_fixture
    service = TwinNoteMergeContext(db_path=db, projection_root=root)
    with connect_write(db, purpose="merge-context-projection-tamper") as con:
        con.execute(
            "UPDATE html_projections SET projection_json=? WHERE projection_id=?",
            ['{"status":"ready"}', source.projection_id],
        )
    with pytest.raises(MergeContextIntegrity):
        service.discover("owner-a")


def test_context_rejects_valid_projection_stored_under_another_row_key(bridge_fixture) -> None:
    db, root, source, _first, _second = bridge_fixture
    replacement_identity = {**source.identity(), "source_sha256": "b" * 64}
    replacement = HtmlProjectionContract(
        **replacement_identity,
        projection_id=derive_projection_id(**replacement_identity),
        status="ready",
        hosted_html_locator=source.hosted_html_locator,
        hosted_html_sha256=source.hosted_html_sha256,
    )
    with connect_write(db, purpose="merge-context-row-key-substitution") as con:
        con.execute(
            "UPDATE html_projections SET identity_json=?, projection_json=? WHERE projection_id=?",
            [replacement.model_dump_json(include=set(replacement.identity())),
             replacement.model_dump_json(), source.projection_id],
        )
    service = TwinNoteMergeContext(db_path=db, projection_root=root)
    with pytest.raises(MergeContextIntegrity):
        service.discover("owner-a")
    with pytest.raises(MergeContextIntegrity):
        service.source_preview("owner-a", source.projection_id)


def test_foreign_malformed_projection_does_not_poison_owner_context(bridge_fixture) -> None:
    db, root, source, _first, _second = bridge_fixture
    with connect_write(db, purpose="merge-context-foreign-malformed") as con:
        con.execute(
            "INSERT INTO html_projections VALUES (?,?,?)",
            ["foreign-malformed", "{}", '{"status":"ready"}'],
        )
    result = TwinNoteMergeContext(db_path=db, projection_root=root).discover("owner-a")
    assert [item["projection_id"] for item in result["source_projections"]] == [
        source.projection_id
    ]
