"""Federation slice primitives.

A slice is the unit of federation: a content-addressable bundle of
public-graph notes that one Antiek instance offers to a peer. The
manifest carries metadata + a Merkle-style content hash; the payload
is the actual notes.

Negotiation is the pre-flight: peer A says "I'd like a slice scoped
to topic X for the past 30 days"; peer B replies with a proposed
slice manifest + sign-off; peer A approves; only then does the
signed payload move.
"""

from __future__ import annotations

import enum
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class SliceItem:
    """One note within a slice — minimal shape for federation transit."""

    note_id: str
    user_id: str  # the creator user_id at the source instance
    content_hash: str  # sha256 of the note content
    topic_tags: tuple[str, ...]
    created_at_source: str


@dataclass(frozen=True)
class SliceManifest:
    """Per-slice metadata. Used for negotiation and as the signed payload."""

    slice_id: str
    source_substrate_id: str
    topic_scope: str
    item_hashes: tuple[str, ...]  # sha256 of each item, in order
    item_count: int
    issued_at: str
    notes: str = ""

    def canonical_bytes(self) -> bytes:
        """Deterministic JSON serialisation for signing.

        sort_keys + no whitespace ensures peers see identical bytes
        regardless of dict-insertion order."""
        return json.dumps({
            "slice_id": self.slice_id,
            "source_substrate_id": self.source_substrate_id,
            "topic_scope": self.topic_scope,
            "item_hashes": list(self.item_hashes),
            "item_count": self.item_count,
            "issued_at": self.issued_at,
            "notes": self.notes,
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True)
class FederationSlice:
    """A complete signable+ingestable slice: manifest + payload + signature."""

    manifest: SliceManifest
    items: tuple[SliceItem, ...]
    manifest_signature: bytes
    signing_key_fingerprint: str


def hash_slice_item(item_payload: bytes) -> str:
    return sha256(item_payload).hexdigest()


def build_manifest(
    *,
    source_substrate_id: str,
    topic_scope: str,
    items: list[SliceItem],
    notes: str = "",
) -> SliceManifest:
    item_hashes = tuple(item.content_hash for item in items)
    return SliceManifest(
        slice_id=f"slice-{uuid.uuid4().hex[:12]}",
        source_substrate_id=source_substrate_id,
        topic_scope=topic_scope,
        item_hashes=item_hashes,
        item_count=len(items),
        issued_at=_now_iso(),
        notes=notes,
    )


class NegotiationStatus(str, enum.Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class SliceNegotiation:
    """Mutable pre-flight handshake between two peers."""

    negotiation_id: str = field(default_factory=lambda: f"neg-{uuid.uuid4().hex[:12]}")
    proposer_substrate_id: str = ""
    responder_substrate_id: str = ""
    topic_query: str = ""
    proposed_manifest: Optional[SliceManifest] = None
    status: NegotiationStatus = NegotiationStatus.PROPOSED
    history: list[tuple[str, str]] = field(default_factory=list)

    def record(self, event: str) -> None:
        self.history.append((_now_iso(), event))

    def approve(self, manifest: SliceManifest) -> None:
        self.proposed_manifest = manifest
        self.status = NegotiationStatus.APPROVED
        self.record(f"approved manifest={manifest.slice_id}")

    def reject(self, reason: str) -> None:
        self.status = NegotiationStatus.REJECTED
        self.record(f"rejected: {reason}")
