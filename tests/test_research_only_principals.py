"""Real owner responses must never contain a research-only source body."""
import pytest

from runtime.db_lock import connect_write
from substrate.graph.search import search
from tests import test_owner_read_path as owner_fixtures
from tests.test_owner_read_path import (
    _OWNER_HEADERS,
    StubEmbedding,
    _gated_book,
    register_fake,
)

_clean_registry = owner_fixtures._clean_registry
db = owner_fixtures.db
owner_client = owner_fixtures.owner_client
stub_embeddings = owner_fixtures.stub_embeddings

PROBE = "PUBLISHERCONFIDENTIALPROBE"


@pytest.mark.parametrize("endpoint", ["search", "ask"])
def test_owner_response_withholds_research_body(db, owner_client, stub_embeddings, endpoint):
    _gated_book(db, "research", content_class="research_only", title="Licensed", probe=PROBE)
    provider = register_fake()
    if endpoint == "search":
        response = owner_client.get("/corpus/search", params={"q": "quantum"}, headers=_OWNER_HEADERS)
    else:
        response = owner_client.post("/books/research/ask", json={"question": "quantum"}, headers=_OWNER_HEADERS)
    assert response.status_code == 200, response.text
    assert PROBE not in response.text
    assert all(PROBE not in prompt for prompt in provider.prompts)


@pytest.mark.parametrize("tag,allowed", [("private_research", True), ("operator_only", False), ("attribution_eligible", False), ("typo", False)])
def test_principal_gate_reads_real_chunks(db, tag, allowed):
    _gated_book(db, "research", content_class="research_only", title="Licensed", probe=PROBE)
    con = connect_write(db, purpose="principal-test")
    try:
        result = search(con, "quantum", model=StubEmbedding(), policy_tag=tag)
    finally:
        con.close()
    assert any(PROBE in hit["chunk_text"] for hit in result["results"]) is allowed


@pytest.mark.parametrize("value,expected", [(None, "attribution_eligible"), ("", "attribution_eligible"), (" attribution_eligible ", "attribution_eligible"), ("private_research", "private_research")])
def test_research_policy_configuration(value, expected):
    from substrate.graph.retrieval_gate import research_policy_tag_from_env

    assert research_policy_tag_from_env(value) == expected


@pytest.mark.parametrize("value", ["operator_only", "typo", "PRIVATE_RESEARCH", "private_research,operator_only"])
def test_research_policy_rejects_owner_and_unknown_tags(value):
    from substrate.graph.retrieval_gate import research_policy_tag_from_env

    with pytest.raises(ValueError, match="ANTIEK_RESEARCH_POLICY_TAG"):
        research_policy_tag_from_env(value)


@pytest.mark.parametrize("length", [1, 199, 200])
def test_quotation_never_returns_short_work_whole(length):
    from substrate.rights.research_only import QuotationPolicy, apply_quotation_policy

    assert apply_quotation_policy("x" * length, QuotationPolicy("brief_quotation", 200)) is None


def _evidence_request():
    from substrate.schemas import EvidenceRetrieveRequestedPayload

    return EvidenceRetrieveRequestedPayload(
        sub_question="quantum", category="market_sizing", evidence_type_required="quantitative",
        chunks_block=PROBE, subgraph_block=PROBE,
    )


@pytest.mark.parametrize("path", ["/trajectory/research-probe", "/trajectory"])
def test_owner_trajectory_withholds_agent_inputs(db, owner_client, path):
    from substrate.event_log import emit_typed, trajectory

    emit_typed("research-probe", _evidence_request(), role="evidence_retriever")
    assert PROBE in str(trajectory("research-probe")), "agent replay must retain context"
    response = owner_client.get(path, headers=_OWNER_HEADERS)
    assert response.status_code == 200, response.text
    assert response.json()["count"] == 1
    assert PROBE not in response.text


def test_event_projection_keeps_agent_event_intact():
    from interfaces.research.api.event_visibility import owner_event_projection

    row = {"action_type": "evidence.retrieve.requested", "payload": _evidence_request().model_dump()}
    row["payload"]["future_agent_context"] = PROBE
    projected = owner_event_projection(row)
    assert PROBE not in str(projected)
    assert row["payload"]["chunks_block"] == PROBE
    assert projected["payload"]["sub_question"] == "quantum"


