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
    register_provider,
    reset_provider_registry,
)
from substrate.event_log import emit_typed, trajectory  # noqa: E402
from substrate.schemas import ActionType  # noqa: E402

# Reuse the stub provider + canned responses from the orchestrator
# end-to-end test — same shape applies here.
from tests.test_loop_one_orchestrator import (  # noqa: E402
    _CONNECTOR_RESPONSE,
    _DECOMPOSER_RESPONSE,
    _KNOWLEDGE_EXTRACTION_RESPONSE,
    _PARAMETER_EXTRACTOR_RESPONSE,
    _SYNTHESIZER_RESPONSE,
    _all_role_config,
    _evidence_response_for,
    _patch_dispatch,
    _RoleStubProvider,
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

    # The transport (KDL ref-validation) makes the evidence/parameter/synthesizer
    # parsers validate chunk_ids against the retrieved chunks block. With real
    # retrieval, the stub's "chunk-1" is not canonical → stripped → "chunk_ids
    # cannot be empty" → empty thesis. Pin the retrieved block so "chunk-1" is
    # canonical, mirroring test_loop_one_orchestrator::test_loop_one_happy_path
    # (which drives the same 9-phase chain with the same stubs).
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

    # Observe the public contract instead of coupling this end-to-end test to
    # the broadcaster's private handler-drain cadence. A cold CI worker may
    # load the semantic model during synthesis, but a real hang still fails at
    # this explicit ceiling.
    deadline = asyncio.get_event_loop().time() + 30.0
    while True:
        status_resp = await async_client.get("/investigations/inv-rest-e2e")
        body = status_resp.json()
        if (
            body["status"] in ("completed", "failed")
            or asyncio.get_event_loop().time() >= deadline
        ):
            break
        await asyncio.sleep(0.05)

    body = status_resp.json()
    assert body["status"] == "completed", body
    # Completion is the public terminal contract, but later-phase subscribers
    # can still be unwinding. Drain them before fixture teardown removes this
    # test's provider/retrieval stubs; otherwise those tasks can consume the
    # next test's global provider registry and make the suite order-dependent.
    await bus.wait_for_handlers(timeout=30.0)
    assert body["current_phase"] == 8  # last entered phase
    assert body["terminal_payload"]["thesis_summary"].startswith("PsiQuantum")
    assert Path(body["terminal_payload"]["master_md_path"]).exists()


# ---------------------------------------------------------------------------
# SPR-01 (Living Roadmap) M3 — the chosen research tier is recorded on the
# investigation and is queryable after the fact via GET /investigations/{id}.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_records_research_tier_on_start_event(async_client):
    """The fast/deep tier the operator chose rides on the start payload and
    is persisted on the INVESTIGATION_START_REQUESTED event — the M3
    'recorded on the investigation' acceptance."""
    r = await async_client.post(
        "/investigations",
        json={
            "question": "Does the moat compound with more dispatches?",
            "investigation_id": "inv-tier-fast",
            "research_tier": "fast",
        },
    )
    assert r.status_code == 202, r.text
    rows = trajectory("inv-tier-fast")
    start = [
        x for x in rows
        if x["action_type"] == ActionType.INVESTIGATION_START_REQUESTED.value
    ]
    assert len(start) == 1
    assert start[0]["payload"]["research_tier"] == "fast"


@pytest.mark.asyncio
async def test_get_status_surfaces_chosen_research_tier(async_client):
    """GET /investigations/{id} reads the chosen tier back out — queryable
    after the fact, not recomputed."""
    await async_client.post(
        "/investigations",
        json={
            "question": "Trace how this idea evolved across sources.",
            "investigation_id": "inv-tier-deep",
            "research_tier": "deep",
        },
    )
    r = await async_client.get("/investigations/inv-tier-deep")
    assert r.status_code == 200
    assert r.json()["research_tier"] == "deep"


@pytest.mark.asyncio
async def test_research_tier_records_none_when_omitted_per_14_4(async_client):
    """§14.4 measurement-window scoping: omitting the tier now RECORDS None,
    not 'deep'. The persisted tier is consumed only by the synthesizer
    override, and during the §14.4 window the synthesizer is pinned to Opus —
    a schema-default 'deep' persisted on every run would silently displace it
    the moment DeepSeek is keyed, corrupting the Sprint-20 measurement. The
    research DISPATCH still defaults to deep at its consumption point
    (normalize_research_tier(None) -> 'deep'); only the recorded/echoed value
    is None. An explicit pick is still recorded + overrides — see
    test_synthesizer_measurement_window_14_4.py."""
    await async_client.post(
        "/investigations",
        json={
            "question": "What is the strongest counter-argument here?",
            "investigation_id": "inv-tier-default",
        },
    )
    r = await async_client.get("/investigations/inv-tier-default")
    assert r.json()["research_tier"] is None


@pytest.mark.asyncio
async def test_legacy_investigation_without_tier_reads_null(async_client):
    """An investigation whose start event predates the research_tier field
    reads NULL — honest absent, never fabricated. This fires the null branch
    of the GET read-back guard (app.py: research_tier stays None when the
    persisted payload has no research_tier key).

    The current schema defaults research_tier to "deep", so emit_typed() can
    never produce a field-less row. We construct a GENUINELY pre-field
    historical row via the low-level log_event() path, which writes the raw
    payload dict verbatim WITHOUT going through the Pydantic schema default —
    exactly the shape a start event written before the field existed has on
    disk. The GET must then read research_tier back as None."""
    from substrate.event_log import log_event

    # Raw start payload with NO research_tier key — the pre-field shape.
    # (matches InvestigationStartRequestedPayload minus the field that
    #  didn't exist yet; the discriminator action_type is still present so
    #  the GET's start-event detection still finds the row.)
    log_event(
        "inv-legacy",
        ActionType.INVESTIGATION_START_REQUESTED.value,
        payload={
            "action_type": ActionType.INVESTIGATION_START_REQUESTED.value,
            "question": "legacy run",
            "context": "",
            "topic_slug": None,
            "max_sub_questions": 4,
        },
        role="operator",
    )
    # Sanity: the persisted row genuinely lacks the field (so we know the
    # assertion below exercises the null branch, not the default-present one).
    start = next(
        x for x in trajectory("inv-legacy")
        if x["action_type"] == ActionType.INVESTIGATION_START_REQUESTED.value
    )
    assert "research_tier" not in start["payload"]

    r = await async_client.get("/investigations/inv-legacy")
    # The read-back guard finds no research_tier key → null, never "deep".
    assert r.json()["research_tier"] is None


# ---------------------------------------------------------------------------
# SPR-01 M2 — the original bug: with NO provider registered, the Ask path
# must surface an honest terminal failure (investigation.failed), NOT hang
# and NOT swallow the error. The frontend reads investigation.failed and
# shows the "no provider configured" state (AIActionFailure); here we prove
# the substrate end of that contract.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_provider_surfaces_terminal_failure_not_hang(
    app_and_bus, async_client,
):
    """No providers registered (the production cold-start bug). POST →
    orchestrator runs → phase 1's decomposer dispatch hits an empty
    registry (KeyError), the bridge emits an empty decomposition, phase 1
    fails its postcondition, and the orchestrator emits a terminal
    investigation.failed. GET must report 'failed' within a bounded wait —
    proving the path does not hang and the error is not swallowed."""
    _, bus = app_and_bus
    # Deliberately register NOTHING — this is the keys-absent posture.
    reset_provider_registry()

    post_resp = await async_client.post(
        "/investigations",
        json={
            "question": "Will the Ask button do anything without a provider?",
            "investigation_id": "inv-no-provider",
            "max_sub_questions": 2,
        },
    )
    assert post_resp.status_code == 202

    deadline = asyncio.get_event_loop().time() + 20.0
    body = None
    while asyncio.get_event_loop().time() < deadline:
        await bus.wait_for_handlers(timeout=2.0)
        status_resp = await async_client.get("/investigations/inv-no-provider")
        body = status_resp.json()
        if body["status"] in ("completed", "failed"):
            break
        await asyncio.sleep(0.05)

    assert body is not None
    # Honest terminal failure — NOT in_progress forever, NOT completed.
    assert body["status"] == "failed", body
    # The failure is queryable (a diagnostic reason is attached), not
    # swallowed.
    assert body["terminal_payload"] is not None
    assert body["terminal_payload"].get("phase") == 1
