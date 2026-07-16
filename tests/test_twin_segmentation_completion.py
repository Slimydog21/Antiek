from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from dataclasses import replace

import pytest
from nacl.signing import SigningKey

from substrate.twin_note_taker import (
    AUTHORITY_VERIFY_KEY_ENV,
    AssetContent,
    ProposedInsight,
    ProposedQuestion,
    TwinProposal,
)
from substrate.twin_recursion.segmentation import build_segmentation_manifest
from substrate.twin_recursion.segmentation_completion import (
    COMPLETION_SCHEMA,
    AggregateCompletionReceipt,
    SegmentationCompletionError,
    SegmentCompletionReceipt,
    proposal_hash,
    receipt_payload,
    sha256,
)
from substrate.twin_recursion.segmentation_completion_ledger import (
    SegmentationCompletionIntegrityError,
    SegmentationCompletionLedger,
)
from substrate.twin_recursion.segmentation_ledger import TwinSegmentationLedger


@pytest.fixture
def signing_key(monkeypatch: pytest.MonkeyPatch) -> SigningKey:
    key = SigningKey.generate()
    monkeypatch.setenv(AUTHORITY_VERIFY_KEY_ENV, base64.b64encode(bytes(key.verify_key)).decode())
    return key


@pytest.fixture
def source() -> AssetContent:
    return AssetContent(
        "book",
        "Large book",
        "Canonical paragraph with real information.\n" * 10_000,
        "book",
        ("evt-source-book",),
    )


def _proposal(label: str) -> TwinProposal:
    return TwinProposal(
        (ProposedInsight(f"Insight {label}", ""),),
        (ProposedQuestion(f"Question {label}?"),),
        f"Synthesis {label}",
    )


def _sign(receipt, key: SigningKey):
    signature = key.sign(receipt_payload(receipt)).signature
    return replace(receipt, signature=base64.b64encode(signature).decode())


def _segment_receipt(manifest, source, index, proposal, key):
    segment = manifest.segments[index]
    verify_key = base64.b64encode(bytes(key.verify_key)).decode()
    receipt = SegmentCompletionReceipt(
        COMPLETION_SCHEMA,
        f"segment-receipt-{index}",
        manifest.account_id,
        manifest.manifest_hash,
        manifest.parent_source_hash,
        index,
        segment.start_char,
        segment.end_char,
        segment.content_sha256,
        "model",
        "approved-hold",
        proposal_hash(proposal),
        "key_" + hashlib.sha256(bytes(key.verify_key)).hexdigest(),
        verify_key,
        4_000_000_000,
        "",
    )
    return _sign(receipt, key)


def _setup(tmp_path, source):
    manifest = build_segmentation_manifest(account_id="acct", asset=source)
    registry = TwinSegmentationLedger(tmp_path / "registry.sqlite")
    registry.register(manifest, account_id="acct", asset=source)
    ledger = SegmentationCompletionLedger(tmp_path / "completion.sqlite")
    ledger.register_manifest(manifest, asset=source, registry=registry)
    return manifest, ledger, registry


def _complete_segments(manifest, ledger, registry, source, key):
    for index in range(len(manifest.segments)):
        proposal = _proposal(str(index))
        ledger.apply_segment(
            manifest,
            asset=source,
            segment_index=index,
            proposal=proposal,
            receipt=_segment_receipt(manifest, source, index, proposal, key),
            registry=registry,
        )


def _ordered_hash(path, manifest):
    with sqlite3.connect(path) as con:
        rows = con.execute(
            "SELECT segment_index,binding_id,completion_digest FROM segment_completion_bindings "
            "ORDER BY segment_index"
        ).fetchall()
    return sha256(json.dumps([list(row) for row in rows], separators=(",", ":")))


def test_signed_segments_and_parent_aggregate_are_exact_and_restart_safe(
    tmp_path, source, signing_key
):
    manifest, ledger, registry = _setup(tmp_path, source)
    _complete_segments(manifest, ledger, registry, source, signing_key)
    pending = ledger.get(
        "acct", "book", manifest.parent_source_hash, asset=source, registry=registry
    )
    assert pending.completed_segments == pending.segment_count and not pending.parent_ready
    aggregate = _proposal("aggregate")
    ordered_hash = _ordered_hash(tmp_path / "completion.sqlite", manifest)
    receipt = _sign(
        AggregateCompletionReceipt(
            COMPLETION_SCHEMA,
            "aggregate-receipt",
            "acct",
            manifest.manifest_hash,
            manifest.parent_source_hash,
            ordered_hash,
            "model",
            "aggregate-hold",
            proposal_hash(aggregate),
            "key_" + hashlib.sha256(bytes(signing_key.verify_key)).hexdigest(),
            base64.b64encode(bytes(signing_key.verify_key)).decode(),
            4_000_000_000,
            "",
        ),
        signing_key,
    )
    ready = ledger.apply_aggregate(
        manifest, asset=source, proposal=aggregate, receipt=receipt, registry=registry
    )
    replay = SegmentationCompletionLedger(tmp_path / "completion.sqlite").apply_aggregate(
        manifest, asset=source, proposal=aggregate, receipt=receipt, registry=registry
    )
    assert ready == replay and ready.parent_ready and ready.body_json
    assert json.loads(ready.body_json)["synthesis_withheld"] is True


