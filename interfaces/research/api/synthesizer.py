"""Synthesizer role bridge (Sprint 7 day 5 — last orchestrate.py role
bridge; closes Loop 1's role chain end-to-end).

Subscribes to ``synthesize.requested`` events. Per request:

1. Renders the synthesizer prompt with the five input blocks.
2. Dispatches the ``synthesizer`` role (Synthesis tier per
   ``substrate/dispatch/config.yaml``).
3. Parses + validates the response.
4. **Wires the constraint loop** (Sprint 7 day 3 machinery): if the
   request supplied non-empty ``constraints``, the bridge constructs
   ``Claim`` objects from the thesis components and drives
   ``run_constraint_loop`` with a re-invoke callable that
   re-dispatches the synthesizer with ``build_revision_prefix``
   prepended.
5. Emits ``SYNTHESIZE_DELIVERED`` carrying the **final** (loop-
   converged) thesis plus the loop's terminal status + iteration
   count.

The constraint loop machinery itself emits its per-iteration
CONSTRAINT_VIOLATION_FOUND / CONSTRAINT_REVISION_TRIGGERED /
CONSTRAINT_LOOP_RESOLVED events; this bridge does NOT duplicate
them.

Failure-mode discipline:

- Provider unavailable on the FIRST dispatch → fallback Delivered
  with empty thesis + ``insufficient_evidence``, policy stamped
  ``synthesizer-fallback/no-provider``. No constraint loop runs.
- Parse failure on the FIRST dispatch → same fallback shape;
  dispatch policy_id preserved.
- Provider/parse failure on a LOOP revision → the loop catches the
  ``None`` claims return and treats it as no-progress; the loop's
  own ``max_iterations_reached`` / ``regressed`` terminus fires.
"""

from __future__ import annotations

import os
import sys
from typing import List, Optional

# Direct import — interfaces/research/api/ depends on substrate + roles.
_PKG_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from middleware.constraint_check import (  # noqa: E402
    ConstraintLoopResult,
    run_constraint_loop,
)
from substrate.dispatch import ProviderError, dispatch  # noqa: E402
from substrate.event_log import emit_typed, trajectory  # noqa: E402
from substrate.schemas import (  # noqa: E402
    ActionType,
    Claim,
    ConstraintCompliance,
    Event,
    ExecutionRisk,
    FalsificationCondition,
    ReasoningPathUsed,
    SynthesizeDeliveredPayload,
    SynthesizeRequestedPayload,
    ThesisComponent,
    ViolationJustification,
)
from roles.synthesizer import (  # noqa: E402
    SynthesizerValidationError,
    ThesisResult,
    build_revision_prefix,
    parse_synthesizer_response,
    render_full_prompt,
)

from .broadcast import EventBroadcaster


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _result_to_thesis_components(result: ThesisResult) -> list[ThesisComponent]:
    return [
        ThesisComponent(
            claim=c.claim,
            confidence=c.confidence,  # type: ignore[arg-type]
            supporting_chunk_ids=list(c.supporting_chunk_ids),
            supporting_path_indices=list(c.supporting_path_indices),
            confidence_basis=c.confidence_basis,
            effective_source_tier=c.effective_source_tier,
            hedging_required=c.hedging_required,
        )
        for c in result.thesis_components
    ]


def _result_to_falsifications(result: ThesisResult) -> list[FalsificationCondition]:
    return [
        FalsificationCondition(
            condition=f.condition,
            specific_observable=f.specific_observable,
            timeframe=f.timeframe,
        )
        for f in result.falsification_conditions
    ]


def _result_to_execution_risks(result: ThesisResult) -> list[ExecutionRisk]:
    return [
        ExecutionRisk(
            risk=r.risk,
            severity_if_manifested=r.severity_if_manifested,  # type: ignore[arg-type]
            leading_indicator=r.leading_indicator,
        )
        for r in result.execution_risks
    ]


def _result_to_constraint_compliance(result: ThesisResult) -> ConstraintCompliance:
    return ConstraintCompliance(
        hard_constraints_satisfied=result.constraint_compliance.hard_constraints_satisfied,
        soft_constraints_violated=list(result.constraint_compliance.soft_constraints_violated),
        violations_justified=[
            ViolationJustification(
                constraint=v.constraint, justification=v.justification,
            )
            for v in result.constraint_compliance.violations_justified
        ],
    )


def _result_to_reasoning_paths(result: ThesisResult) -> list[ReasoningPathUsed]:
    return [
        ReasoningPathUsed(
            path_node_ids=list(p.path_node_ids),
            path_edge_ids=list(p.path_edge_ids),
            support_summary=p.support_summary,
        )
        for p in result.reasoning_paths_used
    ]


