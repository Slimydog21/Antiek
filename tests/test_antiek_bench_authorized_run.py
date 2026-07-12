"""Tests for the authorized-run orchestrator (ask #11).

Each test pins one of the load-bearing invariants documented on the module.
The gate/runner/recorder are fakes; the orchestrator is exercised purely.
"""

from __future__ import annotations

import pytest

from substrate.antiek_bench.authorized_run import (
    DeniedRun,
    ExecutedRun,
    GateDecision,
    ProposedRun,
    RecordReceipt,
    RunOutcome,
    execute_authorized_run,
)


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
class FakeGate:
    """Authorize/deny on demand; count authorize() calls."""

    def __init__(self, authorized: bool, reason: str = "", notes: tuple[str, ...] = ()):
        self._decision = GateDecision(authorized=authorized, reason=reason, notes=notes)
        self.authorize_calls = 0

    def authorize(self, proposed: ProposedRun) -> GateDecision:
        self.authorize_calls += 1
        return self._decision


class _RecorderError(Exception):
    pass


class FakeRunner:
    """Return a canned outcome; count run() calls; optionally raise."""

    def __init__(self, outcome: RunOutcome, *, raises: bool = False):
        self._outcome = outcome
        self._raises = raises
        self.run_calls = 0
        self.seen_proposals: list[ProposedRun] = []

    def run(self, proposed: ProposedRun) -> RunOutcome:
        self.run_calls += 1
        self.seen_proposals.append(proposed)
        if self._raises:
            raise RuntimeError("provider dispatch failed")
        return self._outcome


class FakeRecorder:
    """Return a canned receipt; count record() calls; optionally raise."""

    def __init__(self, receipt: RecordReceipt, *, raises: bool = False):
        self._receipt = receipt
        self._raises = raises
        self.record_calls = 0
        self.seen_runs: list[RunOutcome] = []
        self.seen_week_ids: list[str] = []

    def record(self, run: RunOutcome, *, week_id: str) -> RecordReceipt:
        self.record_calls += 1
        self.seen_runs.append(run)
        self.seen_week_ids.append(week_id)
        if self._raises:
            raise _RecorderError("ledger corruption")
        return self._receipt


def _proposed() -> ProposedRun:
    return ProposedRun(
        task_id="task-exact-01",
        model_id="cand-paid-model",
        week_id="2026-W29",
        authorization_context={"ceiling": 0.01},  # opaque to the orchestrator
        run_inputs={"prompt": "what is 2+2"},
    )


def _outcome(*, cost: float | None = 0.003) -> RunOutcome:
    return RunOutcome(
        verdict={"task_id": "task-exact-01", "score": 1.0},  # opaque payload
        candidate_model_id="cand-paid-model",
        score=1.0,
        success=True,
        reported_cost_usd=cost,
        runner_claimed_charge_executed=False,  # pure runner always claims False
        runner_claimed_authorized=False,
    )


def _receipt() -> RecordReceipt:
    return RecordReceipt(record_hash="abc123", week_id="2026-W29", persisted=True)


# --------------------------------------------------------------------------- #
# Invariant #1 — a denial has zero side-effects.
# --------------------------------------------------------------------------- #
def test_denial_never_runs_and_never_records():
    gate = FakeGate(authorized=False, reason="no operator consent")
    runner = FakeRunner(_outcome())
    recorder = FakeRecorder(_receipt())

    result = execute_authorized_run(_proposed(), gate=gate, runner=runner, recorder=recorder)

    assert isinstance(result, DeniedRun)
    assert result.decision.authorized is False
    assert result.decision.reason == "no operator consent"
    assert gate.authorize_calls == 1
    assert runner.run_calls == 0  # zero side-effects
    assert recorder.record_calls == 0


def test_denial_preserves_gate_notes():
    gate = FakeGate(
        authorized=False,
        reason="pricing unknown",
        notes=("spend unbounded", "no ceiling named"),
    )
    result = execute_authorized_run(
        _proposed(), gate=gate, runner=FakeRunner(_outcome()), recorder=FakeRecorder(_receipt())
    )
    assert isinstance(result, DeniedRun)
    assert result.decision.notes == ("spend unbounded", "no ceiling named")


# --------------------------------------------------------------------------- #
# Invariant #2 — authorize -> run once -> record once, in order.
# --------------------------------------------------------------------------- #
def test_authorized_runs_once_then_records_once():
    gate = FakeGate(authorized=True, reason="ceiling approved")
    runner = FakeRunner(_outcome())
    recorder = FakeRecorder(_receipt())

    result = execute_authorized_run(_proposed(), gate=gate, runner=runner, recorder=recorder)

    assert isinstance(result, ExecutedRun)
    assert gate.authorize_calls == 1
    assert runner.run_calls == 1
    assert recorder.record_calls == 1
    # the recorder saw the runner's outcome and the right week_id
    # the recorder received the run outcome the runner produced
    assert len(recorder.seen_runs) == 1
    assert recorder.seen_week_ids == ["2026-W29"]


def test_authorized_passes_proposal_to_runner_verbatim():
    proposed = _proposed()
    runner = FakeRunner(_outcome())
    execute_authorized_run(
        proposed, gate=FakeGate(True), runner=runner, recorder=FakeRecorder(_receipt())
    )
    assert runner.seen_proposals[0] is proposed  # same object, opaque bundle intact