def test_missing_segment_refuses_aggregate(tmp_path, source, signing_key):
    manifest, ledger, registry = _setup(tmp_path, source)
    proposal = _proposal("aggregate")
    receipt = _sign(
        AggregateCompletionReceipt(
            COMPLETION_SCHEMA,
            "aggregate",
            "acct",
            manifest.manifest_hash,
            manifest.parent_source_hash,
            "0" * 64,
            "model",
            "hold",
            proposal_hash(proposal),
            "key_" + hashlib.sha256(bytes(signing_key.verify_key)).hexdigest(),
            base64.b64encode(bytes(signing_key.verify_key)).decode(),
            4_000_000_000,
            "",
        ),
        signing_key,
    )
    with pytest.raises(SegmentationCompletionError, match="all ordered"):
        ledger.apply_aggregate(
            manifest, asset=source, proposal=proposal, receipt=receipt, registry=registry
        )


def test_segment_substitution_signature_and_source_drift_fail_closed(tmp_path, source, signing_key):
    manifest, ledger, registry = _setup(tmp_path, source)
    proposal = _proposal("0")
    receipt = _segment_receipt(manifest, source, 0, proposal, signing_key)
    mismatched = _sign(replace(receipt, segment_index=1, signature=""), signing_key)
    with pytest.raises(SegmentationCompletionError, match="exact obligation"):
        ledger.apply_segment(
            manifest,
            asset=source,
            segment_index=0,
            proposal=proposal,
            receipt=mismatched,
            registry=registry,
        )
    with pytest.raises(SegmentationCompletionError, match="signature"):
        ledger.apply_segment(
            manifest,
            asset=source,
            segment_index=0,
            proposal=proposal,
            receipt=replace(receipt, signature="invalid"),
            registry=registry,
        )
    with pytest.raises(ValueError, match="conflict"):
        ledger.apply_segment(
            manifest,
            asset=replace(source, content_text=source.content_text + "x"),
            segment_index=0,
            proposal=proposal,
            receipt=receipt,
            registry=registry,
        )


def test_exact_replay_converges_and_changed_completion_conflicts(tmp_path, source, signing_key):
    manifest, ledger, registry = _setup(tmp_path, source)
    proposal = _proposal("0")
    receipt = _segment_receipt(manifest, source, 0, proposal, signing_key)
    first = ledger.apply_segment(
        manifest,
        asset=source,
        segment_index=0,
        proposal=proposal,
        receipt=receipt,
        registry=registry,
    )
    assert (
        ledger.apply_segment(
            manifest,
            asset=source,
            segment_index=0,
            proposal=proposal,
            receipt=receipt,
            registry=registry,
        )
        == first
    )
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            "substrate.twin_recursion.segmentation_completion.time.time", lambda: 5_000_000_000
        )
        assert (
            ledger.apply_segment(
                manifest,
                asset=source,
                segment_index=0,
                proposal=proposal,
                receipt=receipt,
                registry=registry,
            )
            == first
        )
    changed = _proposal("changed")
    with pytest.raises(SegmentationCompletionIntegrityError, match="substitution"):
        ledger.apply_segment(
            manifest,
            asset=source,
            segment_index=0,
            proposal=changed,
            receipt=_segment_receipt(manifest, source, 0, changed, signing_key),
            registry=registry,
        )


def test_schema_and_body_corruption_fail_closed(tmp_path, source, signing_key):
    manifest, ledger, registry = _setup(tmp_path, source)
    with sqlite3.connect(tmp_path / "completion.sqlite") as con:
        con.execute("DROP TRIGGER completion_manifest_immutable")
    with pytest.raises(SegmentationCompletionIntegrityError, match="schema object"):
        ledger.get("acct", "book", manifest.parent_source_hash, asset=source, registry=registry)


def test_ready_read_rechecks_source_and_registry_but_survives_key_rotation(
    tmp_path, source, signing_key, monkeypatch
):
    manifest, ledger, registry = _setup(tmp_path, source)
    _complete_segments(manifest, ledger, registry, source, signing_key)
    rotated = SigningKey.generate()
    monkeypatch.setenv(
        AUTHORITY_VERIFY_KEY_ENV, base64.b64encode(bytes(rotated.verify_key)).decode()
    )
    snapshot = ledger.get(
        "acct", "book", manifest.parent_source_hash, asset=source, registry=registry
    )
    assert snapshot.completed_segments == snapshot.segment_count
    with pytest.raises(ValueError, match="conflict"):
        ledger.get(
            "acct",
            "book",
            manifest.parent_source_hash,
            asset=replace(source, content_text=source.content_text + "drift"),
            registry=registry,
        )


def test_unexpected_trigger_is_schema_corruption(tmp_path, source):
    manifest, ledger, registry = _setup(tmp_path, source)
    with sqlite3.connect(tmp_path / "completion.sqlite") as con:
        con.execute(
            "CREATE TRIGGER exfiltrate_after_insert AFTER INSERT ON completion_manifests "
            "BEGIN SELECT 1; END"
        )
    with pytest.raises(SegmentationCompletionIntegrityError, match="object set"):
        ledger.get("acct", "book", manifest.parent_source_hash, asset=source, registry=registry)


def test_no_source_body_is_persisted(tmp_path, source):
    manifest, _ledger, _registry = _setup(tmp_path, source)
    with sqlite3.connect(tmp_path / "completion.sqlite") as con:
        stored = " ".join(
            str(value)
            for row in con.execute("SELECT manifest_json FROM completion_manifests")
            for value in row
        )
    assert source.content_text[:100] not in stored
    assert manifest.body_sha256 in stored
