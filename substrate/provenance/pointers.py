"""Find every provenance pointer in a recorded value by the shape of its key.

Content that is exported has to clear the rights of everything it stood on,
and what it stood on is recorded in free-form JSON: a node's ``metadata``, an
event's payload. Writers add pointer fields as they need them
(``chunk_id``, ``source_chunk_ids``, ``supporting_claims[].chunk_ids``,
``edge_ids`` ...), so a reader that lists the fields it knows misses the next
one and exports text whose source it never checked. This module does not
list fields. It walks the whole value, at any depth, and takes every value
recorded under a key that names a substrate row:

* a key ending in ``chunk_id`` / ``chunk_ids`` names chunks,
* ``document_id(s)`` or ``doc_id(s)`` names documents,
* ``edge_id(s)`` names graph edges,
* ``source_id(s)`` names a source whose kind the key does not say.

The name must be the whole key or its last ``_``-separated word before the
``_id`` / ``_ids`` suffix, so ``source_chunk_ids`` and ``backup_chunk_ids``
are chunk pointers while ``source_event_ids`` and ``source_node_id`` are not.
Scalars and lists (nested lists too) are both accepted; a dict found under a
pointer key is walked like any other value. A string that holds serialized
JSON (``metadata`` embedded in a payload, a list written as text) is parsed
and walked, so re-encoding a pointer does not hide it.
"""

from __future__ import annotations

import functools
import json
import re
from collections.abc import Callable
from typing import Any, Literal, get_args

from pydantic import BaseModel, ValidationError

PointerKind = Literal["chunk", "document", "edge", "source"]
Pointer = tuple[PointerKind, str]

_POINTER_KEY = re.compile(r"(?:^|_)(chunk|document|doc|edge|source)_ids?$", re.IGNORECASE)
_KINDS: dict[str, PointerKind] = {
    "chunk": "chunk",
    "document": "document",
    "doc": "document",
    "edge": "edge",
    "source": "source",
}

# Investigations whose work a trajectory hands on to: an escalated question's
# child research, a launched or sub-investigation. Their sources are the
# parent's sources too.
_CHILD_INVESTIGATION_KEY = re.compile(
    r"(?:^|_)(?:child|sub|launched)_investigation_ids?$", re.IGNORECASE
)

# The investigation a spawned child names as its parent in its own log: the
# spawn event's and the start request's parent_investigation_id. A cascade
# leaf and a chase child are linked this way only; the parent's events never
# name them.
_PARENT_INVESTIGATION_KEY = re.compile(r"(?:^|_)parent_investigation_ids?$", re.IGNORECASE)

# A synthesis a recorded value names, wherever the key sits: the envelope's
# synthesis_id or one carried in a payload. Its manifest pins its sources.
_SYNTHESIS_KEY = re.compile(r"(?:^|_)synthesis_ids?$", re.IGNORECASE)


def pointer_kind(key: object) -> PointerKind | None:
    """The kind of row ``key`` names, or None when it is not a pointer key."""
    if not isinstance(key, str):
        return None
    match = _POINTER_KEY.search(key)
    return _KINDS[match.group(1).lower()] if match else None


def _child_kind(key: object) -> Literal["investigation"] | None:
    if isinstance(key, str) and _CHILD_INVESTIGATION_KEY.search(key):
        return "investigation"
    return None


def _parent_kind(key: object) -> Literal["investigation"] | None:
    if isinstance(key, str) and _PARENT_INVESTIGATION_KEY.search(key):
        return "investigation"
    return None


def _synthesis_kind(key: object) -> Literal["synthesis"] | None:
    if isinstance(key, str) and _SYNTHESIS_KEY.search(key):
        return "synthesis"
    return None


def _decoded(text: str) -> object:
    """``text`` parsed as JSON when it holds a JSON object or array."""
    stripped = text.strip()
    if not stripped or stripped[0] not in "[{":
        return None
    try:
        return json.loads(stripped)
    except (TypeError, ValueError):
        return None


