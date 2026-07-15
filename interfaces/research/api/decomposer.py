"""Decomposer role bridge (Sprint 6 day 1-2 — first orchestrate.py
role extraction).

Subscribes to ``decompose.requested`` events. For each request:

1. Renders the decomposer prompt with the request's
   ``question`` + ``context`` placeholders.
2. Dispatches the ``decomposer`` role (Pro tier per
   ``substrate/dispatch/config.yaml``).
3. Parses + validates the response (closed taxonomy, 4-8
   sub-questions, 8-20 keywords).
4. Runs ``check_paraphrases`` against the top-level question.
5. If any sub-question is flagged: emits
   ``DECOMPOSER_PARAPHRASE_FLAGGED``, regenerates ONCE with
   ``regenerate_instruction`` prepended to the user prompt, re-runs
   the paraphrase check, emits ``DECOMPOSER_REGENERATED``. Even when
   the second pass is still flagged the bridge proceeds — one regen
   is the upstream's hard cap.
6. Emits ``DECOMPOSE_QUESTION_DELIVERED`` with the final structured
   output + paraphrase-pass summary.

Failure-mode discipline (mirrors wrestling + grounding):

- Malformed JSON / schema validation failure → emit Delivered with
  empty decomposition + flagged_count_final = 0 (the trajectory
  shows the request was answered, even if poorly; the operator can
  re-request manually). A validation-failed marker is logged to
  stderr for forensics.
- Provider unavailable → same fallback shape, policy_id stamped
  ``decomposer-fallback/no-provider`` so RL trajectory consumers can
  filter.
- Embedder unavailable → paraphrase check is SKIPPED (treated as
  "no flags"); the decomposer output ships as-is. Mirrors the
  upstream's ``except Exception: flagged = []`` defensive line.
"""

from __future__ import annotations

import os
import sys

# Direct import — interfaces/research/api/ depends on substrate + roles.
_PKG_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from roles.decomposer import (  # noqa: E402
    DecomposerValidationError,
    DecompositionResult,
    ParaphraseFlag,
    check_paraphrases,
    parse_decomposer_response,
    regenerate_instruction,
    render_full_prompt,
)
from substrate.dispatch import ProviderError, dispatch  # noqa: E402
from substrate.event_log import emit_typed, trajectory  # noqa: E402
from substrate.graph.search import EmbeddingModel  # noqa: E402
from substrate.schemas import (  # noqa: E402
    ActionType,
    DecomposeQuestionDeliveredPayload,
    DecomposeQuestionRequestedPayload,
    DecomposerParaphraseFlaggedPayload,
    DecomposerRegeneratedPayload,
    Event,
    Keyword,
    ParaphraseFlagRecord,
    SubQuestion,
)

from .broadcast import EventBroadcaster  # noqa: E402
from .research_tier_routing import persisted_research_tier_override  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _result_to_payload_lists(
    result: DecompositionResult,
) -> tuple[list[SubQuestion], list[Keyword]]:
    """Convert the parser's frozen dataclasses to the Pydantic shapes
    the ``DecomposeQuestionDelivered`` payload expects."""
    sq = [
        SubQuestion(
            sub_question=s.sub_question,
            category=s.category,  # type: ignore[arg-type]
            rationale=s.rationale,
            evidence_type_required=s.evidence_type_required,  # type: ignore[arg-type]
        )
        for s in result.decomposition
    ]
    kw = [Keyword(term=k.term, synonyms=list(k.synonyms)) for k in result.keywords]
    return sq, kw


def _flags_to_payload(flags: list[ParaphraseFlag]) -> list[ParaphraseFlagRecord]:
    return [
        ParaphraseFlagRecord(
            index=f.index, sub_question=f.sub_question, cosine=f.cosine,
        )
        for f in flags
    ]


def _empty_delivered_payload() -> DecomposeQuestionDeliveredPayload:
    """Fallback shape when the dispatch / parser fails. Keeps the
    trajectory honest: the request was answered (the bridge ran), the
    answer is empty, downstream can tell from the zero counts that
    the run failed substantively."""
    return DecomposeQuestionDeliveredPayload(
        decomposition=[],
        keywords=[],
        paraphrase_pass_count=1,
        paraphrase_flagged_count_final=0,
    )


def _safe_check_paraphrases(
    question: str,
    sub_questions: list[str],
    *,
    embedder: EmbeddingModel | None,
) -> list[ParaphraseFlag]:
    """Wrap ``check_paraphrases`` with the upstream's defensive guard:
    embedder/model failures degrade to "no flags" rather than killing
    the whole decomposition run."""
    try:
        return check_paraphrases(question, sub_questions, embedder=embedder)
    except Exception as exc:  # pragma: no cover — diagnostic
        print(
            f"decomposer.handle: paraphrase check skipped — {exc!r}",
            flush=True,
        )
        return []


# ---------------------------------------------------------------------------
# Handler factory
# ---------------------------------------------------------------------------


