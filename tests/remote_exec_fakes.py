"""Deterministic fake ``RemoteExecProvider``s for the SPR-02 test suite.

No network, no Daytona SDK, no credentials — every remote-exec test runs
against one of these fakes so the suite is reproducible in CI and the live
Daytona run stays operator-gated. The fakes satisfy the ``RemoteExecProvider``
protocol structurally (no inheritance), mirroring how a real provider would.

Three shapes:

  * ``FakeProvider`` — happy path. Provisions a sandbox, streams a configurable
    number of cost-bearing steps + a note + a question, records every
    provision/teardown/steer so tests can assert on lifecycle.
  * ``FailingProvider`` — raises in ``run`` after a configurable step so the
    failure-isolation arm is exercised deterministically.
  * ``UnavailableProvider`` — its ``probe`` raises ``RemoteExecUnavailable`` so
    the factory's fallback-on-unavailable path is exercised without touching
    the SDK.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from runtime.remote_exec.provider import (
    RemoteCommand,
    RemoteExecRuntimeError,
    RemoteExecUnavailable,
    RemoteSignal,
    RemoteStepEvent,
    Sandbox,
)


class FakeProvider:
    """Happy-path fake. Records lifecycle so tests assert teardown happened."""

    def __init__(
        self,
        *,
        name: str = "fake-daytona",
        steps: int = 3,
        cost_per_step: float = 0.01,
        tokens_per_step: int = 10,
        delay_s: float = 0.0,
        emit_note: bool = True,
        model: str = "fake-research-leaf",
    ):
        self._name = name
        self._steps = steps
        self._cost = cost_per_step
        self._tokens = tokens_per_step
        self._delay = delay_s
        self._emit_note = emit_note
        self._model = model
        self.provisioned: list[str] = []
        self.torn_down: list[str] = []
        self.steered: list[RemoteCommand] = []
        self._stops: dict[str, bool] = {}

    @property
    def name(self) -> str:
        return self._name

    # tests can call this to assert availability without a probe hook
    def probe(self) -> None:
        return None

    async def provision(self, plan) -> Sandbox:
        iid = plan.investigation_id
        self.provisioned.append(iid)
        return Sandbox(sandbox_id=f"sbx-{iid}", investigation_id=iid,
                       meta={"alive": True})

    async def run(self, sandbox: Sandbox, plan) -> AsyncIterator[RemoteStepEvent]:
        iid = sandbox.investigation_id
        seq = 0
        seq += 1
        yield RemoteStepEvent(seq=seq, kind="plan",
                              text=f"plan for: {plan.sub_question}",
                              provider=self._name, model=self._model)
        for i in range(self._steps):
            if self._stops.get(iid):
                break
            if self._delay:
                await asyncio.sleep(self._delay)
            seq += 1
            yield RemoteStepEvent(
                seq=seq, kind="step", text=f"step {i} on '{plan.sub_question}'",
                cost_usd=self._cost, tokens=self._tokens,
                provider=self._name, model=self._model,
                data={"input_tokens": 4, "output_tokens": self._tokens,
                      "latency_ms": 12, "tier": "pro"},
            )
        if self._emit_note and not self._stops.get(iid):
            seq += 1
            yield RemoteStepEvent(seq=seq, kind="note",
                                  text=f"insight from {iid}: {plan.sub_question}",
                                  provider=self._name, model=self._model)
            seq += 1
            yield RemoteStepEvent(seq=seq, kind="question",
                                  text=f"open question from {iid}?",
                                  provider=self._name, model=self._model)

    async def steer(self, sandbox: Sandbox, command: RemoteCommand) -> None:
        self.steered.append(command)
        if command.signal == RemoteSignal.STOP:
            self._stops[sandbox.investigation_id] = True

    async def teardown(self, sandbox: Sandbox) -> None:
        # Idempotent: record once even if called twice.
        if sandbox.investigation_id not in self.torn_down:
            self.torn_down.append(sandbox.investigation_id)
        sandbox.meta["alive"] = False


class FailingProvider(FakeProvider):
    """Raises a ``RemoteExecRuntimeError`` mid-run after ``fail_after`` steps."""

    def __init__(self, *, fail_after: int = 1, **kwargs):
        super().__init__(**kwargs)
        self._fail_after = fail_after

    async def run(self, sandbox: Sandbox, plan) -> AsyncIterator[RemoteStepEvent]:
        seq = 0
        for i in range(self._steps):
            if i == self._fail_after:
                raise RemoteExecRuntimeError(f"injected remote failure at step {i}")
            seq += 1
            yield RemoteStepEvent(seq=seq, kind="step", text=f"step {i}",
                                  cost_usd=self._cost, tokens=self._tokens,
                                  provider=self._name, model=self._model,
                                  data={"tier": "pro"})


class UnavailableProvider:
    """``probe`` raises ``RemoteExecUnavailable`` — drives the factory's
    fallback-on-unavailable path with no SDK and no network."""

    name = "unavailable"

    def probe(self) -> None:
        raise RemoteExecUnavailable("fake: SDK/credentials missing")

    async def provision(self, plan) -> Sandbox:  # pragma: no cover — never reached
        raise RemoteExecUnavailable("fake")

    async def run(self, sandbox, plan):  # pragma: no cover — never reached
        raise RemoteExecUnavailable("fake")
        yield  # marks async generator

    async def steer(self, sandbox, command) -> None:  # pragma: no cover
        ...

    async def teardown(self, sandbox) -> None:  # pragma: no cover
        ...
