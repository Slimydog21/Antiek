"""The entry gate and the content hash of the companion document (LB-9a;
LB-9 spec D6, D7, D8 and D15). Pure: it reads nothing and writes nothing.

An entry drawn from a research-artifact body is a synthesis, so its gate is
only ``served`` or ``withheld``, never ``cite_only`` (TC §1.2 rev 6). It is
served only when every part it draws on clears:

- every source in each contributing thread's excerpt-source set is resolved
  and servable after the owner overlay;
- no contributing thread's walk is unreadable, and none is unreconciled;
- every pin of the entry's own node clears the same way (the mixed-sources
  rule: the text draws on them too, so the most restrictive part wins).

A thread with no sources is ``withheld · unresolved``, as is an entry with no
contributing thread or with no text to serve. Among withheld parts the reason
is lineage_unreconciled over unresolved over not_servable.

``source_refs`` lists the entry's own pins, then every thread source that did
not clear, once each, under the quotation rule: ``served``, ``cite_only ·
unresolved``, ``cite_only · not_servable``, or ``withheld · not_servable``
with the document and passage dropped when the owner overlay applies.

``content_hash`` covers the served projection. A withheld entry contributes
its gate, reason and refs but never a hash of its text, so the hash cannot
confirm a guess at withheld words.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from substrate.companion_document.rights import DocumentRights, is_servable, owner_overlay_withholds
from substrate.companion_document.store import EntryKind, SourcePin
from substrate.schemas.gated_text import (
    Gate,
    GatedText,
    GateReason,
    SourceAnchor,
    SourceRef,
    TextOrigin,
    most_restrictive,
)

#: The version tag inside the hashed material.
CONTENT_HASH_VERSION = "companion_document.content.v1"


@dataclass(frozen=True, slots=True)
class SourceVerdict:
    """One source pointer and the live rights of the document it reaches;
    ``rights`` is None when the pointer does not reach a live document."""

    kind: str
    id: str
    rights: DocumentRights | None
    anchor: SourceAnchor | None = None


@dataclass(frozen=True, slots=True)
class ThreadVerdict:
    """A contributing thread's excerpt-source set as the rights reads saw it.
    No ref computes ``lineage_unreconciled`` yet, so LB-9 never sets it, but
    the composer honours it."""

    thread_id: str
    sources: tuple[SourceVerdict, ...]
    unreadable: bool = False
    lineage_unreconciled: bool = False


@dataclass(frozen=True, slots=True)
class ComposedEntry:
    """An entry's gated content and its ``doc_ids`` (the distinct documents
    of its own pins that survive the overlay)."""

    content: GatedText
    doc_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProcessRef:
    """The newest event that produced or refined the entry's node."""

    thread_id: str
    event_id: str


@dataclass(frozen=True, slots=True)
class EntryProjection:
    """One entry of the served projection, as the hash sees it.
    ``text_sha256`` is the server-side hash of the node label, present for
    every entry whose label exists; it enters the hash only when served."""

    entry_id: str
    kind: EntryKind
    content: GatedText
    thread_ids: tuple[str, ...]
    doc_ids: tuple[str, ...]
    process_ref: ProcessRef
    confidence: str | None
    text_sha256: str | None

    def __post_init__(self) -> None:
        if self.content.gate == "served":
            served = self.content.text or ""
            if self.text_sha256 != hashlib.sha256(served.encode("utf-8")).hexdigest():
                raise ValueError("a served entry's text_sha256 must be the hash of its served text")


def source_verdicts(
    pins: Iterable[SourcePin], rights: Mapping[str, DocumentRights | None]
) -> tuple[SourceVerdict, ...]:
    """Join pins to the rights read. A pin with no document, a document that
    does not exist, and a document the rights read did not cover are all
    unresolved."""
    return tuple(
        SourceVerdict(
            pin.kind, pin.id, None if pin.document_id is None else rights.get(pin.document_id)
        )
        for pin in pins
    )


