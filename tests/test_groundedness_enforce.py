"""Groundedness Gate SPR-03 — enforcement + provenance tests.

The load-bearing gates (each pins one rigor card of the SPR-03 spec):

- OFF is a no-op (rigor #1): flag off → Phase-6 emit-anyway path unchanged,
  no new signal fires, ctx.synthesis untouched.
- FLAG marks (rigor #2): flag=flag, below-threshold → groundedness.failed
  emitted + ctx.synthesis STILL set (deposits; observability+alert).
- BLOCK prevents deposit (rigor #3): flag=block, below-threshold →
  ctx.synthesis nulled (the synthesis never reaches Phase 7 / the graph).
  Not a post-hoc annotation; a real deposit-prevention.
- Semantic-support catches densely-cited (rigor #5): a claim with
  resolving-but-non-entailing chunks is detected unsupported, DISTINCT
  from an unresolved-id case (data error vs groundedness failure).
- Node slot populated (M4 reframed): the existing
  KnowledgeUnitContract.groundedness_score population (insight_question
  projection) is PINNED so a future refactor can't silently un-set it.
"""

from __future__ import annotations

import pytest

# Import the API package FIRST (mirrors test_orchestrator_groundedness.py —
# sidesteps the package-init circular import).
import interfaces.research.api  # noqa: F401,E402
from orchestration.loop_one.orchestrator import (  # noqa: E402
    InvestigationContext,
    _enforce_groundedness,
    _score_phase_6_synthesis,
)
from substrate.eval.groundedness import enforce as enforce_mod  # noqa: E402
from substrate.eval.groundedness.enforce import (  # noqa: E402
    ENFORCE_ENV_VAR,
    EnforcePosture,
)
from substrate.event_log import trajectory  # noqa: E402
from substrate.schemas.events import (  # noqa: E402
    ActionType,
    ConstraintCompliance,
    SynthesizeDeliveredPayload,
    ThesisComponent,
)


@pytest.fixture(autouse=True)
def _isolate_events(tmp_path, monkeypatch):
    """Isolate event log + DB. Force the flag OFF unless a test overrides."""
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "absent.duckdb"))
    monkeypatch.delenv("ANTIEK_EVENTS_DISABLED", raising=False)
    # The default MUST be OFF for every test — a test that wants enforcement
    # sets it explicitly. This makes "OFF is the default" machine-checkable.
    monkeypatch.delenv(ENFORCE_ENV_VAR, raising=False)
    # Where the groundedness.failed events land.
    yield tmp_path


def _ctx(score_kind: str = "faithful") -> InvestigationContext:
    """Build a context whose synthesis scores faithful or below-threshold.

    - ``faithful``: claim text == chunk text (lexical scores ~1.0; NLI entails).
    - ``hallucinated``: claim asserts a number the chunk lacks (lexical + NLI
      both score it below threshold — fabricated precision).
    - ``densely_cited``: a claim that cites chunks that resolve but do NOT
      entail it (the SPR-01 blind-spot class — NLI catches, lexical misses).

    No live DB: the resolver yields no chunk text, so the scorer sees claims
    with no evidence → score 0.0 (below threshold). For tests that need real
    chunk text, inject via the provenance audit path instead.
    """
    ctx = InvestigationContext(investigation_id=f"inv-{score_kind}", question="q?")
    if score_kind == "faithful":
        claim = "The radar achieves 24 dB of gain."
    elif score_kind == "hallucinated":
        claim = "The radar achieves 99 dB of gain."  # fabricated number
    else:
        claim = "The radar achieves 24 dB of gain."  # cited but unresolved
    ctx.synthesis = SynthesizeDeliveredPayload(
        thesis_summary=claim,
        implicit_recommendation="proceed",  # type: ignore[arg-type]
        thesis_components=[
            ThesisComponent(
                claim=claim,
                confidence="high",
                supporting_chunk_ids=["chunk-1"],
            ),
        ],
        constraint_compliance=ConstraintCompliance(hard_constraints_satisfied=True),
        conviction_level=0.8,
    )
    return ctx


