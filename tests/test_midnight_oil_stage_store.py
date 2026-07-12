from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import pytest

from substrate.midnight_oil.budget_ledger import (
    BudgetLedger,
    CallHold,
    CallNotDispatched,
    ReservationNotFound,
)
from substrate.midnight_oil.durable_job import DurableJobStore
from substrate.midnight_oil.job import create_job
from substrate.midnight_oil.operation_queue import DurableOperationQueue
from substrate.midnight_oil.stages import (
    StageEffectReceipt,
    StageKind,
    StagePlan,
    StagePlanItem,
    StageRejectionReceipt,
    effect_receipt_id,
    provider_effect_key,
    stage_key,
    stage_plan_hash,
    stage_rejection_receipt_id,
)

OPERATION = "operation-stage-store"
WORKER = "stage-worker"
ROUTE_HASH = "a" * 64
INPUT_HASH = "b" * 64
CEILING = 100


def _item(
    ordinal: int,
    kind: StageKind,
    *,
    predecessors: tuple[str, ...] = (),
    shard: int | None = None,
    operation_id: str = OPERATION,
) -> StagePlanItem:
    key = stage_key(operation_id=operation_id, goal_index=0, kind=kind, shard_index=shard)
    return StagePlanItem(
        ordinal=ordinal,
        kind=kind,
        goal_index=0,
        shard_index=shard,
        shard_count=1 if kind == "gather" else None,
        predecessor_stage_keys=predecessors,
        router_role="gatherer" if kind == "gather" else kind,
        route_plan_sha256=ROUTE_HASH,
        projected_max_cents=10,
        stage_key=key,
        provider_effect_key=provider_effect_key(key),
    )


def _plan(job_id: str, operation_id: str = OPERATION) -> StagePlan:
    planner = _item(0, "planner", operation_id=operation_id)
    gather = _item(
        1,
        "gather",
        predecessors=(planner.stage_key,),
        shard=0,
        operation_id=operation_id,
    )
    verifier = _item(
        2, "verifier", predecessors=(gather.stage_key,), operation_id=operation_id
    )
    synth = _item(
        3, "synthesizer", predecessors=(verifier.stage_key,), operation_id=operation_id
    )
    stages = (planner, gather, verifier, synth)
    return StagePlan(
        operation_id=operation_id,
        job_id=job_id,
        approved_ceiling_cents=CEILING,
        stages=stages,
        plan_hash=stage_plan_hash(
            operation_id=operation_id,
            job_id=job_id,
            approved_ceiling_cents=CEILING,
            stages=stages,
        ),
    )


def test_prepare_stage_plan_replaces_only_pristine_prior_operation(tmp_path: Path) -> None:
    store = DurableJobStore(tmp_path / "jobs.sqlite3")
    job = create_job(["Investigate"], 15, store=store, job_id="job-prepare")
    first = _plan(job.job_id, "operation-first")
    second = _plan(job.job_id, "operation-second")

    assert store.prepare_stage_plan(first) == store.prepare_stage_plan(first)
    prepared = store.prepare_stage_plan(second)
    assert store.get_stage_plan(job.job_id) == second
    assert all(row.state == "planned" and row.revision == 0 for row in prepared)


