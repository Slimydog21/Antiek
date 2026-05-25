"""SPR-02 M3 — the remote ResearchRunner, against a FAKE provider only.

No live Daytona, no SDK, no credentials, no network. Gates:

  * ``RemoteResearchRunner`` structurally satisfies the ``ResearchRunner``
    protocol (the SPR-01 contract surface).
  * its ``StepEvent`` is byte-for-byte the same dataclass the host-local
    runner yields — SPR-06/09 cannot tell the runners apart.
  * ``cancel`` provably tears the remote sandbox down (the negative test).
"""

from __future__ import annotations

import os
import tempfile

import pytest

from runtime.remote_exec import RemoteResearchRunner, RemoteStepEvent
from runtime.research_runner import (
    BudgetCap,
    Command,
    CommandKind,
    ResearchPlan,
    ResearchRunner,
    RunState,
    StepEvent,
)
from runtime.research_runner import StepEvent as HostLocalStepEvent
from substrate.contracts import ResearchRunner as ContractResearchRunner
from substrate.contracts import StepEvent as ContractStepEvent
from substrate.event_log import trajectory
from tests.remote_exec_fakes import FailingProvider, FakeProvider


@pytest.fixture
def events_dir(monkeypatch):
    d = tempfile.mkdtemp()
    ev = os.path.join(d, "events")
    os.makedirs(ev, exist_ok=True)
    monkeypatch.setenv("ANTIEK_EVENTS_DIR", ev)
    return ev


def _plan(i: int, *, cap=1.0, max_steps=50) -> ResearchPlan:
    return ResearchPlan(investigation_id=f"inv-{i}", sub_question=f"q{i}?",
                        budget=BudgetCap(cost_usd=cap, max_steps=max_steps))


def test_package_loads_without_daytona_sdk():
    # The optional-SDK idiom (mirrors acquisition/urls/client_browserbase.py):
    # the package imports cleanly with the Daytona SDK absent, and enabling
    # remote-exec without it raises RemoteExecUnavailable loudly — never a
    # silent degradation.
    import importlib

    import runtime.remote_exec as pkg

    importlib.reload(pkg)  # imports clean even when daytona_sdk is not installed

    from runtime.remote_exec import RemoteExecUnavailable
    from runtime.remote_exec.daytona import DaytonaProvider

    # constructing does not import the SDK or touch the network
    prov = DaytonaProvider()
    # probing without the SDK / creds raises loudly
    os.environ.pop("DAYTONA_API_KEY", None)
    with pytest.raises(RemoteExecUnavailable):
        prov.probe()


def test_remote_runner_satisfies_protocol():
    # The runtime_checkable protocol from runtime AND the re-export from the
    # SPR-01 contract package both accept the remote runner — proving the
    # drop-in shape is correct against the canonical import surface.
    r = RemoteResearchRunner(FakeProvider())
    assert isinstance(r, ResearchRunner)
    assert isinstance(r, ContractResearchRunner)
    # Every protocol method the host-local runner exposes is present on the
    # remote runner with the same name — the methodical parity behind the
    # isinstance check above.
    for method in ("start", "stream", "steer", "status", "cost", "cancel"):
        assert callable(getattr(r, method)), f"missing protocol method {method}"


def test_stepevent_shape_conformance_via_spr01_harness():
    # The SPR-01 conformance harness (verify_conformance) takes a Pydantic
    # contract. The runner protocol is a Protocol (checked above via
    # isinstance), but the *StepEvent shape* — the thing SPR-06/09 read — can
    # be put through the harness: a reference Pydantic model of the host-local
    # StepEvent's crossing fields, verified against the StepEvent the remote
    # runner emits. A pass means a consumer expecting the contract can read
    # the remote runner's events identically.

    from pydantic import BaseModel

    from substrate.contracts import verify_conformance

    class StepEventContract(BaseModel):
        investigation_id: str
        seq: int
        kind: str
        text: str
        cost_usd: float
        tokens: int
        state: object | None = None
        data: dict

    # the StepEvent the remote runner yields (the contract re-export) conforms
    result = verify_conformance(StepEvent, StepEventContract)
    assert result.ok, result.diff
    # and it is the SAME dataclass the host-local runner yields
    assert StepEvent is HostLocalStepEvent


def test_stepevent_shape_is_identical_to_host_local():
    # The contract re-exports the very dataclass the host-local runner yields,
    # and the remote runner yields that same type. Identity, not similarity.
    assert ContractStepEvent is StepEvent
    assert HostLocalStepEvent is StepEvent
    # RemoteStepEvent (the provider-seam event) carries every field StepEvent
    # carries that crosses to the consumer (kind/text/cost_usd/tokens/data/seq);
    # the runner maps it 1:1.
    import dataclasses
    se = {f.name for f in dataclasses.fields(StepEvent)}
    rse = {f.name for f in dataclasses.fields(RemoteStepEvent)}
    crossing = {"seq", "kind", "text", "cost_usd", "tokens", "data"}
    assert crossing <= se
    assert crossing <= rse


