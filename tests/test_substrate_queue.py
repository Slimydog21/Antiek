"""Tests for substrate/queue -- bounded FIFO with watermark back-pressure."""

from __future__ import annotations

from pathlib import Path

import pytest

from substrate.observability.burn import BurnRecorder
from substrate.observability.burn_context import (
    BurnContext,
    reset_burn_context,
    set_burn_context,
)
from substrate.queue import (
    BoundedQueue,
    QueueEmpty,
    QueueFull,
    QueueRegistry,
    get_registry,
)


@pytest.fixture(autouse=True)
def _reset_burn():
    BurnRecorder._reset_instances()
    yield
    BurnRecorder._reset_instances()


@pytest.fixture
def fresh_registry():
    r = get_registry()
    r.reset()
    yield r
    r.reset()


def test_bounded_queue_rejects_zero_capacity() -> None:
    with pytest.raises(ValueError, match="capacity must be >= 1"):
        BoundedQueue("q", capacity=0)


def test_bounded_queue_rejects_invalid_watermark() -> None:
    with pytest.raises(ValueError):
        BoundedQueue("q", capacity=10, watermark_pct=1.5)
    with pytest.raises(ValueError):
        BoundedQueue("q", capacity=10, watermark_pct=0)


def test_enqueue_up_to_capacity() -> None:
    q = BoundedQueue("q", capacity=3)
    q.enqueue("a")
    q.enqueue("b")
    q.enqueue("c")
    assert q.depth() == 3


def test_enqueue_at_capacity_raises_queue_full() -> None:
    q = BoundedQueue("q", capacity=2)
    q.enqueue("a")
    q.enqueue("b")
    with pytest.raises(QueueFull) as ei:
        q.enqueue("c")
    assert ei.value.queue_name == "q"
    assert ei.value.capacity == 2
    assert ei.value.current_depth == 2


def test_try_enqueue_returns_bool() -> None:
    q = BoundedQueue("q", capacity=1)
    assert q.try_enqueue("a") is True
    assert q.try_enqueue("b") is False
    assert q.depth() == 1


def test_dequeue_returns_fifo() -> None:
    q = BoundedQueue("q", capacity=3)
    for x in ("a", "b", "c"):
        q.enqueue(x)
    assert q.dequeue() == "a"
    assert q.dequeue() == "b"
    assert q.dequeue() == "c"


def test_dequeue_empty_raises() -> None:
    q = BoundedQueue("q", capacity=3)
    with pytest.raises(QueueEmpty):
        q.dequeue()


def test_enqueue_after_dequeue_room_returns() -> None:
    q = BoundedQueue("q", capacity=2)
    q.enqueue("a")
    q.enqueue("b")
    q.dequeue()
    q.enqueue("c")
    assert list(q) == ["b", "c"]


def test_watermark_count_exact() -> None:
    q = BoundedQueue("q", capacity=10, watermark_pct=0.8)
    assert q.watermark_count == 8


def test_watermark_edge_trigger_fires_once(tmp_path: Path) -> None:
    ctx = BurnContext(session_id="wm", project_root=tmp_path)
    token = set_burn_context(ctx)
    try:
        q = BoundedQueue("q-wm", capacity=10, watermark_pct=0.8)
        for i in range(10):
            try:
                q.enqueue(i)
            except QueueFull:
                pass
        recorder = BurnRecorder.for_project(tmp_path)
        rows = recorder.query("SELECT * FROM burn_events WHERE tool_id='queue.watermark'")
        assert len(rows) == 1
        assert "crossed watermark" in (rows[0]["error"] or "")
    finally:
        reset_burn_context(token)


def test_watermark_re_arms_after_drop_below(tmp_path: Path) -> None:
    ctx = BurnContext(session_id="wm", project_root=tmp_path)
    token = set_burn_context(ctx)
    try:
        q = BoundedQueue("q-rearm", capacity=10, watermark_pct=0.8)
        for i in range(8):
            q.enqueue(i)
        for _ in range(3):
            q.dequeue()
        for i in range(3):
            q.enqueue("again-" + str(i))
        recorder = BurnRecorder.for_project(tmp_path)
        rows = recorder.query("SELECT * FROM burn_events WHERE tool_id='queue.watermark'")
        assert len(rows) == 2
    finally:
        reset_burn_context(token)


def test_stats_tracks_counters() -> None:
    q = BoundedQueue("q-stats", capacity=2)
    q.enqueue("a")
    q.enqueue("b")
    try:
        q.enqueue("c")
    except QueueFull:
        pass
    q.dequeue()
    s = q.stats()
    assert s["enqueue_count"] == 2
    assert s["dequeue_count"] == 1
    assert s["reject_count"] == 1
    assert s["depth"] == 1


def test_register_then_get(fresh_registry: QueueRegistry) -> None:
    q = BoundedQueue("autoresearch.fanout", capacity=20)
    fresh_registry.register(q)
    assert fresh_registry.get("autoresearch.fanout") is q


def test_register_duplicate_name_raises(fresh_registry: QueueRegistry) -> None:
    fresh_registry.register(BoundedQueue("dup", capacity=1))
    with pytest.raises(ValueError, match="already registered"):
        fresh_registry.register(BoundedQueue("dup", capacity=1))


def test_all_stats_returns_one_per_queue(fresh_registry: QueueRegistry) -> None:
    fresh_registry.register(BoundedQueue("a", capacity=5))
    fresh_registry.register(BoundedQueue("b", capacity=10))
    stats = fresh_registry.all_stats()
    names = {s["name"] for s in stats}
    assert names == {"a", "b"}


def test_get_missing_raises(fresh_registry: QueueRegistry) -> None:
    with pytest.raises(KeyError):
        fresh_registry.get("nope")


def test_iter_does_not_dequeue() -> None:
    q = BoundedQueue("q", capacity=5)
    for x in ("a", "b", "c"):
        q.enqueue(x)
    assert list(q) == ["a", "b", "c"]
    assert q.depth() == 3
