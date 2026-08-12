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

import json
import os
import sys
from collections.abc import Awaitable, Callable
from typing import Any

# Direct import — interfaces/research/api/ depends on substrate + roles.
_PKG_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from middleware.constraint_check import (  # noqa: E402
    ConstraintLoopResult,
    Violation,
    run_constraint_loop,
)
from roles.synthesizer import (  # noqa: E402
    SynthesizerValidationError,
    ThesisResult,
    build_revision_prefix,
    parse_synthesizer_response,
    render_full_prompt,
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

from .broadcast import EventBroadcaster  # noqa: E402 — after the sys.path bootstrap above

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


def _result_to_claims(result: ThesisResult) -> list[Claim]:
    """Convert the parsed thesis components into ``Claim`` Pydantic
    models the constraint-loop evaluator reads. ``attribution_region_ids``
    is populated from ``supporting_chunk_ids`` (the chunk acts as the
    attribution anchor for the ``must_attribute`` checker)."""
    claims: list[Claim] = []
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


def _collect_refs_from_json_block(block: str, keys: set[str]) -> tuple[str, ...]:
    try:
        value = json.loads(block)
    except json.JSONDecodeError:
        return ()

    out: list[str] = []
    seen: set[str] = set()

    def collect(item: Any) -> None:
        if isinstance(item, str):
            cleaned = item.strip()
            if cleaned and cleaned not in seen:
                out.append(cleaned)
                seen.add(cleaned)
        elif isinstance(item, list):
            for child in item:
                collect(child)

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if key in keys:
                    collect(child)
                else:
                    visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return tuple(out)


def _extract_bracketed_line_ids(block: str) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line.startswith("[") or "]" not in line:
            continue
        ref_id = line[1:].split("]", 1)[0].strip()
        if not ref_id or any(
            ch.isspace() or ch in '{}[]":,' for ch in ref_id
        ):
            continue
        if ref_id and ref_id not in seen:
            out.append(ref_id)
            seen.add(ref_id)
    return tuple(out)


def _merge_refs(*groups: tuple[str, ...]) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for ref in group:
            if ref not in seen:
                out.append(ref)
                seen.add(ref)
    return tuple(out)


def _canonical_refs_for_request(req: SynthesizeRequestedPayload) -> tuple[
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
]:
    chunk_ids = _merge_refs(
        _collect_refs_from_json_block(
            req.evidence_block,
            {"chunk_id", "chunk_ids", "source_chunk_ids"},
        ),
        _collect_refs_from_json_block(
            req.parameters_block,
            {"chunk_id", "chunk_ids", "source_chunk_ids"},
        ),
        _extract_bracketed_line_ids(req.evidence_block),
    )
    node_ids = _collect_refs_from_json_block(
        req.substrate_block,
        {"node_id", "node_ids", "path_node_ids"},
    )
    edge_ids = _collect_refs_from_json_block(
        req.substrate_block,
        {"edge_id", "edge_ids", "path_edge_ids"},
    )
    return chunk_ids, node_ids, edge_ids


# ---------------------------------------------------------------------------
# Dispatch + parse
# ---------------------------------------------------------------------------


def _research_tier_override(
    investigation_id: str,
) -> tuple[str | None, str | None]:
    """Resolve the (provider, model) research-tier override for THIS
    investigation's SYNTHESIZER dispatch, READ from the persisted start
    event. Returns ``(provider, model)`` to swap the synthesizer's config
    primary, or ``(None, None)`` to leave the config pin untouched.

    §14.4 GUARD (SPR-01 / Foundation — the load-bearing reason this is NOT
    "consume the recorded tier unconditionally"):
    ------------------------------------------------------------------
    The ``synthesis`` tier is PINNED to ``zai_reasoning / glm-5.2`` in
    config.yaml — the claude-less posture (#213, 2026-07-06): every tier's
    primary is GLM-5.2, synthesis with thinking ENABLED as the reasoned
    replacement for the prior Opus synthesis. The §14.4 measurement window
    (2026-05-19 → Sprint-20) has CLOSED; Opus is no longer in the footprint,
    but this guard's RULE still holds — it now protects the GLM-5.2 synthesis
    pin from being displaced by a research-tier choice. The synthesizer is a
    DIFFERENT role from the research-runner: the fast/deep research-tier
    choice governs the RESEARCH lane (which provider does the reasoning-heavy
    retrieval/decomposition work), NOT the synthesis voice.

    The defect this guards: the start-event ``research_tier`` used to
    default to "deep" (== DEFAULT_RESEARCH_TIER). A schema-DEFAULT "deep"
    was byte-indistinguishable from an operator-EXPLICIT "deep", so the
    instant ``DEEPSEEK_API_KEY`` was set (the literal "turn the AI on"
    deploy), every default investigation's synthesis silently routed onto
    DeepSeek and §14.4 was voided. The only prior guard was provider-
    absence — which evaporates the moment the key is present.

    THE RULE (hard-to-vary): while the §14.4 window is open, NO research-tier
    choice — fast, deep, the schema default, or none — may displace the
    synthesizer's config pin. The function therefore returns (None, None)
    for EVERY recorded tier. Concretely:
      • no start event / no recorded tier (legacy runs)      → (None, None)
      • recorded tier is null  (schema default "no choice")  → (None, None)
      • recorded tier == DEFAULT_RESEARCH_TIER ("deep")      → (None, None)
      • recorded tier is explicit "fast"                     → (None, None)

    WHY the pin holds for EVERY tier (the sharpen-round correction): an
    earlier cut fired the override for an explicit non-default tier ("fast"
    → MiMo). That CONTRADICTED §14.4's own rationale — the window exists to
    measure Opus on the human-read artifact, and routing synthesis onto MiMo
    for fast investigations corrupts exactly the traffic the verdict is taken
    over. "The fast/deep choice is most felt at synthesis" is the steelman
    for letting it through (recorded in the SPR-01 handoff); it loses during
    the window because §14.4 measures the SYNTHESIS VOICE, and a measurement
    taken over mixed Opus/MiMo voices answers no question. The tier choice
    still does real work — it routes the RESEARCH lane (below) — it simply
    does not touch synthesis until the pin lifts.

    The function reads the recorded tier (rather than short-circuiting to
    (None, None) on line one) on purpose: it keeps the start-event read as
    the single point where the SUNSET lands, so when the Sprint-20 verdict
    flips the pin, the per-tier synthesizer routing is re-enabled HERE with
    one diff and the regression guard (tests/test_dispatch_synthesis_pin.py)
    is the thing that flips with it — not scattered across call sites.

    PRESERVED: this function feeds ONLY the synthesizer. The research-runner
    lane still resolves DEFAULT_RESEARCH_TIER / an explicit "deep" / "fast"
    to its provider via ``resolve_research_tier`` at its OWN call site —
    DEFAULT_RESEARCH_TIER's meaning for the research lane is UNCHANGED.

    SUNSET: when the Sprint-20 §14.4 verdict is recorded (or the window
    auto-reverts), this guard's reason expires — see config.yaml ``synthesis``
    tier and the SPR-06 invariant declaration. Lifting the guard is an
    operator-ratified edit, not a silent one: re-enable the per-tier
    override for explicit, non-default tiers below, and flip the matching
    assertions in test_dispatch_synthesis_pin.py."""
    start_action = ActionType.INVESTIGATION_START_REQUESTED.value
    try:
        rows = trajectory(investigation_id)
    except Exception:  # pragma: no cover — diagnostic; never block synthesis
        return None, None
    for r in rows:
        if r.get("action_type") == start_action:
            payload = r.get("payload")
            if isinstance(payload, dict):
                _recorded = payload.get("research_tier")  # noqa: F841
                # §14.4 (window open): whatever was recorded — fast, deep,
                # the default, or nothing — the synthesizer keeps its config
                # pin. The recorded tier governs the research lane elsewhere,
                # never the synthesis voice. SUNSET (Sprint-20 verdict):
                # resolve `_recorded` to a (provider, model) here ONLY for an
                # explicit non-default tier whose provider is live, e.g.
                #     if _recorded and _recorded != DEFAULT_RESEARCH_TIER:
                #         t = resolve_research_tier(_recorded)
                #         if t.provider in _PROVIDER_REGISTRY:
                #             return t.provider, t.model
            break
    return None, None


def _dispatch_once(prompt: str, event: Event, *, attempt: int = 0) -> tuple[str | None, str]:
    """One dispatch attempt. Returns (response_text, policy_id) or
    (None, fallback_policy_id) on ProviderError / KeyError."""
    provider_override, model_override = _research_tier_override(
        event.investigation_id,
    )
    try:
        from .research_owner_dispatch import dispatch_loop_one
        result = dispatch_loop_one(prompt, "synthesizer", investigation_id=event.investigation_id,
                                   semantic_call_id="phase6", attempt=attempt) or dispatch(
            prompt,
            "synthesizer",
            investigation_id=event.investigation_id,
            parent_event_id=event.event_id,
            provider_override=provider_override,
            model_override=model_override,
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
    rerender_with_prefix: Callable[[str], str] | None = None,
    canonical_chunk_ids: tuple[str, ...] = (),
    canonical_node_ids: tuple[str, ...] = (),
    canonical_edge_ids: tuple[str, ...] = (),
) -> tuple[ThesisResult | None, str]:
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
    response_text, policy_id = _dispatch_once(prompt, event, attempt=0)
    if response_text is None:
        return None, policy_id

    try:
        return parse_synthesizer_response(
            response_text,
            canonical_chunk_ids=canonical_chunk_ids,
            canonical_node_ids=canonical_node_ids,
            canonical_edge_ids=canonical_edge_ids,
        ), policy_id
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

    retry_text, retry_policy = _dispatch_once(retry_prompt, event, attempt=1)
    if retry_text is None:
        return None, retry_policy

    try:
        return parse_synthesizer_response(
            retry_text,
            canonical_chunk_ids=canonical_chunk_ids,
            canonical_node_ids=canonical_node_ids,
            canonical_edge_ids=canonical_edge_ids,
        ), retry_policy
    except SynthesizerValidationError as exc2:
        print(
            f"synthesizer.handle: self-repair retry also failed — {exc2}",
            flush=True,
        )
        return None, retry_policy


# ---------------------------------------------------------------------------
# Handler factory
# ---------------------------------------------------------------------------


def make_synthesizer_handler(
    broadcaster: EventBroadcaster,
) -> Callable[[Event], Awaitable[None]]:
    """Build the synthesizer handler. Registered against
    ``ActionType.SYNTHESIZE_REQUESTED``."""

    async def handle_synthesize_request(event: Event) -> None:
        if not isinstance(event.payload, SynthesizeRequestedPayload):
            return
        req = event.payload
        canonical_chunk_ids, canonical_node_ids, canonical_edge_ids = (
            _canonical_refs_for_request(req)
        )

        # ── 1. First dispatch ──
        first_prompt = render_full_prompt(
            question=req.question,
            decomposition_block=req.decomposition_block,
            evidence_block=req.evidence_block,
            parameters_block=req.parameters_block,
            substrate_block=req.substrate_block,
        )
        first_result, policy_id = _dispatch_and_parse(
            first_prompt,
            event,
            canonical_chunk_ids=canonical_chunk_ids,
            canonical_node_ids=canonical_node_ids,
            canonical_edge_ids=canonical_edge_ids,
        )
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

        def synthesizer_callable(violations: list[Violation], iteration: int) -> list[Claim]:
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
                revised_prompt,
                event,
                canonical_chunk_ids=canonical_chunk_ids,
                canonical_node_ids=canonical_node_ids,
                canonical_edge_ids=canonical_edge_ids,
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
    emitted_event_id: str | None,
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
