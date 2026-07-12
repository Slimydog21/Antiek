from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from substrate.midnight_oil.budget_ledger import BudgetLedger, CallNotDispatched
from substrate.midnight_oil.durable_job import DurableJobStore
from substrate.midnight_oil.job import create_job
from substrate.midnight_oil.live_roles import CanonicalSourceReceipt
from substrate.midnight_oil.live_stage_engine import (
    LiveSwarmStageEngine,
    StageDispatchClaimLost,
    StageProviderResponse,
    StageRunResult,
    stage_input_sha256,
)
from substrate.midnight_oil.operation_queue import DurableOperationQueue
from substrate.midnight_oil.stages import (
    StageKind,
    StagePlan,
    StagePlanItem,
    provider_effect_key,
    stage_key,
    stage_plan_hash,
)

OPERATION = "operation-live-stage"
JOB = "job-live-stage"
WORKER = "worker-live-stage"
INPUT_HASH = stage_input_sha256("plan", ())
VALIDATOR_HASH = "c" * 64


def _item(
    ordinal: int,
    kind: StageKind,
    *,
    predecessors: tuple[str, ...] = (),
    shard: int | None = None,
) -> StagePlanItem:
    key = stage_key(operation_id=OPERATION, goal_index=0, kind=kind, shard_index=shard)
    return StagePlanItem(
        ordinal=ordinal,
        kind=kind,
        goal_index=0,
        shard_index=shard,
        shard_count=1 if kind == "gather" else None,
        predecessor_stage_keys=predecessors,
        router_role="gatherer" if kind == "gather" else kind,
        route_plan_sha256="a" * 64,
        projected_max_cents=10,
        stage_key=key,
        provider_effect_key=provider_effect_key(key),
    )


def _plan() -> StagePlan:
    planner = _item(0, "planner")
    gather = _item(1, "gather", predecessors=(planner.stage_key,), shard=0)
    verifier = _item(2, "verifier", predecessors=(gather.stage_key,))
    synth = _item(3, "synthesizer", predecessors=(verifier.stage_key,))
    stages = (planner, gather, verifier, synth)
    return StagePlan(
        operation_id=OPERATION,
        job_id=JOB,
        approved_ceiling_cents=100,
        stages=stages,
        plan_hash=stage_plan_hash(
            operation_id=OPERATION,
            job_id=JOB,
            approved_ceiling_cents=100,
            stages=stages,
        ),
    )


def _planner_json() -> str:
    return json.dumps(
        {
            "role": "planner",
            "schema_version": 1,
            "research_frame": "Test the claim.",
            "questions": [
                {
                    "question_id": "q-1",
                    "question": "What does the evidence show?",
                    "inclusion_criteria": ["Primary source"],
                    "exclusion_criteria": [],
                    "expected_evidence_types": ["Document"],
                    "falsifiers": ["Direct contradiction"],
                }
            ],
        }
    )


@dataclass
class FakeDispatch:
    response_text: str = field(default_factory=_planner_json)
    error: Exception | None = None
    calls: list[tuple[str, str]] = field(default_factory=list)
    route_hash: str = "a" * 64

    def route_plan_sha256(self, role: str) -> str:
        return self.route_hash

    def __call__(
        self,
        prompt: str,
        role: str,
        *,
        investigation_id: str,
        idempotency_key: str,
    ) -> StageProviderResponse:
        self.calls.append((role, idempotency_key))
        if self.error is not None:
            raise self.error
        return StageProviderResponse(
            text=self.response_text,
            route_receipt_id="route-planner",
            provider_event_id="event-planner",
            actual_cents=6,
        )


@dataclass
class SequenceDispatch:
    responses: dict[str, str]
    calls: list[tuple[str, str]] = field(default_factory=list)

    def route_plan_sha256(self, role: str) -> str:
        return "a" * 64

    def __call__(
        self,
        prompt: str,
        role: str,
        *,
        investigation_id: str,
        idempotency_key: str,
    ) -> StageProviderResponse:
        self.calls.append((role, idempotency_key))
        return StageProviderResponse(
            text=self.responses[role],
            route_receipt_id=f"route-{role}",
            provider_event_id=f"event-{role}",
            actual_cents=6,
        )


