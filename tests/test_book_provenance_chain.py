"""Tests for ``substrate.book_provenance_chain`` — the acquisition provenance-chain
integrity verifier (book-purchase-transport spec invariant #7).

Each test isolates ONE defect so the four independent properties (complete /
ordered / chained / tamper-evident) are exercised independently, plus the honest
``None`` states (unknown key -> unknown tamper-evidence -> unknown intact)."""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence

import pytest

from substrate.book_provenance_chain import (
    REASON_GENESIS_PARENTED,
    REASON_NON_GENESIS_AT_HEAD,
    REASON_PARENT_MISMATCH,
    STAGES,
    BrokenLink,
    ChainStage,
    ProvenanceChainError,
    compute_stage_hash,
    verify_provenance_chain,
)

_KEY = b"operator-acquisition-signing-key"
_DOC = "book://antiek/9780000000001"

_DEFAULT_PAYLOADS: dict[str, str] = {
    "source_resolution": "https://store.example/works/1 (resolved deep link)",
    "authorization": "receipt:#733 ownership-confirmed order=ORD-1",
    "ingest": "basis:isbn13:9780000000001",
    "sanitize": "sanitize_book_html build=#729 redproof=100",
    "host": "serve.py path=/library/9780000000001 deny-by-default",
}
_DEFAULT_ACTORS: dict[str, str] = {
    "source_resolution": "acquisition/connector:store-resolver",
    "authorization": "operator+runtime.byok.store",
    "ingest": "acquisition/books/classify_and_ingest",
    "sanitize": "services/html_projection/sanitize_book_html",
    "host": "substrate/books/serve",
}
_DEFAULT_TIMESTAMPS: dict[str, str] = {
    "source_resolution": "2026-07-13T08:00:00Z",
    "authorization": "2026-07-13T08:01:00Z",
    "ingest": "2026-07-13T08:02:00Z",
    "sanitize": "2026-07-13T08:03:00Z",
    "host": "2026-07-13T08:04:00Z",
}


def _stamp(
    document_id: str = _DOC,
    key: bytes = _KEY,
    stage_order: Sequence[str] = STAGES,
    payloads: dict[str, str] | None = None,
    actors: dict[str, str] | None = None,
    timestamps: dict[str, str] | None = None,
) -> list[ChainStage]:
    """Build a cryptographically valid chain: each stage's claimed_hash is the
    HMAC over its own fields, and each non-genesis stage's parent_hash is the
    prior stage's claimed_hash (a true hash-chain)."""
    payloads = payloads or _DEFAULT_PAYLOADS
    actors = actors or _DEFAULT_ACTORS
    timestamps = timestamps or _DEFAULT_TIMESTAMPS
    stages: list[ChainStage] = []
    parent: str | None = None
    for name in stage_order:
        unsigned = ChainStage(
            document_id, name, actors[name], parent, payloads[name], timestamps[name], ""
        )
        digest = compute_stage_hash(unsigned, key)
        stages.append(dataclasses.replace(unsigned, claimed_hash=digest))
        parent = digest
    return stages


def test_intact_chain_all_properties_hold() -> None:
    stages = _stamp()
    report = verify_provenance_chain(stages, key=_KEY)

    assert report.document_id == _DOC
    assert report.complete is True
    assert report.ordered is True
    assert report.chained is True
    assert report.single_document is True
    assert report.tamper_evident is True
    assert report.intact is True
    assert report.present_stages == STAGES
    assert report.missing_stages == ()
    assert report.broken_links == ()
    assert report.tampered_stages == ()
    assert report.authority == "advisory"


def test_empty_chain_fails_complete_not_crash() -> None:
    report = verify_provenance_chain([], key=_KEY)

    assert report.complete is False
    assert report.intact is False
    assert report.missing_stages == STAGES
    assert report.present_stages == ()
    assert report.document_id == ""
    assert "empty chain" in " ".join(report.notes)


def test_missing_stage_breaks_completeness_only() -> None:
    order = ("source_resolution", "authorization", "ingest", "sanitize")
    stages = _stamp(stage_order=order)
    report = verify_provenance_chain(stages, key=_KEY)

    assert report.complete is False
    assert report.missing_stages == ("host",)
    assert report.ordered is True  # the four present are in canonical order
    assert report.chained is True  # links are intact among the present stages
    assert report.intact is False


