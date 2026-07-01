"""RLM-backed long-document wrestling route.

This module is intentionally called from the existing wrestling
``distillation.requested`` handler and returns a boolean:

- ``False`` means the legacy single-call path should run.
- ``True`` means this module emitted the terminal event, or an RLM
  lifecycle failure event, and the legacy path should not double-handle.
"""

from __future__ import annotations

from contextlib import suppress
from decimal import Decimal

from interfaces.research.rlm_repl import RLMRepl
from orchestration.rlm import (
    RLM_DOC_THRESHOLD_TOKENS,
    RLMEventEmitter,
    create_session,
    run_loop_with_timeout,
    session_failed_payload,
    session_started_payload,
)
from orchestration.rlm.bridge import is_ratified
from orchestration.rlm.session import RLM_DEFAULT_MAX_ITERATIONS
from substrate.dispatch import ProviderError, dispatch
from substrate.event_log import emit_typed, trajectory
from substrate.schemas import DistillationDeliveredPayload, DistillationRequestedPayload, Event

from .broadcast import EventBroadcaster


def _estimate_tokens_from_text(text: str) -> int:
    return max(0, len(text.encode("utf-8")) // 4)


def _system_prompt(*, prompt_chars: int) -> str:
    return (
        "You are reading a long document. The full document is in the Python "
        f"variable prompt (length: {prompt_chars} chars). The user's question "
        "is in user_question. The selected region, if any, is in "
        "region_of_interest. Write Python code in the REPL to slice the "
        "document and call llm_query or llm_batch as needed. Set "
        "answer['content'] to a JSON string with rendered_text and claims, "
        "then set answer['ready'] = True when complete."
    )


async def maybe_handle_rlm_distillation(
    *,
    event: Event,
    request: DistillationRequestedPayload,
    broadcaster: EventBroadcaster,
    db_path: str,
    resolve_document_text,
    resolve_region_text,
    parse_claims_response,
    sha256_prefix,
) -> bool:
    """Handle above-threshold ratified distillation via the RLM runner."""

    if not event.document_id or not is_ratified():
        return False

    full_document = resolve_document_text(db_path, event.document_id)
    if not full_document:
        return False

    estimated_tokens = _estimate_tokens_from_text(full_document)
    if estimated_tokens < RLM_DOC_THRESHOLD_TOKENS:
        return False

    region_text = resolve_region_text(
        event.investigation_id,
        event.document_id,
        request.region_id,
        db_path=db_path,
    )
    if region_text is None and request.region_id:
        region_text = f"(region {request.region_id} not found in document chunks)"
    elif region_text is None:
        region_text = "(whole-document distillation requested)"

    session = create_session(
        investigation_id=event.investigation_id,
        root_role="wrestler",
        document_id=event.document_id,
    )
    emitter = RLMEventEmitter(
        broadcaster.broadcast,
        investigation_id=event.investigation_id,
        document_id=event.document_id,
        param_version="wrestling-rlm-v0",
    )
    await emitter.emit(
        session_started_payload(
            session,
            estimated_tokens=estimated_tokens,
            max_iterations=RLM_DEFAULT_MAX_ITERATIONS,
        )
    )

    root_prompt = _system_prompt(prompt_chars=len(full_document))
    repl = RLMRepl(
        corpus={
            "prompt": full_document,
            "region_of_interest": region_text,
            "user_question": request.user_prompt,
            "system_prompt": root_prompt,
        },
        max_iterations=RLM_DEFAULT_MAX_ITERATIONS,
    )

    def llm_query(prompt: str) -> str:
        result = dispatch(
            prompt,
            "synthesizer",
            investigation_id=event.investigation_id,
            parent_event_id=event.event_id,
        )
        return result.text

    def llm_batch(prompts: list[str]) -> list[str]:
        return [llm_query(str(prompt)) for prompt in prompts]

    repl.registry.install("llm_query", llm_query)
    repl.registry.install("llm_batch", llm_batch)
    repl.registry.install("search_graph", lambda query, top_k=5: [])

    last_codegen_cost = Decimal("0.00")

    def generate_code(summary) -> str:
        nonlocal last_codegen_cost
        result = dispatch(
            "\n\n".join([
                root_prompt,
                summary.format_for_prompt(),
            ]),
            "synthesizer",
            investigation_id=event.investigation_id,
            parent_event_id=event.event_id,
        )
        last_codegen_cost = Decimal(str(result.cost_usd))
        return result.text

    try:
        loop_result = await run_loop_with_timeout(
            repl=repl,
            generate_code=generate_code,
            session=session,
            emitter=emitter,
            cost_usd=lambda _summary, _code: last_codegen_cost,
            iteration_summary=lambda summary, _code: (
                f"RLM wrestling iteration {summary.iteration + 1}"
            ),
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
        return True

    if loop_result.status not in {"completed", "cost_capped"}:
        return True

    claims, rendered_text = parse_claims_response(
        loop_result.final_answer,
        region_id=request.region_id,
    )
    token_count = repl.summarise().answer_content_len
    policy_id = "rlm-wrestling/evented-loop"
    delivered_event_id = emit_typed(
        event.investigation_id,
        DistillationDeliveredPayload(
            request_event_id=event.event_id,
            claims=claims,
            rendered_text=rendered_text,
            rendered_text_hash=sha256_prefix(rendered_text),
            token_count=token_count,
        ),
        parent_event_id=event.event_id,
        role="synthesizer",
        document_id=event.document_id,
        policy_id=policy_id,
    )
    if delivered_event_id is None:
        return True
    for row in trajectory(event.investigation_id):
        if row.get("event_id") == delivered_event_id:
            with suppress(Exception):
                await broadcaster.broadcast(Event.model_validate(row))
            return True
    return True


__all__ = ["maybe_handle_rlm_distillation"]