def test_owner_websocket_withholds_context_but_agent_handler_receives_it(db, owner_client):
    from substrate.schemas import ActionType

    bus = owner_client.app.state.broadcaster
    bus.unregister_all_handlers()
    received = []

    async def agent_handler(event):
        received.append(event.payload.chunks_block)

    bus.register_handler(ActionType.EVIDENCE_RETRIEVE_REQUESTED.value, agent_handler)
    with owner_client.websocket_connect("/ws/events", headers=_OWNER_HEADERS) as ws:
        response = owner_client.post(
            "/events/typed",
            json={"investigation_id": "research-probe", "payload": _evidence_request().model_dump(mode="json")},
            headers=_OWNER_HEADERS,
        )
        assert response.status_code == 201, response.text
        frame = ws.receive_json()
        assert frame["event_id"] == response.json()["event_id"]
        assert PROBE not in str(frame)
    assert received == [PROBE]


@pytest.mark.asyncio
@pytest.mark.parametrize("tag", ["operator_only", "unknown"])
async def test_loop_rejects_invalid_principal_before_retrieval(monkeypatch, tag):
    from interfaces.research.api.broadcast import EventBroadcaster
    from orchestration.loop_one import orchestrator as loop
    from orchestration.loop_one.coordinator import InvestigationCoordinator
    from substrate.schemas import DecomposeQuestionDeliveredPayload, SubQuestion

    monkeypatch.setenv("ANTIEK_RESEARCH_POLICY_TAG", tag)
    monkeypatch.setattr(loop, "enter_phase", lambda *args, **kwargs: None)
    retrieved = []

    async def retrieval(*args, **kwargs):
        retrieved.append(True)
        return ""

    monkeypatch.setattr(loop, "_render_chunks_block_for_sub_question_async", retrieval)
    ctx = loop.InvestigationContext(
        investigation_id="invalid-principal", question="quantum",
        decomposition=DecomposeQuestionDeliveredPayload(
            decomposition=[SubQuestion(sub_question="quantum", category="market_sizing", rationale="test", evidence_type_required="quantitative")],
            keywords=[],
        ),
    )
    bus = EventBroadcaster()
    assert not await loop._run_phase_2(ctx, bus, InvestigationCoordinator(bus))
    assert "ANTIEK_RESEARCH_POLICY_TAG" in ctx.fail_reason
    assert retrieved == []


@pytest.mark.parametrize("tag,allowed", [("operator_only", False), ("private_research", True)])
def test_turbopuffer_owner_and_agent_use_canonical_gate(db, tmp_path, tag, allowed):
    from substrate.graph.retrieval_adapters.turbopuffer import TurbopufferSubstrate

    _gated_book(db, "research", content_class="research_only", title="Licensed", probe=PROBE)
    con = connect_write(db, purpose="principal-adapter-test")
    try:
        adapter = TurbopufferSubstrate.from_con(con, model=StubEmbedding(), db_path=db, manifest_dir=tmp_path)
        result = adapter.query("quantum", policy_tag=tag)
    finally:
        con.close()
    assert any(PROBE in hit["chunk_text"] for hit in result["results"]) is allowed
    assert result["status"] == "duckdb — non_servable_policy"


def test_owner_full_export_refuses_research_source(db, owner_client):
    _gated_book(db, "research", content_class="research_only", title="Licensed", probe=PROBE)
    response = owner_client.get("/export/my-graph", headers=_OWNER_HEADERS)
    assert response.status_code == 403
    assert PROBE.encode() not in response.content


@pytest.mark.parametrize("sealed", [False, True])
def test_owner_full_export_refuses_historical_agent_context(db, owner_client, sealed):
    from substrate.event_log import emit_typed, seal_investigation

    emit_typed("research-probe", _evidence_request(), role="evidence_retriever")
    if sealed:
        seal_investigation("research-probe")
    response = owner_client.get("/export/my-graph", headers=_OWNER_HEADERS)
    assert response.status_code == 403
    assert PROBE.encode() not in response.content


@pytest.mark.parametrize("payload", [PROBE, [PROBE], None])
def test_owner_projection_withholds_malformed_legacy_agent_context(payload):
    from interfaces.research.api.event_visibility import owner_event_projection

    row = {"action_type": "evidence.retrieve.requested", "payload": payload}
    assert PROBE not in str(owner_event_projection(row))
