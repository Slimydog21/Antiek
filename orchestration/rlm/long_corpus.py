"""RLM-2 — long-corpus synthesizer RLM mode (rlm_integration_spec.md).

Per rlm_integration_spec.md RLM-2: ~250 LOC. The synthesizer's
context budget caps out around 256K tokens. For long-corpus
investigations (Phase 8 patches across hundreds of investigations),
the substrate needs an RLM-mode synthesizer that walks the corpus
hierarchically.

The pattern: split the long corpus into batches that fit a single
synthesizer call; produce a synthesizer-output per batch; then
synthesize across the batch outputs. Same recursive pattern as
RLM-1 but for synthesis instead of wrestling.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from decimal import Decimal

from .prime_agent_backend import (
    PrimeAgentOutcome,
    PrimeAgentRequest,
    PrimeAgentRLMBackend,
)
from .session import (
    RLMSession,
    create_session,
    iterate_session,
)

PRIME_EVIDENCE_LABEL = "[Supplemental Prime Agent evidence; non-canonical]"


@dataclass(frozen=True)
class LongCorpusBatch:
    """One batch of corpus content that fits a single synthesizer call."""

    batch_id: str
    corpus_chunk_ids: tuple[str, ...]
    batch_token_count: int


def synthesize_long_corpus(
    *,
    corpus_chunk_ids: list[str],
    chunk_token_counts: dict[str, int],
    target_batch_token_budget: int,
    investigation_id: str,
    synthesize_batch_fn: Callable[[LongCorpusBatch], tuple[str, Decimal]],
    reduce_batch_outputs_fn: Callable[[list[str]], tuple[str, Decimal]],
    prime_backend: PrimeAgentRLMBackend | None = None,
    prime_outcome_sink: Callable[[PrimeAgentOutcome], None] | None = None,
    canonical_checkpoint_sink: Callable[[list[str]], None] | None = None,
    resume_batch_outputs: list[str] | None = None,
) -> tuple[str, RLMSession]:
    """Synthesize across a long corpus via RLM batched mode.

    Args:
        corpus_chunk_ids: ordered list of chunk_ids in the corpus
        chunk_token_counts: chunk_id → token count
        target_batch_token_budget: aim for batches near this size
        investigation_id: investigation this synthesis is for
        synthesize_batch_fn: produces a batch synthesis + reports cost
        reduce_batch_outputs_fn: reduces batch outputs into final
            synthesis + reports cost

    Returns:
        (final_synthesis_text, RLMSession with iteration history)
    """
    session = create_session(
        investigation_id=investigation_id,
        root_role="synthesizer",
    )

    batches: list[LongCorpusBatch] = []
    current_chunks: list[str] = []
    current_tokens = 0
    batch_counter = 0
    for chunk_id in corpus_chunk_ids:
        chunk_tokens = chunk_token_counts.get(chunk_id, 1000)
        if current_tokens + chunk_tokens > target_batch_token_budget and current_chunks:
            batches.append(LongCorpusBatch(
                batch_id=f"batch-{batch_counter:04d}",
                corpus_chunk_ids=tuple(current_chunks),
                batch_token_count=current_tokens,
            ))
            batch_counter += 1
            current_chunks = []
            current_tokens = 0
        current_chunks.append(chunk_id)
        current_tokens += chunk_tokens
    if current_chunks:
        batches.append(LongCorpusBatch(
            batch_id=f"batch-{batch_counter:04d}",
            corpus_chunk_ids=tuple(current_chunks),
            batch_token_count=current_tokens,
        ))

    batch_outputs: list[str] = list(resume_batch_outputs or [])
    if resume_batch_outputs is None:
        for batch in batches:
            output, cost = synthesize_batch_fn(batch)
            if session.state.status == "cost_capped":
                break
            iterate_session(session, summary=f"Synthesized {batch.batch_id}", cost_usd=cost)
            batch_outputs.append(output)
        if canonical_checkpoint_sink is not None:
            canonical_checkpoint_sink(list(batch_outputs))

    reduction_inputs = list(batch_outputs)
    if prime_backend is not None:
        try:
            outcome = prime_backend.run(PrimeAgentRequest(
                prompt="\n\n".join(batch_outputs),
                workflow="rlm-long-corpus",
                request_id=f"{investigation_id}:long-corpus:reduce",
            ))
            if prime_outcome_sink is not None:
                with suppress(Exception):
                    prime_outcome_sink(outcome)
            if (
                outcome.receipt.state.value in {"success", "succeeded"}
                and outcome.evidence is not None
                and outcome.evidence.supplemental
            ):
                reduction_inputs.append(
                    f"{PRIME_EVIDENCE_LABEL}\n{outcome.evidence.text}"
                )
        except Exception:
            if getattr(prime_backend, "fail_closed", False):
                raise

    final, reduce_cost = reduce_batch_outputs_fn(reduction_inputs)
    session.complete(final_summary=final)
    return (final, session)
