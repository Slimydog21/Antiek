"""A retried POST /investigations with the same investigation_id is a replay.

``InvestigationStartRequest`` tells callers to supply a stable id when
retrying the same question. On the house path (no ``operation_id``) the
endpoint used to re-emit ``investigation.start_requested`` and re-broadcast it
on every POST, so each retry spawned another detached Loop One run. The ACU
start charge is idempotent on ``investigation_id``, so the second paid run was
never metered, and the two runs overwrote each other's coordinator futures:
one completed, the other timed out and logged ``investigation.failed`` after
it, so GET reported a deposited synthesis as ``failed``.

These tests drive the real endpoint with the real Loop One handler wired by
``create_app`` and count what the defect multiplied: start events, broadcasts,
and ``loop_one:<id>`` tasks.
"""

from __future__ import annotations

import asyncio
import os
import sys
from types import SimpleNamespace

import httpx
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from interfaces.research.api import EventBroadcaster, create_app  # noqa: E402
from orchestration.loop_one.coordinator import InvestigationCoordinator  # noqa: E402
from processing.embedding import _reset_default_provider  # noqa: E402
from substrate.dispatch import reset_provider_registry  # noqa: E402
from substrate.event_log import emit_typed, trajectory  # noqa: E402
from substrate.schemas import ActionType, Event, InvestigationCompletedPayload  # noqa: E402

_START = ActionType.INVESTIGATION_START_REQUESTED.value


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "graph.duckdb"))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    monkeypatch.setenv("ANTIEK_RESEARCH_PHASE_LOG_DIR", str(tmp_path / "phase_logs"))
    monkeypatch.setenv("ANTIEK_RESEARCH_DIR", str(tmp_path / "research"))
    monkeypatch.setenv("ANTIEK_KNOWLEDGE_SKILLS_DIR", str(tmp_path / "skills"))
    _reset_default_provider()
    reset_provider_registry()
    yield
    _reset_default_provider()
    reset_provider_registry()


@pytest.fixture
async def harness():
    bus = EventBroadcaster()
    # register_providers=False: no env key can put a real provider behind
    # the Loop One run the first POST legitimately starts.
    app = create_app(broadcaster=bus, cors_origins=[], register_providers=False)
    broadcasts: list[str] = []

    async def _count(event: Event) -> None:
        broadcasts.append(event.investigation_id)

    bus.register_handler(_START, _count)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, broadcasts
    # No provider is registered, so any spawned run can only fail; cancel what
    # is left so no detached task outlives the test's event loop.
    for task in asyncio.all_tasks():
        if task.get_name().startswith("loop_one:"):
            task.cancel()


async def _settle() -> None:
    # Bus handlers run as background tasks; give them a few loop turns.
    for _ in range(5):
        await asyncio.sleep(0)


def _loop_one_tasks(investigation_id: str) -> int:
    name = f"loop_one:{investigation_id}"
    return sum(1 for t in asyncio.all_tasks() if t.get_name() == name)


def _start_rows(investigation_id: str) -> list[dict]:
    return [r for r in trajectory(investigation_id) if r["action_type"] == _START]


_BODY = {
    "question": "PsiQuantum photonic quantum roadmap question.",
    "investigation_id": "inv-retry-stable",
    "max_sub_questions": 4,
}


@pytest.mark.asyncio
async def test_retry_with_same_id_is_one_start_event_and_one_run(harness):
    client, broadcasts = harness
    r1 = await client.post("/investigations", json=_BODY)
    await _settle()
    r2 = await client.post("/investigations", json=_BODY)  # client retry
    await _settle()

    assert r1.status_code == 202, r1.text
    assert r2.status_code == 202, r2.text
    assert r2.json()["start_event_id"] == r1.json()["start_event_id"]
    assert len(_start_rows("inv-retry-stable")) == 1
    assert broadcasts == ["inv-retry-stable"]
    assert _loop_one_tasks("inv-retry-stable") <= 1


@pytest.mark.asyncio
async def test_retry_after_terminal_does_not_start_a_second_run(harness):
    client, broadcasts = harness
    r1 = await client.post("/investigations", json=_BODY)
    await _settle()
    for task in asyncio.all_tasks():
        if task.get_name() == "loop_one:inv-retry-stable":
            task.cancel()
    emit_typed(
        "inv-retry-stable",
        InvestigationCompletedPayload(
            thesis_summary="done", implicit_recommendation="insufficient_evidence",
            constraint_loop_status="single_pass", constraint_loop_iterations=1,
            master_md_path=None, domains_patched=[], total_phases_verified=9,
        ),
        role="orchestrator",
    )

    r2 = await client.post("/investigations", json=_BODY)
    await _settle()

    assert r2.status_code == 202, r2.text
    assert r2.json()["start_event_id"] == r1.json()["start_event_id"]
    assert len(_start_rows("inv-retry-stable")) == 1
    assert broadcasts == ["inv-retry-stable"]
    assert _loop_one_tasks("inv-retry-stable") == 0
    status = (await client.get("/investigations/inv-retry-stable")).json()
    assert status["status"] == "completed"


@pytest.mark.asyncio
async def test_same_id_with_a_different_question_is_a_conflict(harness):
    client, broadcasts = harness
    r1 = await client.post("/investigations", json=_BODY)
    await _settle()
    r2 = await client.post(
        "/investigations",
        json={**_BODY, "question": "A different question under the same id."},
    )
    await _settle()

    assert r1.status_code == 202, r1.text
    assert r2.status_code == 409, r2.text
    assert r2.json()["detail"] == "investigation_id_conflict"
    rows = _start_rows("inv-retry-stable")
    assert len(rows) == 1
    assert rows[0]["payload"]["question"] == _BODY["question"]
    assert broadcasts == ["inv-retry-stable"]


@pytest.mark.asyncio
async def test_fresh_ids_still_start_independent_runs(harness):
    client, broadcasts = harness
    a = await client.post("/investigations", json={"question": "First fresh question?"})
    b = await client.post("/investigations", json={"question": "First fresh question?"})
    await _settle()

    assert a.status_code == b.status_code == 202
    assert a.json()["investigation_id"] != b.json()["investigation_id"]
    assert sorted(broadcasts) == sorted(
        [a.json()["investigation_id"], b.json()["investigation_id"]]
    )


# ---------------------------------------------------------------------------
# Coordinator: a second waiter on an occupied key must not orphan the first.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_second_waiter_on_occupied_key_is_refused_and_first_still_resolves():
    bus = EventBroadcaster()
    coordinator = InvestigationCoordinator(bus, action_types=("decompose.delivered",))
    first = asyncio.create_task(
        coordinator.wait_for("inv-x", "decompose.delivered", timeout=2.0)
    )
    await asyncio.sleep(0)
    second = asyncio.create_task(
        coordinator.wait_for("inv-x", "decompose.delivered", timeout=0.5)
    )
    await asyncio.sleep(0)

    await coordinator._on_event(SimpleNamespace(
        event_id="evt-decompose-1", investigation_id="inv-x",
        action_type="decompose.delivered", payload=SimpleNamespace(),
    ))

    # The waiter that registered first owns the key and gets the delivery.
    resolved = await asyncio.wait_for(first, timeout=1.0)
    assert resolved.event_id == "evt-decompose-1"
    # The second is refused with a typed error, not left to time out.
    from orchestration.loop_one.coordinator import WaiterAlreadyRegistered

    with pytest.raises(WaiterAlreadyRegistered):
        await second
