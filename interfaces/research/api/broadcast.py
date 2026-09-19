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
import contextlib
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

from substrate.event_log import (  # noqa: E402
    current_investigation_authority,
    investigation_authority_context,
)
from substrate.investigation_tenancy import InvestigationAuthority  # noqa: E402
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
            with contextlib.suppress(asyncio.QueueEmpty):
                _ = self.queue.get_nowait()
            self.dropped += 1
            with contextlib.suppress(asyncio.QueueFull):
                self.queue.put_nowait(event)


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

    def __init__(self) -> None:
        self._subscribers: set[_Subscriber] = set()
        self._handlers: dict[str, list[EventHandler]] = {}
        self._handler_tasks: set[asyncio.Task] = set()
        self._event_authorities: dict[str, InvestigationAuthority] = {}
        self._broadcast_once_ids: set[str] = set()
        self._confirmed_command_ids: set[str] = set()
        self._confirmed_command_futures: dict[str, asyncio.Future[None]] = {}
        self._lock = asyncio.Lock()

    def bind_event_authority(
        self, event_id: str, authority: InvestigationAuthority
    ) -> None:
        """Attach non-serialized machine authority to one in-process event."""
        existing = self._event_authorities.get(event_id)
        if existing is not None and existing != authority:
            raise RuntimeError("event authority binding conflict")
        self._event_authorities[event_id] = authority

    def authority_for_event(self, event: Event) -> InvestigationAuthority:
        authority = self._event_authorities.get(event.event_id)
        if authority is None or authority.investigation_id != event.investigation_id:
            raise RuntimeError("event machine authority is unavailable")
        return authority

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
        own broadcast (which spawns more handler tasks)."""
        deadline = asyncio.get_event_loop().time() + timeout
        while self._handler_tasks:
            if asyncio.get_event_loop().time() > deadline:
                raise TimeoutError(
                    f"handler tasks still running after {timeout}s: "
                    f"{[t.get_name() for t in self._handler_tasks]}"
                )
            await asyncio.gather(*self._handler_tasks, return_exceptions=True)

    # ── Broadcast ──────────────────────────────────────────────

    async def broadcast(self, event: Event) -> None:
        """Fan an event out to every WS subscriber whose filter matches,
        and schedule every Python-side handler for ``action_type`` as a
        background task.

        Snapshot subscribers and handlers under the lock so concurrent
        register/subscribe calls don't race the dispatch."""
        action_type = _action_type_str(event.action_type)
        contextual_authority = current_investigation_authority(
            event.investigation_id
        )
        if contextual_authority is not None:
            self.bind_event_authority(event.event_id, contextual_authority)
        async with self._lock:
            sub_snapshot = tuple(self._subscribers)
            handler_snapshot = tuple(self._handlers.get(action_type, ()))
            authority = self._event_authorities.get(event.event_id)

        # WS subscribers — direct (queue.put_nowait is non-blocking).
        await asyncio.gather(*(s.offer(event) for s in sub_snapshot))

        # Python handlers — background tasks so a slow handler doesn't
        # block the broadcast or the POST that triggered it. Tasks are
        # tracked so tests can await them deterministically.
        for h in handler_snapshot:
            task = asyncio.create_task(
                _safe_handler(h, event, authority),
                name=f"handler:{action_type}:{h.__name__ if hasattr(h, '__name__') else 'fn'}",
            )
            self._handler_tasks.add(task)
            task.add_done_callback(self._handler_tasks.discard)

    async def broadcast_once(self, event: Event) -> bool:
        """Fan out one durable command event at most once in this process."""
        async with self._lock:
            if event.event_id in self._broadcast_once_ids:
                return False
            self._broadcast_once_ids.add(event.event_id)
        await self.broadcast(event)
        return True

    async def broadcast_confirmed_command_once(self, event: Event) -> bool:
        """Deliver a durable command once after every handler accepts it.

        Unlike ``broadcast_once``, failure is retryable in the same process.
        Concurrent replays join the first delivery and observe its outcome.
        This is intended for short command-acceptance handlers which durably
        claim their own execution lease before returning.
        """

        loop = asyncio.get_running_loop()
        owner = False
        async with self._lock:
            if event.event_id in self._confirmed_command_ids:
                return False
            future = self._confirmed_command_futures.get(event.event_id)
            if future is None:
                future = loop.create_future()
                self._confirmed_command_futures[event.event_id] = future
                owner = True
            sub_snapshot = tuple(self._subscribers)
            handler_snapshot = tuple(
                self._handlers.get(_action_type_str(event.action_type), ())
            )
            authority = self._event_authorities.get(event.event_id)
        if not owner:
            await asyncio.shield(future)
            return False
        try:
            if not handler_snapshot:
                raise RuntimeError("durable command has no registered acceptance handler")
            await asyncio.gather(*(subscriber.offer(event) for subscriber in sub_snapshot))
            for handler in handler_snapshot:
                if authority is None:
                    await handler(event)
                else:
                    with investigation_authority_context(authority):
                        await handler(event)
        except BaseException as exc:
            async with self._lock:
                self._confirmed_command_futures.pop(event.event_id, None)
                if not future.done():
                    future.set_exception(exc)
                    # The owner propagates the exception directly; consume the
                    # Future exception when there are no concurrent joiners.
                    future.exception()
            raise
        async with self._lock:
            self._confirmed_command_ids.add(event.event_id)
            self._confirmed_command_futures.pop(event.event_id, None)
            if not future.done():
                future.set_result(None)
        return True

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


async def _safe_handler(
    handler: EventHandler,
    event: Event,
    authority: InvestigationAuthority | None,
) -> None:
    """Wrap a handler invocation so a thrown exception is logged but
    never propagates to the broadcast loop or any concurrent handler."""
    try:
        if authority is None:
            await handler(event)
        else:
            with investigation_authority_context(authority):
                await handler(event)
    except Exception:  # pragma: no cover — diagnostic surface
        tb = traceback.format_exc(limit=8)
        print(
            f"broadcast handler failed for action_type "
            f"{_action_type_str(event.action_type)!r}: {tb}",
            file=sys.stderr,
        )
