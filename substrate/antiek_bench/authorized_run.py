"""Authorized run orchestrator — the guarded-dispatch keystone (ask #11).

Closes the recursive-benchmark execution loop. The pure runner
(:func:`run_and_score`) and the pure propose path (``/runs/propose``) hardcode
``live_dispatch_authorized=False`` / ``charge_executed=False`` on every result —
*because* the pure layer never dispatches. THIS module is "the authorized runner,
behind the budget gate" that the runner/recorder/gate docstrings all name as the
future module: it sequences **gate -> run -> record** so a paid bench dispatch
only ever executes after operator ceiling-consent + a budget fit check, and is
then recorded with its authority state reconciled to reality.

**Why this is its own module, and why it imports NONE of the siblings.** The
runner, gate, and recorder are each pure substrates shipped in separate PRs off a
frozen main. An orchestrator that hard-imported all three would stack three
off-main PRs and could not be bar-clean independently. Instead the three
collaborators are *injectable protocols*; the route layer that has all four
modules on hand wires the real ``run_and_score`` / ``authorize_execution`` /
``record_verdict`` behind these protocols. The orchestrator owns the ONE thing
that is genuinely hard to vary and lives nowhere else: the **guarded-dispatch
discipline** and the **dual-claim authority reconciliation**.

**The load-bearing invariants (each is a test):**

1. **A denial has zero side-effects.** If the gate does not authorize, the runner
   is never called and the recorder is never called. There is no "tentative" run,
   no phantom record, no partial charge. The pure propose path and the authorized
   path share this guarantee from opposite ends: propose never dispatches;
   authorize, when denied, also never dispatches.
2. **Authorize -> run exactly once -> record exactly once, in that order.** The
   verdict is recorded *iff* the run executed. A recorded run without an
   execution, or an execution without a record, is impossible through this module.
3. **Dual-claim authority reconciliation — no engine grades its own homework.**
   The runner hardcodes ``charge_executed=False`` / ``live_dispatch_authorized=
   False`` (its pure-layer claim, carried verbatim on ``RunOutcome``). The
   orchestrator NEVER overwrites that claim; it adds a *second, independently
   sourced* reconciliation alongside it:
   - ``reconciled_dispatch_authorized`` comes from the GATE (``decision.authorized``)
     — authorization is a property of consent, not of the runner's self-report.
   - ``reconciled_charge_executed`` comes from the SPEND EVIDENCE
     (``reported_cost_usd > 0``) — an actual charge is a property of what the
     provider reported, not of "we went through the paid path." A provider that
     charges without reporting cost is opaque to this layer; we do not fabricate
     knowledge of it (honest None -> False, never invented True).
   Both claims survive to the audit trail so a reviewer can see "runner said no
   charge; orchestrator reconciled a charge because the provider reported $0.003."
   Silently flipping the runner's flag would destroy that provenance.
4. **A runner failure is never recorded as a verdict.** If ``runner.run`` raises,
   the exception propagates and no record is written — there is no verdict to
   record. The orchestrator is pure; it does not swallow, retry, or invent a
   recovery verdict. (Provider-failure recovery is a separate authority concern,
   the Midnight-Oil layer's job.)
5. **A recorder failure propagates honestly.** If ``recorder.record`` raises
   (e.g. a tamper-evident hash-chain break), it propagates — the run executed but
   was not recorded, and we never silently recover a corrupt ledger. The caller
   learns the truth.
6. **No clock, no I/O, no dispatch of its own.** ``is_expired`` is caller-resolved
   before the gate; the provider call lives behind the injected runner; the ledger
   write lives behind the injected recorder. This module only sequences decisions.

**Opaqueness contract for the verdict.** Different scorers (exact / rubric /
human) produce differently-shaped verdicts. The orchestrator does NOT introspect
the verdict — it forwards it to the recorder verbatim as ``object``. Surfacing
``score`` / ``success`` / ``reported_cost_usd`` on ``RunOutcome`` is the
orchestrator's own auditable copy for reconciliation; the recorder receives the
authoritative verdict object so persistence is lossless.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


# --------------------------------------------------------------------------- #
# Injected collaborators (protocols — import-free of sibling modules).
# --------------------------------------------------------------------------- #
class AuthorizationGate(Protocol):
    """Decides whether a proposed paid dispatch may execute.

    The concrete adapter wraps ``authorize_execution`` (the budget execution
    gate). It interprets the opaque ``authorization_context`` on the proposed run
    (the ceiling / consent / headroom bundle) and returns a pure decision. The
    orchestrator never shapes those inputs — that is the gate adapter's job.
    """

    def authorize(self, proposed: ProposedRun) -> GateDecision:
        ...


class TaskRunner(Protocol):
    """Invokes the candidate model and returns a scored outcome.

    The concrete adapter wraps ``run_and_score`` (the bench runner) behind the
    injected ``ModelCaller``. ``run`` is the ONLY place a live provider call
    happens. The orchestrator calls it at most once per execution.
    """

    def run(self, proposed: ProposedRun) -> RunOutcome:
        ...


class VerdictRecorder(Protocol):
    """Persists one executed run as a tamper-evident dual-output record.

    The concrete adapter wraps ``record_verdict`` (+ ``append_to_ledger``). It
    receives the authoritative ``RunOutcome.verdict`` so persistence is lossless.
    Returns a receipt proving the record landed (hash + persisted flag).
    """

    def record(self, run: RunOutcome, *, week_id: str) -> RecordReceipt:
        ...


# --------------------------------------------------------------------------- #
# Boundary types the orchestrator owns (no sibling imports -> no type drift).
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ProposedRun:
    """Everything needed to attempt one authorized bench run.

    ``authorization_context`` and ``run_inputs`` are opaque bundles the gate and
    runner adapters interpret respectively. Keeping them opaque means this module
    never couples to how ceilings/consents or task prompts are shaped — that is
    the adapters' concern, wired at the route layer.
    """

    task_id: str
    model_id: str
    week_id: str
    authorization_context: object  # ceiling / consent / headroom bundle (gate-interpreted)
    run_inputs: object  # task prompt / caller config bundle (runner-interpreted)


@dataclass(frozen=True)
class GateDecision:
    """The gate's verdict on one proposed execution."""

    authorized: bool
    reason: str
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class RunOutcome:
    """One executed run: the authoritative verdict + the orchestrator's auditable copy.

    The ``runner_claimed_*`` fields carry the pure runner's self-report VERBATIM
    (always False in the pure layer). They are never mutated — the orchestrator
    adds reconciled fields alongside (dual-claim), never overwrites these.
    ``verdict`` is the authoritative scorer output, forwarded to the recorder
    losslessly; the orchestrator does not introspect it.
    """

    verdict: object  # authoritative scorer output; forwarded to the recorder verbatim
    candidate_model_id: str
    score: float | None  # surfaced for the receipt/audit (None = pending human score)
    success: bool | None  # surfaced for the usage-learn signal (None = pending)
    reported_cost_usd: float | None  # provider-reported spend (None = not reported)
    runner_claimed_charge_executed: bool  # pure runner's claim — always False
    runner_claimed_authorized: bool  # pure runner's claim — always False


