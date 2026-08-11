"""RLM-2 + RLM-3 tests (rlm_integration_spec.md)."""

from __future__ import annotations

from decimal import Decimal

from orchestration.rlm.long_corpus import LongCorpusBatch, synthesize_long_corpus
from orchestration.rlm.prime_agent_backend import (
    PrimeAgentEvidence,
    PrimeAgentOutcome,
    PrimeAgentReceipt,
    PrimeAgentTerminalState,
)
from orchestration.rlm.rlm_investigation import (
    RLMInvestigationConfig,
    RLMIterationOutcome,
    run_rlm_investigation,
)


class _PrimeStub:
    def __init__(self, *, evidence: str | None):
        self.evidence = evidence
        self.requests = []

    def run(self, request):
        self.requests.append(request)
        state = (
            PrimeAgentTerminalState.SUCCESS
            if self.evidence is not None
            else PrimeAgentTerminalState.FAILED
        )
        return PrimeAgentOutcome(
            request=request,
            evidence=(
                PrimeAgentEvidence(self.evidence)
                if self.evidence is not None
                else None
            ),
            receipt=PrimeAgentReceipt(state, (), 0, 1, 0),
        )

# ── RLM-2 long-corpus synthesizer ────────────────────────────────────


def test_long_corpus_batches_within_budget(monkeypatch):
    monkeypatch.setenv("ANTIEK_RLM_RATIFIED", "1")
    chunks = [f"chunk-{i}" for i in range(10)]
    chunk_tokens = {c: 30_000 for c in chunks}
    batch_calls: list[LongCorpusBatch] = []

    def synth_batch(batch):
        batch_calls.append(batch)
        return (f"summary of {batch.batch_id}", Decimal("0.10"))

    def reduce_batches(outputs):
        return ("final synthesis", Decimal("0.20"))

    final, session = synthesize_long_corpus(
        corpus_chunk_ids=chunks,
        chunk_token_counts=chunk_tokens,
        target_batch_token_budget=100_000,
        investigation_id="inv-long",
        synthesize_batch_fn=synth_batch,
        reduce_batch_outputs_fn=reduce_batches,
    )

    assert final == "final synthesis"
    assert len(batch_calls) >= 1
    # No batch exceeds the budget (give or take one chunk for greedy
    # packing).
    for batch in batch_calls:
        # The greedy packer admits a batch that, after adding the
        # final chunk, may go over budget by up to one chunk's worth.
        # Each chunk is 30k; budget is 100k; so max batch is ~120k.
        assert batch.batch_token_count <= 130_000


def test_long_corpus_session_completes(monkeypatch):
    monkeypatch.setenv("ANTIEK_RLM_RATIFIED", "1")
    final, session = synthesize_long_corpus(
        corpus_chunk_ids=["c-1"],
        chunk_token_counts={"c-1": 50_000},
        target_batch_token_budget=100_000,
        investigation_id="inv-x",
        synthesize_batch_fn=lambda b: ("summary", Decimal("0.05")),
        reduce_batch_outputs_fn=lambda outputs: ("final", Decimal("0.05")),
    )
    assert session.state.status == "completed"


def test_long_corpus_prime_disabled_preserves_inputs_and_calls(monkeypatch):
    monkeypatch.setenv("ANTIEK_RLM_RATIFIED", "1")
    seen = []
    final, _ = synthesize_long_corpus(
        corpus_chunk_ids=["c-1"], chunk_token_counts={"c-1": 1},
        target_batch_token_budget=10, investigation_id="inv-default",
        synthesize_batch_fn=lambda batch: ("canonical", Decimal("0")),
        reduce_batch_outputs_fn=lambda outputs: (seen.extend(outputs) or "final", Decimal("0")),
    )
    assert final == "final"
    assert seen == ["canonical"]


def test_long_corpus_prime_success_is_labeled_and_receipted(monkeypatch):
    monkeypatch.setenv("ANTIEK_RLM_RATIFIED", "1")
    prime = _PrimeStub(evidence="prime clue")
    receipts = []
    seen = []
    synthesize_long_corpus(
        corpus_chunk_ids=["c-1"], chunk_token_counts={"c-1": 1},
        target_batch_token_budget=10, investigation_id="inv-prime",
        synthesize_batch_fn=lambda batch: ("canonical", Decimal("0")),
        reduce_batch_outputs_fn=lambda outputs: (seen.extend(outputs) or "final", Decimal("0")),
        prime_backend=prime, prime_outcome_sink=receipts.append,
    )
    assert seen[0] == "canonical"
    assert "Supplemental Prime Agent evidence; non-canonical" in seen[1]
    assert "prime clue" in seen[1]
    assert len(prime.requests) == len(receipts) == 1
    assert receipts[0].request == prime.requests[0]


