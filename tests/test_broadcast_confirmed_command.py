from __future__ import annotations

import asyncio

import pytest

from interfaces.research.api.broadcast import EventBroadcaster
from substrate.event_log import prepare_typed_event
from substrate.schemas import Event, InvestigationStartRequestedPayload


def _event() -> Event:
    return prepare_typed_event(
        "inv-confirmed-command",
        InvestigationStartRequestedPayload(question="What is true?"),
        event_id="evt-confirmed-command",
    )


@pytest.mark.asyncio
async def test_confirmed_command_failure_is_retryable_then_suppressed() -> None:
    bus = EventBroadcaster()
    attempts = 0
    accepted: list[str] = []

    async def handler(event: Event) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("fail before durable execution claim")
        accepted.append(event.event_id)

    bus.register_handler("investigation.start_requested", handler)
    with pytest.raises(RuntimeError, match="durable execution claim"):
        await bus.broadcast_confirmed_command_once(_event())
    assert await bus.broadcast_confirmed_command_once(_event()) is True
    assert await bus.broadcast_confirmed_command_once(_event()) is False
    assert attempts == 2
    assert accepted == ["evt-confirmed-command"]


@pytest.mark.asyncio
async def test_confirmed_command_without_handler_is_not_accepted() -> None:
    bus = EventBroadcaster()
    with pytest.raises(RuntimeError, match="no registered acceptance handler"):
        await bus.broadcast_confirmed_command_once(_event())

    accepted: list[str] = []

    async def handler(event: Event) -> None:
        accepted.append(event.event_id)

    bus.register_handler("investigation.start_requested", handler)
    assert await bus.broadcast_confirmed_command_once(_event()) is True
    assert accepted == ["evt-confirmed-command"]


@pytest.mark.asyncio
async def test_concurrent_confirmed_command_replays_join_one_delivery() -> None:
    bus = EventBroadcaster()
    release = asyncio.Event()
    attempts = 0

    async def handler(_event: Event) -> None:
        nonlocal attempts
        attempts += 1
        await release.wait()

    bus.register_handler("investigation.start_requested", handler)
    first = asyncio.create_task(bus.broadcast_confirmed_command_once(_event()))
    await asyncio.sleep(0)
    second = asyncio.create_task(bus.broadcast_confirmed_command_once(_event()))
    release.set()
    assert await asyncio.gather(first, second) == [True, False]
    assert attempts == 1
