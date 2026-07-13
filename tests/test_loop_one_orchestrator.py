"""Tests for orchestration/loop_one/ (Sprint 8 day 3).

End-to-end: post INVESTIGATION_START_REQUESTED with stub providers
for all 5 roles AND a stub LLM for skills.domain.extract; verify the
full phase chain runs and INVESTIGATION_COMPLETED is emitted.

Coverage:

1. Happy path: cold question → INVESTIGATION_COMPLETED with all
   phases verified, MASTER.md path populated, domains_patched
   non-empty.
2. Decomposer dispatch failure → INVESTIGATION_FAILED with
   phase=1, last_completed_phase=None.
3. Synthesizer dispatch failure → INVESTIGATION_FAILED with
   phase=6, last_completed_phase=5.

The fixtures stub every role's provider so the orchestrator can run
without real LLM calls. The constraint loop's re-invoke path is
exercised in test_synthesizer_bridge.py; here the synth stub returns
a clean thesis on the first try.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys
from pathlib import Path

import httpx
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from interfaces.research.api import EventBroadcaster, create_app  # noqa: E402
from orchestration.invariants.deep_research_complete import (  # noqa: E402
    check_deep_research_complete,
)
from processing.embedding import _reset_default_provider  # noqa: E402
from substrate.dispatch import (  # noqa: E402
    DispatchConfig,
    NormalizedUsage,
    ProviderError,
    RawProviderResponse,
    TierConfig,
    TierPricing,
    register_provider,
    reset_provider_registry,
)
from substrate.event_log import trajectory  # noqa: E402
from substrate.schemas import (  # noqa: E402
    ActionType,
    Event,
    InvestigationCompletedPayload,
    InvestigationFailedPayload,
)


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    db_path = tmp_path / "graph.duckdb"
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db_path))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    monkeypatch.setenv("ANTIEK_RESEARCH_PHASE_LOG_DIR", str(tmp_path / "phase_logs"))
    monkeypatch.setenv("ANTIEK_RESEARCH_DIR", str(tmp_path / "research"))
    monkeypatch.setenv("ANTIEK_KNOWLEDGE_SKILLS_DIR", str(tmp_path / "skills"))
    # Seed a domain skill dir so Phase 8 patcher can land.
    quantum_dir = tmp_path / "skills" / "quantum-computing-knowledge"
    quantum_dir.mkdir(parents=True)
    (quantum_dir / "SKILL.md").write_text(
        "# Quantum Computing Knowledge\n\n"
        "## Domain Fundamentals\n\n(Findings will be added.)\n\n"
        "## Key Players\n\n(Findings will be added.)\n\n"
        "## Quantitative Benchmarks\n\n(Findings will be added.)\n\n"
        "## Competitive Dynamics\n\n(Findings will be added.)\n\n"
        "## Open Questions\n\n(Findings will be added.)\n\n"
        "## Monitoring Checklist\n\n(Findings will be added.)\n"
    )
    import duckdb

    from substrate.graph.schema import init_database_at_path

    init_database_at_path(str(db_path))
    con = duckdb.connect(str(db_path))
    try:
        con.execute(
            "INSERT INTO documents "
            "(document_id, source_uri, title, author, source_tier, document_type, "
            "raw_text, metadata, content_class) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                "doc-psi-quantum",
                "https://example.test/psiquantum-roadmap",
                "PsiQuantum photonic quantum roadmap",
                "Antiek fixture",
                1,
                "academic_paper",
                (
                    "PsiQuantum photonic quantum roadmap evidence. "
                    "Quantum X holds at threshold with demonstrated execution "
                    "capability and primary-source support."
                ),
                "{}",
                "restricted_pending_opt_in",
            ],
        )
        con.execute(
            "INSERT INTO chunks "
            "(chunk_id, document_id, chunk_index, section_path, text, token_count) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                "chunk-1",
                "doc-psi-quantum",
                0,
                "Fixture",
                (
                    "PsiQuantum photonic quantum roadmap evidence: Quantum X "
                    "holds at threshold, the photonic substrate is established "
                    "by primary sources, and execution capability is documented."
                ),
                32,
            ],
        )
    finally:
        con.close()
    _reset_default_provider()
    reset_provider_registry()
    yield
    _reset_default_provider()
    reset_provider_registry()


# ---------------------------------------------------------------------------
# Stub providers — one per role + extraction
# ---------------------------------------------------------------------------


class _RoleStubProvider:
    """Dispatches by role: each call inspects the prompt for a tag
    identifying which role is calling and returns the matching canned
    response. Lets a single registered provider serve every role."""

    name = "loop-one-stub"

    def __init__(self, responses_by_tag: dict[str, str], *,
                 raise_for: set[str] | None = None):
        self.responses = responses_by_tag
        self.raise_for = raise_for or set()
        self.call_count: dict[str, int] = {}

    def call(self, *, model, prompt, max_tokens, temperature) -> RawProviderResponse:
        # Identify the role by inspecting the prompt for tag substrings.
        tag = "unknown"
        if "extract the **design-critical parameters" in prompt:
            tag = "parameter_extractor"
        elif "relational reasoning analyst" in prompt:
            tag = "connector"
        elif "senior investment analyst" in prompt:
            tag = "synthesizer"
        elif "evidence analyst" in prompt:
            tag = "evidence_retriever"
        elif "senior diligence analyst" in prompt:
            tag = "decomposer"
        elif "knowledge curator" in prompt:
            tag = "knowledge_extractor"

        self.call_count[tag] = self.call_count.get(tag, 0) + 1

        if tag in self.raise_for:
            raise ProviderError(
                f"stub raising for {tag}",
                provider=self.name, model=model, latency_ms=0,
            )

        text = self.responses.get(tag, '{"error": "no stub for tag " + tag}')

        # Substitute INV_PLACEHOLDER + SQ_PLACEHOLDER with the actual
        # values extracted from the prompt. Lets canned responses
        # cross-check (the decomposer parser rejects mismatched
        # investigation_id; the evidence parser rejects mismatched
        # sub_question).
        import re as _re
        inv_match = _re.search(r"Investigation ID:\s*`([^`]+)`", prompt)
        if inv_match:
            text = text.replace("INV_PLACEHOLDER", inv_match.group(1))
        sq_match = _re.search(r"Sub-question:\s*\n\s*>\s*(.+)", prompt)
        if sq_match:
            sq_text = sq_match.group(1).strip()
            text = text.replace("(any sub-question)", sq_text)
            text = text.replace("(any)", sq_text)

        return RawProviderResponse(
            text=text,
            raw_usage={"input_tokens": 100, "output_tokens": 80},
            finish_reason="end_turn", latency_ms=5,
        )

    def normalize_usage(self, raw_usage):
        return NormalizedUsage(
            input_tokens=int(raw_usage.get("input_tokens", 0)),
            output_tokens=int(raw_usage.get("output_tokens", 0)),
        )


def _all_role_config() -> DispatchConfig:
    """A single tier wired to the single stub provider; every role
    points at the same tier so the stub's tag-based dispatch handles
    all calls."""
    pricing = TierPricing(input_per_mtok=0.0, output_per_mtok=0.0)
    # Tier name must be one of the schema's known Literals
    # (flash / pro / synthesis / verify / local).
    tier = TierConfig(
        name="pro", provider="loop-one-stub", model="stub-model",
        max_tokens=4096, temperature=0.1, context_budget_tokens=128_000,
        pricing=pricing, fallback=None,
    )
    return DispatchConfig(
        role_tiers={
            "decomposer": "pro",
            "evidence_retriever": "pro",
            "parameter_extractor": "pro",
            "connector": "pro",
            "synthesizer": "pro",
            "knowledge_extractor": "pro",
        },
        tiers={"pro": tier},
    )


def _patch_dispatch(monkeypatch, config: DispatchConfig) -> None:
    import substrate.dispatch.router as router
    monkeypatch.setattr(
        router.DispatchConfig, "from_yaml",
        classmethod(lambda cls, path: config),
    )


# ---------------------------------------------------------------------------
# Canned responses
# ---------------------------------------------------------------------------


_DECOMPOSER_RESPONSE = json.dumps({
    "investigation_id": "INV_PLACEHOLDER",
    "decomposition": [
        {
            "sub_question": "What primary evidence shows quantum X?",
            "category": "technology_risk",
            "rationale": "Independent verification of the quantum claim.",
            "evidence_type_required": "quantitative",
        },
        {
            "sub_question": "What is the addressable quantum market?",
            "category": "market_sizing",
            "rationale": "Magnitude bounds the thesis.",
            "evidence_type_required": "quantitative",
        },
        {
            "sub_question": "What execution risks apply?",
            "category": "team_and_execution",
            "rationale": "Bounds credibility of execution claims.",
            "evidence_type_required": "qualitative",
        },
        {
            "sub_question": "Regulatory exposure?",
            "category": "regulatory_exposure",
            "rationale": "Regulatory blocks invalidate the thesis.",
            "evidence_type_required": "mixed",
        },
    ],
    "keywords": [
        {"term": f"keyword_{i}", "synonyms": [f"alt_{i}"]} for i in range(8)
    ],
})


def _evidence_response_for(sub_q: str) -> str:
    """Per-sub-question evidence response. The stub dispatcher routes
    all evidence_retriever calls to the same template; we vary the
    sub_question via the prompt-inspection tagger."""
    return json.dumps({
        "sub_question": sub_q,
        "answer": "Quantum X is established by two Tier-1 sources.",
        "supporting_claims": [
            {
                "claim": "Quantum X holds at threshold",
                "evidence_type": "direct",
                "chunk_ids": ["chunk-1"],
                "edge_ids": [],
                "source_tier_min": 1,
                "confidence": "high",
                "confidence_basis": "two SEC filings + peer-reviewed paper",
            },
        ],
        "evidentiary_gaps": [],
        "insufficient_evidence": False,
    })


_PARAMETER_EXTRACTOR_RESPONSE = json.dumps({
    "parameters": [
        {
            "semantic_anchor": "training_compute",
            "metric_value": {"value_type": "scalar", "value": 1e25, "unit": "FLOP"},
            "qualitative_descriptor": None,
            "evidence_status": "observed",
            "source_chunk_ids": ["chunk-1"],
            "constraint_strictness": "soft",
        },
    ],
})


_CONNECTOR_RESPONSE = json.dumps({
    "keyword_mappings": [],
    "selected_algorithm": "top_n_shortest_paths",
    "algorithm_rationale": "Default choice.",
    "paths": [],
    "natural_language_relationships": [],
})


_SYNTHESIZER_RESPONSE = json.dumps({
    "thesis_summary": (
        "PsiQuantum's photonic quantum approach is well-supported by primary "
        "evidence; the substrate is feasible and the team has demonstrated "
        "execution capability."
    ),
    "implicit_recommendation": "proceed",
    "thesis_components": [
        {
            "claim": (
                "PsiQuantum's photonic substrate is established by primary "
                "sources."
            ),
            "confidence": "high",
            "confidence_basis": "two SEC filings + peer-reviewed paper",
            "supporting_chunk_ids": ["chunk-1"],
            "supporting_path_indices": [],
            "effective_source_tier": 1,
            "hedging_required": False,
        },
    ],
    "falsification_conditions": [
        {
            "condition": "Coherence time below threshold for fault tolerance",
            "specific_observable": "QEC overhead exceeds 10000:1",
            "timeframe": "within 6 quarters",
        },
    ],
    "execution_risks": [
        {
            "risk": "Key engineering team attrition",
            "severity_if_manifested": "high",
            "leading_indicator": "voluntary departure rate",
        },
    ],
    "constraint_compliance": {
        "hard_constraints_satisfied": True,
        "soft_constraints_violated": [],
        "violations_justified": [],
    },
    "reasoning_paths_used": [],
    "conviction_level": 0.72,
})


_KNOWLEDGE_EXTRACTION_RESPONSE = json.dumps({
    "Domain Fundamentals": [
        {
            "text": "Photonic quantum substrates require fewer thermal isolations",
            "confidence": "Measured",
            "date_observed": "2024",
            "source": "PsiQuantum Q3 letter",
        },
    ],
})


# ---------------------------------------------------------------------------
# App / client fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app_and_bus():
    bus = EventBroadcaster()
    app = create_app(broadcaster=bus, cors_origins=[])
    return app, bus


@pytest.fixture
async def async_client(app_and_bus):
    app, _ = app_and_bus
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _post_start(
    ac, *, investigation_id: str, question: str,
    topic_slug: str | None = "psi-quantum-demo",
) -> None:
    payload = {
        "action_type": "investigation.start_requested",
        "question": question,
        "context": "",
        "topic_slug": topic_slug,
        "max_sub_questions": 4,
    }
    r = await ac.post(
        "/events/typed",
        json={
            "investigation_id": investigation_id,
            "payload": payload,
            "role": "operator",
        },
    )
    assert r.status_code == 201, r.text


async def _await_terminal(bus, investigation_id: str, *, timeout: float = 10.0):
    """Wait for INVESTIGATION_COMPLETED or _FAILED to appear in the
    trajectory. The orchestrator runs as a detached asyncio.Task —
    we poll the trajectory rather than register another handler."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        with contextlib.suppress(TimeoutError):
            await bus.wait_for_handlers(timeout=2.0)
        rows = trajectory(investigation_id)
        for r in rows:
            at = r.get("action_type")
            if at in (
                ActionType.INVESTIGATION_COMPLETED.value,
                ActionType.INVESTIGATION_FAILED.value,
            ):
                return r
        await asyncio.sleep(0.05)
    return None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_loop_one_happy_path_emits_completed(
    monkeypatch, app_and_bus, async_client,
):
    _, bus = app_and_bus
    inv = "inv-loop-happy"
    monkeypatch.setattr(
        "orchestration.loop_one.orchestrator._render_chunks_block_for_sub_question",
        lambda _q, top_k=5, policy_tag="attribution_eligible": (
            "[chunk-1] Source tier: 1 | Document: PsiQuantum photonic quantum "
            "roadmap | Section: Fixture | Similarity: 1.000\n\n"
            "PsiQuantum photonic quantum roadmap evidence: Quantum X holds "
            "at threshold, the photonic substrate is established by primary "
            "sources, and execution capability is documented.\n"
        ),
    )

    # Tag-based stub that responds for every role + the knowledge
    # extractor. Sub-question text varies per call but the evidence
    # template is generic.
    evidence_responses = _evidence_response_for("(any sub-question)")
    register_provider(_RoleStubProvider({
        "decomposer": _DECOMPOSER_RESPONSE,
        "evidence_retriever": evidence_responses,
        "parameter_extractor": _PARAMETER_EXTRACTOR_RESPONSE,
        "connector": _CONNECTOR_RESPONSE,
        "synthesizer": _SYNTHESIZER_RESPONSE,
        "knowledge_extractor": _KNOWLEDGE_EXTRACTION_RESPONSE,
    }))
    _patch_dispatch(monkeypatch, _all_role_config())

    await _post_start(
        async_client, investigation_id=inv,
        question="Is PsiQuantum's photonic quantum roadmap defensible?",
    )

    terminal = await _await_terminal(bus, inv, timeout=30.0)
    assert terminal is not None, "no terminal event landed in trajectory"
    assert terminal["action_type"] == ActionType.INVESTIGATION_COMPLETED.value

    e = Event.model_validate(terminal)
    assert isinstance(e.payload, InvestigationCompletedPayload)
    p = e.payload
    assert p.thesis_summary.startswith("PsiQuantum")
    assert p.implicit_recommendation == "proceed"
    assert p.constraint_loop_status in ("single_pass", "passed")
    assert p.master_md_path is not None
    assert Path(p.master_md_path).exists()
    assert p.total_phases_verified == 8
    assert "quantum-computing-knowledge" in p.domains_patched

    ok, reason = check_deep_research_complete(inv)
    assert ok is True, reason