def source_ref(verdict: SourceVerdict, admitted_owners: frozenset[str]) -> SourceRef:
    """A pointer's own gate under the quotation rule, with the owner overlay."""
    doc = verdict.rights
    if doc is None:
        return SourceRef(kind=verdict.kind, id=verdict.id, gate="cite_only", reason="unresolved")
    if owner_overlay_withholds(doc, admitted_owners):
        return SourceRef(kind=verdict.kind, id=verdict.id, gate="withheld", reason="not_servable")
    anchor = (
        verdict.anchor
        if verdict.anchor is not None and verdict.anchor.document_id == doc.document_id
        else None
    )
    if not is_servable(doc):
        return SourceRef(
            kind=verdict.kind,
            id=verdict.id,
            document_id=doc.document_id,
            anchor=anchor,
            gate="cite_only",
            reason="not_servable",
        )
    return SourceRef(
        kind=verdict.kind, id=verdict.id, document_id=doc.document_id, anchor=anchor, gate="served"
    )


def _as_synthesis_part(ref: SourceRef) -> tuple[Gate, GateReason | None]:
    """A source as one part of a synthesis: anything short of served
    withholds, with the ref's own reason."""
    return ("served", None) if ref.gate == "served" else ("withheld", ref.reason)


def thread_gate(
    thread: ThreadVerdict, admitted_owners: frozenset[str]
) -> tuple[Gate, GateReason | None]:
    """The excerpt gate of one contributing thread."""
    parts: list[tuple[Gate, GateReason | None]] = []
    if thread.lineage_unreconciled:
        parts.append(("withheld", "lineage_unreconciled"))
    if thread.unreadable or not thread.sources:
        parts.append(("withheld", "unresolved"))
    parts.extend(_as_synthesis_part(source_ref(s, admitted_owners)) for s in thread.sources)
    return most_restrictive(parts)


def compose_entry(
    *,
    text: str | None,
    own_pins: Sequence[SourceVerdict],
    threads: Sequence[ThreadVerdict],
    admitted_owners: frozenset[str],
) -> ComposedEntry:
    """Gate one entry. ``text`` is the node's live label, used only when the
    entry is served; ``admitted_owners`` are the requester's identities."""
    own_refs = [source_ref(v, admitted_owners) for v in own_pins]
    parts: list[tuple[Gate, GateReason | None]] = [thread_gate(t, admitted_owners) for t in threads]
    parts.extend(_as_synthesis_part(r) for r in own_refs)
    if not threads:
        parts.append(("withheld", "unresolved"))
    gate, reason = most_restrictive(parts)
    if gate == "served" and text is None:
        gate, reason = "withheld", "unresolved"

    refs: list[SourceRef] = []
    for ref in [
        *own_refs,
        *(
            r
            for t in threads
            for r in (source_ref(s, admitted_owners) for s in t.sources)
            if r.gate != "served"
        ),
    ]:
        if ref not in refs:
            refs.append(ref)
    origin: TextOrigin = "source" if own_pins else "unsourced"
    content = GatedText(
        text=text if gate == "served" else None,
        gate=gate,
        reason=reason,
        origin=origin,
        source_refs=refs,
    )
    doc_ids = tuple(sorted({r.document_id for r in own_refs if r.document_id is not None}))
    return ComposedEntry(content=content, doc_ids=doc_ids)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _entry_material(entry: EntryProjection) -> dict[str, Any]:
    material: dict[str, Any] = {
        "entry_id": entry.entry_id,
        "kind": entry.kind,
        "gate": entry.content.gate,
        "reason": entry.content.reason,
        "origin": entry.content.origin,
        "source_refs": sorted(
            _canonical(r.model_dump(mode="json")) for r in entry.content.source_refs
        ),
        "thread_ids": sorted(entry.thread_ids),
        "doc_ids": sorted(entry.doc_ids),
        "process_ref": {
            "thread_id": entry.process_ref.thread_id,
            "event_id": entry.process_ref.event_id,
        },
        "confidence": entry.confidence,
    }
    if entry.content.gate == "served":
        material["text_sha256"] = entry.text_sha256
    return material


def content_hash(entries: Iterable[EntryProjection]) -> str:
    """sha256 of the canonical JSON of the served projection: sorted keys,
    entries sorted by id, refs and id lists sorted so a reorder is not a
    change."""
    body = sorted((_entry_material(e) for e in entries), key=lambda m: str(m["entry_id"]))
    return hashlib.sha256(
        _canonical({"v": CONTENT_HASH_VERSION, "entries": body}).encode("utf-8")
    ).hexdigest()


__all__ = [
    "CONTENT_HASH_VERSION",
    "ComposedEntry",
    "EntryProjection",
    "ProcessRef",
    "SourceVerdict",
    "ThreadVerdict",
    "compose_entry",
    "content_hash",
    "source_ref",
    "source_verdicts",
    "thread_gate",
]
