from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb
import pytest
from pydantic import ValidationError

from substrate.contracts.html_projection import (
    AnchorMapping,
    HtmlProjectionContract,
    SemanticLocator,
    derive_anchor_id,
    derive_projection_id,
)
from substrate.reading.projection import ProjectionStore
from substrate.reading.projection.source_catalog import (
    ProjectionSourceCandidate,
    enumerate_projection_sources,
)
from substrate.reading.regions import (
    CanonicalDocumentRegion,
    RegionConflict,
    RegionStore,
    derive_region_id,
)

SHA = "a" * 64


def _projection(status: str = "ready", document_id: str = "doc") -> HtmlProjectionContract:
    identity = {
        "source_asset_id": "asset", "source_document_id": document_id,
        "source_sha256": SHA, "converter_id": "pdfium", "converter_version": "1",
        "sanitizer_policy": "policy", "sanitizer_version": "1",
    }
    projection_id = derive_projection_id(**identity)
    locator = SemanticLocator(semantic_id="section")
    values: dict[str, object] = {
        **identity, "projection_id": projection_id, "status": status, "anchor_mappings": (),
    }
    if status == "ready":
        values.update(
            hosted_html_locator="ready.html", hosted_html_sha256="b" * 64,
            anchor_mappings=(AnchorMapping(
                source_locator=locator, state="resolved",
                html_anchor_id=derive_anchor_id(projection_id, locator),
            ),),
        )
    return HtmlProjectionContract.model_validate(values)


def _region(projection: HtmlProjectionContract, **changes: object) -> CanonicalDocumentRegion:
    locator = SemanticLocator(semantic_id="section")
    identity: dict[str, object] = {
        "document_id": projection.source_document_id,
        "projection_id": projection.projection_id,
        "source_locator": locator.model_dump(),
        "html_anchor_id": derive_anchor_id(projection.projection_id, locator),
        "char_start": 0, "char_end": 4, "exact_text_sha256": SHA,
    }
    identity.update({key: value for key, value in changes.items() if key != "created_event_id"})
    values = {**identity, "region_id": derive_region_id(**identity), **changes}
    return CanonicalDocumentRegion.model_validate(values)


def _persist_ready(con: duckdb.DuckDBPyConnection, ready: HtmlProjectionContract) -> None:
    store = ProjectionStore(con)
    cleared = {
        "hosted_html_locator": None, "hosted_html_sha256": None, "anchor_mappings": (),
    }
    store.claim(ready.model_copy(update={"status": "queued", **cleared}))
    store.transition(ready.model_copy(update={"status": "extracting", **cleared}))
    store.transition(ready.model_copy(update={"status": "sanitizing", **cleared}))
    store.transition(ready)


def test_region_identity_validation_and_event_independence() -> None:
    projection = _projection()
    assert _region(projection, created_event_id="one").region_id == _region(
        projection, created_event_id="two"
    ).region_id
    assert _region(projection).region_id != _region(projection, char_end=5).region_id
    with pytest.raises(ValidationError, match="supplied together"):
        _region(projection).model_copy(update={"char_end": None}).model_validate(
            _region(projection).model_dump() | {"char_end": None}
        )
    with pytest.raises(ValidationError, match="canonical derived anchor"):
        CanonicalDocumentRegion.model_validate(_region(projection).model_dump() | {"html_anchor_id": "wrong"})


def test_store_replay_guards_and_reopen(tmp_path: Path) -> None:
    db = tmp_path / "regions.duckdb"
    con = duckdb.connect(str(db))
    projection = _projection()
    _persist_ready(con, projection)
    region = _region(projection)
    store = RegionStore(con)
    assert store.claim(region) == store.claim(region)
    forged = region.model_copy(update={"created_event_id": "different"})
    with pytest.raises(RegionConflict):
        store.claim(forged)
    with pytest.raises(RegionConflict):
        store.claim(region.model_copy(update={"region_id": "region-" + "0" * 64}))
    con.close()
    reopened = duckdb.connect(str(db))
    assert RegionStore(reopened).load(region.region_id) == region
    assert RegionStore(reopened).list(document_id="doc") == (region,)
    assert RegionStore(reopened).list(
        projection_id=projection.projection_id, document_id="doc"
    ) == (region,)
    with pytest.raises(KeyError):
        RegionStore(reopened).load("region-" + "f" * 64)