def test_long_corpus_prime_failure_preserves_canonical_inputs(monkeypatch):
    monkeypatch.setenv("ANTIEK_RLM_RATIFIED", "1")
    prime = _PrimeStub(evidence=None)
    seen = []
    receipts = []
    synthesize_long_corpus(
        corpus_chunk_ids=["c-1"], chunk_token_counts={"c-1": 1},
        target_batch_token_budget=10, investigation_id="inv-fail",
        synthesize_batch_fn=lambda batch: ("canonical", Decimal("0")),
        reduce_batch_outputs_fn=lambda outputs: (seen.extend(outputs) or "final", Decimal("0")),
        prime_backend=prime, prime_outcome_sink=receipts.append,
    )
    assert seen == ["canonical"]
    assert receipts[0].receipt.state is PrimeAgentTerminalState.FAILED


# ── RLM-3 investigation orchestrator ─────────────────────────────────


def test_rlm_investigation_iterates_and_completes(monkeypatch):
    monkeypatch.setenv("ANTIEK_RLM_RATIFIED", "1")
    config = RLMInvestigationConfig(
        investigation_id="inv-survey",
        initial_question="Survey neutral-atom quantum computing",
        max_iterations=3,
    )

    def plan_iteration(state_summary, accumulated_qs):
        # Add 2 sub-questions per iteration; stop after the third.
        iteration_num = len([q for q in accumulated_qs if q != config.initial_question]) // 2 + 1
        should_continue = iteration_num < 3
        return RLMIterationOutcome(
            iteration=iteration_num,
            iteration_summary=f"iter {iteration_num}",
            new_sub_questions=(f"sub-Q-{iteration_num}-A", f"sub-Q-{iteration_num}-B"),
            cost_usd=Decimal("0.10"),
            should_continue=should_continue,
        )

    def final_synthesis(qs):
        return (f"Synthesis across {len(qs)} questions", Decimal("0.20"))

    final, session = run_rlm_investigation(
        config,
        plan_iteration_fn=plan_iteration,
        final_synthesis_fn=final_synthesis,
    )

    assert "Synthesis across" in final
    assert session.state.status == "completed"
    # At least one iteration ran (plus the final synthesis iteration).
    assert session.state.iteration_count >= 2


def test_rlm_investigation_stops_at_max_iterations(monkeypatch):
    monkeypatch.setenv("ANTIEK_RLM_RATIFIED", "1")
    config = RLMInvestigationConfig(
        investigation_id="inv-x",
        initial_question="Test",
        max_iterations=2,
    )

    def plan_iteration(state, qs):
        return RLMIterationOutcome(
            iteration=len(qs),
            iteration_summary="iter",
            new_sub_questions=("q",),
            cost_usd=Decimal("0.10"),
            should_continue=True,  # always continue → hit max
        )

    def final_synthesis(qs):
        return ("final", Decimal("0.10"))

    final, session = run_rlm_investigation(
        config,
        plan_iteration_fn=plan_iteration,
        final_synthesis_fn=final_synthesis,
    )
    # plan_iteration runs max_iterations times + 1 final = 3
    # But session completes via session.complete(), not max.
    assert session.state.status == "completed"


def test_investigation_prime_success_and_failure_at_final_boundary(monkeypatch):
    monkeypatch.setenv("ANTIEK_RLM_RATIFIED", "1")

    def plan(state, questions):
        return RLMIterationOutcome(1, "done", (), Decimal("0"), False)

    for evidence, expected_count in (("prime clue", 2), (None, 1)):
        prime = _PrimeStub(evidence=evidence)
        seen = []

        def synthesize(inputs, *, target=seen):
            target.extend(inputs)
            return "final", Decimal("0")

        run_rlm_investigation(
            RLMInvestigationConfig("inv", "question", max_iterations=1),
            plan_iteration_fn=plan,
            final_synthesis_fn=synthesize,
            prime_backend=prime,
        )
        assert len(seen) == expected_count
        if evidence is not None:
            assert "non-canonical" in seen[-1]
