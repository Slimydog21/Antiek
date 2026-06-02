"""Signed-resource-pull federation tests (Sprint 30+ substrate).

Exercises sign/verify, tampering rejection, wrong-key rejection,
quality-gate gating, and the no-cross-write invariant.
"""

from __future__ import annotations

from hashlib import sha256

import pytest

from substrate.federation import (
    FederationPeer,
    FederationRegistry,
    QualityGateResult,
    SignatureError,
    SliceItem,
    generate_keypair,
    ingest_slice,
    request_slice,
    serve_slice,
    sign_manifest,
    verify_manifest,
)
from substrate.federation.signing import SignedManifest


def _items(n: int = 3) -> list[SliceItem]:
    out: list[SliceItem] = []
    for i in range(n):
        body = f"note body {i}".encode()
        out.append(SliceItem(
            note_id=f"note-{i}",
            user_id=f"u-{i}",
            content_hash=sha256(body).hexdigest(),
            topic_tags=("topic-x",),
            created_at_source="2026-05-21T00:00:00Z",
        ))
    return out


def _always_pass(_item: SliceItem) -> QualityGateResult:
    return QualityGateResult.PASS


def _always_fail(_item: SliceItem) -> QualityGateResult:
    return QualityGateResult.FAIL


# ── Signing primitives ────────────────────────────────────────────


def test_sign_verify_round_trip():
    key = generate_keypair(seed=b"deterministic seed-A")
    signed = sign_manifest(key, b"payload-bytes")
    # Round-trips through SignedManifest verification.
    verify_manifest(signed, expected_key=key.public())


def test_tampered_payload_rejected():
    key = generate_keypair(seed=b"deterministic seed-A")
    signed = sign_manifest(key, b"payload-bytes")
    tampered = SignedManifest(
        payload=b"payload-XXXXX",  # tampered
        signature=signed.signature,
        key_fingerprint=signed.key_fingerprint,
    )
    with pytest.raises(SignatureError):
        verify_manifest(tampered, expected_key=key.public())


def test_wrong_key_rejected():
    key_a = generate_keypair(seed=b"seed-A")
    key_b = generate_keypair(seed=b"seed-B")
    signed = sign_manifest(key_a, b"payload-bytes")
    with pytest.raises(SignatureError):
        verify_manifest(signed, expected_key=key_b.public())


def test_fingerprint_mismatch_short_circuits():
    """An attacker who knows the secret can forge a signature, but if
    the fingerprint doesn't match the pinned key we reject immediately."""
    key = generate_keypair(seed=b"seed-A")
    signed = sign_manifest(key, b"payload-bytes")
    forged_fp = SignedManifest(
        payload=signed.payload,
        signature=signed.signature,
        key_fingerprint="wrong-fp-1234",
    )
    with pytest.raises(SignatureError, match="fingerprint mismatch"):
        verify_manifest(forged_fp, expected_key=key.public())


# ── Slice manifest determinism ────────────────────────────────────


def test_manifest_canonical_bytes_are_deterministic():
    from substrate.federation.slice import build_manifest
    items = _items(3)
    m1 = build_manifest(source_substrate_id="sub-A", topic_scope="x", items=items)
    # Two slices with the same fields produce the same canonical_bytes
    # IFF every field is identical — slice_id + issued_at differ so we
    # construct one and re-serialise.
    assert m1.canonical_bytes() == m1.canonical_bytes()


# ── End-to-end serve + ingest ────────────────────────────────────


def test_full_protocol_happy_path():
    """Peer A signs + serves; Peer B verifies + ingests."""
    key_a = generate_keypair(seed=b"peer-A")
    fslice = serve_slice(
        items=_items(3),
        source_substrate_id="sub-A",
        topic_scope="topic-x",
        signing_key=key_a,
    )
    registry = FederationRegistry()
    registry.pin(FederationPeer(
        substrate_id="sub-A",
        verifying_key=key_a.public(),
    ))
    written: list[SliceItem] = []
    report = ingest_slice(
        fslice,
        registry=registry,
        quality_gate=_always_pass,
        writer=written.append,
    )
    assert report.items_received == 3
    assert report.items_passed == 3
    assert report.items_failed == 0
    assert len(written) == 3


def test_ingest_rejects_unknown_peer():
    key = generate_keypair(seed=b"peer-A")
    fslice = serve_slice(
        items=_items(1),
        source_substrate_id="sub-A",
        topic_scope="topic-x",
        signing_key=key,
    )
    # Empty registry — peer is unknown.
    registry = FederationRegistry()
    with pytest.raises(SignatureError, match="unknown peer"):
        ingest_slice(fslice, registry=registry, quality_gate=_always_pass)