def _groundedness_failed_count(tmp_path) -> int:
    """Count groundedness.failed events emitted to the isolated event log."""
    events_dir = tmp_path / "events"
    if not events_dir.exists():
        return 0
    n = 0
    for fn in events_dir.iterdir():
        if not fn.name.endswith((".jsonl", ".parquet")):
            continue
        iid = fn.name.rsplit(".", 1)[0]
        for row in trajectory(iid, events_dir=str(events_dir)):
            if row.get("action_type") == ActionType.GROUNDEDNESS_FAILED:
                n += 1
    return n


# ---------------------------------------------------------------------------
# rigor #1: OFF is a no-op (the single most important test).
# ---------------------------------------------------------------------------


def test_enforce_off_is_noop(_isolate_events):
    """With the flag OFF (the default), _enforce_groundedness must NOT:
    - emit any groundedness.failed event
    - mutate ctx.synthesis
    It receives the score result and does nothing with it. This is the
    byte-for-byte-today's-behavior assertion the SPR-03 spec demands."""
    ctx = _ctx("faithful")
    synthesis_before = ctx.synthesis
    # A below-threshold result handed to the enforcer under OFF posture.
    fake_result = _score_phase_6_synthesis(ctx)  # populates the real score
    assert fake_result is not None  # sanity: scorer produced a result

    failed_before = _groundedness_failed_count(_isolate_events)
    _enforce_groundedness(ctx, fake_result)
    failed_after = _groundedness_failed_count(_isolate_events)

    assert failed_after == failed_before, (
        "OFF posture emitted a groundedness.failed event — OFF must be a true no-op."
    )
    assert ctx.synthesis is synthesis_before, (
        "OFF posture mutated ctx.synthesis — OFF must not touch the synthesis."
    )


def test_enforce_default_posture_is_off():
    """The env default is OFF — a fresh environment never enables enforcement.
    Machine-checkable so a future change to the default can't slip through."""
    assert enforce_mod.current_posture() is EnforcePosture.OFF
    assert not enforce_mod.should_enforce()
    assert not enforce_mod.should_block()


def test_enforce_unknown_env_fails_safe_to_off(monkeypatch):
    """A typo in the env value must NEVER accidentally enable enforcement
    (especially not block). Fails-safe to OFF."""
    monkeypatch.setenv(ENFORCE_ENV_VAR, "blcock")  # typo
    assert enforce_mod.current_posture() is EnforcePosture.OFF
    monkeypatch.setenv(ENFORCE_ENV_VAR, "BLOCKED")  # wrong vocab
    assert enforce_mod.current_posture() is EnforcePosture.OFF


# ---------------------------------------------------------------------------
# rigor #2 + #3: FLAG marks (still deposits); BLOCK prevents deposit.
# ---------------------------------------------------------------------------


def test_enforce_flag_marks_but_deposits(_isolate_events, monkeypatch):
    """flag=flag on a below-threshold synthesis: groundedness.failed emitted
    AND ctx.synthesis STILL set (deposit happens; observability+alert, not a
    destructive block). The synthesis is not lost — the alert surfaces it."""
    monkeypatch.setenv(ENFORCE_ENV_VAR, "flag")
    assert enforce_mod.current_posture() is EnforcePosture.FLAG
    ctx = _ctx("hallucinated")  # below threshold (fabricated number)
    result = _score_phase_6_synthesis(ctx)
    assert result is not None and result.score < result.supported_threshold  # sanity

    failed_before = _groundedness_failed_count(_isolate_events)
    _enforce_groundedness(ctx, result)
    failed_after = _groundedness_failed_count(_isolate_events)

    assert failed_after == failed_before + 1, (
        "FLAG posture must emit exactly one groundedness.failed on a below-threshold synthesis."
    )
    assert ctx.synthesis is not None, (
        "FLAG posture must NOT null ctx.synthesis — it deposits (alert, not block)."
    )


