"""Tests for the Loop 1 REST endpoints (Sprint 8 day 4).

POST /investigations + GET /investigations/{id}.

Coverage:

1. POST with explicit investigation_id returns 202 + handle.
2. POST without investigation_id auto-generates one.
3. POST validation: empty question → 422.
4. GET on never-started investigation → status="not_found".
5. GET on in-progress investigation → "in_progress" + last delivered.
6. GET on completed investigation → "completed" + terminal_payload.
7. End-to-end: POST → orchestrator drives chain → GET reports
   completed with thesis_summary + master_md_path in terminal_payload.
8. Orchestrator picks up the POSTed start event (the bridge subscribes
   to the broadcast that POST triggers).
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
    ProviderError,
    RawProviderResponse,
    TierConfig,
    TierPricing,
    register_provider,
    reset_provider_registry,
)
from substrate.event_log import emit_typed, trajectory  # noqa: E402
from substrate.schemas import ActionType  # noqa: E402

# Reuse the stub provider + canned responses from the orchestrator
# end-to-end test — same shape applies here.
from tests.test_loop_one_orchestrator import (  # noqa: E402
    _DECOMPOSER_RESPONSE,
    _PARAMETER_EXTRACTOR_RESPONSE,
    _CONNECTOR_RESPONSE,
    _SYNTHESIZER_RESPONSE,
    _KNOWLEDGE_EXTRACTION_RESPONSE,
    _RoleStubProvider,
    _all_role_config,
    _evidence_response_for,
    _patch_dispatch,
)


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "graph.duckdb"))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    monkeypatch.setenv("ANTIEK_RESEARCH_PHASE_LOG_DIR", str(tmp_path / "phase_logs"))
    monkeypatch.setenv("ANTIEK_RESEARCH_DIR", str(tmp_path / "research"))
    monkeypatch.setenv("ANTIEK_KNOWLEDGE_SKILLS_DIR", str(tmp_path / "skills"))
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


# ---------------------------------------------------------------------------
# 1-3. POST shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_explicit_id_returns_handle(async_client):
    r = await async_client.post(
        "/investigations",
        json={
            "question": "Will TSMC dominate N2 yield by 2027?",
            "topic_slug": "tsmc-n2",
            "investigation_id": "inv-explicit",
        },
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["investigation_id"] == "inv-explicit"
    assert body["status"] == "started"
    assert body["start_event_id"]


@pytest.mark.asyncio
async def test_post_auto_generates_id(async_client):
    r = await async_client.post(
        "/investigations",
        json={"question": "Will TSMC dominate N2 by 2027?"},
    )
    assert r.status_code == 202
    body = r.json()
    assert body["investigation_id"].startswith("inv-")
    assert len(body["investigation_id"]) > 5


@pytest.mark.asyncio
async def test_post_validates_question_length(async_client):
    r = await async_client.post(
        "/investigations", json={"question": "x"},  # too short
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_post_emits_typed_start_event_into_trajectory(async_client):
    r = await async_client.post(
        "/investigations",
        json={
            "question": "What's the load-bearing constraint on X?",
            "investigation_id": "inv-evt",
        },
    )
    assert r.status_code == 202
    rows = trajectory("inv-evt")
    start_rows = [
        x for x in rows
        if x["action_type"] == ActionType.INVESTIGATION_START_REQUESTED.value
    ]
    assert len(start_rows) == 1
    assert start_rows[0]["role"] == "operator"


# ---------------------------------------------------------------------------
# 4-6. GET status shapes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_not_found_when_no_events(async_client):
    r = await async_client.get("/investigations/inv-missing")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "not_found"
    assert body["investigation_id"] == "inv-missing"


@pytest.mark.asyncio
async def test_get_in_progress_for_started_but_unfinished(async_client):
    # Emit a start event directly so no orchestrator runs (no providers
    # registered → orchestrator's first dispatch will fail and emit
    # a FAILED terminal). Wait briefly so the orchestrator gets a
    # chance to run; assert the GET correctly captures phase 1 fail
    # OR in_progress depending on timing.
    from substrate.schemas import InvestigationStartRequestedPayload
    emit_typed(
        "inv-prog",
        InvestigationStartRequestedPayload(
            question="Why does X happen?", context="", topic_slug=None,
            max_sub_questions=4,
        ),
        role="operator",
    )
    r = await async_client.get("/investigations/inv-prog")
    body = r.json()
    # No orchestrator ran (POST path wasn't used so broadcast didn't
    # fire); status is in_progress.
    assert body["status"] == "in_progress"


@pytest.mark.asyncio
async def test_get_completed_after_terminal_event(async_client):
    from substrate.schemas import (
        InvestigationCompletedPayload,
        InvestigationStartRequestedPayload,
    )
    emit_typed(
        "inv-done",
        InvestigationStartRequestedPayload(
            question="terminal-shape test", context="", topic_slug=None,
            max_sub_questions=4,
        ),
        role="operator",
    )
    emit_typed(
        "inv-done",
        InvestigationCompletedPayload(
            thesis_summary="X is supported.",
            implicit_recommendation="proceed",
            constraint_loop_status="single_pass",
            constraint_loop_iterations=1,
            master_md_path="/tmp/MASTER.md",
            domains_patched=["q-knowledge"],
            total_phases_verified=8,
        ),
        role="orchestrator",
    )
    r = await async_client.get("/investigations/inv-done")
    body = r.json()
    assert body["status"] == "completed"
    assert body["terminal_payload"] is not None
    assert body["terminal_payload"]["thesis_summary"] == "X is supported."
    assert body["terminal_payload"]["domains_patched"] == ["q-knowledge"]
    # SPR-11 M3: no rubric.scored event was emitted for this investigation,
    # so the score is null — honest absent, never a fabricated number.
    assert body["rubric_score"] is None


# ---------------------------------------------------------------------------
# SPR-11 M3 — inline-rubric score surfaced on GET /investigations/{id}.
# The endpoint READS the persisted rubric.scored event (it never recomputes
# the score). Cases: present (with sub-scores), present (free-form note →
# null sub-scores), absent (covered above).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_surfaces_persisted_rubric_score_with_subscores(async_client):
    from middleware.outcomes import emit_rubric_scored
    from substrate.schemas import InvestigationStartRequestedPayload

    emit_typed(
        "inv-rubric",
        InvestigationStartRequestedPayload(
            question="rubric-surface test", context="", topic_slug=None,
            max_sub_questions=4,
        ),
        role="operator",
    )
    # Mirror exactly what orchestration/loop_one/orchestrator.py persists:
    # final_score = composite, sub-scores encoded in the notes string.
    emit_rubric_scored(
        investigation_id="inv-rubric",
        synthesis_id="syn-inv-rubric",
        rubric_id="synthesis-deterministic-v1",
        final_score=0.71,
        deterministic_score=0.71,
        judged_score=None,
        notes=(
            "voice=0.80 conviction=0.50 "
            "citation_density=1.00 constraint=1.00"
        ),
    )
    r = await async_client.get("/investigations/inv-rubric")
    body = r.json()
    score = body["rubric_score"]
    assert score is not None
    assert abs(score["composite"] - 0.71) < 1e-6
    # Sub-scores parsed back out of the persisted note.
    assert abs(score["voice_style"] - 0.80) < 1e-6
    assert abs(score["conviction"] - 0.50) < 1e-6
    assert abs(score["citation_density"] - 1.00) < 1e-6
    assert abs(score["constraint_compliance"] - 1.00) < 1e-6


@pytest.mark.asyncio
async def test_get_rubric_score_null_subscores_for_freeform_note(async_client):
    from middleware.outcomes import emit_rubric_scored
    from substrate.schemas import InvestigationStartRequestedPayload

    emit_typed(
        "inv-rubric-floor",
        InvestigationStartRequestedPayload(
            question="rubric-floor test", context="", topic_slug=None,
            max_sub_questions=4,
        ),
        role="operator",
    )
    # The insufficient-evidence floor case: a free-form note, no sub-scores.
    emit_rubric_scored(
        investigation_id="inv-rubric-floor",
        synthesis_id="syn-inv-rubric-floor",
        rubric_id="synthesis-deterministic-v1",
        final_score=0.10,
        deterministic_score=0.10,
        judged_score=None,
        notes="synthesizer declined to produce a thesis (insufficient_evidence)",
    )
    r = await async_client.get("/investigations/inv-rubric-floor")
    score = r.json()["rubric_score"]
    assert score is not None
    assert abs(score["composite"] - 0.10) < 1e-6
    # No sub-scores in the note → null, never invented.
    assert score["voice_style"] is None
    assert score["conviction"] is None
    assert score["citation_density"] is None
    assert score["constraint_compliance"] is None


@pytest.mark.asyncio
async def test_get_failed_after_failed_event(async_client):
    from substrate.schemas import (
        InvestigationFailedPayload,
        InvestigationStartRequestedPayload,
    )
    emit_typed(
        "inv-fail",
        InvestigationStartRequestedPayload(
            question="terminal-fail test", context="", topic_slug=None,
            max_sub_questions=4,
        ),
        role="operator",
    )
    emit_typed(
        "inv-fail",
        InvestigationFailedPayload(
            phase=6, reason="postcondition failed: vacuous falsifications",
            last_completed_phase=5,
        ),
        role="orchestrator",
    )
    r = await async_client.get("/investigations/inv-fail")
    body = r.json()
    assert body["status"] == "failed"
    assert body["terminal_payload"]["phase"] == 6
    assert body["terminal_payload"]["last_completed_phase"] == 5


# ---------------------------------------------------------------------------
# 7-8. End-to-end: POST → orchestrator → GET reports completed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_end_to_end_post_drives_orchestrator(
    monkeypatch, app_and_bus, async_client,
):
    """The big one: POST /investigations triggers the orchestrator
    (which subscribes to investigation.start_requested via the
    broadcast that POST fires). The 9-phase chain runs against stub
    providers; GET returns completed with the verdict."""
    _, bus = app_and_bus

    register_provider(_RoleStubProvider({
        "decomposer": _DECOMPOSER_RESPONSE,
        "evidence_retriever": _evidence_response_for("(any sub-question)"),
        "parameter_extractor": _PARAMETER_EXTRACTOR_RESPONSE,
        "connector": _CONNECTOR_RESPONSE,
        "synthesizer": _SYNTHESIZER_RESPONSE,
        "knowledge_extractor": _KNOWLEDGE_EXTRACTION_RESPONSE,
    }))
    _patch_dispatch(monkeypatch, _all_role_config())

    post_resp = await async_client.post(
        "/investigations",
        json={
            "question": "Is PsiQuantum's photonic quantum roadmap defensible?",
            "topic_slug": "psi-quantum-via-rest",
            "max_sub_questions": 4,
            "investigation_id": "inv-rest-e2e",
        },
    )
    assert post_resp.status_code == 202

    # Wait for the orchestrator's coroutine to drive the chain.
    deadline = asyncio.get_event_loop().time() + 20.0
    while asyncio.get_event_loop().time() < deadline:
        await bus.wait_for_handlers(timeout=2.0)
        status_resp = await async_client.get("/investigations/inv-rest-e2e")
        body = status_resp.json()
        if body["status"] in ("completed", "failed"):
            break
        await asyncio.sleep(0.05)

    body = status_resp.json()
    assert body["status"] == "completed", body
    assert body["current_phase"] == 8  # last entered phase
    assert body["terminal_payload"]["thesis_summary"].startswith("PsiQuantum")
    assert Path(body["terminal_payload"]["master_md_path"]).exists()
