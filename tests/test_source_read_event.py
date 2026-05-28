"""Living Roadmap SPR-07 M4 — the ``source.read`` typed event round-trips
through the single-writer funnel and carries the dwell EVIDENCE (never a body),
so SiteSee's per-source "read" tint is substrate-derived (closes the SPR-06
``spr-06-source-read-event-gap.md`` gap).

These assert the SUBSTRATE side: the event persists with its dwell evidence,
is a member of the typed union, and structurally carries NO source body (§9.0 —
the read of a source records the reader's own dwell, never the source text). The
frontend half (emit-once-per-session on the dwell threshold + the SiteSee
resolver lighting the "read" tint) is covered by the reader / sitesee vitest
suites.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from substrate.event_log import emit_typed, trajectory
from substrate.schemas.events import (
    EVENT_SCHEMA_VERSION,
    TYPED_PAYLOAD_ACTION_TYPES,
    SourceReadPayload,
)


@pytest.fixture(autouse=True)
def _events_dir(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="antiek-source-read-")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmp, "events"))


# ── schema ──────────────────────────────────────────────────────────────────


def test_source_read_payload_defaults():
    p = SourceReadPayload()
    assert p.action_type == "source.read"
    assert p.chunk_id is None
    assert p.dwell_ms == 0
    assert p.page_count == 0


def test_source_read_is_in_the_typed_union():
    assert "source.read" in TYPED_PAYLOAD_ACTION_TYPES


def test_source_read_carries_no_body_field():
    """§9.0: the event records the reader's dwell EVIDENCE, never the source
    body. No excerpt/text/body field exists on the payload — leaking a withheld
    source's body through this event is structurally impossible."""
    fields = set(SourceReadPayload.model_fields)
    for forbidden in ("excerpt", "text", "body", "full_text", "snippet", "content"):
        assert forbidden not in fields
    # Only the anchor + the dwell evidence are carried.
    assert {"chunk_id", "dwell_ms", "page_count"} <= fields


def test_source_read_rejects_negative_dwell():
    """The dwell evidence is a measurement, never negative."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SourceReadPayload(dwell_ms=-1)
    with pytest.raises(ValidationError):
        SourceReadPayload(page_count=-1)


# ── persistence: the emitted event round-trips with its evidence ─────────────


def test_emitted_source_read_event_round_trips_through_the_funnel():
    event_id = emit_typed(
        "read-doc-book-1",
        SourceReadPayload(chunk_id="chunk-7", dwell_ms=45_000, page_count=4),
        document_id="doc-book-1",
        role="reader/source-read",
        policy_id="reader/source-read",
    )
    assert event_id is not None

    events = trajectory("read-doc-book-1")
    read_events = [e for e in events if e.get("action_type") == "source.read"]
    assert len(read_events) == 1
    payload = read_events[0]["payload"]
    # The dwell evidence that justified the "read" verdict is reconstructable
    # from the event alone (defensibility — the threshold's witness).
    assert payload["dwell_ms"] == 45_000
    assert payload["page_count"] == 4
    assert payload["chunk_id"] == "chunk-7"
    # The document the read is attributed to rides the Event envelope.
    assert read_events[0]["document_id"] == "doc-book-1"
    assert read_events[0]["schema_version"] == EVENT_SCHEMA_VERSION


def test_source_read_event_carries_only_metadata_no_source_text():
    """A persisted source.read event carries the anchor + dwell evidence and
    nothing resembling the source body — verified on the round-tripped row."""
    emit_typed(
        "read-doc-2",
        SourceReadPayload(chunk_id="chunk-2", dwell_ms=30_000, page_count=2),
        document_id="doc-2",
    )
    events = trajectory("read-doc-2")
    read = next(e for e in events if e.get("action_type") == "source.read")
    assert set(read["payload"]) == {"action_type", "chunk_id", "dwell_ms", "page_count"}
