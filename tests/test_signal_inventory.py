"""Own Your Mind P0 L15 — the signal-inventory endpoint + the one new
event types of the P0 batch (surface.served_impression, v35; link.monster.digested, v36).

Two concerns:

1. ``GET /ops/signal-inventory`` — the event-schema inventory is generated
   by MECHANICAL introspection of ``substrate/schemas/events.py`` (the
   ActionType enum + the TypedPayload discriminated union), never a
   hand-maintained duplicate list. The tests assert count/schema-version
   floors and that the mapping tracks the live schema module.
2. The schema change itself — ``surface.served_impression`` exists as an
   ActionType, its payload is a member of the typed union, and an Event
   envelope carrying it round-trips through the emit → trajectory path
   with the current ``schema_version == 40``.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from substrate.event_log import emit_typed, trajectory  # noqa: E402
from substrate.schemas.events import (  # noqa: E402
    EVENT_SCHEMA_VERSION,
    TYPED_PAYLOAD_ACTION_TYPES,
    ActionType,
    Event,
    SurfaceServedImpressionPayload,
)


@pytest.fixture(autouse=True)
def _events_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))


@pytest.fixture
def client() -> TestClient:
    from interfaces.research.api.app import create_app

    return TestClient(
        create_app(register_wrestling=False, register_providers=False)
    )


# ── GET /ops/signal-inventory ──────────────────────────────────────────────


def test_signal_inventory_shape_and_floors(client):
    r = client.get("/ops/signal-inventory")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {
        "generated_at",
        "schema_version",
        "count",
        "signals",
        "by_domain",
    }
    assert body["generated_at"]
    # The inventory reports the live schema version, including later feedback events.
    assert body["schema_version"] == EVENT_SCHEMA_VERSION == 40
    assert body["count"] >= 100
    assert len(body["signals"]) == body["count"]


def test_signal_inventory_entries_are_mechanical(client):
    """Every entry mirrors the live ActionType enum — no hand-maintained
    duplicate can drift from the schema."""
    body = client.get("/ops/signal-inventory").json()
    by_value = {s["action_type"]: s for s in body["signals"]}
    assert len(by_value) == len(ActionType)
    for member in ActionType:
        entry = by_value[member.value]
        # The per-domain grouping is the first dotted segment.
        assert entry["domain"] == member.value.split(".", 1)[0]


def test_signal_inventory_payload_classes_come_from_typed_union(client):
    """payload_class is resolved from the TypedPayload union, and every
    typed action type in the inventory is a member of
    TYPED_PAYLOAD_ACTION_TYPES (the file's own mapping table)."""
    import typing

    from substrate.schemas.events import TypedPayload

    body = client.get("/ops/signal-inventory").json()
    typed = {s["action_type"]: s["payload_class"] for s in body["signals"] if s["typed"]}
    union_variants = typing.get_args(typing.get_args(TypedPayload)[0])
    class_names = {v.__name__ for v in union_variants}
    for value, class_name in typed.items():
        assert class_name in class_names
        assert value in TYPED_PAYLOAD_ACTION_TYPES
    # The inverse direction: every typed action type is listed as typed.
    for value in TYPED_PAYLOAD_ACTION_TYPES:
        entry = next(s for s in body["signals"] if s["action_type"] == value)
        assert entry["typed"] is True
        assert entry["payload_class"]


def test_signal_inventory_includes_served_impression(client):
    body = client.get("/ops/signal-inventory").json()
    entry = next(
        s for s in body["signals"] if s["action_type"] == "surface.served_impression"
    )
    assert entry["payload_class"] == "SurfaceServedImpressionPayload"
    assert entry["typed"] is True
    assert entry["domain"] == "surface"
    assert body["by_domain"]["surface"]["count"] >= 1


# ── surface.served_impression schema (v35) ─────────────────────────────────


def test_served_impression_action_type_exists():
    assert ActionType.SURFACE_SERVED_IMPRESSION.value == "surface.served_impression"
    assert ActionType.SURFACE_SERVED_IMPRESSION.value in TYPED_PAYLOAD_ACTION_TYPES


def test_served_impression_payload_fields():
    payload = SurfaceServedImpressionPayload(
        surface="research_workstation.ranked_list",
        item_kind="document",
        item_id="doc-1",
        ranked_position=0,
        ranked_version="param-0.2.0",
        timestamp=datetime(2026, 8, 12, tzinfo=UTC),
        user_id="__operator__",
    )
    assert payload.action_type == "surface.served_impression"
    assert payload.ranked_position == 0
    assert payload.item_id == "doc-1"


def test_served_impression_round_trips_through_event_envelope(tmp_path, monkeypatch):
    """Construct the envelope, emit through the single-writer funnel, and
    read it back from the trajectory — schema_version 35 and all payload
    fields intact."""
    payload = SurfaceServedImpressionPayload(
        surface="personal_space.recommendations",
        item_kind="synthesis",
        item_id="syn-42",
        ranked_position=2,
        ranked_version="param-0.2.0",
        timestamp=datetime(2026, 8, 12, tzinfo=UTC),
        user_id="__operator__",
    )
    event = Event(
        event_id="evt-served-1",
        investigation_id="inv-served",
        action_type=payload.action_type,
        payload=payload,
        param_version="0.2.0",
        emitted_at=datetime(2026, 8, 12, tzinfo=UTC),
    )
    assert event.schema_version == 40

    emitted_id = emit_typed("inv-served", payload)
    assert emitted_id is not None
    rows = trajectory("inv-served")
    assert len(rows) == 1
    row = rows[0]
    assert row["action_type"] == "surface.served_impression"
    assert row["schema_version"] == 40
    assert row["payload"]["surface"] == "personal_space.recommendations"
    assert row["payload"]["item_kind"] == "synthesis"
    assert row["payload"]["item_id"] == "syn-42"
    assert row["payload"]["ranked_position"] == 2
    assert row["payload"]["ranked_version"] == "param-0.2.0"
    assert row["payload"]["user_id"] == "__operator__"
    assert row["payload"]["timestamp"]
    # Read-side reconstruction treats it as a typed payload, not a dict.
    reconstructed = Event.model_validate(row)
    assert isinstance(reconstructed.payload, SurfaceServedImpressionPayload)


def test_served_impression_rejects_negative_ranked_position():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SurfaceServedImpressionPayload(
            surface="s",
            item_kind="document",
            item_id="doc-1",
            ranked_position=-1,
            ranked_version="v1",
            timestamp=datetime(2026, 8, 12, tzinfo=UTC),
            user_id="__operator__",
        )


def test_signal_inventory_includes_link_monster_digested(client):
    body = client.get("/ops/signal-inventory").json()
    entry = next(
        s for s in body["signals"] if s["action_type"] == "link.monster.digested"
    )
    assert entry["payload_class"] == "LinkMonsterDigestedPayload"
    assert entry["typed"] is True
    assert entry["domain"] == "link"
