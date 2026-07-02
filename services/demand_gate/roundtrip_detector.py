"""Round-trip detector (HPRJ SPR-08 M2).

The only admissible signal of real format demand is a ROUND-TRIP: an artifact
Antiek exported, carried elsewhere or modified externally, and re-imported
(via SPR-07's signature-checked island-only path). This classifies a
re-imported artifact against the export registry, mechanically:

- ``returned_unmodified`` — same document_id AND same canonical content hash:
  the file came back unchanged (a weak signal — it was kept).
- ``traveled_and_changed`` — same document_id, DIFFERENT content hash: the file
  was modified externally and re-imported. This is the STRONGEST admissible
  demand signal (per the pre-registered criteria).
- ``novel`` — unknown document_id: not a tracked round-trip.

The content hash is the SHA-256 of the canonical content bytes (the same
canonicalisation the `.antiek` signature covers), so two exports of the same
content hash-match regardless of zip envelope. Detection emits a typed event;
no path depends on the operator remembering to check anything.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from services.antiek_format.native_writer import _canonical_tiptap_node
from services.antiek_format.signature import canonical_json_bytes

ROUNDTRIP_EVENT_TYPE: str = "demand_gate.roundtrip_detected"


def content_hash(content_tiptap: dict) -> str:
    """SHA-256 of the CANONICAL content bytes — the identity that survives the
    zip envelope and matches what the signature covers. Canonicalises first
    (the same `_canonical_tiptap_node` the writer applies) so a raw dict
    recorded at export time and the canonical dict returned by `read_antiek`
    hash-match for the same logical content."""
    canonical = _canonical_tiptap_node(content_tiptap)
    return hashlib.sha256(canonical_json_bytes(canonical)).hexdigest()


@dataclass(frozen=True)
class RoundTripResult:
    classification: str  # returned_unmodified | traveled_and_changed | novel
    document_id: str
    is_roundtrip: bool
    content_hash: str
    event: dict | None  # the typed detection event, or None when novel


class ExportRegistry:
    """What Antiek has exported, so a re-import is classifiable mechanically.
    Keyed document_id -> set of exported content hashes. In production this is
    persisted alongside the export events; the class is storage-agnostic +
    deterministic so the detector is unit-testable."""

    def __init__(self) -> None:
        self._by_doc: dict[str, set[str]] = {}

    def record_export(self, document_id: str, content_tiptap: dict) -> str:
        """Record an export; returns the content hash recorded."""
        h = content_hash(content_tiptap)
        self._by_doc.setdefault(document_id, set()).add(h)
        return h

    def knows_document(self, document_id: str) -> bool:
        return document_id in self._by_doc

    def knows_exact(self, document_id: str, hash_: str) -> bool:
        return hash_ in self._by_doc.get(document_id, set())


def classify_roundtrip(
    document_id: str, content_tiptap: dict, registry: ExportRegistry
) -> RoundTripResult:
    """Classify a re-imported artifact against the export registry."""
    h = content_hash(content_tiptap)
    if registry.knows_exact(document_id, h):
        classification = "returned_unmodified"
    elif registry.knows_document(document_id):
        classification = "traveled_and_changed"
    else:
        classification = "novel"

    is_roundtrip = classification != "novel"
    event: dict | None = None
    if is_roundtrip:
        event = {
            "action_type": ROUNDTRIP_EVENT_TYPE,
            "document_id": document_id,
            "classification": classification,
            "content_hash": h,
        }
    return RoundTripResult(
        classification=classification,
        document_id=document_id,
        is_roundtrip=is_roundtrip,
        content_hash=h,
        event=event,
    )


__all__ = [
    "ExportRegistry",
    "ROUNDTRIP_EVENT_TYPE",
    "RoundTripResult",
    "classify_roundtrip",
    "content_hash",
]