def test_store_rejects_nonready_unmapped_and_cross_document() -> None:
    con = duckdb.connect(":memory:")
    queued = _projection("queued")
    ProjectionStore(con).claim(queued)
    with pytest.raises(RegionConflict, match="ready"):
        RegionStore(con).claim(_region(queued))
    ready = _projection(document_id="other")
    _persist_ready(con, ready)
    with pytest.raises(RegionConflict, match="canonical validation"):
        RegionStore(con).claim(
            _region(ready).model_copy(update={"region_id": "region-" + "0" * 64})
        )
    values = _region(ready).model_dump() | {"document_id": "doc"}
    values["region_id"] = derive_region_id(**{k: v for k, v in values.items() if k not in {"region_id", "created_event_id"}})
    with pytest.raises(RegionConflict, match="source document"):
        RegionStore(con).claim(CanonicalDocumentRegion.model_validate(values))

    valid = _region(ready)
    unmapped_locator = SemanticLocator(semantic_id="not-mapped")
    unmapped_values = valid.model_dump() | {
        "source_locator": unmapped_locator.model_dump(),
        "html_anchor_id": derive_anchor_id(ready.projection_id, unmapped_locator),
    }
    unmapped_values["region_id"] = derive_region_id(
        **{
            key: value
            for key, value in unmapped_values.items()
            if key not in {"region_id", "created_event_id"}
        }
    )
    unmapped = CanonicalDocumentRegion.model_validate(unmapped_values)
    with pytest.raises(RegionConflict, match="not exactly resolved"):
        RegionStore(con).claim(unmapped)
    with pytest.raises(RegionConflict, match="canonical validation"):
        RegionStore(con).claim(valid.model_copy(update={"html_anchor_id": "forged"}))


def test_discovered_source_projects_into_a_canonical_region(tmp_path: Path) -> None:
    source = b"%PDF-1.7\nsource"
    object_path = tmp_path / "pdf/source.pdf"
    object_path.parent.mkdir()
    object_path.write_bytes(source)
    con = duckdb.connect(":memory:")
    con.execute(
        "CREATE TABLE documents(document_id TEXT, document_type TEXT, raw_text TEXT, metadata TEXT)"
    )
    con.execute(
        "INSERT INTO documents VALUES (?, ?, ?, ?)",
        [
            "doc",
            "pdf",
            "never projection bytes",
            json.dumps(
                {
                    "html_projection_source": {
                        "source_asset_id": "asset",
                        "object_key": "pdf/source.pdf",
                        "sha256": hashlib.sha256(source).hexdigest(),
                        "byte_size": len(source),
                        "media_type": "application/pdf",
                    }
                }
            ),
        ],
    )

    (candidate,) = enumerate_projection_sources(con, tmp_path)
    assert isinstance(candidate, ProjectionSourceCandidate)
    ready = _projection(document_id=candidate.document_id).model_copy(
        update={
            "source_asset_id": candidate.source_asset_id,
            "source_sha256": candidate.sha256,
        }
    )
    identity = ready.identity()
    ready = ready.model_copy(
        update={
            "projection_id": derive_projection_id(**identity),
            "anchor_mappings": (),
        }
    )
    locator = SemanticLocator(semantic_id="section")
    ready = ready.model_copy(
        update={
            "anchor_mappings": (
                AnchorMapping(
                    source_locator=locator,
                    state="resolved",
                    html_anchor_id=derive_anchor_id(ready.projection_id, locator),
                ),
            )
        }
    )
    ready = HtmlProjectionContract.model_validate(ready.model_dump())
    _persist_ready(con, ready)

    region = _region(ready)
    assert RegionStore(con).claim(region).projection_id == ready.projection_id
