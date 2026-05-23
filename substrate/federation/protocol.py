"""Signed-resource-pull protocol — request / serve / ingest.

The protocol has three steps and one invariant:

  1. request_slice — receiver asks sender for a slice matching a
     negotiated manifest. Returns a FederationSlice (signed).
  2. serve_slice — sender packages items + signs manifest. Pure
     function of (items, signing_key, manifest_args).
  3. ingest_slice — receiver verifies the signature against a PINNED
     partner key, runs each item through the §13.9 quality gate, and
     writes only PASS items into the RECEIVER's own DB.

Invariant: writes happen ONLY on the receiver, ONLY after signature
verification AND quality-gate PASS. No code path lets a federated
slice write into the sender's DB or bypass the receiver's quality
gate. This is the architectural safeguard the Sprint 30+ adversarial
review tests.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Callable, Optional

from .signing import (
    SignatureError,
    SignedManifest,
    SigningKey,
    VerifyingKey,
    sign_manifest,
    verify_manifest,
)
from .slice import (
    FederationSlice,
    SliceItem,
    SliceManifest,
    build_manifest,
)


class QualityGateResult(str, enum.Enum):
    PASS = "pass"
    FAIL = "fail"


QualityGateCallable = Callable[[SliceItem], QualityGateResult]


@dataclass(frozen=True)
class FederationPeer:
    """A known peer Antiek instance. Pinned by fingerprint."""

    substrate_id: str
    verifying_key: VerifyingKey
    contact_url: str = ""


@dataclass
class FederationRegistry:
    """Receiver-side registry of trusted peers."""

    peers: dict[str, FederationPeer] = field(default_factory=dict)

    def pin(self, peer: FederationPeer) -> None:
        self.peers[peer.substrate_id] = peer

    def lookup(self, substrate_id: str) -> Optional[FederationPeer]:
        return self.peers.get(substrate_id)


@dataclass(frozen=True)
class IngestionReport:
    """Result of an ingest_slice call."""

    slice_id: str
    source_substrate_id: str
    items_received: int
    items_passed: int
    items_failed: int
    failed_item_ids: tuple[str, ...]


def request_slice(
    *,
    requesting_substrate_id: str,
    peer_substrate_id: str,
    topic_query: str,
    server_resolver: Callable[[str, str], FederationSlice],
) -> FederationSlice:
    """Receiver-side: send a request and receive a signed slice.

    `server_resolver(topic_query, requester_substrate_id) -> FederationSlice`
    is the transport-layer abstraction. In production this is an HTTP
    GET against the peer; in tests it's an in-process function.
    """
    return server_resolver(topic_query, requesting_substrate_id)


def serve_slice(
    *,
    items: list[SliceItem],
    source_substrate_id: str,
    topic_scope: str,
    signing_key: SigningKey,
    notes: str = "",
) -> FederationSlice:
    """Sender-side: package items + sign the manifest."""
    manifest = build_manifest(
        source_substrate_id=source_substrate_id,
        topic_scope=topic_scope,
        items=items,
        notes=notes,
    )
    signed = sign_manifest(signing_key, manifest.canonical_bytes())
    return FederationSlice(
        manifest=manifest,
        items=tuple(items),
        manifest_signature=signed.signature,
        signing_key_fingerprint=signed.key_fingerprint,
    )


def ingest_slice(
    fslice: FederationSlice,
    *,
    registry: FederationRegistry,
    quality_gate: QualityGateCallable,
    writer: Optional[Callable[[SliceItem], None]] = None,
) -> IngestionReport:
    """Receiver-side: verify signature, run quality gate, write items.

    Raises SignatureError if the peer is unknown OR the signature
    fails. Per-item quality-gate failures are recorded in the report
    but do not raise — the slice as a whole is accepted, only the
    failing items are dropped.

    `writer` is an optional callable that persists an item into the
    receiver's DB. None means dry-run (verify + gate only).
    """
    peer = registry.lookup(fslice.manifest.source_substrate_id)
    if peer is None:
        raise SignatureError(
            f"unknown peer substrate_id={fslice.manifest.source_substrate_id!r}",
        )
    verify_manifest(
        SignedManifest(
            payload=fslice.manifest.canonical_bytes(),
            signature=fslice.manifest_signature,
            key_fingerprint=fslice.signing_key_fingerprint,
        ),
        expected_key=peer.verifying_key,
    )

    passed = 0
    failed_ids: list[str] = []
    for item in fslice.items:
        verdict = quality_gate(item)
        if verdict == QualityGateResult.PASS:
            passed += 1
            if writer is not None:
                writer(item)
        else:
            failed_ids.append(item.note_id)

    return IngestionReport(
        slice_id=fslice.manifest.slice_id,
        source_substrate_id=fslice.manifest.source_substrate_id,
        items_received=len(fslice.items),
        items_passed=passed,
        items_failed=len(failed_ids),
        failed_item_ids=tuple(failed_ids),
    )