def test_enforce_block_prevents_deposit(_isolate_events, monkeypatch):
    """flag=block on a below-threshold synthesis: ctx.synthesis is nulled so
    the synthesis never reaches Phase 7 / the graph. This is a REAL
    deposit-prevention (the load-bearing rigor #3 assertion), not a post-hoc
    annotation. groundedness.failed is also emitted (never a silent drop)."""
    monkeypatch.setenv(ENFORCE_ENV_VAR, "block")
    assert enforce_mod.current_posture() is EnforcePosture.BLOCK
    ctx = _ctx("hallucinated")
    result = _score_phase_6_synthesis(ctx)
    assert result is not None and result.score < result.supported_threshold

    failed_before = _groundedness_failed_count(_isolate_events)
    _enforce_groundedness(ctx, result)
    failed_after = _groundedness_failed_count(_isolate_events)

    assert ctx.synthesis is None, (
        "BLOCK posture must null ctx.synthesis so the synthesis is not deposited. "
        "A gate that annotates post-hoc is observability wearing a gate's clothes."
    )
    assert failed_after == failed_before + 1, (
        "BLOCK must emit groundedness.failed (typed rejection logged, never silent)."
    )


def test_enforce_above_threshold_is_noop_even_when_on(_isolate_events, monkeypatch):
    """A GROUNDED synthesis is never flagged or blocked, even under block
    posture. The gate only acts on below-threshold scores."""
    monkeypatch.setenv(ENFORCE_ENV_VAR, "block")
    ctx = _ctx("faithful")
    result = _score_phase_6_synthesis(ctx)
    # The faithful claim with no live DB still scores 0.0 (no chunk text resolves).
    # So construct a result that IS above threshold by hand to test this path.
    assert result is not None
    # Force the score above threshold to verify the gate passes it through.
    from substrate.eval.groundedness.scorer import GroundednessResult
    above = GroundednessResult(
        score=0.95,
        scored_claims=1,
        total_claims=1,
        backend="test",
        scorer_id="test",
        supported_threshold=result.supported_threshold,
        per_claim=(),
    )
    failed_before = _groundedness_failed_count(_isolate_events)
    _enforce_groundedness(ctx, above)
    failed_after = _groundedness_failed_count(_isolate_events)
    assert failed_after == failed_before
    assert ctx.synthesis is not None


def test_enforce_none_result_is_noop(_isolate_events, monkeypatch):
    """A None result (no synthesis / scorer crashed) is a no-op under any
    posture. The crash already surfaced via groundedness.failed in the
    scorer's own except block — the enforcer doesn't double-fire."""
    monkeypatch.setenv(ENFORCE_ENV_VAR, "block")
    ctx = _ctx("faithful")
    failed_before = _groundedness_failed_count(_isolate_events)
    _enforce_groundedness(ctx, None)
    failed_after = _groundedness_failed_count(_isolate_events)
    assert failed_after == failed_before
    assert ctx.synthesis is not None  # untouched


# ---------------------------------------------------------------------------
# rigor #5: semantic-support audit — distinct from id-resolution.
# ---------------------------------------------------------------------------


def test_audit_distinguishes_unresolved_id_from_unsupported():
    """The SPR-03 spec rigor #5: an unresolved chunk id (DATA error) is a
    different failure from a resolved-but-unsupported claim (GROUNDEDNESS
    failure). The audit must keep them distinct so a debugger knows which
    problem is happening."""
    from substrate.eval.groundedness.provenance import (
        SUPPORTED,
        UNRESOLVED_ID,
        audit_claim_support,
    )

    # A payload with two claims: one cites an id that resolves, one cites an
    # id that does not.
    payload = SynthesizeDeliveredPayload(
        thesis_summary="s",
        implicit_recommendation="proceed",  # type: ignore[arg-type]
        thesis_components=[
            ThesisComponent(
                claim="The radar achieves 24 dB of gain.",
                confidence="high",
                supporting_chunk_ids=["chunk-real"],
            ),
            ThesisComponent(
                claim="Anything at all.",
                confidence="high",
                supporting_chunk_ids=["chunk-missing"],
            ),
        ],
        constraint_compliance=ConstraintCompliance(hard_constraints_satisfied=True),
    )
    # Resolver: only chunk-real resolves.
    def resolver(cid: str) -> str | None:
        return {"chunk-real": "The radar achieves 24 dB of gain."}.get(cid)

    verdicts = audit_claim_support(payload, resolver, backend=_lex_backend())
    assert len(verdicts) == 2
    by_claim = {v.claim: v for v in verdicts}
    # The faithful claim with resolving text: SUPPORTED.
    assert by_claim["The radar achieves 24 dB of gain."].verdict == SUPPORTED
    # The claim whose id resolved to nothing: UNRESOLVED_ID (distinct from unsupported).
    missing = by_claim["Anything at all."]
    assert missing.verdict == UNRESOLVED_ID
    assert missing.unresolved_ids == ["chunk-missing"]
    assert missing.score is None  # honest unknown, not 0.0