def _result_to_claims(result: ThesisResult) -> List[Claim]:
    """Convert the parsed thesis components into ``Claim`` Pydantic
    models the constraint-loop evaluator reads. ``attribution_region_ids``
    is populated from ``supporting_chunk_ids`` (the chunk acts as the
    attribution anchor for the ``must_attribute`` checker)."""
    claims: List[Claim] = []
    for i, c in enumerate(result.thesis_components):
        claims.append(Claim(
            claim_id=f"synth-{i}",
            text=c.claim,
            confidence=c.confidence,  # type: ignore[arg-type]
            attribution_region_ids=list(c.supporting_chunk_ids),
        ))
    return claims


def _empty_delivered_payload(
    *,
    status: str = "single_pass",
    iterations: int = 1,
) -> SynthesizeDeliveredPayload:
    """Fallback shape — empty thesis with ``insufficient_evidence``
    recommendation. The trajectory shows the request was answered;
    downstream consumers can tell from the empty components that the
    synth failed."""
    return SynthesizeDeliveredPayload(
        thesis_summary="",
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
        conviction_level=None,
        constraint_loop_status=status,  # type: ignore[arg-type]
        constraint_loop_iterations=iterations,
    )


# ---------------------------------------------------------------------------
# Dispatch + parse
# ---------------------------------------------------------------------------


def _dispatch_once(prompt: str, event: Event) -> tuple[Optional[str], str]:
    """One dispatch attempt. Returns (response_text, policy_id) or
    (None, fallback_policy_id) on ProviderError / KeyError."""
    try:
        result = dispatch(
            prompt,
            "synthesizer",
            investigation_id=event.investigation_id,
            parent_event_id=event.event_id,
        )
        return result.text, f"{result.provider}/{result.model}"
    except (ProviderError, KeyError) as exc:
        print(
            f"synthesizer.handle: dispatch failed — "
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )
        return None, "synthesizer-fallback/no-provider"


def _dispatch_and_parse(
    prompt: str,
    event: Event,
    *,
    rerender_with_prefix=None,
) -> tuple[Optional[ThesisResult], str]:
    """Dispatch + parse with one self-repair retry on parse failure.

    When the model produces structurally-malformed output (typically:
    empty ``falsification_conditions``, missing top-level keys, etc.)
    the bridge gives the model ONE chance to fix it by re-dispatching
    with the validation error prepended. If the retry also fails to
    parse, returns ``(None, policy_id)`` and the caller falls through
    to the empty-delivered shape (existing contract).

    ``rerender_with_prefix(prefix: str) -> str`` is an optional
    closure that lets the caller re-render the full prompt with a
    user-template prefix. When omitted, the retry simply prepends to
    the original prompt — adequate for the parse-failure case where
    the model needs to see what was structurally wrong with its
    previous attempt."""
    response_text, policy_id = _dispatch_once(prompt, event)
    if response_text is None:
        return None, policy_id

    try:
        return parse_synthesizer_response(response_text), policy_id
    except SynthesizerValidationError as exc:
        first_error = exc
        print(
            f"synthesizer.handle: parse failed — {first_error} — attempting one self-repair",
            flush=True,
        )

    # 2026-05-18 H2.5: one self-repair attempt. The synthesizer's
    # response was structurally wrong; tell the model exactly what
    # was wrong and re-dispatch. Most observed grok-4.3 failure modes
    # (empty falsification_conditions, missing keys, wrong recommendation
    # vocabulary) recover on a single retry once the model sees its
    # own mistake described.
    repair_prefix = (
        "Your previous response failed the substrate's structural "
        "contract with the following error:\n\n"
        f"    {first_error!s}\n\n"
        "This is your one and only chance to fix it. Produce a "
        "response that satisfies the contract above. Pay particular "
        "attention to the substrate's non-negotiable constraints in "
        "the system prompt — they are not stylistic preferences.\n\n"
        "----\n\n"
    )
    if rerender_with_prefix is not None:
        retry_prompt = rerender_with_prefix(repair_prefix)
    else:
        retry_prompt = repair_prefix + prompt

    retry_text, retry_policy = _dispatch_once(retry_prompt, event)
    if retry_text is None:
        return None, retry_policy

    try:
        return parse_synthesizer_response(retry_text), retry_policy
    except SynthesizerValidationError as exc2:
        print(
            f"synthesizer.handle: self-repair retry also failed — {exc2}",
            flush=True,
        )
        return None, retry_policy


# ---------------------------------------------------------------------------
# Handler factory
# ---------------------------------------------------------------------------