def test_out_of_order_stage_breaks_ordering_only() -> None:
    # canonical ranks: source0 auth1 ingest2 sanitize3 host4 -> swap ingest/sanitize
    order = (
        "source_resolution",
        "authorization",
        "sanitize",
        "ingest",
        "host",
    )
    stages = _stamp(stage_order=order)
    report = verify_provenance_chain(stages, key=_KEY)

    assert report.complete is True  # all five present
    assert report.ordered is False  # sanitize(3) before ingest(2) is a reversal
    assert report.chained is True  # stamped in list order, so links hold positionally
    assert report.intact is False


def test_duplicate_stage_breaks_ordering_only() -> None:
    stages = _stamp()
    last = stages[-1]  # host
    unsigned_dup = ChainStage(
        last.document_id,
        last.stage,
        last.actor,
        last.claimed_hash,  # links to the prior host's receipt
        last.payload,
        "2026-07-13T08:05:00Z",
        "",
    )
    stamped_dup = dataclasses.replace(
        unsigned_dup, claimed_hash=compute_stage_hash(unsigned_dup, _KEY)
    )
    stages.append(stamped_dup)
    report = verify_provenance_chain(stages, key=_KEY)

    assert report.complete is True  # all five canonical stages present
    assert report.ordered is False  # host, host is not strictly increasing
    assert report.chained is True  # dup parent_hash matches prior host claimed_hash
    assert report.intact is False


def test_broken_link_parent_mismatch() -> None:
    stages = _stamp()
    # corrupt the sanitize stage's parent_hash so it no longer matches ingest's receipt
    bad_index = STAGES.index("sanitize")
    stages[bad_index] = dataclasses.replace(stages[bad_index], parent_hash="deadbeef")
    report = verify_provenance_chain(stages, key=_KEY)

    assert report.chained is False
    assert report.complete is True
    assert report.ordered is True
    assert len(report.broken_links) == 1
    link = report.broken_links[0]
    assert isinstance(link, BrokenLink)
    assert link.stage == "sanitize"
    assert link.reason == REASON_PARENT_MISMATCH
    assert link.expected == stages[bad_index - 1].claimed_hash
    assert link.actual == "deadbeef"
    assert report.intact is False


def test_genesis_must_be_unparented() -> None:
    stages = _stamp()
    # give the genesis source_resolution stage a spurious parent
    stages[0] = dataclasses.replace(stages[0], parent_hash="pretend-parent")
    report = verify_provenance_chain(stages, key=_KEY)

    assert report.chained is False
    assert len(report.broken_links) == 1
    assert report.broken_links[0].stage == "source_resolution"
    assert report.broken_links[0].reason == REASON_GENESIS_PARENTED
    assert report.broken_links[0].expected == "(none)"


def test_non_genesis_at_head_is_broken() -> None:
    # a single authorization stage cannot be the chain head (no genesis before it)
    unsigned = ChainStage(
        _DOC,
        "authorization",
        _DEFAULT_ACTORS["authorization"],
        None,
        _DEFAULT_PAYLOADS["authorization"],
        _DEFAULT_TIMESTAMPS["authorization"],
        "",
    )
    stage = dataclasses.replace(unsigned, claimed_hash=compute_stage_hash(unsigned, _KEY))
    report = verify_provenance_chain([stage], key=_KEY)

    assert report.chained is False
    assert report.broken_links[0].reason == REASON_NON_GENESIS_AT_HEAD
    assert report.complete is False
    assert report.intact is False


def test_tampered_payload_breaks_tamper_evidence_only() -> None:
    stages = _stamp()
    # alter ingest's evidence but LEAVE its old claimed_hash -> recompute won't match.
    # the downstream sanitize.parent_hash still equals ingest's (unchanged) claimed_hash,
    # so chaining stays intact; only tamper-evidence fails.
    tamper_index = STAGES.index("ingest")
    stages[tamper_index] = dataclasses.replace(
        stages[tamper_index], payload="EVIL ALTERED EVIDENCE"
    )
    report = verify_provenance_chain(stages, key=_KEY)

    assert report.complete is True
    assert report.ordered is True
    assert report.chained is True
    assert report.tamper_evident is False
    assert report.tampered_stages == ("ingest",)
    assert report.intact is False