def test_audit_flags_resolved_but_unsupported():
    """A claim whose chunks RESOLVE but do not ENTAIL it is the densely-cited-
    hallucination failure — detected as RESOLVED_BUT_UNSUPPORTED, not as
    unresolved (the ids are fine; the model hallucinated). This is the case
    presence-only checks are blind to."""
    from substrate.eval.groundedness.provenance import (
        RESOLVED_BUT_UNSUPPORTED,
        audit_claim_support,
    )

    payload = SynthesizeDeliveredPayload(
        thesis_summary="s",
        implicit_recommendation="proceed",  # type: ignore[arg-type]
        thesis_components=[
            ThesisComponent(
                # Fabricated number: chunk says 24 dB, claim says 99 dB.
                # Resolves fine; does not entail.
                claim="The radar achieves 99 dB of gain.",
                confidence="high",
                supporting_chunk_ids=["chunk-radar"],
            ),
        ],
        constraint_compliance=ConstraintCompliance(hard_constraints_satisfied=True),
    )
    def resolver(cid: str) -> str | None:
        return {"chunk-radar": "The radar achieves 24 dB of gain."}.get(cid)

    verdicts = audit_claim_support(payload, resolver, backend=_lex_backend())
    assert len(verdicts) == 1
    v = verdicts[0]
    assert v.verdict == RESOLVED_BUT_UNSUPPORTED, (
        f"a resolving-but-non-entailing claim must be RESOLVED_BUT_UNSUPPORTED, got {v.verdict}"
    )
    assert v.unresolved_ids == []  # the id resolved; this is a groundedness failure, not data
    assert v.score is not None and v.score < 0.5


def _lex_backend():
    """Lexical backend for audit tests (deterministic, no model cache needed).
    The audit's DEFAULT is NLI, but the distinction-logic tests don't depend
    on which backend catches what — they test the verdict taxonomy."""
    from substrate.eval.groundedness.scorer import lexical_entailment_score
    return lexical_entailment_score


# ---------------------------------------------------------------------------
# M4 (reframed): pin the existing groundedness_score population.
# ---------------------------------------------------------------------------


def test_knowledge_unit_groundedness_slot_is_populated_by_projection():
    """M4 honest reframe: the spec's 'populate SynthesisNode.groundedness_score'
    targeted a contract (SynthesisNode) that is NOT on the synthesis write-
    path — it's the per-unit KnowledgeUnitContract, and the
    substrate/graph/insight_question projection ALREADY populates the slot
    (verified: insight_question.py:988 sets groundedness_score=...). This
    test PINS that population so a future refactor can't silently un-set it.

    If this test fails, either (a) the projection stopped populating the slot
    (regression — the graph lost its truth-score), or (b) the slot was
    removed (contract change — update this test deliberately)."""
    import inspect

    import substrate.graph.insight_question as iq

    # The projection function that builds a KnowledgeUnitContract.
    source = inspect.getsource(iq)
    # It must set groundedness_score= at construction (the slot population).
    assert "groundedness_score=" in source, (
        "substrate/graph/insight_question.py no longer populates "
        "groundedness_score at KnowledgeUnitContract construction — the graph "
        "lost its per-unit truth-score. Either restore the population or, if "
        "the contract changed deliberately, update this test."
    )
    # And the contract slot must still exist + be nullable.
    from substrate.contracts.nodes import KnowledgeUnitContract
    fields = KnowledgeUnitContract.model_fields
    assert "groundedness_score" in fields, (
        "KnowledgeUnitContract.groundedness_score slot removed — the graph's "
        "per-unit truth-score has no home."
    )
    assert fields["groundedness_score"].default is None, (
        "groundedness_score must stay nullable (None = un-scored, not a forced value)."
    )
