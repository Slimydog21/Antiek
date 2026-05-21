"""RLM bridge event emission tests — wrestling.document_loaded
escalation/deferral → rlm.bridge.decided typed event."""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone

import pytest


@pytest.fixture()
def isolated_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-rlm-bridge-emit-")
    db_path = os.path.join(tmpdir, "antiek.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    try:
        from substrate.graph import ensure_initialized
        ensure_initialized(db_path)
        yield db_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


class _RecordingBroadcaster:
    """Minimal broadcaster shim recording every event for assertion."""

    def __init__(self) -> None:
        self.events: list = []

    async def broadcast(self, event) -> None:
        self.events.append(event)


def _make_doc_loaded_event(
    *,
    document_id: str,
    investigation_id: str,
    size_bytes: int,
):
    from substrate.schemas.events import (
        ActionType,
        DocumentLoadedPayload,
        Event,
    )

    payload = DocumentLoadedPayload(
        media_type="pdf",
        source_uri=f"file:///tmp/{document_id}.pdf",
        title=f"doc {document_id}",
        content_hash="deadbeef",
        size_bytes=size_bytes,
        page_count=10,
    )
    return Event(
        event_id=f"evt-{uuid.uuid4().hex[:8]}",
        investigation_id=investigation_id,
        action_type=ActionType.DOCUMENT_LOADED,
        payload=payload,
        param_version="test-v0",
        emitted_at=datetime.now(timezone.utc),
        document_id=document_id,
    )


def test_above_threshold_defer_emits_typed_event(isolated_db, monkeypatch):
    """An above-threshold document with no ratification → emits
    rlm.bridge.decided with reason='deferred_pending_ratification'."""
    monkeypatch.delenv("ANTIEK_RLM_RATIFIED", raising=False)

    from interfaces.research.api.wrestling import make_document_loaded_handler

    bus = _RecordingBroadcaster()
    handler = make_document_loaded_handler(
        db_path=isolated_db, broadcaster=bus,
    )
    # 1 MiB doc → ~262 144 estimated tokens, well above the 64K threshold.
    event = _make_doc_loaded_event(
        document_id="doc-large",
        investigation_id="inv-1",
        size_bytes=1_048_576,
    )
    asyncio.run(handler(event))

    # One rlm.bridge.decided event should have been broadcast.
    bridge_events = [
        e for e in bus.events
        if (e.action_type.value if hasattr(e.action_type, "value") else e.action_type)
        == "rlm.bridge.decided"
    ]
    assert len(bridge_events) == 1
    evt = bridge_events[0]
    assert evt.payload.reason == "deferred_pending_ratification"
    assert evt.payload.above_threshold is True
    assert evt.payload.escalated is False
    assert evt.payload.document_id_ref == "doc-large"
    assert evt.document_id == "doc-large"


def test_below_threshold_does_not_emit_event(isolated_db, monkeypatch):
    """Below-threshold documents skip emission (event log stays focused
    on real bridge weigh-ins)."""
    monkeypatch.delenv("ANTIEK_RLM_RATIFIED", raising=False)

    from interfaces.research.api.wrestling import make_document_loaded_handler

    bus = _RecordingBroadcaster()
    handler = make_document_loaded_handler(
        db_path=isolated_db, broadcaster=bus,
    )
    # Small doc → ~250 estimated tokens, far below 64K.
    event = _make_doc_loaded_event(
        document_id="doc-tiny",
        investigation_id="inv-1",
        size_bytes=1_000,
    )
    asyncio.run(handler(event))
    bridge_events = [
        e for e in bus.events
        if (e.action_type.value if hasattr(e.action_type, "value") else e.action_type)
        == "rlm.bridge.decided"
    ]
    assert bridge_events == []


def test_above_threshold_escalation_when_ratified(isolated_db, monkeypatch):
    """ANTIEK_RLM_RATIFIED=1 + above-threshold → emits with reason
    'escalated_to_rlm' and a non-None session_id."""
    monkeypatch.setenv("ANTIEK_RLM_RATIFIED", "1")

    from interfaces.research.api.wrestling import make_document_loaded_handler

    bus = _RecordingBroadcaster()
    handler = make_document_loaded_handler(
        db_path=isolated_db, broadcaster=bus,
    )
    event = _make_doc_loaded_event(
        document_id="doc-large-rat",
        investigation_id="inv-1",
        size_bytes=2_097_152,  # 2 MiB → ~524k tokens
    )
    asyncio.run(handler(event))
    bridge_events = [
        e for e in bus.events
        if (e.action_type.value if hasattr(e.action_type, "value") else e.action_type)
        == "rlm.bridge.decided"
    ]
    assert len(bridge_events) == 1
    p = bridge_events[0].payload
    assert p.reason == "escalated_to_rlm"
    assert p.escalated is True
    assert p.session_id is not None
    assert p.session_id.startswith("rlm-")
