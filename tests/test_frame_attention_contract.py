"""SPR-05 M2 — the per-second frame-attention telemetry contract.

Proves the typed wire-shape the SPR-07 emitter must satisfy: ranges/units are
validated, the lens vocabulary is enforced, the batch is the unit (not one row
per second), and the schema is version-stamped.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from substrate.ad_inventory.frame_attention import (
    FRAME_TELEMETRY_SCHEMA_VERSION,
    FRAME_WEIGHTING_VERSION,
    SUPPORTED_FRAME_TELEMETRY_SCHEMA_VERSIONS,
    VALID_LENSES,
    FrameAttentionSample,
    FrameSecond,
    WindowFrameBatch,
)


def test_sample_accepts_valid_ranges():
    s = FrameAttentionSample(
        asset_id="doc-1",
        viewport_area_fraction=0.5,
        prominence=0.8,
        focused_dwell_ms=900,
        content_class="public_domain",
        chunk_id="chunk-1",
    )
    assert s.asset_id == "doc-1"
    assert s.chunk_id == "chunk-1"


def test_sample_allows_no_chunk():
    """An asset in frame with no resolved chunk (a cover/title card) is valid —
    the asset is what is monetized; the chunk is trace detail."""
    s = FrameAttentionSample(
        asset_id="doc-1", viewport_area_fraction=1.0, prominence=1.0,
        focused_dwell_ms=1000, content_class="public_domain", chunk_id=None,
    )
    assert s.chunk_id is None


@pytest.mark.parametrize("area", [-0.1, 1.1, 2.0])
def test_sample_rejects_out_of_range_area(area):
    with pytest.raises(ValueError):
        FrameAttentionSample(
            asset_id="d", viewport_area_fraction=area, prominence=0.5,
            focused_dwell_ms=0,
        )


@pytest.mark.parametrize("prom", [-0.1, 1.5])
def test_sample_rejects_out_of_range_prominence(prom):
    with pytest.raises(ValueError):
        FrameAttentionSample(
            asset_id="d", viewport_area_fraction=0.5, prominence=prom,
            focused_dwell_ms=0,
        )


@pytest.mark.parametrize("dwell", [-1, 1001, 5000])
def test_sample_rejects_out_of_range_dwell(dwell):
    """Dwell is per-second: [0, 1000] ms. >1000 would double-count a second."""
    with pytest.raises(ValueError):
        FrameAttentionSample(
            asset_id="d", viewport_area_fraction=0.5, prominence=0.5,
            focused_dwell_ms=dwell,
        )


def test_frame_second_rejects_unknown_lens():
    with pytest.raises(ValueError):
        FrameSecond(second_index=0, lens="doomscroll", samples=())


def test_frame_second_rejects_negative_index():
    with pytest.raises(ValueError):
        FrameSecond(second_index=-1, lens="read", samples=())


def test_all_four_lenses_valid():
    assert {"read", "research", "write", "speak"} == VALID_LENSES
    for lens in VALID_LENSES:
        FrameSecond(second_index=0, lens=lens, samples=())


def test_batch_is_version_stamped_by_default():
    """The batch carries a schema version so an old emitter is identifiable."""
    b = WindowFrameBatch(window_id="w-1", seconds=(), ad_value_usd_cents=100)
    assert b.schema_version == FRAME_TELEMETRY_SCHEMA_VERSION


def test_batch_rejects_negative_ad_value():
    with pytest.raises(ValueError):
        WindowFrameBatch(window_id="w-1", seconds=(), ad_value_usd_cents=-5)


def test_versions_are_distinct_surfaces():
    """Telemetry-shape version and weighting-math version are separate so a
    dispute can isolate 'the contract changed' from 'the math changed'."""
    assert FRAME_TELEMETRY_SCHEMA_VERSION != FRAME_WEIGHTING_VERSION


def test_version_gate_accepts_current_and_previous_wire_only():
    """Ad-pipeline gap S1 (frame-telemetry-v3): the gate accepts the CURRENT
    version plus the previous one (v2 — a strict wire subset of v3: the value
    hint is simply absent) so old emitters keep working. The client-priced v1
    shape is NOT in the accepted set."""
    assert FRAME_TELEMETRY_SCHEMA_VERSION == "frame-telemetry-v3"
    assert {
        "frame-telemetry-v2",
        FRAME_TELEMETRY_SCHEMA_VERSION,
    } == SUPPORTED_FRAME_TELEMETRY_SCHEMA_VERSIONS
    assert "frame-telemetry-v1" not in SUPPORTED_FRAME_TELEMETRY_SCHEMA_VERSIONS


def test_batch_is_the_unit_not_per_second_rows():
    """A batch holds MANY seconds in one object — the emitter flushes one batch
    per window, not one record per second (the batching/flush rule)."""
    seconds = tuple(
        FrameSecond(second_index=i, lens="read", samples=())
        for i in range(600)
    )
    b = WindowFrameBatch(window_id="w-1", seconds=seconds, ad_value_usd_cents=600)
    # 600 seconds, ONE batch object.
    assert len(b.seconds) == 600


def test_models_are_frozen():
    s = FrameAttentionSample(
        asset_id="d", viewport_area_fraction=0.5, prominence=0.5,
        focused_dwell_ms=0,
    )
    with pytest.raises(FrozenInstanceError):
        s.asset_id = "other"  # type: ignore[misc]
