"""BoundedQueue -- capacity-limited FIFO with watermark back-pressure."""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any, Iterator

from substrate.observability.burn import BurnEvent, BurnRecorder
from substrate.observability.burn_context import current_burn_context


class QueueFull(RuntimeError):
    def __init__(self, queue_name: str, capacity: int, current_depth: int) -> None:
        self.queue_name = queue_name
        self.capacity = capacity
        self.current_depth = current_depth
        super().__init__(
            f"queue {queue_name!r} full: depth={current_depth} capacity={capacity}"
        )


class QueueEmpty(RuntimeError):
    pass


class BoundedQueue:
    def __init__(self, name: str, capacity: int, *, watermark_pct: float = 0.8) -> None:
        if capacity < 1:
            raise ValueError(f"capacity must be >= 1, got {capacity}")
        if not 0 < watermark_pct <= 1.0:
            raise ValueError(f"watermark_pct must be in (0, 1], got {watermark_pct}")
        self.name = name
        self.capacity = capacity
        self.watermark_pct = watermark_pct
        self.watermark_count = max(1, int(capacity * watermark_pct))
        self._items: deque[Any] = deque()
        self._lock = threading.Lock()
        self._above_watermark = False
        self._enqueue_count = 0
        self._dequeue_count = 0
        self._reject_count = 0
        self._watermark_crossings = 0

    def enqueue(self, item: Any) -> None:
        with self._lock:
            depth = len(self._items)
            if depth >= self.capacity:
                self._reject_count += 1
                raise QueueFull(self.name, self.capacity, depth)
            self._items.append(item)
            new_depth = depth + 1
            self._enqueue_count += 1
            if not self._above_watermark and new_depth >= self.watermark_count:
                self._above_watermark = True
                self._watermark_crossings += 1
                self._emit_watermark_event(new_depth)
            elif self._above_watermark and new_depth < self.watermark_count:
                self._above_watermark = False

    def try_enqueue(self, item: Any) -> bool:
        try:
            self.enqueue(item)
            return True
        except QueueFull:
            return False

    def dequeue(self) -> Any:
        with self._lock:
            if not self._items:
                raise QueueEmpty(f"queue {self.name!r} empty")
            item = self._items.popleft()
            self._dequeue_count += 1
            new_depth = len(self._items)
            if self._above_watermark and new_depth < self.watermark_count:
                self._above_watermark = False
            return item

    def depth(self) -> int:
        with self._lock:
            return len(self._items)

    def stats(self) -> dict[str, int | float]:
        with self._lock:
            return {
                "name": self.name,
                "capacity": self.capacity,
                "watermark_pct": self.watermark_pct,
                "watermark_count": self.watermark_count,
                "depth": len(self._items),
                "enqueue_count": self._enqueue_count,
                "dequeue_count": self._dequeue_count,
                "reject_count": self._reject_count,
                "watermark_crossings": self._watermark_crossings,
                "above_watermark": self._above_watermark,
            }

    def __iter__(self) -> Iterator[Any]:
        with self._lock:
            return iter(list(self._items))

    def _emit_watermark_event(self, depth: int) -> None:
        try:
            ctx = current_burn_context()
        except Exception:
            return
        recorder = BurnRecorder.for_project(ctx.project_root)
        recorder.record(
            BurnEvent(
                session_id=ctx.session_id,
                project_id=ctx.project_id,
                call_id=f"queue-watermark-{self.name}-{int(time.time() * 1e6)}",
                model="n/a",
                tool_id="queue.watermark",
                input_tokens=depth,
                output_tokens=self.capacity,
                error=f"queue {self.name!r} crossed watermark "
                f"({int(self.watermark_pct * 100)}%): depth={depth}/{self.capacity}",
                extension_ids_active=ctx.extension_ids_active,
            )
        )


class QueueRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queues: dict[str, BoundedQueue] = {}

    def register(self, queue: BoundedQueue) -> BoundedQueue:
        with self._lock:
            if queue.name in self._queues:
                raise ValueError(f"queue {queue.name!r} already registered")
            self._queues[queue.name] = queue
            return queue

    def get(self, name: str) -> BoundedQueue:
        with self._lock:
            if name not in self._queues:
                raise KeyError(f"no queue registered with name {name!r}")
            return self._queues[name]

    def all_stats(self) -> list[dict]:
        with self._lock:
            return [q.stats() for q in self._queues.values()]

    def reset(self) -> None:
        with self._lock:
            self._queues.clear()


_GLOBAL_REGISTRY = QueueRegistry()


def get_registry() -> QueueRegistry:
    return _GLOBAL_REGISTRY