def test_prepare_stage_plan_refuses_non_pristine_replacement(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    first = runtime.plan.stages[0]
    runtime.store.register_stage_intent(
        job_id=runtime.plan.job_id,
        stage_key=first.stage_key,
        input_evidence_sha256=INPUT_HASH,
        operation_queue=runtime.queue,
        worker_id=WORKER,
        lease_generation=runtime.lease_generation,
        now_ms=20,
    )
    with pytest.raises(ValueError, match="non-pristine"):
        runtime.store.prepare_stage_plan(
            _plan(runtime.plan.job_id, "operation-replacement")
        )


@dataclass
class Runtime:
    store: DurableJobStore
    plan: StagePlan
    ledger: BudgetLedger
    queue: DurableOperationQueue
    lease_generation: int

    def kwargs(self, now_ms: int = 20) -> dict[str, object]:
        return {
            "budget_ledger": self.ledger,
            "operation_queue": self.queue,
            "worker_id": WORKER,
            "lease_generation": self.lease_generation,
            "now_ms": now_ms,
        }


def _runtime(tmp_path: Path) -> Runtime:
    store = DurableJobStore(tmp_path / "jobs.sqlite3")
    job = create_job(["Investigate"], 15, store=store, job_id="job-stage-store")
    plan = _plan(job.job_id)
    store.initialize_stage_plan(plan)
    ledger = BudgetLedger(store.budget_db_path())
    ledger.ensure_schema()
    ledger.reserve(
        job.job_id,
        CEILING,
        {"planner": 25, "gatherer": 25, "verifier": 25, "synthesizer": 25},
    )
    queue = DurableOperationQueue(tmp_path / "queue.sqlite3")
    queue.enqueue_once(
        operation_id=OPERATION,
        owner_user_id="owner",
        job_id=job.job_id,
        enqueued_at_ms=10,
        options={
            "max_steps": None,
            "auto_deposit": True,
            "draft_combined": True,
            "force_offline": False,
        },
    )
    leased, won = queue.lease(
        operation_id=OPERATION,
        worker_id=WORKER,
        leased_at_ms=11,
        lease_expires_at_ms=1_000,
    )
    assert won
    return Runtime(store, plan, ledger, queue, leased.lease_generation)


def _reserve(runtime: Runtime, ordinal: int = 0):  # type: ignore[no-untyped-def]
    item = runtime.plan.stages[ordinal]
    hold = runtime.ledger.reserve_call(
        runtime.plan.job_id,
        item.router_role,
        item.projected_max_cents,
        call_key=item.stage_key,
    )
    receipt = runtime.store.reserve_stage(
        job_id=runtime.plan.job_id,
        stage_key=item.stage_key,
        expected_revision=0,
        input_evidence_sha256=INPUT_HASH,
        **runtime.kwargs(),  # type: ignore[arg-type]
    )
    assert receipt.budget_hold_id == hold.hold_id
    return item, hold, receipt


def _evidence(item: StagePlanItem, label: str = "planner") -> dict[str, object]:
    return {
        "step_key": item.provider_effect_key,
        "spawn_id": None,
        "output_text": json.dumps({"result": label}),
        "insights": [f"insight-{label}"],
        "questions": [f"question-{label}"],
        "route_receipt": {
            "route_receipt_id": f"route-{label}",
            "event_id": f"event-{label}",
            "actual_cents": 6,
        },
        "source_receipts": [],
    }


def _effect(
    item: StagePlanItem,
    evidence: dict[str, object],
    *,
    returned_at_ms: int = 30,
) -> StageEffectReceipt:
    canonical = json.dumps(evidence, sort_keys=True, separators=(",", ":"))
    output_hash = hashlib.sha256(canonical.encode()).hexdigest()
    kind = item.kind
    fields = dict(
        stage_key=item.stage_key,
        provider_effect_key_value=item.provider_effect_key,
        kind=kind,
        output_schema=f"midnight-oil.{kind}-output/v1",
        output_sha256=output_hash,
        route_receipt_id=f"route-{kind if kind != 'gather' else 'gather'}",
        source_receipt_ids=(),
        provider_event_id=f"event-{kind if kind != 'gather' else 'gather'}",
        actual_cents=6,
    )
    return StageEffectReceipt(
        receipt_id=effect_receipt_id(**fields),  # type: ignore[arg-type]
        stage_key=item.stage_key,
        provider_effect_key=item.provider_effect_key,
        kind=kind,
        output_schema=fields["output_schema"],  # type: ignore[arg-type]
        output_sha256=output_hash,
        route_receipt_id=f"route-{kind}",
        source_receipt_ids=(),
        provider_event_id=f"event-{kind}",
        actual_cents=6,
        returned_at_ms=returned_at_ms,
    )


def _rejection(item: StagePlanItem, *, actual_cents: int = 6) -> StageRejectionReceipt:
    return StageRejectionReceipt(
        receipt_id=stage_rejection_receipt_id(
            stage_key=item.stage_key,
            provider_effect_key_value=item.provider_effect_key,
            kind=item.kind,
            route_receipt_id=f"route-{item.kind}",
            provider_event_id=f"event-{item.kind}",
            raw_response_sha256="f" * 64,
            actual_cents=actual_cents,
            rejection_code="schema_invalid",
            validator_sha256="1" * 64,
            issue_digest_sha256="2" * 64,
        ),
        stage_key=item.stage_key,
        provider_effect_key=item.provider_effect_key,
        kind=item.kind,
        route_receipt_id=f"route-{item.kind}",
        provider_event_id=f"event-{item.kind}",
        raw_response_sha256="f" * 64,
        actual_cents=actual_cents,
        rejection_code="schema_invalid",
        validator_sha256="1" * 64,
        issue_digest_sha256="2" * 64,
        returned_at_ms=30,
    )


def test_plan_is_atomic_restart_safe_and_sql_json_identity_is_checked(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    first = runtime.store.list_stages(runtime.plan.job_id)
    assert runtime.store.initialize_stage_plan(runtime.plan) == first
    restarted = DurableJobStore(runtime.store.path)
    assert restarted.list_stages(runtime.plan.job_id) == first
    with sqlite3.connect(runtime.store.path) as connection:
        encoded = first[0].model_copy(update={"job_id": "foreign"}).model_dump_json()
        connection.execute(
            "UPDATE midnight_oil_stage_receipts SET receipt_json = ? "
            "WHERE job_id = ? AND stage_key = ?",
            (encoded, runtime.plan.job_id, first[0].stage_key),
        )
    with pytest.raises(ValueError, match="SQL identity"):
        restarted.get_stage(runtime.plan.job_id, first[0].stage_key)


def test_reserve_requires_exact_live_lease_and_budget_exposure(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    item, hold, receipt = _reserve(runtime)
    exposure = runtime.ledger.stage_exposure(runtime.plan.job_id, item.stage_key)
    assert (
        exposure.call_key,
        exposure.hold_id,
        exposure.role,
        exposure.projected_cents,
        exposure.state,
    ) == (item.stage_key, hold.hold_id, item.router_role, item.projected_max_cents, "open")
    assert receipt.lease_generation == runtime.lease_generation

    other = _runtime(tmp_path / "wrong-generation")
    other_item = other.plan.stages[0]
    other.ledger.reserve_call(
        other.plan.job_id,
        other_item.router_role,
        other_item.projected_max_cents,
        call_key=other_item.stage_key,
    )
    with pytest.raises(RuntimeError, match="lease is stale"):
        other.store.reserve_stage(
            job_id=other.plan.job_id,
            stage_key=other_item.stage_key,
            expected_revision=0,
            input_evidence_sha256=INPUT_HASH,
            **other.kwargs() | {"lease_generation": other.lease_generation + 1},  # type: ignore[arg-type]
        )
    with pytest.raises(RuntimeError, match="lease is stale"):
        other.store.reserve_stage(
            job_id=other.plan.job_id,
            stage_key=other_item.stage_key,
            expected_revision=0,
            input_evidence_sha256=INPUT_HASH,
            **other.kwargs(now_ms=1_000),  # type: ignore[arg-type]
        )


def test_fake_or_conflicting_hold_is_rejected(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    item = runtime.plan.stages[0]
    with pytest.raises(ReservationNotFound):
        runtime.store.reserve_stage(
            job_id=runtime.plan.job_id,
            stage_key=item.stage_key,
            expected_revision=0,
            input_evidence_sha256=INPUT_HASH,
            **runtime.kwargs(),  # type: ignore[arg-type]
        )
    runtime.ledger.reserve_call(
        runtime.plan.job_id,
        "gatherer",
        item.projected_max_cents,
        call_key=item.stage_key,
    )
    with pytest.raises(ValueError, match="budget exposure"):
        runtime.store.reserve_stage(
            job_id=runtime.plan.job_id,
            stage_key=item.stage_key,
            expected_revision=0,
            input_evidence_sha256=INPUT_HASH,
            **runtime.kwargs(),  # type: ignore[arg-type]
        )


def test_return_replay_ignores_observation_time_and_returns_original(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    item, _, reserved = _reserve(runtime)
    evidence = _evidence(item)
    effect = _effect(item, evidence, returned_at_ms=30)
    returned = runtime.store.checkpoint_stage_returned(
        job_id=runtime.plan.job_id,
        stage_key=item.stage_key,
        expected_revision=reserved.revision,
        effect=effect,
        stage_evidence=evidence,
        **runtime.kwargs(now_ms=31),  # type: ignore[arg-type]
    )
    replay = runtime.store.checkpoint_stage_returned(
        job_id=runtime.plan.job_id,
        stage_key=item.stage_key,
        expected_revision=reserved.revision,
        effect=effect.model_copy(update={"returned_at_ms": 999}),
        stage_evidence=evidence,
        **runtime.kwargs(now_ms=32),  # type: ignore[arg-type]
    )
    assert replay == returned
    assert replay.returned_at_ms == 30
    persisted = runtime.store.get_stage_effect(runtime.plan.job_id, item.stage_key)
    assert persisted == (effect, evidence)


def test_recovery_read_rejects_structurally_valid_evidence_cost_tampering(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    item, _, reserved = _reserve(runtime)
    evidence = _evidence(item)
    runtime.store.checkpoint_stage_returned(
        job_id=runtime.plan.job_id,
        stage_key=item.stage_key,
        expected_revision=reserved.revision,
        effect=_effect(item, evidence),
        stage_evidence=evidence,
        **runtime.kwargs(now_ms=31),  # type: ignore[arg-type]
    )
    tampered = json.loads(json.dumps(evidence))
    tampered["route_receipt"]["actual_cents"] = 5
    with sqlite3.connect(runtime.store.path) as connection:
        connection.execute(
            "UPDATE midnight_oil_stage_effects SET evidence_json = ? WHERE job_id = ?",
            (json.dumps(tampered), runtime.plan.job_id),
        )
    with pytest.raises(ValueError, match="conflicts with its effect receipt"):
        runtime.store.get_stage_effect(runtime.plan.job_id, item.stage_key)
    with pytest.raises(ValueError, match="conflicts with its effect receipt"):
        runtime.store.get_job(runtime.plan.job_id)


def test_settle_requires_settled_exact_hold_and_live_lease(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    item, hold, reserved = _reserve(runtime)
    evidence = _evidence(item)
    returned = runtime.store.checkpoint_stage_returned(
        job_id=runtime.plan.job_id,
        stage_key=item.stage_key,
        expected_revision=reserved.revision,
        effect=_effect(item, evidence),
        stage_evidence=evidence,
        **runtime.kwargs(now_ms=31),  # type: ignore[arg-type]
    )
    with pytest.raises(ValueError, match="budget exposure"):
        runtime.store.mark_stage_settled(
            job_id=runtime.plan.job_id,
            stage_key=item.stage_key,
            expected_revision=returned.revision,
            **runtime.kwargs(now_ms=32),  # type: ignore[arg-type]
        )
    runtime.ledger.settle(hold, 6)
    settled = runtime.store.mark_stage_settled(
        job_id=runtime.plan.job_id,
        stage_key=item.stage_key,
        expected_revision=returned.revision,
        **runtime.kwargs(now_ms=33),  # type: ignore[arg-type]
    )
    exposure = runtime.ledger.stage_exposure(runtime.plan.job_id, item.stage_key)
    assert exposure.state == "settled" and exposure.confirmed_cents == 6
    assert settled.state == "settled"


def test_proven_no_dispatch_is_terminal_and_never_unlocks_successor(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    item = runtime.plan.stages[0]
    reserved_receipt = None

    def checkpoint(_hold: object) -> None:
        nonlocal reserved_receipt
        reserved_receipt = runtime.store.reserve_stage(
            job_id=runtime.plan.job_id,
            stage_key=item.stage_key,
            expected_revision=0,
            input_evidence_sha256=INPUT_HASH,
            **runtime.kwargs(),  # type: ignore[arg-type]
        )

    def refused() -> tuple[str, int]:
        raise CallNotDispatched("route refused before network")

    with pytest.raises(CallNotDispatched):
        runtime.ledger.guarded_call(
            runtime.plan.job_id,
            item.router_role,
            item.projected_max_cents,
            refused,
            call_key=item.stage_key,
            after_reserve=checkpoint,
        )
    assert reserved_receipt is not None
    failed = runtime.store.mark_stage_not_dispatched(
        job_id=runtime.plan.job_id,
        stage_key=item.stage_key,
        expected_revision=reserved_receipt.revision,
        reason="route_refused",
        **runtime.kwargs(now_ms=30),  # type: ignore[arg-type]
    )
    assert failed.state == "not_dispatched"
    assert (
        runtime.store.mark_stage_not_dispatched(
            job_id=runtime.plan.job_id,
            stage_key=item.stage_key,
            expected_revision=reserved_receipt.revision,
            reason="route_refused",
            **runtime.kwargs(now_ms=999),  # type: ignore[arg-type]
        )
        == failed
    )
    successor = runtime.plan.stages[1]
    runtime.ledger.reserve_call(
        runtime.plan.job_id,
        successor.router_role,
        successor.projected_max_cents,
        call_key=successor.stage_key,
    )
    assert runtime.queue.get(OPERATION).next_step_index == 0  # type: ignore[union-attr]
    with pytest.raises(ValueError, match="queue cursor"):
        runtime.store.reserve_stage(
            job_id=runtime.plan.job_id,
            stage_key=successor.stage_key,
            expected_revision=0,
            input_evidence_sha256=INPUT_HASH,
            **runtime.kwargs(now_ms=31),  # type: ignore[arg-type]
        )


def test_known_paid_invalid_response_is_audited_settled_and_not_merged(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    item, hold, reserved = _reserve(runtime)
    rejection = _rejection(item)
    rejected = runtime.store.checkpoint_stage_rejected(
        job_id=runtime.plan.job_id,
        stage_key=item.stage_key,
        expected_revision=reserved.revision,
        rejection=rejection,
        **runtime.kwargs(now_ms=31),  # type: ignore[arg-type]
    )
    assert rejected.state == "rejected"
    assert runtime.store.get_stage_rejection(runtime.plan.job_id, item.stage_key) == rejection
    assert runtime.store.get_job(runtime.plan.job_id)["step_evidence"] == []  # type: ignore[index]
    runtime.ledger.settle(hold, rejection.actual_cents)
    terminal = runtime.store.mark_stage_rejection_settled(
        job_id=runtime.plan.job_id,
        stage_key=item.stage_key,
        expected_revision=rejected.revision,
        **runtime.kwargs(now_ms=32),  # type: ignore[arg-type]
    )
    assert terminal.state == "rejected_settled"


def test_rejection_receipt_tampering_fails_recovery_and_job_projection(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    item, _, reserved = _reserve(runtime)
    rejection = _rejection(item)
    runtime.store.checkpoint_stage_rejected(
        job_id=runtime.plan.job_id,
        stage_key=item.stage_key,
        expected_revision=reserved.revision,
        rejection=rejection,
        **runtime.kwargs(now_ms=31),  # type: ignore[arg-type]
    )
    tampered = rejection.model_copy(update={"actual_cents": 5}).model_dump_json()
    with sqlite3.connect(runtime.store.path) as connection:
        connection.execute(
            "UPDATE midnight_oil_stage_rejections SET rejection_json = ? WHERE job_id = ?",
            (tampered, runtime.plan.job_id),
        )
    with pytest.raises(ValueError, match="receipt id conflicts"):
        runtime.store.get_stage_rejection(runtime.plan.job_id, item.stage_key)
    with pytest.raises(ValueError, match="receipt id conflicts"):
        runtime.store.get_job(runtime.plan.job_id)


def test_concurrent_return_checkpoints_have_one_winner_without_evidence_loss(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    item, _, reserved = _reserve(runtime)
    evidence = _evidence(item)
    effect = _effect(item, evidence)

    def checkpoint(label: str) -> str:
        altered = dict(evidence)
        altered["output_text"] = json.dumps({"result": label})
        try:
            runtime.store.checkpoint_stage_returned(
                job_id=runtime.plan.job_id,
                stage_key=item.stage_key,
                expected_revision=reserved.revision,
                effect=effect,
                stage_evidence=altered,
                **runtime.kwargs(now_ms=31),  # type: ignore[arg-type]
            )
        except ValueError:
            return "conflict"
        return "won"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(checkpoint, ("planner", "hostile")))
    assert outcomes.count("won") == 1
    assert outcomes.count("conflict") == 1
    job = runtime.store.get_job(runtime.plan.job_id)
    assert job is not None and len(job["step_evidence"]) == 1


def test_stage_effects_survive_stale_whole_job_projection_write(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    stale = runtime.store.get_job(runtime.plan.job_id)
    assert stale is not None
    item, _, reserved = _reserve(runtime)
    evidence = _evidence(item)
    runtime.store.checkpoint_stage_returned(
        job_id=runtime.plan.job_id,
        stage_key=item.stage_key,
        expected_revision=reserved.revision,
        effect=_effect(item, evidence),
        stage_evidence=evidence,
        **runtime.kwargs(now_ms=31),  # type: ignore[arg-type]
    )
    runtime.store.put_job(stale)
    recovered = runtime.store.get_job(runtime.plan.job_id)
    assert recovered is not None
    assert recovered["returned_step_keys"] == [item.provider_effect_key]
    assert recovered["step_evidence"] == [evidence]


def test_unknown_requires_unknown_exposure_and_rejects_expired_lease(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    item, hold, reserved = _reserve(runtime)
    runtime.ledger._mark_hold_unknown(hold)  # exact ambiguity injection
    unknown = runtime.store.mark_stage_unknown(
        job_id=runtime.plan.job_id,
        stage_key=item.stage_key,
        expected_revision=reserved.revision,
        **runtime.kwargs(now_ms=40),  # type: ignore[arg-type]
    )
    assert unknown.state == "unknown"
    with pytest.raises(RuntimeError, match="lease is stale"):
        runtime.store.checkpoint_stage_returned(
            job_id=runtime.plan.job_id,
            stage_key=item.stage_key,
            expected_revision=unknown.revision,
            effect=_effect(item, _evidence(item), returned_at_ms=1_001),
            stage_evidence=_evidence(item),
            **runtime.kwargs(now_ms=1_000),  # type: ignore[arg-type]
        )


def test_caller_fabricated_callhold_cannot_authorize_settlement(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    item, hold, reserved = _reserve(runtime)
    evidence = _evidence(item)
    returned = runtime.store.checkpoint_stage_returned(
        job_id=runtime.plan.job_id,
        stage_key=item.stage_key,
        expected_revision=reserved.revision,
        effect=_effect(item, evidence),
        stage_evidence=evidence,
        **runtime.kwargs(now_ms=31),  # type: ignore[arg-type]
    )
    fake = CallHold(
        hold_id="fake",
        run_id=runtime.plan.job_id,
        role=item.router_role,
        projected_max_cents=item.projected_max_cents,
        call_key=item.stage_key,
    )
    with pytest.raises(ReservationNotFound):
        runtime.ledger.settle(fake, 1)
    with pytest.raises(ValueError, match="budget exposure"):
        runtime.store.mark_stage_settled(
            job_id=runtime.plan.job_id,
            stage_key=item.stage_key,
            expected_revision=returned.revision,
            **runtime.kwargs(now_ms=32),  # type: ignore[arg-type]
        )
    assert (
        runtime.ledger.stage_exposure(runtime.plan.job_id, item.stage_key).hold_id == hold.hold_id
    )


def test_budget_exposure_change_before_fence_prevents_stage_commit(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    item = runtime.plan.stages[0]
    hold = runtime.ledger.reserve_call(
        runtime.plan.job_id,
        item.router_role,
        item.projected_max_cents,
        call_key=item.stage_key,
    )
    entered = threading.Event()
    proceed = threading.Event()
    original = runtime.ledger.run_stage_fenced

    def delayed(*args, **kwargs):  # type: ignore[no-untyped-def]
        entered.set()
        assert proceed.wait(timeout=5)
        return original(*args, **kwargs)

    runtime.ledger.run_stage_fenced = delayed  # type: ignore[method-assign]
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(
            runtime.store.reserve_stage,
            job_id=runtime.plan.job_id,
            stage_key=item.stage_key,
            expected_revision=0,
            input_evidence_sha256=INPUT_HASH,
            **runtime.kwargs(),  # type: ignore[arg-type]
        )
        assert entered.wait(timeout=5)
        runtime.ledger.settle(hold, 5)
        proceed.set()
        with pytest.raises(ValueError, match="budget exposure"):
            pending.result(timeout=5)
    assert runtime.store.get_stage(runtime.plan.job_id, item.stage_key).state == "planned"  # type: ignore[union-attr]


def test_lease_generation_change_before_fence_prevents_stage_commit(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    item = runtime.plan.stages[0]
    runtime.ledger.reserve_call(
        runtime.plan.job_id,
        item.router_role,
        item.projected_max_cents,
        call_key=item.stage_key,
    )
    entered = threading.Event()
    proceed = threading.Event()
    original = runtime.queue.run_fenced

    def delayed(**kwargs):  # type: ignore[no-untyped-def]
        entered.set()
        assert proceed.wait(timeout=5)
        return original(**kwargs)

    runtime.queue.run_fenced = delayed  # type: ignore[method-assign]
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(
            runtime.store.reserve_stage,
            job_id=runtime.plan.job_id,
            stage_key=item.stage_key,
            expected_revision=0,
            input_evidence_sha256=INPUT_HASH,
            **runtime.kwargs(),  # type: ignore[arg-type]
        )
        assert entered.wait(timeout=5)
        successor, won = runtime.queue.lease(
            operation_id=OPERATION,
            worker_id="successor",
            leased_at_ms=1_000,
            lease_expires_at_ms=2_000,
        )
        assert won and successor.lease_generation > runtime.lease_generation
        proceed.set()
        with pytest.raises(RuntimeError, match="lease is stale"):
            pending.result(timeout=5)
    assert runtime.store.get_stage(runtime.plan.job_id, item.stage_key).state == "planned"  # type: ignore[union-attr]


def test_exact_replays_need_no_live_or_current_external_authority(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    item, hold, reserved = _reserve(runtime)
    runtime.ledger.settle(hold, 6)
    runtime.queue.run_fenced(
        operation_id=OPERATION,
        worker_id=WORKER,
        lease_generation=runtime.lease_generation,
        now_ms=40,
        expected_step_index=0,
        action=lambda: (None, True),
    )
    assert (
        runtime.store.reserve_stage(
            job_id=runtime.plan.job_id,
            stage_key=item.stage_key,
            expected_revision=0,
            input_evidence_sha256=INPUT_HASH,
            **runtime.kwargs(now_ms=2_000),  # type: ignore[arg-type]
        )
        == reserved
    )

    unknown_runtime = _runtime(tmp_path / "unknown")
    unknown_item, unknown_hold, unknown_reserved = _reserve(unknown_runtime)
    unknown_runtime.ledger._mark_hold_unknown(unknown_hold)
    unknown = unknown_runtime.store.mark_stage_unknown(
        job_id=unknown_runtime.plan.job_id,
        stage_key=unknown_item.stage_key,
        expected_revision=unknown_reserved.revision,
        **unknown_runtime.kwargs(now_ms=30),  # type: ignore[arg-type]
    )
    unknown_runtime.ledger.resolve_unknown(unknown_hold.hold_id, 2)
    unknown_runtime.queue.acknowledge_terminal(
        operation_id=OPERATION,
        worker_id=WORKER,
        lease_generation=unknown_runtime.lease_generation,
        terminal_state="failed_reconcile",
        completed_at_ms=60,
    )
    assert (
        unknown_runtime.store.mark_stage_unknown(
            job_id=unknown_runtime.plan.job_id,
            stage_key=unknown_item.stage_key,
            expected_revision=unknown_reserved.revision,
            **unknown_runtime.kwargs(now_ms=10_000),  # type: ignore[arg-type]
        )
        == unknown
    )

    returned_runtime = _runtime(tmp_path / "returned")
    returned_item, returned_hold, returned_reserved = _reserve(returned_runtime)
    evidence = _evidence(returned_item)
    effect = _effect(returned_item, evidence)
    returned = returned_runtime.store.checkpoint_stage_returned(
        job_id=returned_runtime.plan.job_id,
        stage_key=returned_item.stage_key,
        expected_revision=returned_reserved.revision,
        effect=effect,
        stage_evidence=evidence,
        **returned_runtime.kwargs(now_ms=31),  # type: ignore[arg-type]
    )
    returned_runtime.ledger.settle(returned_hold, 4)
    returned_runtime.queue.acknowledge_terminal(
        operation_id=OPERATION,
        worker_id=WORKER,
        lease_generation=returned_runtime.lease_generation,
        terminal_state="failed",
        completed_at_ms=50,
    )
    assert (
        returned_runtime.store.checkpoint_stage_returned(
            job_id=returned_runtime.plan.job_id,
            stage_key=returned_item.stage_key,
            expected_revision=returned_reserved.revision,
            effect=effect.model_copy(update={"returned_at_ms": 9_999}),
            stage_evidence=evidence,
            **returned_runtime.kwargs(now_ms=9_999),  # type: ignore[arg-type]
        )
        == returned
    )

    settled_runtime = _runtime(tmp_path / "settled")
    settled_item, settled_hold, settled_reserved = _reserve(settled_runtime)
    settled_evidence = _evidence(settled_item)
    settled_returned = settled_runtime.store.checkpoint_stage_returned(
        job_id=settled_runtime.plan.job_id,
        stage_key=settled_item.stage_key,
        expected_revision=settled_reserved.revision,
        effect=_effect(settled_item, settled_evidence),
        stage_evidence=settled_evidence,
        **settled_runtime.kwargs(now_ms=31),  # type: ignore[arg-type]
    )
    settled_runtime.ledger.settle(settled_hold, 6)
    settled = settled_runtime.store.mark_stage_settled(
        job_id=settled_runtime.plan.job_id,
        stage_key=settled_item.stage_key,
        expected_revision=settled_returned.revision,
        **settled_runtime.kwargs(now_ms=33),  # type: ignore[arg-type]
    )
    settled_runtime.queue.acknowledge_terminal(
        operation_id=OPERATION,
        worker_id=WORKER,
        lease_generation=settled_runtime.lease_generation,
        terminal_state="complete",
        completed_at_ms=60,
    )
    assert (
        settled_runtime.store.mark_stage_settled(
            job_id=settled_runtime.plan.job_id,
            stage_key=settled_item.stage_key,
            expected_revision=settled_returned.revision,
            **settled_runtime.kwargs(now_ms=10_000),  # type: ignore[arg-type]
        )
        == settled
    )
