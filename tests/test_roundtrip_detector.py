"""SPR-08 M2: round-trip detector — both classes proven BEFORE the window.

A detector first exercised by real data can fail silently and report a false
zero, which would retire the form-factor framing on a measurement bug. So both
classes are proven here on a synthetic round-trip through REAL .antiek bytes.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from services.antiek_format import read_antiek
from services.antiek_format.native_writer import WriterInput, write_antiek
from services.antiek_format.signature import ensure_keypair
from services.demand_gate.roundtrip_detector import (
    ROUNDTRIP_EVENT_TYPE,
    ExportRegistry,
    classify_roundtrip,
)


def _content(text: str) -> dict:
    return {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


def test_returned_unmodified_classified_and_emits_event():
    reg = ExportRegistry()
    reg.record_export("d1", _content("X"))
    r = classify_roundtrip("d1", _content("X"), reg)
    assert r.classification == "returned_unmodified" and r.is_roundtrip
    assert r.event is not None
    assert r.event["action_type"] == ROUNDTRIP_EVENT_TYPE


def test_traveled_and_changed_is_the_strongest_signal():
    reg = ExportRegistry()
    reg.record_export("d1", _content("the original"))
    r = classify_roundtrip("d1", _content("the EDITED version"), reg)
    assert r.classification == "traveled_and_changed" and r.is_roundtrip
    assert r.event is not None


def test_novel_is_not_a_roundtrip_and_emits_nothing():
    reg = ExportRegistry()
    reg.record_export("d1", _content("X"))
    r = classify_roundtrip("d2", _content("Y"), reg)
    assert r.classification == "novel" and not r.is_roundtrip
    assert r.event is None


@pytest.fixture
def keypair(tmp_path):
    return ensure_keypair("u", db_path=str(tmp_path / "k.duckdb"))


def _export_bytes(keypair, text: str) -> bytes:
    inp = WriterInput(
        notebook_id="nb",
        user_id="u",
        document_id="doc-rt",
        parent_document_id=None,
        content_class="notebook",
        title="t",
        content_tiptap=_content(text),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    return write_antiek(inp, keypair=keypair)


def test_synthetic_roundtrip_through_real_artifacts(keypair):
    # Export -> (someone modifies it elsewhere) -> re-import, on REAL .antiek
    # bytes via the signature-checked read path SPR-07 ingests through.
    reg = ExportRegistry()
    original = _export_bytes(keypair, "the original passage")
    reg.record_export("doc-rt", _content("the original passage"))

    # the unmodified file comes back
    back = read_antiek(original)
    assert back.signature_valid
    r_back = classify_roundtrip(back.document_id, back.content_tiptap, reg)
    assert r_back.classification == "returned_unmodified"

    # a modified copy comes back (same document id, different content)
    travelled = read_antiek(_export_bytes(keypair, "the EDITED passage"))
    assert travelled.signature_valid
    r_travelled = classify_roundtrip(
        travelled.document_id, travelled.content_tiptap, reg
    )
    assert r_travelled.classification == "traveled_and_changed"
