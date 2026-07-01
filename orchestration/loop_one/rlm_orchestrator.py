"""RLM-kind investigation entrypoint.

Sprint 13 splits ``investigation.start_requested`` into two lanes:
``loop_one`` keeps the fixed phase chain, while ``rlm`` starts the
open-ended RLM lane. This module owns the latter subscription boundary.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from threading import Lock
from typing import Any

from interfaces.research.api.broadcast import EventBroadcaster
from interfaces.research.rlm_dag import Dag
from interfaces.research.rlm_dag import execute_dag as _execute_dag
from interfaces.research.rlm_repl import ReplSummary, RLMRepl
from orchestration.phase_runner import (
    assert_ready_for_completion,
    enter_phase,
    exit_phase,
    verify_phase,
)
from orchestration.rlm.runner import run_loop_with_timeout
from orchestration.rlm.session import (
    RLM_DEFAULT_MAX_ITERATIONS,
    RLMRatificationRequired,
    RLMSession,
    create_session,
    session_failed_payload,
    session_started_payload,
    sub_call_dispatched_payload,
)
from substrate.dispatch import dispatch
from substrate.dispatch.base import ProviderError
from substrate.graph.rlm_tools import search_graph as _search_graph
from substrate.schemas import (
    ActionType,
    ConstraintCompliance,
    Event,
    InvestigationCompletedPayload,
    InvestigationFailedPayload,
    InvestigationStartRequestedPayload,
    RLMSubCallDispatchedPayload,
    SynthesizeDeliveredPayload,
)

from .coordinator import broadcast_emit
from .orchestrator import InvestigationContext, _run_phase_7

RLM_INVESTIGATION_POLICY_ID = "rlm-orchestrator/root-repl"


def _action_value(action_type) -> str:
    return action_type.value if hasattr(action_type, "value") else str(action_type)


@dataclass(frozen=True)
class _LLMResult:
    text: str
    tier: str
    cost_usd: Decimal


LLMQueryFn = Callable[[str], str | _LLMResult]
LLMBatchFn = Callable[[list[str]], list[str] | tuple[list[str], str, Decimal]]
GenerateCodeFn = Callable[[ReplSummary], str | _LLMResult]
SearchGraphFn = Callable[[str, int], str]
ExecuteDagFn = Callable[..., Any]


class _PersistedRLMEmitter:
    """Adapter expected by ``run_loop_with_timeout``.

    ``RLMEventEmitter`` broadcasts in-memory events; investigation sessions
    need durable JSONL trajectory rows, so this adapter emits through the same
    ``broadcast_emit`` path used by Loop-One.
    """

    def __init__(
        self,
        broadcaster: EventBroadcaster,
        *,
        investigation_id: str,
        role: str = "rlm_orchestrator",
        policy_id: str = RLM_INVESTIGATION_POLICY_ID,
    ) -> None:
        self._broadcaster = broadcaster
        self._investigation_id = investigation_id
        self._role = role
        self._policy_id = policy_id

    async def emit(self, payload):
        event_id = await broadcast_emit(
            self._broadcaster,
            self._investigation_id,
            payload,
            role=self._role,
            policy_id=self._policy_id,
        )
        return type("_EmittedRLMEvent", (), {
            "event_id": event_id,
            "action_type": payload.action_type,
        })()


def _coerce_llm_result(value: str | _LLMResult) -> _LLMResult:
    if isinstance(value, _LLMResult):
        return value
    return _LLMResult(text=str(value), tier="injected", cost_usd=Decimal("0.00"))


def _dispatch_llm_query(
    prompt: str,
    *,
    investigation_id: str,
    parent_event_id: str,
) -> _LLMResult:
    result = dispatch(
        prompt,
        "synthesizer",
        investigation_id=investigation_id,
        parent_event_id=parent_event_id,
    )
    return _LLMResult(
        text=result.text,
        tier=result.tier,
        cost_usd=Decimal(str(result.cost_usd)),
    )


def _install_root_tools(
    repl: RLMRepl,
    *,
    session: RLMSession,
    event: Event,
    pending_sub_calls: list[RLMSubCallDispatchedPayload],
    pending_sub_calls_lock: Lock,
    llm_query_fn: LLMQueryFn | None,
    llm_batch_fn: LLMBatchFn | None,
    search_graph_fn: SearchGraphFn,
    execute_dag_fn: ExecuteDagFn,
) -> None:
    def queue_sub_call(*, prompt_count: int, tier: str, cost_usd: Decimal) -> None:
        payload = sub_call_dispatched_payload(
            session,
            target_role="rlm_orchestrator",
            tier=tier,
            prompt_count=prompt_count,
            parent_event_id=event.event_id,
            cost_usd=cost_usd,
        )
        with pending_sub_calls_lock:
            pending_sub_calls.append(payload)

    def llm_query(prompt: str) -> str:
        if llm_query_fn is None:
            result = _dispatch_llm_query(
                prompt,
                investigation_id=event.investigation_id,
                parent_event_id=event.event_id,
            )
        else:
            result = _coerce_llm_result(llm_query_fn(prompt))
        queue_sub_call(prompt_count=1, tier=result.tier, cost_usd=result.cost_usd)
        return result.text

    def llm_batch(prompts: list[str]) -> list[str]:
        if llm_batch_fn is not None:
            value = llm_batch_fn([str(prompt) for prompt in prompts])
            if isinstance(value, tuple):
                outputs, tier, cost_usd = value
                result_outputs = [str(output) for output in outputs]
                queue_sub_call(
                    prompt_count=len(result_outputs),
                    tier=tier,
                    cost_usd=Decimal(str(cost_usd)),
                )
                return result_outputs
            result_outputs = [str(output) for output in value]
            queue_sub_call(
                prompt_count=len(result_outputs),
                tier="injected",
                cost_usd=Decimal("0.00"),
            )
            return result_outputs

        outputs: list[str] = []
        total_cost = Decimal("0.00")
        tier = "batch"
        for prompt in prompts:
            result = _dispatch_llm_query(
                str(prompt),
                investigation_id=event.investigation_id,
                parent_event_id=event.event_id,
            )
            outputs.append(result.text)
            total_cost += result.cost_usd
            tier = result.tier
        queue_sub_call(prompt_count=len(prompts), tier=tier, cost_usd=total_cost)
        return outputs

    def search_graph(query: str, top_k: int = 5) -> str:
        return search_graph_fn(str(query), int(top_k))

    def execute_dag(plan_or_dag, *, max_retries_per_node: int = 2):
        dag = (
            plan_or_dag
            if isinstance(plan_or_dag, Dag)
            else Dag.from_plan_json(dict(plan_or_dag))
        )
        return execute_dag_fn(
            dag,
            llm_query,
            llm_batch,
            max_retries_per_node=max_retries_per_node,
        ).final_answer()

    repl.registry.install("llm_query", llm_query)
    repl.registry.install("llm_batch", llm_batch)
    repl.registry.install("search_graph", search_graph)
    repl.registry.install("execute_dag", execute_dag)


def _default_generate_code(
    summary: ReplSummary,
    *,
    event: Event,
    root_prompt: str,
) -> _LLMResult:
    return _dispatch_llm_query(
        "\n\n".join([root_prompt, summary.format_for_prompt()]),
        investigation_id=event.investigation_id,
        parent_event_id=event.event_id,
    )


def _synthesis_from_rlm_answer(final_answer: str) -> SynthesizeDeliveredPayload:
    summary = final_answer.strip() or "RLM completed without a terminal answer."
    return SynthesizeDeliveredPayload(
        thesis_summary=summary,
        implicit_recommendation="insufficient_evidence",
        thesis_components=[],
        falsification_conditions=[],
        execution_risks=[],
        constraint_compliance=ConstraintCompliance(
            hard_constraints_satisfied=False,
            soft_constraints_violated=[],
            violations_justified=[],
        ),
        reasoning_paths_used=[],
        constraint_loop_status="single_pass",
        constraint_loop_iterations=1,
    )


async def _verify_phase_noop(
    *,
    investigation_id: str,
    phase: int,
    note: str,
) -> bool:
    enter_phase(investigation_id, phase, note=note)
    exit_phase(investigation_id, phase)
    outcome = verify_phase(investigation_id, phase)
    return outcome.passed


async def _verify_rlm_skipped_loop_one_phases(investigation_id: str) -> bool:
    for phase in range(1, 6):
        ok = await _verify_phase_noop(
            investigation_id=investigation_id,
            phase=phase,
            note=(
                "RLM-kind investigation: Loop-One artifact phase skipped; "
                "RLM iteration events are the upstream evidence"
            ),
        )
        if not ok:
            return False
    return True


async def _deliver_terminal_answer(
    *,
    broadcaster: EventBroadcaster,
    event: Event,
    req: InvestigationStartRequestedPayload,
    final_answer: str,
) -> None:
    synthesis = _synthesis_from_rlm_answer(final_answer)
    await broadcast_emit(
        broadcaster,
        event.investigation_id,
        synthesis,
        role="rlm_orchestrator",
        policy_id=RLM_INVESTIGATION_POLICY_ID,
    )

    if not await _verify_rlm_skipped_loop_one_phases(event.investigation_id):
        await broadcast_emit(
            broadcaster,
            event.investigation_id,
            InvestigationFailedPayload(
                phase=1,
                reason="RLM Loop-One skipped-phase verification failed",
                last_completed_phase=None,
            ),
            role="rlm_orchestrator",
            policy_id=RLM_INVESTIGATION_POLICY_ID,
        )
        return

    if not await _verify_phase_noop(
        investigation_id=event.investigation_id,
        phase=6,
        note="RLM terminal synthesis delivered",
    ):
        await broadcast_emit(
            broadcaster,
            event.investigation_id,
            InvestigationFailedPayload(
                phase=6,
                reason="RLM terminal synthesis failed phase 6 verification",
                last_completed_phase=None,
            ),
            role="rlm_orchestrator",
            policy_id=RLM_INVESTIGATION_POLICY_ID,
        )
        return

    ctx = InvestigationContext(
        investigation_id=event.investigation_id,
        question=req.question,
        context=req.context,
        topic_slug=req.topic_slug,
        max_sub_questions=req.max_sub_questions,
        synthesis=synthesis,
        last_completed_phase=6,
        parent_investigation_id=req.parent_investigation_id,
        research_tier=req.research_tier,
    )
    if not await _run_phase_7(ctx):
        await broadcast_emit(
            broadcaster,
            event.investigation_id,
            InvestigationFailedPayload(
                phase=ctx.failed_phase or 7,
                reason=ctx.fail_reason or "RLM phase 7 delivery failed",
                last_completed_phase=6,
            ),
            role="rlm_orchestrator",
            policy_id=RLM_INVESTIGATION_POLICY_ID,
        )
        return

    if not await _verify_phase_noop(
        investigation_id=event.investigation_id,
        phase=8,
        note=(
            "RLM insufficient-evidence terminal answer; Phase 8 no-op "
            "verified by postcondition"
        ),
    ):
        await broadcast_emit(
            broadcaster,
            event.investigation_id,
            InvestigationFailedPayload(
                phase=8,
                reason="RLM phase 8 no-op verification failed",
                last_completed_phase=7,
            ),
            role="rlm_orchestrator",
            policy_id=RLM_INVESTIGATION_POLICY_ID,
        )
        return
    ctx.last_completed_phase = 8

    try:
        assert_ready_for_completion(event.investigation_id)
    except Exception as exc:
        await broadcast_emit(
            broadcaster,
            event.investigation_id,
            InvestigationFailedPayload(
                phase=9,
                reason=f"assert_ready_for_completion failed: {exc!r}",
                last_completed_phase=8,
            ),
            role="rlm_orchestrator",
            policy_id=RLM_INVESTIGATION_POLICY_ID,
        )
        return

    await broadcast_emit(
        broadcaster,
        event.investigation_id,
        InvestigationCompletedPayload(
            thesis_summary=synthesis.thesis_summary,
            implicit_recommendation=synthesis.implicit_recommendation,
            constraint_loop_status=synthesis.constraint_loop_status,
            constraint_loop_iterations=synthesis.constraint_loop_iterations,
            master_md_path=ctx.master_md_path,
            domains_patched=[],
            total_phases_verified=ctx.last_completed_phase,
        ),
        role="rlm_orchestrator",
        policy_id=RLM_INVESTIGATION_POLICY_ID,
    )


def make_rlm_investigation_handler(
    broadcaster: EventBroadcaster,
    *,
    generate_code_fn: GenerateCodeFn | None = None,
    llm_query_fn: LLMQueryFn | None = None,
    llm_batch_fn: LLMBatchFn | None = None,
    search_graph_fn: SearchGraphFn = _search_graph,
    execute_dag_fn: ExecuteDagFn = _execute_dag,
):
    """Build the RLM-kind handler for ``investigation.start_requested``.

    This is the bootstrap lane wiring: it proves routing, ratification,
    session event emission, and per-investigation isolation. The real root
    planner can replace the deterministic iteration body without changing the
    event subscription contract.
    """

    async def handle_investigation_start(event: Event) -> None:
        if not isinstance(event.payload, InvestigationStartRequestedPayload):
            return
        req = event.payload
        if req.investigation_kind != "rlm":
            return

        try:
            session = create_session(
                investigation_id=event.investigation_id,
                root_role="rlm_orchestrator",
            )
        except RLMRatificationRequired as exc:
            await broadcast_emit(
                broadcaster,
                event.investigation_id,
                InvestigationFailedPayload(
                    phase=1,
                    reason=str(exc),
                    last_completed_phase=None,
                ),
                role="rlm_orchestrator",
                policy_id="rlm-orchestrator/ratification-gate",
            )
            return

        await broadcast_emit(
            broadcaster,
            event.investigation_id,
            session_started_payload(session),
            role="rlm_orchestrator",
            policy_id=RLM_INVESTIGATION_POLICY_ID,
        )

        root_prompt = (
            "You are the RLM root for an open-ended Antiek investigation. "
            "The operator question is in the Python variable question. Use "
            "llm_batch for parallel sub-questions, search_graph for substrate "
            "retrieval, and execute_dag for structured plans. Set "
            "answer['content'] to the terminal synthesis and answer['ready'] "
            "= True when done."
        )
        repl = RLMRepl(
            corpus={
                "question": req.question,
                "context": req.context,
                "topic_slug": req.topic_slug,
                "root_prompt": root_prompt,
            },
            max_iterations=RLM_DEFAULT_MAX_ITERATIONS,
        )

        pending_sub_calls: list[RLMSubCallDispatchedPayload] = []
        pending_sub_calls_lock = Lock()
        _install_root_tools(
            repl,
            session=session,
            event=event,
            pending_sub_calls=pending_sub_calls,
            pending_sub_calls_lock=pending_sub_calls_lock,
            llm_query_fn=llm_query_fn,
            llm_batch_fn=llm_batch_fn,
            search_graph_fn=search_graph_fn,
            execute_dag_fn=execute_dag_fn,
        )

        emitter = _PersistedRLMEmitter(
            broadcaster,
            investigation_id=event.investigation_id,
        )
        last_codegen_cost = Decimal("0.00")

        async def flush_sub_calls() -> None:
            with pending_sub_calls_lock:
                payloads = list(pending_sub_calls)
                pending_sub_calls.clear()
            for payload in payloads:
                await emitter.emit(payload)

        def generate_code(summary: ReplSummary) -> str:
            nonlocal last_codegen_cost
            if generate_code_fn is None:
                result = _default_generate_code(
                    summary,
                    event=event,
                    root_prompt=root_prompt,
                )
            else:
                result = _coerce_llm_result(generate_code_fn(summary))
            last_codegen_cost = result.cost_usd
            return result.text

        try:
            loop_result = await run_loop_with_timeout(
                repl=repl,
                generate_code=generate_code,
                session=session,
                emitter=emitter,
                cost_usd=lambda _summary, _code: last_codegen_cost,
                iteration_summary=lambda summary, _code: (
                    f"RLM investigation iteration {summary.iteration + 1}"
                ),
                after_execute=flush_sub_calls,
            )
        except (ProviderError, KeyError) as exc:
            session.fail()
            await emitter.emit(
                session_failed_payload(
                    session,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
            )
            return

        if loop_result.status == "completed":
            await _deliver_terminal_answer(
                broadcaster=broadcaster,
                event=event,
                req=req,
                final_answer=loop_result.final_answer,
            )

    return handle_investigation_start


def register_handlers(broadcaster: EventBroadcaster) -> None:
    broadcaster.register_handler(
        _action_value(ActionType.INVESTIGATION_START_REQUESTED),
        make_rlm_investigation_handler(broadcaster),
    )


__all__ = ["make_rlm_investigation_handler", "register_handlers"]