async def test_start_streams_to_done_with_identical_event_type(events_dir):
    prov = FakeProvider(steps=2)
    r = RemoteResearchRunner(prov, events_dir=events_dir, seal_on_complete=False)
    h = await r.start("inv-0", _plan(0))
    events = [ev async for ev in r.stream(h)]
    # Every streamed event is the exact StepEvent dataclass (not a remote
    # variant) — a consumer cannot tell this came from a sandbox.
    assert events and all(isinstance(ev, StepEvent) for ev in events)
    kinds = [ev.kind for ev in events]
    assert kinds[0] == "status"          # running
    assert "plan" in kinds and "step" in kinds and "note" in kinds and "question" in kinds
    assert kinds[-1] == "done"
    assert events[-1].state == RunState.DONE
    # the leaf wrote only its own per-investigation JSONL (isolation)
    rows = trajectory("inv-0", events_dir=events_dir)
    assert rows


async def test_cancel_tears_down_the_sandbox(events_dir):
    # The scariest leak: a cancelled leaf that leaves a sandbox running. Prove
    # the fake provider recorded the teardown.
    prov = FakeProvider(steps=50, delay_s=0.02)
    r = RemoteResearchRunner(prov, events_dir=events_dir, seal_on_complete=False)
    h = await r.start("inv-0", _plan(0))
    # let it provision + start
    import asyncio
    await asyncio.sleep(0.03)
    await r.cancel(h)
    assert "inv-0" in prov.provisioned
    assert "inv-0" in prov.torn_down, "cancel must tear the sandbox down"
    assert r.status(h).state in (RunState.STOPPED, RunState.STOPPING, RunState.DONE)


async def test_completion_also_tears_down(events_dir):
    prov = FakeProvider(steps=1)
    r = RemoteResearchRunner(prov, events_dir=events_dir, seal_on_complete=False)
    h = await r.start("inv-0", _plan(0))
    _ = [ev async for ev in r.stream(h)]
    assert "inv-0" in prov.torn_down, "a completed leaf must not leak its sandbox"


async def test_failure_is_isolated_and_tears_down(events_dir):
    # A provider runtime error on one leaf transitions it to FAILED and tears
    # its sandbox down — it does not raise out of the runner.
    prov = FailingProvider(fail_after=1, steps=5)
    r = RemoteResearchRunner(prov, events_dir=events_dir, seal_on_complete=False)
    h = await r.start("inv-0", _plan(0))
    events = [ev async for ev in r.stream(h)]
    assert any(ev.kind == "error" for ev in events)
    assert r.status(h).state == RunState.FAILED
    assert "inv-0" in prov.torn_down


async def test_steer_relays_to_provider(events_dir):
    prov = FakeProvider(steps=50, delay_s=0.02)
    r = RemoteResearchRunner(prov, events_dir=events_dir, seal_on_complete=False)
    h = await r.start("inv-0", _plan(0))
    import asyncio
    await asyncio.sleep(0.03)
    await r.steer(h, Command(kind=CommandKind.REDIRECT, payload={"sub_question": "redirected?"}))
    assert r.status(h).sub_question == "redirected?"
    # the redirect signal reached the sandbox
    assert any(c.signal.value == "redirect" for c in prov.steered)
    await r.cancel(h)


async def test_deepen_raises_cap(events_dir):
    prov = FakeProvider(steps=50, delay_s=0.02)
    r = RemoteResearchRunner(prov, events_dir=events_dir, seal_on_complete=False)
    h = await r.start("inv-0", _plan(0, cap=0.5))
    import asyncio
    await asyncio.sleep(0.03)
    before = r.cost(h).cap_usd
    await r.steer(h, Command(kind=CommandKind.DEEPEN,
                             payload={"extra_budget_usd": 0.5, "follow_up": "go deeper?"}))
    assert r.cost(h).cap_usd == pytest.approx(before + 0.5)
    assert "go deeper?" in r.status(h).follow_ups
    await r.cancel(h)


async def test_command_after_finish_is_noop(events_dir):
    prov = FakeProvider(steps=1)
    r = RemoteResearchRunner(prov, events_dir=events_dir, seal_on_complete=False)
    h = await r.start("inv-0", _plan(0))
    _ = [ev async for ev in r.stream(h)]
    # safe no-op, never an error
    await r.steer(h, Command(kind=CommandKind.STOP))
    await r.cancel(h)  # idempotent teardown
    assert prov.torn_down.count("inv-0") == 1