@dataclass
class Runtime:
    store: DurableJobStore
    ledger: BudgetLedger
    queue: DurableOperationQueue
    dispatch: FakeDispatch | SequenceDispatch
    lease_generation: int

    def engine(
        self,
        *,
        worker_id: str = WORKER,
        lease_generation: int | None = None,
        now_ms: int = 30,
    ) -> EngineHarness:
        return EngineHarness(
            LiveSwarmStageEngine(
                job_id=JOB,
                operation_id=OPERATION,
                worker_id=worker_id,
                lease_generation=lease_generation or self.lease_generation,
                store=self.store,
                ledger=self.ledger,
                operation_queue=self.queue,
                dispatch=self.dispatch,
                now_ms=lambda: now_ms,
                validator_sha256=VALIDATOR_HASH,
            )
        )


@dataclass(frozen=True)
class EngineHarness:
    engine: LiveSwarmStageEngine

    def run_current_stage(
        self,
        *,
        prompt: str,
        input_evidence_sha256: str,
        source_receipts: tuple[dict[str, str], ...] = (),
    ) -> StageRunResult:
        if source_receipts:
            raise ValueError("stage source receipts are invalid")
        if input_evidence_sha256 != stage_input_sha256(prompt, source_receipts):
            raise ValueError("stage input hash conflicts")
        return self.engine.run_current_stage(stage_payload=prompt)


def _runtime(tmp_path: Path, dispatch: FakeDispatch | SequenceDispatch | None = None) -> Runtime:
    store = DurableJobStore(tmp_path / "jobs.sqlite3")
    create_job(["Investigate"], 15, store=store, job_id=JOB)
    store.initialize_stage_plan(_plan())
    ledger = BudgetLedger(store.budget_db_path())
    ledger.ensure_schema()
    ledger.reserve(
        JOB,
        100,
        {"planner": 25, "gatherer": 25, "verifier": 25, "synthesizer": 25},
    )
    queue = DurableOperationQueue(tmp_path / "queue.sqlite3")
    queue.enqueue_once(
        operation_id=OPERATION,
        owner_user_id="owner",
        job_id=JOB,
        enqueued_at_ms=10,
        options={
            "max_steps": None,
            "auto_deposit": True,
            "draft_combined": True,
            "force_offline": False,
        },
    )
    lease, won = queue.lease(
        operation_id=OPERATION,
        worker_id=WORKER,
        leased_at_ms=11,
        lease_expires_at_ms=1_000,
    )
    assert won
    return Runtime(store, ledger, queue, dispatch or FakeDispatch(), lease.lease_generation)