def _collect[K: str](
    value: object, classify: Callable[[object], K | None]
) -> list[tuple[K, str]]:
    found: dict[tuple[K, str], None] = {}

    def take(kind: K, raw: object) -> None:
        if isinstance(raw, bool) or raw is None:
            return
        if isinstance(raw, (int, float)):
            found[(kind, str(raw))] = None
        elif isinstance(raw, str):
            decoded = _decoded(raw)
            if decoded is not None:
                take(kind, decoded)
            elif raw.strip():
                found[(kind, raw.strip())] = None
        elif isinstance(raw, (list, tuple)):
            for item in raw:
                take(kind, item)
        elif isinstance(raw, dict):
            walk(raw)

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, child in node.items():
                kind = classify(key)
                if kind is None:
                    walk(child)
                else:
                    take(kind, child)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)
        elif isinstance(node, str):
            decoded = _decoded(node)
            if decoded is not None:
                walk(decoded)

    walk(value)
    return list(found)


def collect_pointers(value: object) -> list[Pointer]:
    """Every ``(kind, id)`` pointer recorded anywhere in ``value``, in the
    order first met, each once."""
    return _collect(value, pointer_kind)


def collect_child_investigations(value: object) -> list[str]:
    """Every investigation id ``value`` hands work on to, in order, each once."""
    return [iid for _, iid in _collect(value, _child_kind)]


def collect_parent_investigations(value: object) -> list[str]:
    """Every investigation ``value`` names as its parent, in order, each once."""
    return [iid for _, iid in _collect(value, _parent_kind)]


def collect_syntheses(value: object) -> list[str]:
    """Every synthesis id recorded anywhere in ``value``, in order, each once."""
    return [sid for _, sid in _collect(value, _synthesis_kind)]


def is_evidence_key(key: object) -> bool:
    """Whether ``key`` names evidence: a chunk, document, edge or source
    pointer, or a synthesis (whose manifest pins its sources)."""
    return pointer_kind(key) is not None or bool(
        isinstance(key, str) and _SYNTHESIS_KEY.search(key)
    )


def _declared_keys(schema: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(schema, dict):
        for key, value in schema.items():
            if key == "properties" and isinstance(value, dict):
                keys.update(value)
            keys |= _declared_keys(value)
    elif isinstance(schema, list):
        for item in schema:
            keys |= _declared_keys(item)
    return keys


@functools.cache
def _evidence_payload_models() -> dict[str, type[BaseModel]]:
    """The typed payload models that declare an evidence key anywhere in their
    schema, by action type. Read from the schema, so a model that gains an
    evidence field is covered without a list here."""
    from substrate.schemas.events import TypedPayload

    models: dict[str, type[BaseModel]] = {}
    for model in get_args(get_args(TypedPayload)[0]):
        if any(is_evidence_key(k) for k in _declared_keys(model.model_json_schema())):
            action = model.model_fields["action_type"].default
            models[str(getattr(action, "value", action))] = model
    return models


def evidence_payload_intact(action_type: object, payload: Any) -> bool:
    """Whether an event that records evidence still carries what its typed
    schema requires.

    An event whose model declares evidence (a retrieval's supporting chunk and
    edge ids, a synthesis id, a document read) and whose payload is missing,
    null, not an object, or lacks a required field records evidence nobody
    can read any more. A key the schema does not declare is ignored: extras
    lose nothing. Events that declare no evidence are not judged here; the
    research runners write lineage events their typed models would reject."""
    model = _evidence_payload_models().get(str(action_type))
    if model is None:
        return True
    if not isinstance(payload, dict):
        return False
    declared = {k: v for k, v in payload.items() if k in model.model_fields}
    declared["action_type"] = str(action_type)
    try:
        model.model_validate(declared)
    except ValidationError:
        return False
    return True
