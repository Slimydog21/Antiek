"""Deadline and cancellation contracts for BroadcastHub's test drain."""

from __future__ import annotations

import asyncio

import pytest

from interfaces.research.api import EventBroadcaster


@pytest.mark.asyncio
async def test_wait_for_handlers_enforces_deadline_without_cancelling() -> None:
    bus = EventBroadcaster()
    blocker = asyncio.create_task(asyncio.Event().wait(), name="never-drains")
    bus._handler_tasks.add(blocker)

    loop = asyncio.get_running_loop()
    started = loop.time()
    try:
        with pytest.raises(TimeoutError, match="never-drains"):
            await asyncio.wait_for(bus.wait_for_handlers(timeout=0.02), timeout=0.2)
        assert loop.time() - started < 0.2
        assert not blocker.cancelled()
    finally:
        blocker.cancel()
        await asyncio.gather(blocker, return_exceptions=True)
        bus._handler_tasks.discard(blocker)


@pytest.mark.asyncio
async def test_wait_for_handlers_returns_after_current_tasks_drain() -> None:
    bus = EventBroadcaster()
    task = asyncio.create_task(asyncio.sleep(0.01), name="finite-handler")
    bus._handler_tasks.add(task)
    task.add_done_callback(bus._handler_tasks.discard)

    await bus.wait_for_handlers(timeout=0.2)

    assert task.done()
    assert not bus._handler_tasks
