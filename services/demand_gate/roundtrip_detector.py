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
content hash-match regardless of zip envelope. Detection returns a typed event
(``RoundTripResult.event``) carrying who re-imported it, who exported it, and
when. NOTE: nothing in production records exports or persists these events yet
(see ``analysis.GateNotRunnable``); the verdict refuses to run on a window that
was never instrumented rather than reporting that absence as RETIRE.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

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
    """What Antiek has exported, and BY WHOM, so a re-import is classifiable
    mechanically and "exported by a non-operator" (pre-registered criterion 1)
    is checkable. Keyed document_id -> set of exported content hashes, plus
    exporter ids per (document_id, content_hash): WHO exported WHICH bytes, so
    an unmodified re-import is attributed to the exporters of exactly that
    content, not to everyone who ever exported some version of the document.
    In-memory only: no production caller persists it yet. Storage-agnostic +
    deterministic so it is unit-testable."""

    def __init__(self) -> None:
        self._by_doc: dict[str, set[str]] = {}
        self._exporters: dict[tuple[str, str], set[str]] = {}

    def record_export(self, document_id: str, content_tiptap: dict, *, exporter_id: str) -> str:
        """Record an export by ``exporter_id``; returns the content hash recorded.
        An export with no exporter cannot be attributed, so it is refused."""
        if not isinstance(exporter_id, str) or not exporter_id.strip():
            raise ValueError("record_export requires a non-blank exporter_id")
        h = content_hash(content_tiptap)
        self._by_doc.setdefault(document_id, set()).add(h)
        self._exporters.setdefault((document_id, h), set()).add(exporter_id)
        return h

    def exporters_of(self, document_id: str, hash_: str | None = None) -> list[str]:
        """Exporters of that exact content when ``hash_`` is given; otherwise
        everyone who exported ANY version of the document (the only honest
        answer when the source export is ambiguous)."""
        if hash_ is not None:
            return sorted(self._exporters.get((document_id, hash_), set()))
        return sorted(
            {x for (doc, _), ids in self._exporters.items() if doc == document_id for x in ids}
        )

    def knows_document(self, document_id: str) -> bool:
        return document_id in self._by_doc

    def knows_exact(self, document_id: str, hash_: str) -> bool:
        return hash_ in self._by_doc.get(document_id, set())


def classify_roundtrip(
    document_id: str,
    content_tiptap: dict,
    registry: ExportRegistry,
    *,
    user_id: str | None = None,
    emitted_at: datetime | None = None,
) -> RoundTripResult:
    """Classify a re-imported artifact against the export registry.

    ``user_id`` is WHO re-imported it and rides on the event, with the
    exporters (``exported_by``) and the detection time (``emitted_at``,
    default now): the verdict admits a round-trip only when both actors are
    pinned testers and the time is inside the window (see
    ``compute_verdict``).

    ``exported_by`` is the exporters of the matched content for
    ``returned_unmodified``. For ``traveled_and_changed`` the source export is
    ambiguous (the edited bytes match no export), so it is every exporter of
    the document; the verdict refuses such a round-trip if any of them is the
    operator."""
    h = content_hash(content_tiptap)
    if registry.knows_exact(document_id, h):
        classification = "returned_unmodified"
        exported_by = registry.exporters_of(document_id, h)
    elif registry.knows_document(document_id):
        classification = "traveled_and_changed"
        exported_by = registry.exporters_of(document_id)
    else:
        classification = "novel"
        exported_by = []

    is_roundtrip = classification != "novel"
    event: dict | None = None
    if is_roundtrip:
        event = {
            "action_type": ROUNDTRIP_EVENT_TYPE,
            "document_id": document_id,
            "classification": classification,
            "content_hash": h,
            "user_id": user_id,
            "exported_by": exported_by,
            "emitted_at": (emitted_at or datetime.now(UTC)).isoformat(),
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