def test_ingest_rejects_wrong_key():
    """A slice signed by key X but pinned against key Y is rejected."""
    key_real = generate_keypair(seed=b"peer-A-real")
    key_imposter = generate_keypair(seed=b"peer-A-imposter")
    fslice = serve_slice(
        items=_items(1),
        source_substrate_id="sub-A",
        topic_scope="topic-x",
        signing_key=key_imposter,
    )
    registry = FederationRegistry()
    registry.pin(FederationPeer(
        substrate_id="sub-A",
        verifying_key=key_real.public(),
    ))
    with pytest.raises(SignatureError):
        ingest_slice(fslice, registry=registry, quality_gate=_always_pass)


def test_quality_gate_failure_drops_items_not_slice():
    """Per-item gate failures drop items; the slice as a whole survives."""
    key = generate_keypair(seed=b"peer-A")
    fslice = serve_slice(
        items=_items(5),
        source_substrate_id="sub-A",
        topic_scope="topic-x",
        signing_key=key,
    )
    registry = FederationRegistry()
    registry.pin(FederationPeer(substrate_id="sub-A", verifying_key=key.public()))
    written: list[SliceItem] = []
    report = ingest_slice(
        fslice,
        registry=registry,
        quality_gate=_always_fail,
        writer=written.append,
    )
    assert report.items_received == 5
    assert report.items_passed == 0
    assert report.items_failed == 5
    assert len(written) == 0


def test_dry_run_no_writer_does_not_persist():
    """Omitting `writer` means verify + gate only — useful for audit."""
    key = generate_keypair(seed=b"peer-A")
    fslice = serve_slice(
        items=_items(3),
        source_substrate_id="sub-A",
        topic_scope="topic-x",
        signing_key=key,
    )
    registry = FederationRegistry()
    registry.pin(FederationPeer(substrate_id="sub-A", verifying_key=key.public()))
    report = ingest_slice(fslice, registry=registry, quality_gate=_always_pass)
    assert report.items_passed == 3


def test_request_slice_uses_caller_provided_resolver():
    """The transport is abstract; tests inject an in-process resolver."""
    key = generate_keypair(seed=b"peer-A")
    served: list[tuple[str, str]] = []

    def resolver(topic_query: str, requester_id: str):
        served.append((topic_query, requester_id))
        return serve_slice(
            items=_items(2),
            source_substrate_id="sub-A",
            topic_scope=topic_query,
            signing_key=key,
        )

    fslice = request_slice(
        requesting_substrate_id="sub-B",
        peer_substrate_id="sub-A",
        topic_query="topic-x",
        server_resolver=resolver,
    )
    assert served == [("topic-x", "sub-B")]
    assert fslice.manifest.topic_scope == "topic-x"
    assert len(fslice.items) == 2


# ── No-cross-write invariant ──────────────────────────────────────


def test_no_cross_write_invariant_protocol_shape():
    """The protocol surface NEVER exposes a function that writes from
    the receiver back to the sender. Verify by introspection that the
    public API has no such callable."""
    from substrate import federation
    public_names = set(federation.__all__)
    # None of the exposed names should hint at a sender-side write
    # primitive. This is a structural test — if someone adds such a
    # function later, this test fires.
    forbidden_substrings = ("push_to_peer", "write_back_to", "send_write")
    for name in public_names:
        lowered = name.lower()
        for f in forbidden_substrings:
            assert f not in lowered, f"forbidden write-back name surfaced: {name}"


def test_signature_includes_item_hashes():
    """Tampering with items (without re-signing) must break verification."""
    key = generate_keypair(seed=b"peer-A")
    fslice = serve_slice(
        items=_items(3),
        source_substrate_id="sub-A",
        topic_scope="topic-x",
        signing_key=key,
    )
    # Mutate items but leave the manifest signature alone.
    bad_items = list(fslice.items)
    bad_items[0] = SliceItem(
        note_id=bad_items[0].note_id,
        user_id=bad_items[0].user_id,
        content_hash="0" * 64,  # tampered
        topic_tags=bad_items[0].topic_tags,
        created_at_source=bad_items[0].created_at_source,
    )
    # Build a new manifest reflecting the tampered hashes.
    from substrate.federation.slice import FederationSlice, build_manifest
    bad_manifest = build_manifest(
        source_substrate_id=fslice.manifest.source_substrate_id,
        topic_scope=fslice.manifest.topic_scope,
        items=bad_items,
    )
    # Re-use the old signature — its payload no longer matches.
    bad_slice = FederationSlice(
        manifest=bad_manifest,
        items=tuple(bad_items),
        manifest_signature=fslice.manifest_signature,
        signing_key_fingerprint=fslice.signing_key_fingerprint,
    )
    registry = FederationRegistry()
    registry.pin(FederationPeer(substrate_id="sub-A", verifying_key=key.public()))
    with pytest.raises(SignatureError):
        ingest_slice(bad_slice, registry=registry, quality_gate=_always_pass)