@pytest.mark.asyncio
async def test_loop_one_decomposer_failure_emits_failed_at_phase_1(
    monkeypatch, app_and_bus, async_client,
):
    """When the decomposer dispatch fails, the orchestrator must
    emit INVESTIGATION_FAILED with phase=1 + the diagnostic."""
    _, bus = app_and_bus
    inv = "inv-loop-fail-1"

    # Stub raises for decomposer — the bridge sends an empty
    # Delivered payload (the bridge's fallback shape), which fails
    # the Phase 1 postcondition (no orientation.md on disk).
    register_provider(_RoleStubProvider({
        "decomposer": "{}",  # parse will fail
    }, raise_for=set()))
    _patch_dispatch(monkeypatch, _all_role_config())

    await _post_start(
        async_client, investigation_id=inv,
        question="Anything will do here.",
    )

    terminal = await _await_terminal(bus, inv, timeout=25.0)
    assert terminal is not None
    assert terminal["action_type"] == ActionType.INVESTIGATION_FAILED.value
    e = Event.model_validate(terminal)
    p = e.payload
    assert isinstance(p, InvestigationFailedPayload)
    assert p.phase == 1
    # The orchestrator's reason references one of: timeout,
    # postcondition failure, or the semantic empty-decomposition
    # guard (the bridge's fallback Delivered payload had no
    # sub-questions, which Phase 1 explicitly rejects via
    # the orchestrator's role-output sanity check).
    assert (
        "postcondition failed" in p.reason
        or "timed out" in p.reason
        or "no sub-questions" in p.reason
    )
    assert p.last_completed_phase is None


