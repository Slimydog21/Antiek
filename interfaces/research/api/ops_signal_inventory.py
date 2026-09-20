"""Own Your Mind P0 — signal-inventory endpoint (L15, read-only).

``GET /ops/signal-inventory`` publishes what the platform collects: the
ActionType vocabulary of ``substrate/schemas/events.py``, enumerated
MECHANICALLY at request time — no hand-maintained duplicate list that can
drift from the schema.

Each signal carries:

- ``action_type`` — the enum's string value (the Parquet-stable id).
- ``payload_class`` — the typed payload's class name, resolved from the
  discriminated ``TypedPayload`` union via each variant's ``action_type``
  discriminator default; null when the action type has no typed payload
  yet (legacy dict-payload events).
- ``typed`` — whether the action type is a member of the typed union.
- ``domain`` — the first dotted segment of the value (``dispatch.call`` →
  ``dispatch``), a mechanical per-domain grouping.

The payload also carries ``schema_version`` (the live
``EVENT_SCHEMA_VERSION``), ``count`` (the number of ActionType members),
and a ``by_domain`` grouping with per-domain counts. GET-only; reads the
schema module, never the event store.
"""

from __future__ import annotations

import typing
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, FastAPI

from substrate.schemas.events import EVENT_SCHEMA_VERSION, ActionType, TypedPayload

signal_inventory_router = APIRouter(prefix="/ops", tags=["ops"])


def _payload_class_by_action_type() -> dict[str, str]:
    """Map action-type string -> payload class name, mechanically.

    Every typed payload declares ``action_type: Literal[ActionType.X] =
    ActionType.X``; the field's default IS the enum member it belongs to.
    Iterating the discriminated union is the mapping table — no copy."""
    mapping: dict[str, str] = {}
    # TypedPayload is Annotated[Union[...], Field(discriminator=...)] — unwrap
    # the Annotated layer to reach the variant union.
    union = typing.get_args(TypedPayload)[0]
    for variant in typing.get_args(union):
        action_type = variant.model_fields["action_type"].default
        value = (
            action_type.value if hasattr(action_type, "value") else str(action_type)
        )
        mapping[value] = variant.__name__
    return mapping


def signal_inventory() -> dict[str, Any]:
    """Build the inventory from live schema introspection. Pure function —
    testable without HTTP."""
    payload_map = _payload_class_by_action_type()
    signals: list[dict[str, Any]] = []
    by_domain: dict[str, list[str]] = {}
    for member in ActionType:
        value = member.value
        domain = value.split(".", 1)[0]
        signals.append(
            {
                "action_type": value,
                "payload_class": payload_map.get(value),
                "typed": value in payload_map,
                "domain": domain,
            }
        )
        by_domain.setdefault(domain, []).append(value)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "schema_version": EVENT_SCHEMA_VERSION,
        "count": len(signals),
        "signals": signals,
        "by_domain": {
            domain: {"count": len(values), "action_types": values}
            for domain, values in sorted(by_domain.items())
        },
    }


@signal_inventory_router.get("/signal-inventory")
async def get_signal_inventory() -> dict[str, Any]:
    """Publish the event-schema signal inventory (Own Your Mind P0 L15)."""
    return signal_inventory()


def register_ops_signal_inventory_routes(app: FastAPI) -> None:
    """Mount ``GET /ops/signal-inventory``. One call from ``create_app``."""
    app.include_router(signal_inventory_router)


__all__ = ["register_ops_signal_inventory_routes", "signal_inventory"]
