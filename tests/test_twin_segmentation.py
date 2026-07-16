from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from substrate.twin_note_taker import MAX_CONTENT_CHARS, AssetContent
from substrate.twin_recursion.segmentation import (
    TARGET_SEGMENT_CHARS,
    TwinSegmentationError,
    build_segmentation_manifest,
    verify_segmentation_manifest,
)
from substrate.twin_recursion.segmentation_ledger import (
    TRIGGERS,
    TwinSegmentationIntegrityError,
    TwinSegmentationLedger,
)


@pytest.fixture
def asset() -> AssetContent:
    paragraph = "A stable paragraph of canonical source material.\n"
    return AssetContent(
        asset_id="book-1",
        title="A large book",
        content_text=paragraph * ((MAX_CONTENT_CHARS // len(paragraph)) + 2_000),
        content_class="book",
        source_event_ids=("evt-source-book-1",),
    )


def test_manifest_is_lossless_ordered_bounded_and_deterministic(asset):
    first = build_segmentation_manifest(account_id="acct", asset=asset)
    second = build_segmentation_manifest(account_id="acct", asset=asset)
    assert first == second and first.manifest_hash == second.manifest_hash
    assert len(first.segments) >= 2
    cursor = 0
    reconstructed = []
    for index, segment in enumerate(first.segments):
        assert segment.index == index and segment.start_char == cursor
        assert 0 < segment.length <= MAX_CONTENT_CHARS
        reconstructed.append(asset.content_text[segment.start_char : segment.end_char])
        cursor = segment.end_char
    assert cursor == len(asset.content_text)
    assert "".join(reconstructed) == asset.content_text
    assert first.segments[0].end_char <= TARGET_SEGMENT_CHARS


def test_long_line_uses_bounded_hard_fallback_without_loss():
    asset = AssetContent("long", "Long", "x" * (MAX_CONTENT_CHARS * 2 + 7), "book", ("evt-long",))
    manifest = build_segmentation_manifest(account_id="acct", asset=asset)
    assert [segment.length for segment in manifest.segments] == [
        TARGET_SEGMENT_CHARS,
        TARGET_SEGMENT_CHARS,
        len(asset.content_text) - 2 * TARGET_SEGMENT_CHARS,
    ]
    verify_segmentation_manifest(manifest, account_id="acct", asset=asset)


def test_tiny_tail_is_rebalanced_into_materializable_segments():
    asset = AssetContent(
        "tail", "Tail", "x" * (TARGET_SEGMENT_CHARS * 2 + 1), "book", ("evt-tail",)
    )
    manifest = build_segmentation_manifest(account_id="acct", asset=asset)
    assert all(
        len(asset.content_text[item.start_char : item.end_char].strip()) >= 24
        for item in manifest.segments
    )
    assert manifest.segments[-1].length >= 24


def test_manifest_is_hash_only_and_exact_source_drift_fails(asset):
    manifest = build_segmentation_manifest(account_id="acct", asset=asset)
    encoded = manifest.to_json()
    assert asset.content_text[:100] not in encoded
    with pytest.raises(TwinSegmentationError, match="conflict"):
        verify_segmentation_manifest(
            manifest, account_id="acct", asset=replace(asset, content_text=asset.content_text + "x")
        )
    with pytest.raises(TwinSegmentationError, match="conflict"):
        verify_segmentation_manifest(manifest, account_id="other", asset=asset)


def test_only_oversized_sources_can_enter_segmentation():
    asset = AssetContent("small", "Small", "x" * MAX_CONTENT_CHARS, "book", ("evt-small",))
    with pytest.raises(TwinSegmentationError, match="oversized"):
        build_segmentation_manifest(account_id="acct", asset=asset)


def test_registry_is_atomic_restart_safe_hash_only_and_parent_stays_pending(tmp_path, asset):
    path = tmp_path / "segments.sqlite"
    manifest = build_segmentation_manifest(account_id="acct", asset=asset)
    first = TwinSegmentationLedger(path).register(manifest, account_id="acct", asset=asset)
    second = TwinSegmentationLedger(path).register(manifest, account_id="acct", asset=asset)
    assert first == second
    assert first.segment_count == first.pending_segments == len(manifest.segments)
    assert first.aggregate_state == "pending" and not first.parent_ready
    with sqlite3.connect(path) as con:
        stored = " ".join(
            str(value)
            for row in con.execute("SELECT manifest_json FROM segmentation_manifests")
            for value in row
        )
    assert asset.content_text[:100] not in stored
    TwinSegmentationLedger(path).verify_integrity()


def test_concurrent_exact_registration_converges(tmp_path, asset):
    path = tmp_path / "segments.sqlite"
    manifest = build_segmentation_manifest(account_id="acct", asset=asset)
    TwinSegmentationLedger(path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        snapshots = list(
            pool.map(
                lambda _index: TwinSegmentationLedger(path).register(
                    manifest, account_id="acct", asset=asset
                ),
                range(8),
            )
        )
    assert all(snapshot == snapshots[0] for snapshot in snapshots)


def test_manifest_substitution_and_schema_or_obligation_corruption_fail_closed(tmp_path, asset):
    path = tmp_path / "segments.sqlite"
    manifest = build_segmentation_manifest(account_id="acct", asset=asset)
    ledger = TwinSegmentationLedger(path)
    ledger.register(manifest, account_id="acct", asset=asset)
    changed = replace(manifest, aggregate_obligation_id="aggregate_" + "0" * 64)
    with pytest.raises(TwinSegmentationError, match="conflict"):
        ledger.register(changed, account_id="acct", asset=asset)

    with sqlite3.connect(path) as con:
        con.execute("DROP TRIGGER segmentation_obligation_no_update")
        con.execute(
            "UPDATE segmentation_obligations SET content_sha256='forged' WHERE segment_index=0"
        )
        con.execute(TRIGGERS["segmentation_obligation_no_update"])
    with pytest.raises(TwinSegmentationIntegrityError, match="conflict"):
        ledger.register(manifest, account_id="acct", asset=asset)
    with pytest.raises(TwinSegmentationIntegrityError, match="conflict"):
        ledger.get("acct", asset.asset_id, manifest.parent_source_hash)
    with pytest.raises(TwinSegmentationIntegrityError, match="conflict"):
        ledger.verify_integrity()


def test_manifest_json_has_contiguous_ranges_and_no_raw_body(asset):
    manifest = build_segmentation_manifest(account_id="acct", asset=asset)
    raw = json.loads(manifest.to_json())
    assert raw["segments"][0]["start_char"] == 0
    assert raw["segments"][-1]["end_char"] == len(asset.content_text)
    assert "content_text" not in raw


def test_integrity_rejects_manifest_identity_substitution(tmp_path, asset):
    path = tmp_path / "segments.sqlite"
    manifest = build_segmentation_manifest(account_id="acct", asset=asset)
    ledger = TwinSegmentationLedger(path)
    ledger.register(manifest, account_id="acct", asset=asset)
    raw = json.loads(manifest.to_json())
    raw["account_id"] = "other"
    forged = json.dumps(raw, sort_keys=True, separators=(",", ":"))
    with sqlite3.connect(path) as con:
        con.execute("DROP TRIGGER segmentation_manifest_no_update")
        con.execute(
            "UPDATE segmentation_manifests SET manifest_json=?,manifest_hash=?",
            (forged, __import__("hashlib").sha256(forged.encode()).hexdigest()),
        )
        con.execute(TRIGGERS["segmentation_manifest_no_update"])
    with pytest.raises(TwinSegmentationIntegrityError, match="invalid"):
        ledger.verify_integrity()