@pytest.mark.asyncio
async def test_loop_one_synthesizer_unparseable_converges_via_insufficient_evidence(
    monkeypatch, app_and_bus, async_client, tmp_path,
):
    """When phase 1-5 land but the synthesizer can't produce a
    parseable thesis (even after one self-repair retry), the bridge
    falls through to the empty-delivered shape with
    ``insufficient_evidence`` recommendation. Phase 6's escape hatch
    accepts that as converged — the investigation terminates as
    ``completed``, not ``failed``. Observability is preserved: the
    empty thesis_summary + thesis_components signal the substrate
    couldn't produce a defensible answer.

    History: pre-2026-05-18 (H2.5), the same path produced
    investigation.failed because Phase 6 had no escape hatch. The
    H2.5 change graduated the substrate to "underdetermined is a
    valid terminal state" — the operator now sees verdicts like
    "no defensible thesis from the available evidence" instead of
    opaque substrate failures."""
    _, bus = app_and_bus
    inv = "inv-loop-synth-unparseable"

    # Seed the research dir with the phase 1-5 artifacts so those
    # postconditions pass (we want to isolate the synth-failure path).
    research_dir = Path(tmp_path / "research" / inv)
    research_dir.mkdir(parents=True)
    (research_dir / "orientation.md").write_text(
        "# Orientation\n\n"
        + ("intro prose. " * 60)
        + "\n\n## Prior Graph Knowledge\n\n"
        + "Based on chunk_abc123 we know X.\n"
    )
    body_500 = "round 1 content. " * 50
    for n in (
        "round1-technical.md", "round1-competitive.md",
        "round1-strategic.md",
    ):
        (research_dir / n).write_text(body_500)
    (research_dir / "round1-critique.md").write_text(
        "Critique covers technical, competitive, and strategic.\n"
    )
    (research_dir / "round2-technical.md").write_text(body_500)
    (research_dir / "round2-critique.md").write_text(
        "Round 2 critique " * 40
    )

    # Synth stub returns un-parseable text on both first dispatch and
    # the self-repair retry. Bridge emits a fallback Delivered with
    # insufficient_evidence + empty falsifications, which Phase 6's
    # escape hatch now accepts.
    register_provider(_RoleStubProvider({
        "decomposer": _DECOMPOSER_RESPONSE,
        "evidence_retriever": _evidence_response_for("(any)"),
        "parameter_extractor": _PARAMETER_EXTRACTOR_RESPONSE,
        "connector": _CONNECTOR_RESPONSE,
        "synthesizer": "this is not JSON at all",
    }))
    _patch_dispatch(monkeypatch, _all_role_config())

    await _post_start(
        async_client, investigation_id=inv,
        question="PsiQuantum roadmap question.",
    )

    terminal = await _await_terminal(bus, inv, timeout=30.0)
    assert terminal is not None
    assert terminal["action_type"] == ActionType.INVESTIGATION_COMPLETED.value
    e = Event.model_validate(terminal)
    # The completion payload carries thesis_summary="" — the operator-
    # facing signal that the substrate couldn't produce a defensible
    # thesis. The investigation IS complete; the answer IS "underdetermined."
    p = e.payload
    assert p.implicit_recommendation == "insufficient_evidence"
    assert p.thesis_summary == ""