@dataclass(frozen=True)
class RecordReceipt:
    """Proof that one run was recorded."""

    record_hash: str | None  # None if recorded in-memory only (no ledger chain)
    week_id: str
    persisted: bool


@dataclass(frozen=True)
class DeniedRun:
    """The gate denied execution. Zero side-effects: no run, no record, no charge."""

    decision: GateDecision


@dataclass(frozen=True)
class ExecutedRun:
    """The gate authorized, the runner ran once, the recorder recorded once.

    ``reconciled_*`` fields are the orchestrator's INDEPENDENTLY-SOURCED
    authority state, sitting alongside (never overwriting) the runner's own claim
    on ``run``. See the module docstring's dual-claim invariant #3.
    """

    decision: GateDecision  # authorized=True
    run: RunOutcome  # the runner's pure outcome (its own claims intact)
    receipt: RecordReceipt  # the recorded result
    reconciled_dispatch_authorized: bool  # sourced from the GATE (decision.authorized)
    reconciled_charge_executed: bool  # sourced from SPEND EVIDENCE (reported_cost > 0)


AuthorizedRunResult = DeniedRun | ExecutedRun


def _reconcile_charge(reported_cost_usd: float | None) -> bool:
    """Charge executed iff a positive provider-reported cost exists.

    None (provider did not report) -> False (honest: we cannot prove a charge).
    0.0 -> False (a free run does not charge). This is spend EVIDENCE, never an
    assumption that "the paid path ran, therefore it charged."
    """
    return reported_cost_usd is not None and reported_cost_usd > 0.0


def execute_authorized_run(
    proposed: ProposedRun,
    *,
    gate: AuthorizationGate,
    runner: TaskRunner,
    recorder: VerdictRecorder,
) -> AuthorizedRunResult:
    """Attempt one authorized bench run: gate -> run -> record.

    Returns :class:`DeniedRun` (zero side-effects) when the gate does not
    authorize, or :class:`ExecutedRun` (run once, recorded once, authority
    reconciled from independent sources) when it does.

    Raises propagate: a runner error means no verdict -> no record; a recorder
    error means the run executed unrecorded. The orchestrator never swallows,
    retries, or invents a recovery verdict (it is pure).
    """
    decision = gate.authorize(proposed)

    if not decision.authorized:
        # Invariant #1: a denial touches neither runner nor recorder.
        return DeniedRun(decision=decision)

    # Invariant #2: run exactly once, then record exactly once, in that order.
    run = runner.run(proposed)
    receipt = recorder.record(run, week_id=proposed.week_id)

    # Invariant #3: dual-claim reconciliation from INDEPENDENT sources. The
    # runner's own claims on ``run`` are left intact; we add reconciled fields.
    return ExecutedRun(
        decision=decision,
        run=run,
        receipt=receipt,
        reconciled_dispatch_authorized=True,  # the gate authorized this dispatch
        reconciled_charge_executed=_reconcile_charge(run.reported_cost_usd),
    )


__all__ = [
    "AuthorizationGate",
    "TaskRunner",
    "VerdictRecorder",
    "ProposedRun",
    "GateDecision",
    "RunOutcome",
    "RecordReceipt",
    "DeniedRun",
    "ExecutedRun",
    "AuthorizedRunResult",
    "execute_authorized_run",
]