def make_decomposer_handler(
    broadcaster: EventBroadcaster,
    *,
    embedder: EmbeddingModel | None = None,
):
    """Build the handler closed over a broadcaster + embedder.
    Registered against ``ActionType.DECOMPOSE_QUESTION_REQUESTED``.

    ``embedder`` is optional — when None, ``check_paraphrases`` falls
    back to its lazy default (sentence-transformers). Tests pass a
    deterministic stub.
    """

    async def handle_decompose_request(event: Event) -> None:
        if not isinstance(event.payload, DecomposeQuestionRequestedPayload):
            return  # defensive — handler keyed on action_type
        req = event.payload
        question = req.question.strip()
        context = req.context or ""

        if not question:
            return  # nothing to decompose

        # ── Pass 1: dispatch + parse ──
        prompt = render_full_prompt(
            investigation_id=event.investigation_id,
            question=question,
            context=context,
        )
        result_1, policy_id_1 = _dispatch_and_parse(
            prompt, event, label="initial",
        )
        if result_1 is None:
            await _emit_delivered(
                event,
                payload=_empty_delivered_payload(),
                policy_id=policy_id_1,
                broadcaster=broadcaster,
            )
            return

        # ── Paraphrase guard ──
        sub_q_texts = [s.sub_question for s in result_1.decomposition]
        flags_1 = _safe_check_paraphrases(question, sub_q_texts, embedder=embedder)

        if not flags_1:
            sq, kw = _result_to_payload_lists(result_1)
            await _emit_delivered(
                event,
                payload=DecomposeQuestionDeliveredPayload(
                    decomposition=sq,
                    keywords=kw,
                    paraphrase_pass_count=1,
                    paraphrase_flagged_count_final=0,
                ),
                policy_id=policy_id_1,
                broadcaster=broadcaster,
            )
            return

        # ── Pass 2: regenerate with instruction prepended ──
        emit_typed(
            event.investigation_id,
            DecomposerParaphraseFlaggedPayload(
                pass_index=1,
                n_sub_questions=len(sub_q_texts),
                flagged=_flags_to_payload(flags_1),
            ),
            parent_event_id=event.event_id,
            role="decomposer",
            policy_id=policy_id_1,
        )
        regen_prompt = render_full_prompt(
            investigation_id=event.investigation_id,
            question=question,
            context=context,
            extra_user_prefix=regenerate_instruction(flags_1),
        )
        result_2, policy_id_2 = _dispatch_and_parse(
            regen_prompt, event, label="regen",
        )
        if result_2 is None:
            # Regen dispatch/parse failed — fall back to pass 1 output.
            sq, kw = _result_to_payload_lists(result_1)
            await _emit_delivered(
                event,
                payload=DecomposeQuestionDeliveredPayload(
                    decomposition=sq, keywords=kw,
                    paraphrase_pass_count=2,
                    paraphrase_flagged_count_final=len(flags_1),
                ),
                policy_id=policy_id_2,
                broadcaster=broadcaster,
            )
            return

        sub_q_texts_2 = [s.sub_question for s in result_2.decomposition]
        flags_2 = _safe_check_paraphrases(question, sub_q_texts_2, embedder=embedder)

        emit_typed(
            event.investigation_id,
            DecomposerRegeneratedPayload(
                flagged_after_regen=_flags_to_payload(flags_2),
                still_flagged=bool(flags_2),
            ),
            parent_event_id=event.event_id,
            role="decomposer",
            policy_id=policy_id_2,
        )

        sq, kw = _result_to_payload_lists(result_2)
        await _emit_delivered(
            event,
            payload=DecomposeQuestionDeliveredPayload(
                decomposition=sq,
                keywords=kw,
                paraphrase_pass_count=2,
                paraphrase_flagged_count_final=len(flags_2),
            ),
            policy_id=policy_id_2,
            broadcaster=broadcaster,
        )

    return handle_decompose_request


# ---------------------------------------------------------------------------
# Dispatch + parse + emit helpers
# ---------------------------------------------------------------------------


def _dispatch_and_parse(
    prompt: str,
    event: Event,
    *,
    label: str,
) -> tuple[DecompositionResult | None, str]:
    """Run one decomposer dispatch + parse. Returns
    ``(DecompositionResult, policy_id)`` on success, ``(None, fallback_id)``
    when the call or the parse failed. The fallback policy_id marks
    the failure shape for trajectory filtering.
    """
    provider_override, model_override = persisted_research_tier_override(
        event.investigation_id,
    )
    try:
        result = dispatch(
            prompt,
            "decomposer",
            investigation_id=event.investigation_id,
            parent_event_id=event.event_id,
            provider_override=provider_override,
            model_override=model_override,
        )
        response_text = result.text
        policy_id = f"{result.provider}/{result.model}"
    except (ProviderError, KeyError) as exc:
        print(
            f"decomposer.handle[{label}]: dispatch failed — "
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )
        return None, "decomposer-fallback/no-provider"

    try:
        parsed = parse_decomposer_response(
            response_text,
            expected_investigation_id=event.investigation_id,
        )
        return parsed, policy_id
    except DecomposerValidationError as exc:
        print(
            f"decomposer.handle[{label}]: parse failed — {exc}",
            flush=True,
        )
        return None, policy_id


async def _emit_delivered(
    event: Event,
    *,
    payload: DecomposeQuestionDeliveredPayload,
    policy_id: str,
    broadcaster: EventBroadcaster,
) -> None:
    eid = emit_typed(
        event.investigation_id,
        payload,
        parent_event_id=event.event_id,
        role="decomposer",
        policy_id=policy_id,
    )
    await _broadcast_emitted(event, eid, broadcaster)


async def _broadcast_emitted(
    event: Event,
    emitted_event_id: str | None,
    broadcaster: EventBroadcaster,
) -> None:
    """Look up the just-emitted event in the trajectory and broadcast
    so subscribed WS clients see the decomposition in real time."""
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


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_handlers(
    broadcaster: EventBroadcaster,
    *,
    embedder: EmbeddingModel | None = None,
) -> None:
    """Wire the decomposer handler into the broadcaster. Called once at
    app startup from ``app.create_app``."""
    broadcaster.register_handler(
        ActionType.DECOMPOSE_QUESTION_REQUESTED.value,
        make_decomposer_handler(broadcaster, embedder=embedder),
    )
