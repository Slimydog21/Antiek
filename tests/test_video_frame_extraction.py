"""Video frame extraction tests (Sprint 30+ thread 4)."""

from __future__ import annotations

import pytest

from acquisition.video import (
    DEFAULT_MAX_FRAMES,
    DEFAULT_UNIFORM_INTERVAL_S,
    StubFrameExtractor,
    extract_uniform,
    plan_uniform_timestamps,
)

# ── plan_uniform_timestamps ───────────────────────────────────────


def test_plan_uniform_timestamps_for_normal_duration():
    # 5-minute clip with default 30s interval → 10 frames.
    ts = plan_uniform_timestamps(duration_ms=300_000)
    assert len(ts) == 10
    assert ts[0] == 1_000  # default start_offset_ms
    assert ts[1] == 31_000
    assert ts[-1] < 300_000


def test_plan_uniform_timestamps_respects_max_frames():
    # Long clip + small interval → max_frames cap kicks in.
    ts = plan_uniform_timestamps(
        duration_ms=3_600_000,  # 1 hour
        interval_s=1,
        max_frames=50,
    )
    assert len(ts) == 50


def test_plan_uniform_timestamps_zero_duration_empty():
    assert plan_uniform_timestamps(duration_ms=0) == []


def test_plan_uniform_timestamps_negative_interval_raises():
    with pytest.raises(ValueError):
        plan_uniform_timestamps(duration_ms=300_000, interval_s=-1)


# ── StubFrameExtractor ────────────────────────────────────────────


def test_stub_returns_frame_per_timestamp():
    stub = StubFrameExtractor()
    frames = stub.extract(
        video_source="file:///tmp/x.mp4",
        timestamps_ms=[1000, 2000, 3000],
    )
    assert len(frames) == 3
    assert frames[0].timestamp_ms == 1000
    assert frames[0].page_or_frame_id == "frame-1000"


def test_stub_captures_call_args():
    stub = StubFrameExtractor()
    stub.extract(video_source="x.mp4", timestamps_ms=[500])
    assert len(stub.calls) == 1
    assert stub.calls[0]["video_source"] == "x.mp4"
    assert stub.calls[0]["timestamps_ms"] == [500]


def test_extract_uniform_chains_plan_and_extract():
    stub = StubFrameExtractor()
    frames = extract_uniform(
        stub,
        video_source="x.mp4",
        duration_ms=120_000,  # 2 minutes
    )
    # Expect 4 frames at default 30s interval starting at 1s.
    assert len(frames) == 4
    # Stub captured the planned timestamps.
    assert stub.calls[-1]["timestamps_ms"] == [1_000, 31_000, 61_000, 91_000]


def test_default_constants_are_reasonable():
    assert DEFAULT_UNIFORM_INTERVAL_S > 0
    assert DEFAULT_MAX_FRAMES > 0
