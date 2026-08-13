"""In-process pub/sub for the live event feed.

The FastAPI app holds one ``EventBroadcaster`` per process. When a typed
event flows through the API (POST /events/typed), the handler validates,
calls ``emit_typed``, and then broadcasts to every connected WebSocket.

What this DOES cover:
- Events emitted via the API surface land in real time on every
  subscribed WebSocket.

What this DOES NOT cover (yet):
- Events emitted by background processes (cron, dispatch from other
  Python processes, CLI tools) write to the same JSONL trajectory but
  do NOT broadcast through this in-process bus. Clients see those
  events on the next ``GET /trajectory`` fetch or page reload.

Adding a filesystem watcher that tails the JSONL and broadcasts new
lines is a Sprint-2 concern. For Sprint 1, foreground/API-emitted
events are sufficient to validate the reading-UI roundtrip end-to-end.
"""

from __future__ import annotations

import asyncio
import os
import sys
import traceback
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from fastapi import WebSocket

# Direct import — the API surface depends on substrate, never the other way.
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from substrate.schemas import Event  # noqa: E402

# A Python-side handler. Returns an awaitable so handlers can fan out
# work (dispatch calls, DB writes) without blocking the broadcast loop.
EventHandler = Callable[[Event], Awaitable[None]]


def _action_type_str(action_type: Any) -> str:
    """Coerce the envelope's ``action_type`` to its string value. Pydantic
    yields either a string or an ActionType enum depending on how the
    Event was constructed; the handler dispatch key must be the string."""
    return action_type.value if hasattr(action_type, "value") else str(action_type)


class _Subscriber:
    """One subscribed WebSocket. The queue is bounded so a slow client
    can't accumulate unbounded memory — when full, we drop the oldest
    frame and increment ``dropped`` for the client to see in a future
    diagnostic endpoint."""

    __slots__ = ("ws", "investigation_id", "queue", "dropped")

    def __init__(
        self,
        ws: WebSocket,
        *,
        investigation_id: str | None,
        max_queue: int = 256,
    ):
        self.ws = ws
        self.investigation_id = investigation_id
        self.queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=max_queue)
        self.dropped: int = 0

    def matches(self, event: Event) -> bool:
        """A None filter matches every event; a set filter matches only
        events whose investigation_id equals the filter."""
        if self.investigation_id is None:
            return True
        return event.investigation_id == self.investigation_id

    async def offer(self, event: Event) -> None:
        if not self.matches(event):
            return
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            # Drop oldest, enqueue newest. Keeps the live tail current
            # even when the client falls behind.
            try:
                _ = self.queue.get_nowait()
            except asyncio.QueueEmpty:  # pragma: no cover — race
                pass
            self.dropped += 1
            try:
                self.queue.put_nowait(event)
            except asyncio.QueueFull:  # pragma: no cover — re-race
                pass