def test_key_unknown_yields_unknown_tamper_and_unknown_intact() -> None:
    stages = _stamp()  # structurally perfect
    report = verify_provenance_chain(stages, key=None)

    assert report.complete is True
    assert report.ordered is True
    assert report.chained is True
    assert report.tamper_evident is None  # cannot check without the key
    assert report.intact is None  # structurally sound but unverified -> unknown
    assert "signing key not supplied" in " ".join(report.notes)


def test_key_unknown_with_structural_fail_is_definitively_false() -> None:
    order = ("source_resolution", "authorization", "ingest", "sanitize")
    stages = _stamp(stage_order=order)
    report = verify_provenance_chain(stages, key=None)

    assert report.complete is False
    assert report.tamper_evident is None
    assert report.intact is False  # structural failure is definitive regardless of key


def test_mixed_document_chain_is_defect() -> None:
    stages = _stamp()
    other = "book://antiek/9780000000002"
    # re-stamp the host stage under a different document_id
    host = stages[-1]
    unsigned = ChainStage(
        other,
        host.stage,
        host.actor,
        host.parent_hash,
        host.payload,
        host.timestamp,
        "",
    )
    stages[-1] = dataclasses.replace(unsigned, claimed_hash=compute_stage_hash(unsigned, _KEY))
    report = verify_provenance_chain(stages, key=_KEY)

    assert report.single_document is False
    assert report.intact is False
    assert "mixed-document" in " ".join(report.notes)


def test_structural_pass_but_tampered_is_definitively_false() -> None:
    stages = _stamp()
    stages[2] = dataclasses.replace(stages[2], payload="tampered")
    report = verify_provenance_chain(stages, key=_KEY)

    assert report.complete is True
    assert report.chained is True
    assert report.tamper_evident is False
    assert report.intact is False  # structural ok but tampered -> False, not None


def test_compute_stage_hash_deterministic_and_payload_sensitive() -> None:
    base = ChainStage(
        _DOC,
        "ingest",
        _DEFAULT_ACTORS["ingest"],
        "abc123",
        _DEFAULT_PAYLOADS["ingest"],
        _DEFAULT_TIMESTAMPS["ingest"],
        "",
    )
    altered = dataclasses.replace(base, payload="different evidence")
    assert compute_stage_hash(base, _KEY) == compute_stage_hash(base, _KEY)
    assert compute_stage_hash(base, _KEY) != compute_stage_hash(altered, _KEY)
    assert compute_stage_hash(base, _KEY) != compute_stage_hash(base, b"different-key")


def test_validation_unknown_stage_raises() -> None:
    bad = ChainStage(_DOC, "not_a_stage", "actor", None, "payload", "2026-07-13T08:00:00Z", "hash")
    with pytest.raises(ProvenanceChainError):
        verify_provenance_chain([bad], key=_KEY)


@pytest.mark.parametrize(
    "field_name",
    ["document_id", "actor", "payload", "timestamp", "claimed_hash"],
)
def test_validation_empty_required_fields_raise(field_name: str) -> None:
    base_kwargs: dict[str, object] = {
        "document_id": _DOC,
        "stage": "source_resolution",
        "actor": "actor",
        "parent_hash": None,
        "payload": "payload",
        "timestamp": "2026-07-13T08:00:00Z",
        "claimed_hash": "hash",
    }
    base_kwargs[field_name] = ""
    with pytest.raises(ProvenanceChainError):
        verify_provenance_chain([ChainStage(**base_kwargs)], key=_KEY)  # type: ignore[arg-type]


def test_free_book_chain_is_still_intact() -> None:
    # a free/public-domain book (no purchase) still needs the full chain; the
    # authorization payload records the public-domain basis, not a purchase.
    payloads = dict(_DEFAULT_PAYLOADS)
    payloads["authorization"] = "receipt:#733 public-domain:US-pre-1929 no-purchase"
    stages = _stamp(payloads=payloads)
    report = verify_provenance_chain(stages, key=_KEY)
    assert report.intact is True