def make_synthesizer_handler(broadcaster: EventBroadcaster):
    """Build the synthesizer handler. Registered against
    ``ActionType.SYNTHESIZE_REQUESTED``."""

    async def handle_synthesize_request(event: Event) -> None:
        if not isinstance(event.payload, SynthesizeRequestedPayload):
            return
        req = event.payload

        # ── 1. First dispatch ──
        first_prompt = render_full_prompt(
            question=req.question,
            decomposition_block=req.decomposition_block,
            evidence_block=req.evidence_block,
            parameters_block=req.parameters_block,
            substrate_block=req.substrate_block,
        )
        first_result, policy_id = _dispatch_and_parse(first_prompt, event)
        if first_result is None:
            await _emit_delivered(
                event,
                payload=_empty_delivered_payload(),
                policy_id=policy_id,
                broadcaster=broadcaster,
            )
            return

        # ── 2. Constraint loop (if constraints supplied) ──
        # The loop's re-invoke callable re-dispatches the synthesizer
        # with the violation context prepended. When the loop has no
        # constraints, ``run_constraint_loop`` short-circuits to
        # ``single_pass`` after one no-op iteration — that's exactly
        # the behavior we want for unconstrained syntheses.
        latest_result: ThesisResult = first_result

        def synthesizer_callable(violations, iteration):
            nonlocal latest_result
            prefix = build_revision_prefix(violations)
            revised_prompt = render_full_prompt(
                question=req.question,
                decomposition_block=req.decomposition_block,
                evidence_block=req.evidence_block,
                parameters_block=req.parameters_block,
                substrate_block=req.substrate_block,
                extra_user_prefix=prefix,
            )
            revised_result, _revised_policy = _dispatch_and_parse(
                revised_prompt, event,
            )
            if revised_result is None:
                # Loop receives the previous claims unchanged. The
                # loop will detect no improvement and exit
                # ``regressed`` or ``max_iterations_reached``
                # depending on iteration index.
                return _result_to_claims(latest_result)
            latest_result = revised_result
            return _result_to_claims(revised_result)

        loop_result: ConstraintLoopResult = run_constraint_loop(
            investigation_id=event.investigation_id,
            initial_claims=_result_to_claims(first_result),
            constraints=list(req.constraints),
            synthesizer_callable=synthesizer_callable,
            parent_event_id=event.event_id,
        )

        # ── 3. Emit Delivered with the loop-converged thesis ──
        final_result = latest_result
        await _emit_delivered(
            event,
            payload=SynthesizeDeliveredPayload(
                thesis_summary=final_result.thesis_summary,
                implicit_recommendation=final_result.implicit_recommendation,  # type: ignore[arg-type]
                thesis_components=_result_to_thesis_components(final_result),
                falsification_conditions=_result_to_falsifications(final_result),
                execution_risks=_result_to_execution_risks(final_result),
                constraint_compliance=_result_to_constraint_compliance(final_result),
                reasoning_paths_used=_result_to_reasoning_paths(final_result),
                conviction_level=final_result.conviction_level,
                constraint_loop_status=loop_result.final_status,  # type: ignore[arg-type]
                constraint_loop_iterations=loop_result.total_iterations,
            ),
            policy_id=policy_id,
            broadcaster=broadcaster,
        )

    return handle_synthesize_request


# ---------------------------------------------------------------------------
# Emit helpers
# ---------------------------------------------------------------------------


async def _emit_delivered(
    event: Event,
    *,
    payload: SynthesizeDeliveredPayload,
    policy_id: str,
    broadcaster: EventBroadcaster,
) -> None:
    eid = emit_typed(
        event.investigation_id,
        payload,
        parent_event_id=event.event_id,
        role="synthesizer",
        policy_id=policy_id,
    )
    await _broadcast_emitted(event, eid, broadcaster)


async def _broadcast_emitted(
    event: Event,
    emitted_event_id: Optional[str],
    broadcaster: EventBroadcaster,
) -> None:
    if emitted_event_id is None:
        return
    for row in reversed(trajectory(event.investigation_id)):
        if row.get("event_id") == emitted_event_id:
            try:
                emitted = Event.model_validate(row)
                await broadcaster.broadcast(emitted)
            except Exception:  # pragma: no cover — never block on broadcast
                pass
            return


def register_handlers(broadcaster: EventBroadcaster) -> None:
    """Wire the synthesizer handler into the broadcaster. Called once
    at app startup from ``app.create_app``."""
    broadcaster.register_handler(
        ActionType.SYNTHESIZE_REQUESTED.value,
        make_synthesizer_handler(broadcaster),
    )