class EventBroadcaster:
    """Process-singleton pub/sub for typed events.

    Two flavors of subscriber:

    1. **WebSocket subscribers** (``_Subscriber``) get events fanned out
       to a bounded async queue; they're consumed by the WS handler in
       ``app.py`` and serialized to the client.
    2. **Python-side handlers** (``EventHandler``) registered per
       ``action_type``. Used by ``wrestling.py`` (and future role
       modules) to react to events server-side — build a context pack,
       dispatch an LLM call, emit downstream events.

    Both run outside the broadcast lock. Slow WS subscribers drop
    frames; long-running handlers run as background tasks so they don't
    block the broadcast loop or hold up the API POST that triggered the
    event."""

    # Owner-model dispatch registry (set by app.py on startup; consumed by
    # research_owner_dispatch). Carries the FastAPI app needed to revalidate
    # credential authority for owner-bound BYOT launches.
    _owner_model_app: object | None = None

    def __init__(self) -> None:
        self._subscribers: set[_Subscriber] = set()
        self._handlers: dict[str, list[EventHandler]] = {}
        self._handler_tasks: set[asyncio.Task] = set()
        self._lock = asyncio.Lock()

    # ── WS subscribers ──────────────────────────────────────────

    async def subscribe(
        self,
        ws: WebSocket,
        *,
        investigation_id: str | None = None,
    ) -> _Subscriber:
        sub = _Subscriber(ws, investigation_id=investigation_id)
        async with self._lock:
            self._subscribers.add(sub)
        return sub

    async def unsubscribe(self, sub: _Subscriber) -> None:
        async with self._lock:
            self._subscribers.discard(sub)

    # ── Python-side handlers ───────────────────────────────────

    def register_handler(self, action_type: str, handler: EventHandler) -> None:
        """Register a Python-side async handler for an action_type. May
        be called many times; all handlers for an action_type fire in
        registration order (each in its own asyncio task)."""
        self._handlers.setdefault(action_type, []).append(handler)

    def unregister_all_handlers(self) -> None:
        """Drop every registered handler. Used by tests for isolation."""
        self._handlers.clear()

    async def wait_for_handlers(self, timeout: float = 30.0) -> None:
        """Test helper: await every in-flight handler task. Useful when a
        test posts an event that triggers a handler and needs to verify
        the handler's downstream emit landed before asserting.

        Drains the task set repeatedly because a handler can spawn its
        own broadcast (which spawns more handler tasks). A timeout reports
        unfinished tasks without cancelling production-like handler work."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while self._handler_tasks:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError(
                    f"handler tasks still running after {timeout}s: "
                    f"{[t.get_name() for t in self._handler_tasks]}"
                )
            snapshot = tuple(self._handler_tasks)
            done, pending = await asyncio.wait(snapshot, timeout=remaining)
            if done:
                # Retrieve exceptions just as the former gather(...,
                # return_exceptions=True) did, without propagating them here.
                await asyncio.gather(*done, return_exceptions=True)
            if pending:
                raise TimeoutError(
                    f"handler tasks still running after {timeout}s: "
                    f"{[t.get_name() for t in pending]}"
                )

    # ── Broadcast ──────────────────────────────────────────────

    async def broadcast(self, event: Event) -> None:
        """Fan an event out to every WS subscriber whose filter matches,
        and schedule every Python-side handler for ``action_type`` as a
        background task.

        Snapshot subscribers and handlers under the lock so concurrent
        register/subscribe calls don't race the dispatch."""
        action_type = _action_type_str(event.action_type)
        async with self._lock:
            sub_snapshot = tuple(self._subscribers)
            handler_snapshot = tuple(self._handlers.get(action_type, ()))

        # WS subscribers — direct (queue.put_nowait is non-blocking).
        await asyncio.gather(*(s.offer(event) for s in sub_snapshot))

        # Python handlers — background tasks so a slow handler doesn't
        # block the broadcast or the POST that triggered it. Tasks are
        # tracked so tests can await them deterministically.
        for h in handler_snapshot:
            task = asyncio.create_task(
                _safe_handler(h, event),
                name=f"handler:{action_type}:{h.__name__ if hasattr(h, '__name__') else 'fn'}",
            )
            self._handler_tasks.add(task)
            task.add_done_callback(self._handler_tasks.discard)

    async def stream(self, sub: _Subscriber) -> AsyncIterator[Event]:
        """Yield events from this subscriber's queue until cancelled."""
        while True:
            event = await sub.queue.get()
            yield event

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    @property
    def handler_count(self) -> int:
        return sum(len(hs) for hs in self._handlers.values())


async def _safe_handler(handler: EventHandler, event: Event) -> None:
    """Wrap a handler invocation so a thrown exception is logged but
    never propagates to the broadcast loop or any concurrent handler."""
    try:
        await handler(event)
    except Exception:  # pragma: no cover — diagnostic surface
        tb = traceback.format_exc(limit=8)
        print(
            f"broadcast handler failed for action_type "
            f"{_action_type_str(event.action_type)!r}: {tb}",
            file=sys.stderr,
        )