def test_valid_provider_stage_settles_once_and_advances_cursor(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    result = runtime.engine().run_current_stage(prompt="plan", input_evidence_sha256=INPUT_HASH)
    assert (result.outcome, result.provider_calls) == ("settled", 1)
    assert runtime.queue.get(OPERATION).next_step_index == 1  # type: ignore[union-attr]
    assert len(runtime.dispatch.calls) == 1
    effect = runtime.store.get_stage_effect(JOB, _plan().stages[0].stage_key)
    assert effect is not None and effect[0].actual_cents == 6


def test_invalid_known_paid_output_is_rejected_settled_without_cursor_advance(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path, FakeDispatch(response_text="not-json"))
    result = runtime.engine().run_current_stage(prompt="plan", input_evidence_sha256=INPUT_HASH)
    assert (result.outcome, result.provider_calls) == ("rejected_settled", 1)
    assert runtime.queue.get(OPERATION).next_step_index == 0  # type: ignore[union-attr]
    assert runtime.ledger.balance(JOB).spent_cents == 6
    rejection = runtime.store.get_stage_rejection(JOB, _plan().stages[0].stage_key)
    assert (
        rejection is not None
        and rejection.raw_response_sha256 == hashlib.sha256(b"not-json").hexdigest()
    )


def test_empty_known_paid_output_is_rejected_not_mislabeled_unknown(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, FakeDispatch(response_text=""))
    result = runtime.engine().run_current_stage(prompt="plan", input_evidence_sha256=INPUT_HASH)
    assert result.outcome == "rejected_settled"
    assert runtime.ledger.balance(JOB).spent_cents == 6


def test_proven_no_dispatch_is_terminal_without_spend_or_advance(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, FakeDispatch(error=CallNotDispatched("offline")))
    result = runtime.engine().run_current_stage(prompt="plan", input_evidence_sha256=INPUT_HASH)
    assert (result.outcome, result.provider_calls) == ("not_dispatched", 1)
    assert runtime.ledger.balance(JOB).spent_cents == 0
    assert runtime.queue.get(OPERATION).next_step_index == 0  # type: ignore[union-attr]


def test_ambiguous_provider_failure_becomes_unknown_and_never_replays(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path, FakeDispatch(error=TimeoutError("ambiguous")))
    first = runtime.engine().run_current_stage(prompt="plan", input_evidence_sha256=INPUT_HASH)
    second = runtime.engine().run_current_stage(prompt="plan", input_evidence_sha256=INPUT_HASH)
    assert (first.outcome, second.outcome) == ("unknown", "unknown")
    assert len(runtime.dispatch.calls) == 1


def test_intent_open_hold_is_adopted_with_exact_durable_input(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    item = _plan().stages[0]
    engine = runtime.engine().engine
    prompt, _ = engine._prepare_role(item, _plan().stages, "plan", ())
    intent_hash = stage_input_sha256(prompt, ())
    runtime.store.register_stage_intent(
        job_id=JOB,
        stage_key=item.stage_key,
        input_evidence_sha256=intent_hash,
        operation_queue=runtime.queue,
        worker_id=WORKER,
        lease_generation=runtime.lease_generation,
        now_ms=19,
    )
    runtime.ledger.reserve_call(
        JOB, item.router_role, item.projected_max_cents, call_key=item.stage_key
    )
    result = runtime.engine().run_current_stage(prompt="plan", input_evidence_sha256=INPUT_HASH)
    assert (result.outcome, result.provider_calls) == ("settled", 1)
    assert len(runtime.dispatch.calls) == 1


def test_planned_open_hold_without_intent_cannot_substitute_input(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    item = _plan().stages[0]
    runtime.ledger.reserve_call(
        JOB, item.router_role, item.projected_max_cents, call_key=item.stage_key
    )
    different_hash = stage_input_sha256("different", ())
    with pytest.raises(ValueError, match="hold without durable input intent"):
        runtime.engine().run_current_stage(prompt="different", input_evidence_sha256=different_hash)
    assert runtime.dispatch.calls == []


def test_concurrent_same_lease_invocations_cross_transport_once(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    barrier = threading.Barrier(2)
    original = runtime.store.reserve_stage

    def delayed_reserve(**kwargs):  # type: ignore[no-untyped-def]
        barrier.wait()
        return original(**kwargs)

    runtime.store.reserve_stage = delayed_reserve  # type: ignore[method-assign]

    def run_once(_: int) -> str:
        try:
            return (
                runtime.engine()
                .run_current_stage(prompt="plan", input_evidence_sha256=INPUT_HASH)
                .outcome
            )
        except StageDispatchClaimLost:
            return "claim_lost"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = sorted(pool.map(run_once, range(2)))
    assert outcomes == ["claim_lost", "settled"]
    assert len(runtime.dispatch.calls) == 1


def test_reserved_open_stage_is_ambiguous_on_restart_and_does_not_dispatch(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    item = _plan().stages[0]
    runtime.ledger.reserve_call(
        JOB, item.router_role, item.projected_max_cents, call_key=item.stage_key
    )
    runtime.store.reserve_stage(
        job_id=JOB,
        stage_key=item.stage_key,
        expected_revision=0,
        input_evidence_sha256=INPUT_HASH,
        budget_ledger=runtime.ledger,
        operation_queue=runtime.queue,
        worker_id=WORKER,
        lease_generation=runtime.lease_generation,
        now_ms=20,
    )
    with pytest.raises(StageDispatchClaimLost, match="still be active"):
        runtime.engine().run_current_stage(prompt="plan", input_evidence_sha256=INPUT_HASH)
    successor, won = runtime.queue.lease(
        operation_id=OPERATION,
        worker_id="successor",
        leased_at_ms=1_000,
        lease_expires_at_ms=2_000,
    )
    assert won
    result = runtime.engine(
        worker_id="successor",
        lease_generation=successor.lease_generation,
        now_ms=1_100,
    ).run_current_stage(prompt="plan", input_evidence_sha256=INPUT_HASH)
    assert (result.outcome, result.provider_calls) == ("unknown", 0)
    assert runtime.dispatch.calls == []


@pytest.mark.parametrize(
    ("response_text", "expected"),
    [(_planner_json(), "settled"), ("not-json", "rejected_settled")],
)
def test_checkpointed_unknown_exposure_reconciles_without_provider_replay(
    tmp_path: Path, response_text: str, expected: str
) -> None:
    runtime = _runtime(tmp_path, FakeDispatch(response_text=response_text))
    original_settle = runtime.ledger.settle

    def lose_settlement(hold, actual_cents):  # type: ignore[no-untyped-def]
        runtime.ledger._mark_hold_unknown(hold)
        raise RuntimeError("crash after checkpoint")

    runtime.ledger.settle = lose_settlement  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="crash after checkpoint"):
        runtime.engine().run_current_stage(prompt="plan", input_evidence_sha256=INPUT_HASH)
    runtime.ledger.settle = original_settle  # type: ignore[method-assign]
    result = runtime.engine().run_current_stage(prompt="plan", input_evidence_sha256=INPUT_HASH)
    assert result.outcome == expected
    assert result.provider_calls == 0
    assert len(runtime.dispatch.calls) == 1


@pytest.mark.parametrize("exposure_state", ["released", "settled"])
def test_successor_recovers_or_rejects_reserved_terminal_exposure(
    tmp_path: Path, exposure_state: str
) -> None:
    runtime = _runtime(tmp_path)
    item = _plan().stages[0]
    hold = runtime.ledger.reserve_call(
        JOB, item.router_role, item.projected_max_cents, call_key=item.stage_key
    )
    runtime.store.reserve_stage(
        job_id=JOB,
        stage_key=item.stage_key,
        expected_revision=0,
        input_evidence_sha256=INPUT_HASH,
        budget_ledger=runtime.ledger,
        operation_queue=runtime.queue,
        worker_id=WORKER,
        lease_generation=runtime.lease_generation,
        now_ms=20,
    )
    if exposure_state == "released":
        runtime.ledger.release_stage_call(JOB, item.stage_key)
    else:
        runtime.ledger.settle(hold, 6)
    successor, won = runtime.queue.lease(
        operation_id=OPERATION,
        worker_id="successor",
        leased_at_ms=1_000,
        lease_expires_at_ms=2_000,
    )
    assert won
    engine = runtime.engine(
        worker_id="successor",
        lease_generation=successor.lease_generation,
        now_ms=1_100,
    )
    if exposure_state == "released":
        result = engine.run_current_stage(prompt="plan", input_evidence_sha256=INPUT_HASH)
        assert result.outcome == "not_dispatched"
    else:
        with pytest.raises(ValueError, match="settled budget exposure"):
            engine.run_current_stage(prompt="plan", input_evidence_sha256=INPUT_HASH)
    assert runtime.dispatch.calls == []


def test_invalid_local_source_receipt_fails_before_hold_or_provider(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    with pytest.raises(ValueError, match="source receipts"):
        runtime.engine().run_current_stage(
            prompt="plan",
            input_evidence_sha256=INPUT_HASH,
            source_receipts=({"source_id": "source-1", "raw_secret": "forbidden"},),
        )
    assert runtime.dispatch.calls == []
    assert runtime.ledger.balance(JOB).held_cents == 0


def test_forged_input_hash_fails_before_hold_or_provider(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    with pytest.raises(ValueError, match="input hash conflicts"):
        runtime.engine().run_current_stage(prompt="plan", input_evidence_sha256="b" * 64)
    assert runtime.dispatch.calls == []
    assert runtime.ledger.balance(JOB).held_cents == 0


def test_route_config_drift_fails_before_hold_or_provider(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, FakeDispatch(route_hash="d" * 64))
    with pytest.raises(ValueError, match="dispatch config conflicts"):
        runtime.engine().run_current_stage(prompt="plan", input_evidence_sha256=INPUT_HASH)
    assert runtime.dispatch.calls == []
    assert runtime.ledger.balance(JOB).held_cents == 0


def test_causal_four_role_chain_loads_only_durable_predecessors(tmp_path: Path) -> None:
    claim = "The primary source supports the bounded proposition."
    excerpt_text = "untrusted source text"
    excerpt_sha = hashlib.sha256(excerpt_text.encode()).hexdigest()
    proposition_digest = hashlib.sha256(f"q-1\x00{claim}".encode()).hexdigest()
    proposition_id = f"prop-{proposition_digest[:16]}"
    dispatch = SequenceDispatch(
        {
            "planner": _planner_json(),
            "gatherer": json.dumps(
                {
                    "role": "gatherer",
                    "schema_version": 1,
                    "question_id": "q-1",
                    "evidence": [
                        {
                            "evidence_id": "ev-0123456789abcdef",
                            "source_receipt_id": "source-1",
                            "document_id": "doc-1",
                            "chunk_id": "chunk-1",
                            "excerpt_sha256": excerpt_sha,
                            "claim": claim,
                            "relevance": "Directly answers q-1.",
                            "limitations": ["Single source"],
                        }
                    ],
                    "search_limitations": ["Operator corpus only"],
                }
            ),
            "verifier": json.dumps(
                {
                    "role": "verifier",
                    "schema_version": 1,
                    "findings": [
                        {
                            "finding_id": "vf-0123456789abcdef",
                            "proposition_id": proposition_id,
                            "question_id": "q-1",
                            "claim": claim,
                            "status": "supported",
                            "evidence_ids": ["ev-0123456789abcdef"],
                            "rationale": "The canonical excerpt supports it.",
                            "missing_evidence": [],
                        }
                    ],
                    "evidence_dispositions": [
                        {
                            "evidence_id": "ev-0123456789abcdef",
                            "question_id": "q-1",
                            "disposition": "considered_support",
                            "rationale": "Primary evidence was accepted.",
                        }
                    ],
                }
            ),
            "synthesizer": json.dumps(
                {
                    "role": "synthesizer",
                    "schema_version": 1,
                    "claims": [
                        {
                            "claim_id": "cl-0123456789abcdef",
                            "proposition_id": proposition_id,
                            "text": claim,
                            "finding_id": "vf-0123456789abcdef",
                            "evidence_ids": ["ev-0123456789abcdef"],
                            "confidence": "low",
                        }
                    ],
                    "summary_claim_ids": ["cl-0123456789abcdef"],
                    "addressed_contradictions": [],
                    "addressed_gaps": [],
                    "limitations": ["Single operator-corpus source"],
                    "open_questions": [],
                }
            ),
        }
    )
    runtime = _runtime(tmp_path, dispatch)
    assert runtime.engine().engine.run_current_stage(stage_payload={}).outcome == "settled"
    source = CanonicalSourceReceipt(
        source_receipt_id="source-1",
        question_id="q-1",
        document_id="doc-1",
        chunk_id="chunk-1",
        excerpt_sha256=excerpt_sha,
    )
    assert (
        runtime.engine()
        .engine.run_current_stage(
            stage_payload={"excerpts": [{"source_receipt_id": "source-1", "text": excerpt_text}]},
            source_receipts=(source,),
        )
        .outcome
        == "settled"
    )
    assert runtime.engine().engine.run_current_stage(stage_payload={}).outcome == "settled"
    assert runtime.engine().engine.run_current_stage(stage_payload={}).outcome == "settled"
    assert runtime.queue.get(OPERATION).next_step_index == 4  # type: ignore[union-attr]
    assert [role for role, _ in dispatch.calls] == [
        "planner",
        "gatherer",
        "verifier",
        "synthesizer",
    ]


def test_gather_excerpt_hash_mismatch_fails_before_paid_call(tmp_path: Path) -> None:
    dispatch = SequenceDispatch({"planner": _planner_json()})
    runtime = _runtime(tmp_path, dispatch)
    assert runtime.engine().engine.run_current_stage(stage_payload={}).outcome == "settled"
    source = CanonicalSourceReceipt(
        source_receipt_id="source-1",
        question_id="q-1",
        document_id="doc-1",
        chunk_id="chunk-1",
        excerpt_sha256=hashlib.sha256(b"authoritative").hexdigest(),
    )
    with pytest.raises(ValueError, match="canonical content hash"):
        runtime.engine().engine.run_current_stage(
            stage_payload={"excerpts": [{"source_receipt_id": "source-1", "text": "substituted"}]},
            source_receipts=(source,),
        )
    assert len(dispatch.calls) == 1


def test_tampered_durable_predecessor_fails_before_next_paid_call(tmp_path: Path) -> None:
    dispatch = SequenceDispatch({"planner": _planner_json()})
    runtime = _runtime(tmp_path, dispatch)
    assert runtime.engine().engine.run_current_stage(stage_payload={}).outcome == "settled"
    item = _plan().stages[0]
    with sqlite3.connect(runtime.store.path) as connection:
        row = connection.execute(
            "SELECT evidence_json FROM midnight_oil_stage_effects WHERE stage_key = ?",
            (item.stage_key,),
        ).fetchone()
        assert row is not None
        evidence = json.loads(str(row[0]))
        evidence["output_text"] = _planner_json().replace("Test the claim.", "Tampered.")
        connection.execute(
            "UPDATE midnight_oil_stage_effects SET evidence_json = ? WHERE stage_key = ?",
            (json.dumps(evidence), item.stage_key),
        )
    with pytest.raises(ValueError, match="effect receipt"):
        runtime.engine().engine.run_current_stage(
            stage_payload={"excerpts": []}, source_receipts=()
        )
    assert len(dispatch.calls) == 1


def test_gather_duplicate_receipt_claim_is_paid_rejection_not_accepted(
    tmp_path: Path,
) -> None:
    text = "authoritative excerpt"
    excerpt_sha = hashlib.sha256(text.encode()).hexdigest()
    evidence = {
        "source_receipt_id": "source-1",
        "document_id": "doc-1",
        "chunk_id": "chunk-1",
        "excerpt_sha256": excerpt_sha,
        "claim": "Bounded claim.",
        "relevance": "Direct evidence.",
        "limitations": [],
    }
    dispatch = SequenceDispatch(
        {
            "planner": _planner_json(),
            "gatherer": json.dumps(
                {
                    "role": "gatherer",
                    "schema_version": 1,
                    "question_id": "q-1",
                    "evidence": [
                        {**evidence, "evidence_id": "ev-0123456789abcdef"},
                        {**evidence, "evidence_id": "ev-fedcba9876543210"},
                    ],
                    "search_limitations": [],
                }
            ),
        }
    )
    runtime = _runtime(tmp_path, dispatch)
    assert runtime.engine().engine.run_current_stage(stage_payload={}).outcome == "settled"
    source = CanonicalSourceReceipt(
        source_receipt_id="source-1",
        question_id="q-1",
        document_id="doc-1",
        chunk_id="chunk-1",
        excerpt_sha256=excerpt_sha,
    )
    result = runtime.engine().engine.run_current_stage(
        stage_payload={"excerpts": [{"source_receipt_id": "source-1", "text": text}]},
        source_receipts=(source,),
    )
    assert result.outcome == "rejected_settled"
    assert runtime.queue.get(OPERATION).next_step_index == 1  # type: ignore[union-attr]