# --------------------------------------------------------------------------- #
# Invariant #3 — dual-claim authority reconciliation from independent sources.
# --------------------------------------------------------------------------- #
def test_reconciled_dispatch_authorized_true_when_gate_authorizes():
    result = execute_authorized_run(
        _proposed(),
        gate=FakeGate(True),
        runner=FakeRunner(_outcome()),
        recorder=FakeRecorder(_receipt()),
    )
    assert isinstance(result, ExecutedRun)
    assert result.reconciled_dispatch_authorized is True


def test_reconciled_charge_from_positive_reported_cost():
    result = execute_authorized_run(
        _proposed(),
        gate=FakeGate(True),
        runner=FakeRunner(_outcome(cost=0.003)),
        recorder=FakeRecorder(_receipt()),
    )
    assert isinstance(result, ExecutedRun)
    assert result.reconciled_charge_executed is True


def test_reconciled_charge_false_when_cost_unreported():
    # provider did not report cost -> honest False (never fabricated True)
    result = execute_authorized_run(
        _proposed(),
        gate=FakeGate(True),
        runner=FakeRunner(_outcome(cost=None)),
        recorder=FakeRecorder(_receipt()),
    )
    assert isinstance(result, ExecutedRun)
    assert result.reconciled_charge_executed is False


def test_reconciled_charge_false_when_cost_zero():
    # a free run does not charge
    result = execute_authorized_run(
        _proposed(),
        gate=FakeGate(True),
        runner=FakeRunner(_outcome(cost=0.0)),
        recorder=FakeRecorder(_receipt()),
    )
    assert isinstance(result, ExecutedRun)
    assert result.reconciled_charge_executed is False


def test_runner_pure_claims_left_intact_on_executed_run():
    # the orchestrator never overwrites the runner's own (False) claims
    result = execute_authorized_run(
        _proposed(),
        gate=FakeGate(True),
        runner=FakeRunner(_outcome(cost=0.003)),
        recorder=FakeRecorder(_receipt()),
    )
    assert isinstance(result, ExecutedRun)
    assert result.run.runner_claimed_charge_executed is False
    assert result.run.runner_claimed_authorized is False
    # yet the reconciled fields reflect reality — both survive to the audit trail
    assert result.reconciled_charge_executed is True
    assert result.reconciled_dispatch_authorized is True


def test_receipt_carried_on_executed_run():
    receipt = _receipt()
    result = execute_authorized_run(
        _proposed(),
        gate=FakeGate(True),
        runner=FakeRunner(_outcome()),
        recorder=FakeRecorder(receipt),
    )
    assert isinstance(result, ExecutedRun)
    assert result.receipt is receipt


# --------------------------------------------------------------------------- #
# Invariant #4 — a runner failure is never recorded as a verdict.
# --------------------------------------------------------------------------- #
def test_runner_exception_propagates_and_nothing_recorded():
    gate = FakeGate(True)
    runner = FakeRunner(_outcome(), raises=True)
    recorder = FakeRecorder(_receipt())

    with pytest.raises(RuntimeError, match="provider dispatch failed"):
        execute_authorized_run(_proposed(), gate=gate, runner=runner, recorder=recorder)

    assert runner.run_calls == 1  # the dispatch was attempted
    assert recorder.record_calls == 0  # no phantom record for a failed run


# --------------------------------------------------------------------------- #
# Invariant #5 — a recorder failure propagates honestly (no silent recovery).
# --------------------------------------------------------------------------- #
def test_recorder_exception_propagates():
    gate = FakeGate(True)
    runner = FakeRunner(_outcome())
    recorder = FakeRecorder(_receipt(), raises=True)

    with pytest.raises(_RecorderError, match="ledger corruption"):
        execute_authorized_run(_proposed(), gate=gate, runner=runner, recorder=recorder)

    assert runner.run_calls == 1  # the run executed ...
    assert recorder.record_calls == 1  # ... but the record raised, and propagated


# --------------------------------------------------------------------------- #
# Purity + value semantics.
# --------------------------------------------------------------------------- #
def test_purity_no_io_imports():
    import inspect

    from substrate.antiek_bench import authorized_run as mod

    src = inspect.getsource(mod)
    # the orchestrator owns no clock, no filesystem, no network, no dispatch
    for forbidden in ("import os", "import time", "import asyncio", "import requests", "open(", "datetime."):
        assert forbidden not in src, f"purity breach: {forbidden!r} in orchestrator source"


def test_boundary_types_are_frozen():
    import dataclasses

    from substrate.antiek_bench.authorized_run import (
        DeniedRun,
        ExecutedRun,
        GateDecision,
        ProposedRun,
        RecordReceipt,
        RunOutcome,
    )

    for cls in (ProposedRun, GateDecision, RunOutcome, RecordReceipt, DeniedRun, ExecutedRun):
        assert dataclasses.is_dataclass(cls)

    # Constructed frozen instances reject attribute assignment.
    p = ProposedRun("t", "m", "w", None, None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.task_id = "x"  # type: ignore[misc]
    d = DeniedRun(GateDecision(False, "r"))
    with pytest.raises(dataclasses.FrozenInstanceError):
        d.decision = GateDecision(True, "r")  # type: ignore[misc]
