"""Mirror substrate facts into PostHog without making PostHog truth.

Maps duckdb_plane.md §10 layers to stable product event names. Always pass
``antiek_event_id`` when a jsonl event was already emitted for the same fact.
"""

from __future__ import annotations

from typing import Any, Literal

from substrate.observability.posthog import capture

AntiekLayer = Literal["research", "read", "write", "speak", "engine", "agents"]

_LAYER_EVENTS: dict[str, str] = {
    "research": "antiek_research",
    "read": "antiek_read",
    "write": "antiek_write",
    "speak": "antiek_speak",
    "engine": "antiek_engine",
    "agents": "antiek_agents",
}


def mirror_layer_event(
    layer: AntiekLayer,
    verb: str,
    *,
    antiek_event_id: str | None = None,
    distinct_id: str | None = None,
    **properties: Any,
) -> str | None:
    """PostHog capture with ``antiek_layer`` + ``antiek_verb`` properties."""
    props = dict(properties)
    props["antiek_layer"] = layer
    props["antiek_verb"] = verb
    event = f"{_LAYER_EVENTS[layer]}_{verb}"
    return capture(
        event,
        distinct_id=distinct_id,
        properties=props,
        antiek_event_id=antiek_event_id,
    )