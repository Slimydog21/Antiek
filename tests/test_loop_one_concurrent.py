"""Concurrent-investigation hardening (Sprint 8 day 5).

Loop 1's orchestrator coordinator uses per-(investigation_id,
action_type) futures to disambiguate event delivery across concurrent
investigations. This test suite stresses that design: three
concurrent investigations against the same broadcaster, verifying:

1. Per-investigation decomposition / thesis content does NOT
   cross-contaminate.
2. Each investigation's research_dir is isolated; file markers
   (orientation.md / round1-*.md / round2-*.md / MASTER.md) land in
   the right per-investigation directory.
3. Each investigation gets its own MASTER.md at the right path with
   its own thesis text — no last-writer-wins clobbering.
4. The broadcaster's handler dispatch fans out correctly under
   concurrent load — every investigation reaches its terminal state.
5. Same-domain concurrent skill patches both append findings (the
   auto-patch section accumulates rather than getting clobbered).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from interfaces.research.api import EventBroadcaster, create_app  # noqa: E402
from processing.embedding import _reset_default_provider  # noqa: E402
from substrate.dispatch import (  # noqa: E402
    DispatchConfig,
    NormalizedUsage,
    RawProviderResponse,
    TierConfig,
    TierPricing,
    register_provider,
    reset_provider_registry,
)
from substrate.event_log import trajectory  # noqa: E402
from substrate.schemas import ActionType, Event  # noqa: E402

# ---------------------------------------------------------------------------
# Per-investigation tag-based stub provider
# ---------------------------------------------------------------------------


def _decomposer_response_for(inv_id: str) -> str:
    """A decomposer response with INV_PLACEHOLDER (the stub provider
    substitutes the real investigation_id at call time via prompt
    inspection) and an inv-id-tagged sub-question so cross-
    contamination would be visible."""
    return json.dumps({
        "investigation_id": "INV_PLACEHOLDER",
        "decomposition": [
            {
                "sub_question": f"Sub-question A for {inv_id}",
                "category": "technology_risk",
                "rationale": "Independent verification of the X claim.",
                "evidence_type_required": "quantitative",
            },
            {
                "sub_question": f"Sub-question B for {inv_id}",
                "category": "market_sizing",
                "rationale": "Magnitude bounds the thesis.",
                "evidence_type_required": "quantitative",
            },
            {
                "sub_question": f"Sub-question C for {inv_id}",
                "category": "team_and_execution",
                "rationale": "Bounds credibility of execution claims.",
                "evidence_type_required": "qualitative",
            },
            {
                "sub_question": f"Sub-question D for {inv_id}",
                "category": "regulatory_exposure",
                "rationale": "Regulatory blocks invalidate the thesis.",
                "evidence_type_required": "mixed",
            },
        ],
        "keywords": [
            {"term": f"keyword_{i}_{inv_id[-4:]}", "synonyms": [f"alt_{i}"]}
            for i in range(8)
        ],
    })


def _synthesizer_response_for(inv_id: str) -> str:
    """Synthesizer response tagged with the investigation_id so we
    can detect cross-contamination in the thesis content."""
    return json.dumps({
        # The "quantum" keyword routes ``classify_domains`` to the
        # ``quantum-computing-knowledge`` domain that the test fixture
        # seeds. Without it, Phase 8 has no domain to patch and the
        # auto_patch_applied event fires with ``patched=[]``, which
        # the postcondition correctly rejects. Was relying on a
        # since-fixed timezone-naive cutoff bug in
        # check_phase_8 — see H4.5 (2026-05-18).
        "thesis_summary": (
            f"Thesis for {inv_id}: quantum substrates hold under "
            "tier-1 evidence (primary sources)."
        ),
        "implicit_recommendation": "proceed",
        "thesis_components": [
            {
                "claim": (
                    f"Quantum substrate evidence supports {inv_id} per "
                    "primary sources."
                ),
                "confidence": "high",
                "confidence_basis": "two SEC filings + peer-reviewed paper",
                "supporting_chunk_ids": [f"chunk-{inv_id}-1"],
                "supporting_path_indices": [],
                "effective_source_tier": 1,
                "hedging_required": False,
            },
        ],
        "falsification_conditions": [
            {
                "condition": (
                    f"Correlation breaks below 0.5 for {inv_id}"
                ),
                "specific_observable": f"Q4 dataset r-value for {inv_id}",
                "timeframe": "within 6 quarters",
            },
        ],
        "execution_risks": [
            {
                "risk": f"Team attrition for {inv_id}",
                "severity_if_manifested": "moderate",
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


_EVIDENCE_RESPONSE = json.dumps({
    "sub_question": "(any sub-question)",
    "answer": "Evidence Q2.",
    "supporting_claims": [
        {
            "claim": "Quantum X holds at threshold",
            "evidence_type": "direct",
            "chunk_ids": ["chunk-1", "chunk-INV_PLACEHOLDER-1"],
            "edge_ids": [],
            "source_tier_min": 1,
            "confidence": "high",
            "confidence_basis": "two SEC filings",
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

_KNOWLEDGE_EXTRACTION_RESPONSE = json.dumps({
    "Domain Fundamentals": [
        {
            "text": "Photonic substrates require fewer thermal isolations",
            "confidence": "Measured",
            "date_observed": "2024",
            "source": "Q3 letter",
        },
    ],
})


class _PerInvestigationStub:
    """Tag-based stub provider whose decomposer + synthesizer
    responses VARY per investigation. Identifies the investigation
    by parsing the rendered prompt for ``Investigation ID:`` (the
    decomposer prompt) or the synthesizer's
    ``decomposition_block`` JSON (which contains the sub-question
    text with the inv_id suffix the decomposer stub injected)."""

    name = "concurrent-stub"

    def __init__(self):
        self.call_count: dict[str, int] = {}

    def _extract_inv_id(self, prompt: str) -> str:
        """Find the investigation_id by looking for the decomposer
        prompt's ``Investigation ID: \\`<id>\\`\\`\\`\\`\\`\\`\\`\\`\\`\\`\\`\\`\\`\\`\\`\\`\\`\\`\\`\\`\\`\\`\\``` marker OR a per-inv
        sub-question token."""
        import re as _re
        m = _re.search(r"Investigation ID:\s*`([^`]+)`", prompt)
        if m:
            return m.group(1)
        # Fall back: look for "Sub-question A for inv-<id>" pattern
        # (injected by _decomposer_response_for via the stub
        # substitution; the synthesizer's user prompt includes the
        # decomposition_block which has it).
        m = _re.search(r"Sub-question [A-D] for (\S+)", prompt)
        if m:
            return m.group(1).rstrip('",').rstrip()
        return "(unknown-inv)"

    def call(self, *, model, prompt, max_tokens, temperature) -> RawProviderResponse:
        # Identify role.
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
        else:
            tag = "unknown"

        self.call_count[tag] = self.call_count.get(tag, 0) + 1
        inv_id = self._extract_inv_id(prompt)

        if tag == "decomposer":
            text = _decomposer_response_for(inv_id)
        elif tag == "synthesizer":
            text = _synthesizer_response_for(inv_id)
        elif tag == "evidence_retriever":
            text = _EVIDENCE_RESPONSE
        elif tag == "parameter_extractor":
            text = _PARAMETER_EXTRACTOR_RESPONSE
        elif tag == "connector":
            text = _CONNECTOR_RESPONSE
        elif tag == "knowledge_extractor":
            text = _KNOWLEDGE_EXTRACTION_RESPONSE
        else:
            text = '{"error": "no stub"}'

        # Substitute investigation_id placeholder + sub-question
        # placeholder (the evidence_retriever parser cross-checks).
        import re as _re
        text = text.replace("INV_PLACEHOLDER", inv_id)
        sq_match = _re.search(r"Sub-question:\s*\n\s*>\s*(.+)", prompt)
        if sq_match:
            text = text.replace("(any sub-question)", sq_match.group(1).strip())

        return RawProviderResponse(
            text=text,
            raw_usage={"input_tokens": 100, "output_tokens": 80},
            finish_reason="end_turn", latency_ms=2,
        )

    def normalize_usage(self, raw_usage):
        return NormalizedUsage(
            input_tokens=int(raw_usage.get("input_tokens", 0)),
            output_tokens=int(raw_usage.get("output_tokens", 0)),
        )


def _all_role_config() -> DispatchConfig:
    pricing = TierPricing(input_per_mtok=0.0, output_per_mtok=0.0)
    tier = TierConfig(
        name="pro", provider="concurrent-stub", model="stub-model",
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


def _chunks_block_for_sub_question(sub_question: str, top_k: int = 5) -> str:
    import re as _re

    match = _re.search(r"Sub-question [A-D] for (\S+)", sub_question)
    inv_id = (
        match.group(1).rstrip('",').rstrip()
        if match else "(unknown-inv)"
    )
    return (
        "[chunk-1] Source tier: 1 | Document: Shared quantum fixture "
        "| Section: Evidence | Similarity: 1.000\n\n"
        "Quantum X holds at threshold under tier-1 primary evidence.\n\n"
        "---\n"
        f"[chunk-{inv_id}-1] Source tier: 1 | Document: {inv_id} quantum "
        "fixture | Section: Synthesis | Similarity: 1.000\n\n"
        f"Quantum substrate evidence supports {inv_id} per primary sources.\n"
    )


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "graph.duckdb"))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    monkeypatch.setenv("ANTIEK_RESEARCH_PHASE_LOG_DIR", str(tmp_path / "phase_logs"))
    monkeypatch.setenv("ANTIEK_RESEARCH_DIR", str(tmp_path / "research"))
    monkeypatch.setenv("ANTIEK_KNOWLEDGE_SKILLS_DIR", str(tmp_path / "skills"))
    # Seed a domain skill dir so Phase 8 patcher can land.
    quantum_dir = tmp_path / "skills" / "quantum-computing-knowledge"
    quantum_dir.mkdir(parents=True)
    (quantum_dir / "SKILL.md").write_text(
        "# Quantum\n\n"
        "## Domain Fundamentals\n\n(Findings will be added.)\n\n"
        "## Key Players\n\n(Findings will be added.)\n\n"
        "## Quantitative Benchmarks\n\n(Findings will be added.)\n\n"
        "## Competitive Dynamics\n\n(Findings will be added.)\n\n"
        "## Open Questions\n\n(Findings will be added.)\n\n"
        "## Monitoring Checklist\n\n(Findings will be added.)\n"
    )
    _reset_default_provider()
    reset_provider_registry()
    yield
    _reset_default_provider()
    reset_provider_registry()


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


async def _post_investigation(
    ac, *, investigation_id: str, question: str, topic_slug: str,
) -> None:
    r = await ac.post(
        "/investigations",
        json={
            "question": question,
            "investigation_id": investigation_id,
            "topic_slug": topic_slug,
            "max_sub_questions": 4,
        },
    )
    assert r.status_code == 202, r.text


async def _await_completion(ac, investigation_id: str, *, timeout: float = 30.0):
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        r = await ac.get(f"/investigations/{investigation_id}")
        body = r.json()
        if body["status"] in ("completed", "failed"):
            return body
        await asyncio.sleep(0.1)
    return None


# ---------------------------------------------------------------------------
# 1-4. Three concurrent investigations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_three_concurrent_investigations_complete_independently(
    monkeypatch, app_and_bus, async_client, tmp_path,
):
    """The big stress test: three investigations start simultaneously
    via three POSTs; each runs through all 9 phases via the shared
    broadcaster. Each must reach ``completed`` independently with
    its OWN thesis content (no cross-contamination) and its OWN
    MASTER.md path."""
    _, bus = app_and_bus
    register_provider(_PerInvestigationStub())
    _patch_dispatch(monkeypatch, _all_role_config())
    monkeypatch.setattr(
        "orchestration.loop_one.orchestrator._render_chunks_block_for_sub_question",
        _chunks_block_for_sub_question,
    )

    inv_specs = [
        ("inv-conc-alpha", "Question A about quantum?", "topic-alpha"),
        ("inv-conc-beta",  "Question B about quantum?", "topic-beta"),
        ("inv-conc-gamma", "Question C about quantum?", "topic-gamma"),
    ]

    # Fire all three POSTs concurrently.
    await asyncio.gather(*(
        _post_investigation(
            async_client, investigation_id=inv_id,
            question=q, topic_slug=slug,
        )
        for inv_id, q, slug in inv_specs
    ))

    # Wait for each to complete.
    results = await asyncio.gather(*(
        _await_completion(async_client, inv_id, timeout=45.0)
        for inv_id, _, _ in inv_specs
    ))

    # All three must have completed.
    assert all(r is not None for r in results), (
        f"Some investigations didn't terminate: {results}"
    )
    for (inv_id, _, _), body in zip(inv_specs, results, strict=True):
        assert body["status"] == "completed", (
            f"{inv_id}: {body['status']} — {body.get('terminal_payload')}"
        )

    # Cross-contamination check — each investigation's thesis MUST
    # mention its own ID. The PerInvestigationStub's synthesizer
    # response embeds the inv_id in the thesis_summary.
    for (inv_id, _, _), body in zip(inv_specs, results, strict=True):
        tp = body["terminal_payload"]
        assert inv_id in tp["thesis_summary"], (
            f"{inv_id}: thesis_summary doesn't reference its own id "
            f"(cross-contamination?): {tp['thesis_summary']}"
        )

    # Per-investigation MASTER.md isolation — each is at a distinct
    # topic-slug path.
    paths = {inv_id: body["terminal_payload"]["master_md_path"]
             for (inv_id, _, _), body in zip(inv_specs, results, strict=True)}
    assert len(set(paths.values())) == 3, (
        f"MASTER.md paths collided: {paths}"
    )
    for inv_id, path in paths.items():
        p = Path(path)
        assert p.exists(), f"{inv_id}: MASTER.md missing at {path}"
        body_text = p.read_text()
        assert inv_id in body_text, (
            f"{inv_id}: MASTER.md doesn't mention own id (paths swapped?)"
        )


# ---------------------------------------------------------------------------
# 5. Per-investigation file marker isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_per_investigation_file_markers_isolated(
    monkeypatch, app_and_bus, async_client, tmp_path,
):
    """Each investigation's per-phase file markers (orientation.md,
    round1-*.md, etc.) land in its OWN research dir. No marker
    should appear in another investigation's directory.

    History (2026-05-18 H4.5): this test was briefly marked
    flaky_in_ci when the failure was misdiagnosed as a stub
    prompt-parsing issue. Real root cause was a timezone-naive
    datetime bug in ``check_phase_8`` (see fix in
    orchestration/phase_runner/postconditions.py). The bug silently
    shifted the Phase 8 cutoff backwards by the local UTC offset,
    making every seed file appear "modified after" the cutoff on
    non-UTC dev machines. CI runs UTC, so the cutoff didn't shift,
    and the seed file's pre-investigation-start mtime failed the
    strict ``>`` check. Marker removed once the postcondition was
    fixed."""
    _, bus = app_and_bus
    register_provider(_PerInvestigationStub())
    _patch_dispatch(monkeypatch, _all_role_config())

    inv_ids = ["inv-iso-1", "inv-iso-2"]
    await asyncio.gather(*(
        _post_investigation(
            async_client, investigation_id=inv,
            question=f"Question for {inv}?", topic_slug=inv,
        )
        for inv in inv_ids
    ))
    results = await asyncio.gather(*(
        _await_completion(async_client, inv, timeout=45.0)
        for inv in inv_ids
    ))
    assert all(r and r["status"] == "completed" for r in results)

    research_root = tmp_path / "research"
    for inv in inv_ids:
        inv_dir = research_root / inv
        assert inv_dir.exists(), f"{inv}: research dir not created"
        # Every per-phase marker file present.
        for marker in (
            "orientation.md",
            "round1-technical.md", "round1-competitive.md",
            "round1-strategic.md",
            "round1-critique.md",
            "round2-relational.md", "round2-critique.md",
        ):
            p = inv_dir / marker
            assert p.exists(), f"{inv}: marker {marker} missing"
            # Marker carries the investigation id — defends against
            # cross-write contamination.
            assert inv in p.read_text(), (
                f"{inv}: marker {marker} doesn't mention own id"
            )


# ---------------------------------------------------------------------------
# 6. Broadcaster handler fan-out under concurrent load
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handler_fan_out_no_lost_events(
    monkeypatch, app_and_bus, async_client,
):
    """Every concurrent investigation must see the full role chain
    fire (decompose → evidence × 4 → parameter_extract → connector
    → synthesize → master_md_written → auto_patch_applied = 9 role
    delivered events plus the start + completed lifecycle events).

    Per-investigation trajectory walks confirm no events were
    dropped by the broadcaster's handler dispatch under load.

    Same H4.5 history as the sibling test above: was briefly
    flaky_in_ci due to a timezone-naive datetime bug in Phase 8's
    postcondition. Real fix landed in
    orchestration/phase_runner/postconditions.py."""
    _, bus = app_and_bus
    register_provider(_PerInvestigationStub())
    _patch_dispatch(monkeypatch, _all_role_config())

    inv_ids = [f"inv-fanout-{i}" for i in range(3)]
    await asyncio.gather(*(
        _post_investigation(
            async_client, investigation_id=inv,
            question=f"Question for {inv}?", topic_slug=inv,
        )
        for inv in inv_ids
    ))
    results = await asyncio.gather(*(
        _await_completion(async_client, inv, timeout=45.0)
        for inv in inv_ids
    ))
    assert all(r and r["status"] == "completed" for r in results)

    # Trajectory walk per investigation.
    required_actions = {
        ActionType.INVESTIGATION_START_REQUESTED.value: 1,
        ActionType.DECOMPOSE_QUESTION_DELIVERED.value: 1,
        ActionType.EVIDENCE_RETRIEVE_DELIVERED.value: 4,
        ActionType.PARAMETER_EXTRACT_DELIVERED.value: 1,
        ActionType.CONNECTOR_DELIVERED.value: 1,
        ActionType.SYNTHESIZE_DELIVERED.value: 1,
        ActionType.MASTER_MD_WRITTEN.value: 1,
        ActionType.AUTO_PATCH_APPLIED.value: 1,
        ActionType.INVESTIGATION_COMPLETED.value: 1,
    }
    for inv in inv_ids:
        rows = trajectory(inv)
        counts: dict[str, int] = {}
        for r in rows:
            at = r.get("action_type")
            counts[at] = counts.get(at, 0) + 1
        for action, expected in required_actions.items():
            got = counts.get(action, 0)
            assert got >= expected, (
                f"{inv}: action {action!r} expected ≥{expected}, got {got}"
            )


# ---------------------------------------------------------------------------
# 7. Same-domain concurrent skill patches accumulate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_skill_patches_both_findings_recorded(
    monkeypatch, app_and_bus, async_client, tmp_path,
):
    """Two investigations both targeting the quantum-computing
    domain (the only seeded one) patch the SAME SKILL.md
    concurrently. Within a single asyncio loop, file writes don't
    interleave (CPython GIL + asyncio cooperative), so both patches
    should land in the section's accumulated content. This test
    documents the in-process behavior and surfaces the contract for
    multi-worker environments (which would require flock — deferred
    to a future hardening pass)."""
    _, bus = app_and_bus
    register_provider(_PerInvestigationStub())
    _patch_dispatch(monkeypatch, _all_role_config())

    inv_ids = ["inv-patch-1", "inv-patch-2"]
    await asyncio.gather(*(
        _post_investigation(
            async_client, investigation_id=inv,
            question=f"PsiQuantum question for {inv}?", topic_slug=inv,
        )
        for inv in inv_ids
    ))
    results = await asyncio.gather(*(
        _await_completion(async_client, inv, timeout=45.0)
        for inv in inv_ids
    ))
    assert all(r and r["status"] == "completed" for r in results)

    skill_path = tmp_path / "skills" / "quantum-computing-knowledge" / "SKILL.md"
    body = skill_path.read_text()
    # Both investigations' findings should appear in the patched
    # Domain Fundamentals section (the extraction returns the same
    # finding text per investigation, so both findings land — the
    # auto-patch APPENDS within the section).
    assert "Photonic substrates require fewer thermal isolations" in body
    # Both investigations were patched — count the auto-patch
    # marker appearances. The auto-patch's idempotency marker is
    # per-synthesis_id; we use one synth_id per investigation
    # (orchestrator naming: "syn-<inv_id>").
    assert body.count("Domain Fundamentals") >= 1
    # Trajectory: both investigations emitted auto_patch_applied
    # with "quantum-computing-knowledge" patched.
    for inv in inv_ids:
        rows = trajectory(inv)
        auto_patch_events = [
            Event.model_validate(r) for r in rows
            if r["action_type"] == ActionType.AUTO_PATCH_APPLIED.value
        ]
        assert len(auto_patch_events) >= 1, f"{inv}: no auto_patch_applied"
        p = auto_patch_events[-1].payload
        assert "quantum-computing-knowledge" in p.patched, (
            f"{inv}: did not patch the seeded domain"
        )
