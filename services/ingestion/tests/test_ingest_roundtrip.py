"""SPR-08 M2 wiring: ingest_antiek classifies round-trips against a registry.

The detector existed but was never called from the ingest path. These prove it
is now wired: a re-ingested container is classified, detection never changes the
ingest decision, and a quarantined artifact is never classified.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from services.antiek_format import read_antiek
from services.antiek_format.native_writer import WriterInput, write_antiek
from services.antiek_format.signature import ensure_keypair
from services.demand_gate.roundtrip_detector import ExportRegistry
from services.ingestion.ingest_antiek import ingest_antiek


@pytest.fixture
def keypair(tmp_path):
    return ensure_keypair("user-test", db_path=str(tmp_path / "k.duckdb"))


def _container(keypair, text: str) -> bytes:
    inp = WriterInput(
        notebook_id="nb",
        user_id="user-test",
        document_id="doc-1",
        parent_document_id=None,
        content_class="notebook",
        title="t",
        content_tiptap={
            "type": "doc",
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
        },
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    return write_antiek(inp, keypair=keypair)


def _registry_with(keypair, text: str) -> ExportRegistry:
    reg = ExportRegistry()
    r = read_antiek(_container(keypair, text))
    reg.record_export(r.document_id, r.content_tiptap)
    return reg


def test_returned_unmodified_is_classified(keypair):
    reg = _registry_with(keypair, "the passage")
    result = ingest_antiek(_container(keypair, "the passage"), export_registry=reg)
    assert result.ok and result.roundtrip == "returned_unmodified"


def test_traveled_and_changed_is_classified(keypair):
    reg = _registry_with(keypair, "the original")
    # same document_id (doc-1), different content -> the strongest signal
    result = ingest_antiek(_container(keypair, "the EDITED passage"), export_registry=reg)
    assert result.ok and result.roundtrip == "traveled_and_changed"


def test_no_registry_means_no_classification(keypair):
    result = ingest_antiek(_container(keypair, "x"))
    assert result.ok and result.roundtrip is None


def test_quarantined_container_is_never_classified(keypair):
    # Corrupt the SIGNED content (ZIP_STORED -> the text is literally in the
    # bytes) so the signature fails -> quarantined before any classification.
    blob = _container(keypair, "TAMPERTARGET")
    idx = blob.find(b"TAMPERTARGET")
    assert idx != -1
    ba = bytearray(blob)
    ba[idx] ^= 0xFF
    result = ingest_antiek(bytes(ba), export_registry=_registry_with(keypair, "x"))
    assert result.quarantined and result.roundtrip is None


def test_garbage_is_quarantined_and_unclassified(keypair):
    result = ingest_antiek(
        b"definitely not a born-Antiek artifact", export_registry=_registry_with(keypair, "x")
    )
    assert result.quarantined and result.roundtrip is None
