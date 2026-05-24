"""HTTP API tests for the Deep Research Bridge router."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def api_client(tmp_path: Path) -> Iterator[TestClient]:
    """Spin up the full FastAPI app pointing at a fresh DuckDB. We
    bypass dispatch provider registration since none of those calls
    happen on the research_bridge paths.
    """
    db = tmp_path / "api.duckdb"
    os.environ["ANTIEK_DUCKDB_PATH"] = str(db)
    # Initialize the schema BEFORE create_app so /research routes work
    # on the first request.
    from substrate.graph import init_database_at_path
    from substrate.research_bridge import init_research_bridge_at_path

    init_database_at_path(str(db))
    init_research_bridge_at_path(str(db))

    from interfaces.research.api.app import create_app

    # ``register_providers=False`` keeps tests off the operator's
    # dispatch credentials.
    app = create_app(register_providers=False, register_wrestling=False)
    client = TestClient(app)
    yield client
    # Clean up the env var override.
    del os.environ["ANTIEK_DUCKDB_PATH"]


def test_post_paste_round_trip(api_client: TestClient, fixture_text) -> None:
    text = fixture_text("anthropic")
    r = api_client.post(
        "/research/pastes",
        json={"raw_text": text, "operator_label": "test-anthropic"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["source"] == "anthropic", body
    doc_id = body["document_id"]

    # Raw round-trip via the /raw endpoint
    r2 = api_client.get(f"/research/pastes/{doc_id}/raw")
    assert r2.status_code == 200
    assert r2.json()["raw_text"] == text


def test_post_paste_too_large(api_client: TestClient) -> None:
    from substrate.research_bridge.ingest import MAX_PASTE_BYTES
    too_big = "x" * (MAX_PASTE_BYTES + 1)
    r = api_client.post("/research/pastes", json={"raw_text": too_big})
    assert r.status_code == 413


def test_post_paste_empty_rejected(api_client: TestClient) -> None:
    r = api_client.post("/research/pastes", json={"raw_text": "   "})
    # Pydantic min_length=1 catches it as 422 before reaching the body
    # of the route handler. Either 422 path is acceptable.
    assert r.status_code in (422, 400)


def test_post_paste_unknown_source_override(
    api_client: TestClient, fixture_text
) -> None:
    r = api_client.post(
        "/research/pastes",
        json={
            "raw_text": fixture_text("chatgpt"),
            "source_override": "definitely_not_a_provider",
        },
    )
    assert r.status_code == 422


def test_list_pastes_filter_by_source(
    api_client: TestClient, fixture_text
) -> None:
    # Insert one of each source via the API
    for src in ("chatgpt", "anthropic", "grok", "alphasense"):
        r = api_client.post(
            "/research/pastes",
            json={"raw_text": fixture_text(src), "operator_label": src},
        )
        assert r.status_code == 201, f"{src}: {r.text}"

    # List all → 4 pastes
    r = api_client.get("/research/pastes")
    assert r.status_code == 200
    assert r.json()["count"] == 4

    # Filter by source
    r = api_client.get("/research/pastes?source=alphasense")
    assert r.status_code == 200
    pastes = r.json()["pastes"]
    assert len(pastes) == 1
    assert pastes[0]["source"] == "alphasense"


def test_get_paste_detail(api_client: TestClient, fixture_text) -> None:
    text = fixture_text("alphasense")
    r = api_client.post(
        "/research/pastes",
        json={"raw_text": text, "session_id": "S-2026-05-24"},
    )
    doc_id = r.json()["document_id"]

    r2 = api_client.get(f"/research/pastes/{doc_id}")
    assert r2.status_code == 200
    body = r2.json()
    assert body["source"] == "alphasense"
    assert body["session_id"] == "S-2026-05-24"
    assert body["raw_text"] == text
    assert body["chunk_count"] >= 1
    assert len(body["events"]) == 1
    assert body["events"][0]["call_site"] == "http_api"


def test_get_paste_404(api_client: TestClient) -> None:
    r = api_client.get("/research/pastes/doc-deadbeefdeadbeef")
    assert r.status_code == 404


def test_detect_preview_does_not_write(api_client: TestClient, fixture_text) -> None:
    text = fixture_text("alphasense")
    r = api_client.post("/research/detect", json={"raw_text": text})
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "alphasense"
    assert 0.0 <= body["confidence"] <= 1.0
    assert set(body["per_source"].keys()) == {"chatgpt", "anthropic", "grok", "alphasense"}
    # No write: the paste list is still empty.
    assert api_client.get("/research/pastes").json()["count"] == 0


def test_detect_empty_rejected(api_client: TestClient) -> None:
    r = api_client.post("/research/detect", json={"raw_text": ""})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# /research/pastes/{id}/extract — SPR-02
# ---------------------------------------------------------------------------


def _monkey_dispatch_llm(monkeypatch, response_text: str) -> None:
    """Patch the dispatch LLM callable factory so the API route uses a
    fake instead of routing through the real dispatch + Anthropic
    client.
    """
    from substrate.research_bridge import LlmCallResult
    import interfaces.research.api.research_bridge as bridge_routes

    def _fake_factory():
        def _call(prompt: str) -> LlmCallResult:
            return LlmCallResult(
                text=response_text,
                input_tokens=10, output_tokens=5, cost_usd=0.0001,
                model_id="fake/test-model",
            )
        return _call

    monkeypatch.setattr(
        bridge_routes,
        "build_dispatch_llm_callable",
        _fake_factory,
    )


def test_post_extract_happy_path(
    api_client: TestClient, fixture_text, monkeypatch
) -> None:
    text = fixture_text("alphasense")
    r = api_client.post("/research/pastes", json={"raw_text": text})
    doc_id = r.json()["document_id"]

    import json
    quote = "Buy / Hold / Sell consensus (sell-side): 9 Buy / 4 Hold / 1 Sell."
    assert quote in text
    _monkey_dispatch_llm(
        monkeypatch,
        json.dumps({
            "insights": [{"summary": "Mixed sell-side", "quote": quote,
                          "llm_confidence": 0.9}],
            "open_questions": [],
        }),
    )

    r2 = api_client.post(f"/research/pastes/{doc_id}/extract", json={})
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["status"] == "ok"
    assert len(body["insights"]) == 1
    assert body["insights"][0]["summary"] == "Mixed sell-side"


def test_post_extract_404_unknown_doc(api_client: TestClient, monkeypatch) -> None:
    _monkey_dispatch_llm(monkeypatch, '{"insights": [], "open_questions": []}')
    r = api_client.post("/research/pastes/doc-deadbeef/extract", json={})
    assert r.status_code == 404


def test_extract_cache_hit_on_repeat(
    api_client: TestClient, fixture_text, monkeypatch
) -> None:
    text = fixture_text("anthropic")
    r = api_client.post("/research/pastes", json={"raw_text": text})
    doc_id = r.json()["document_id"]

    import json
    quote = "Prime Intellect is the named incumbent at the substrate layer."
    _monkey_dispatch_llm(
        monkeypatch,
        json.dumps({
            "insights": [{"summary": "PI lead", "quote": quote, "llm_confidence": 0.9}],
            "open_questions": [],
        }),
    )
    r1 = api_client.post(f"/research/pastes/{doc_id}/extract", json={})
    assert r1.json()["status"] == "ok"
    r2 = api_client.post(f"/research/pastes/{doc_id}/extract", json={})
    assert r2.json()["status"] == "cache_hit"


def test_get_items_returns_extracted(
    api_client: TestClient, fixture_text, monkeypatch
) -> None:
    text = fixture_text("grok")
    r = api_client.post("/research/pastes", json={"raw_text": text})
    doc_id = r.json()["document_id"]

    import json
    quote = "Prime Intellect dominates substrate"
    _monkey_dispatch_llm(
        monkeypatch,
        json.dumps({
            "insights": [{"summary": "PI dominance", "quote": quote, "llm_confidence": 0.9}],
            "open_questions": [],
        }),
    )
    api_client.post(f"/research/pastes/{doc_id}/extract", json={})

    r = api_client.get(f"/research/pastes/{doc_id}/items")
    assert r.status_code == 200
    body = r.json()
    assert len(body["insights"]) == 1
    assert body["insights"][0]["summary"] == "PI dominance"


# ---------------------------------------------------------------------------
# Gap-finder routes — SPR-05
# ---------------------------------------------------------------------------


def _dispatch_with_canned_sequence(monkeypatch, responses: list) -> list:
    """Patch the dispatch LLM factory to return a sequence of canned
    responses. ``responses`` is a list of dicts shaped {text,
    input_tokens, output_tokens, cost_usd, model_id}.

    Returns the same list so the caller can dynamically mutate the
    cascade response after the cluster call lands (see
    test_post_find_gaps_happy_path)."""
    from substrate.research_bridge import LlmCallResult
    import interfaces.research.api.research_bridge as bridge_routes

    state = {"i": 0}

    def _factory():
        def _call(prompt: str) -> LlmCallResult:
            i = state["i"]
            state["i"] = i + 1
            if i >= len(responses):
                # Default fallback
                return LlmCallResult(text='{"prompts": []}', model_id="fake")
            r = responses[i]
            # Inject the cluster_id parsed from the prompt into the
            # cascade response if a placeholder is present.
            text = r.get("text", "")
            if "__placeholder__" in text:
                import re
                m = re.search(r"cluster_id:\s*(rgcl-[a-f0-9]+)", prompt)
                if m:
                    text = text.replace("__placeholder__", m.group(1))
            return LlmCallResult(
                text=text,
                input_tokens=r.get("input_tokens", 0),
                output_tokens=r.get("output_tokens", 0),
                cost_usd=r.get("cost_usd", 0.0),
                model_id=r.get("model_id", "fake"),
            )
        return _call

    monkeypatch.setattr(bridge_routes, "build_dispatch_llm_callable", _factory)
    return responses


def _setup_paste_and_extract(client: TestClient, monkeypatch, source: str, fixture_text):
    """Helper: paste a fixture + extract one Q from it. Returns
    (document_id, question_id)."""
    text = fixture_text(source)
    r = client.post("/research/pastes", json={"raw_text": text})
    doc_id = r.json()["document_id"]

    import json
    if source == "anthropic":
        quote = "Anthropic-internal verifier work has appeared in three 2024 papers but has not been productised"
        q_summary = "Will Anthropic ship internal verifier as product"
    else:  # alphasense
        quote = "management indicated they will disclose Compute Marketplace customer commitments."
        q_summary = "Will compute marketplace customer commitments materialize"
    _monkey_dispatch_llm(
        monkeypatch,
        json.dumps({
            "insights": [],
            "open_questions": [{"summary": q_summary, "quote": quote,
                                "llm_confidence": 0.9}],
        }),
    )
    client.post(f"/research/pastes/{doc_id}/extract", json={})
    # Read the question_id back.
    items = client.get(f"/research/pastes/{doc_id}/items").json()
    qid = items["open_questions"][0]["item_id"]
    return doc_id, qid


def test_post_find_gaps_happy_path(
    api_client: TestClient, fixture_text, monkeypatch
) -> None:
    import json as _json
    doc_a, q_a = _setup_paste_and_extract(api_client, monkeypatch, "anthropic", fixture_text)
    doc_b, q_b = _setup_paste_and_extract(api_client, monkeypatch, "alphasense", fixture_text)

    _dispatch_with_canned_sequence(monkeypatch, [
        {
            "text": _json.dumps({
                "clusters": [{
                    "label": "Verifier productisation",
                    "priority_rank": 0,
                    "question_ids": [q_a, q_b],
                }],
            }),
            "input_tokens": 200, "output_tokens": 60, "cost_usd": 0.002,
            "model_id": "fake/cluster",
        },
        {
            "text": _json.dumps({
                "prompts": [{
                    "cluster_id": "__placeholder__",
                    "order_index": 0,
                    "prompt_text": "Verifier productisation status across Anthropic and PRIM",
                    "target_provider": "anthropic",
                    "rationale": "Anthropic is directly relevant",
                }],
            }),
            "input_tokens": 300, "output_tokens": 90, "cost_usd": 0.004,
            "model_id": "fake/cascade",
        },
    ])

    r = api_client.post("/research/gaps", json={
        "scope_block_ids": [doc_a, doc_b],
        "operator_label": "API smoke",
        "session_id": "S-api-test",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["run"]["operator_label"] == "API smoke"
    assert len(body["clusters"]) == 1
    assert len(body["prompts"]) == 1
    assert body["prompts"][0]["target_provider"] == "anthropic"


def test_post_find_gaps_rejects_empty_scope(api_client: TestClient) -> None:
    r = api_client.post("/research/gaps", json={"scope_block_ids": []})
    assert r.status_code == 422


def test_get_gap_run_404(api_client: TestClient) -> None:
    r = api_client.get("/research/gaps/rgrun-nope")
    assert r.status_code == 404


def test_signal_and_would_run_percentage(
    api_client: TestClient, fixture_text, monkeypatch
) -> None:
    import json as _json
    doc_a, q_a = _setup_paste_and_extract(api_client, monkeypatch, "anthropic", fixture_text)
    doc_b, q_b = _setup_paste_and_extract(api_client, monkeypatch, "alphasense", fixture_text)

    _dispatch_with_canned_sequence(monkeypatch, [
        {"text": _json.dumps({"clusters": [{
            "label": "Productisation timeline", "priority_rank": 0,
            "question_ids": [q_a, q_b],
        }]}), "model_id": "fake"},
        {"text": _json.dumps({"prompts": [
            {"cluster_id": "__placeholder__", "order_index": 0,
             "prompt_text": "Verifier productisation status check",
             "target_provider": "anthropic", "rationale": "x"},
            {"cluster_id": "__placeholder__", "order_index": 1,
             "prompt_text": "Verifier marketplace commitments",
             "target_provider": "alphasense", "rationale": "x"},
        ]}), "model_id": "fake"},
    ])
    r = api_client.post("/research/gaps", json={
        "scope_block_ids": [doc_a, doc_b], "operator_label": "test",
    })
    prompts = r.json()["prompts"]
    assert len(prompts) == 2

    r1 = api_client.post(
        f"/research/gaps/prompts/{prompts[0]['prompt_id']}/signal",
        json={"signal_type": "would_run"},
    )
    assert r1.status_code == 201
    r2 = api_client.post(
        f"/research/gaps/prompts/{prompts[1]['prompt_id']}/signal",
        json={"signal_type": "skip"},
    )
    assert r2.status_code == 201

    # Aggregate
    r = api_client.get("/research/gaps/signals/percentage")
    body = r.json()
    assert body["would_run_count"] == 1
    assert body["total_signalled"] == 2
    assert body["percentage"] == 0.5


def test_signal_invalid_type(api_client: TestClient) -> None:
    """Even on an unknown prompt_id the input validation fires first."""
    r = api_client.post(
        "/research/gaps/prompts/rgpr-deadbeef/signal",
        json={"signal_type": "lol"},
    )
    assert r.status_code == 422


def test_answer_links_paste_to_prompt(
    api_client: TestClient, fixture_text, monkeypatch
) -> None:
    import json as _json
    doc_a, q_a = _setup_paste_and_extract(api_client, monkeypatch, "anthropic", fixture_text)
    _dispatch_with_canned_sequence(monkeypatch, [
        {"text": _json.dumps({"clusters": [{
            "label": "Verifier productisation", "priority_rank": 0,
            "question_ids": [q_a],
        }]}), "model_id": "fake"},
        {"text": _json.dumps({"prompts": [{
            "cluster_id": "__placeholder__", "order_index": 0,
            "prompt_text": "Verifier productisation timeline ?",
            "target_provider": "anthropic", "rationale": "x",
        }]}), "model_id": "fake"},
    ])
    gaps = api_client.post(
        "/research/gaps", json={"scope_block_ids": [doc_a]},
    ).json()
    prompt_id = gaps["prompts"][0]["prompt_id"]

    # Paste an answer back as a new paste.
    answer = api_client.post(
        "/research/pastes",
        json={"raw_text": "Anthropic released VerifyKit on 2025-01-15.\n\n" * 5},
    ).json()
    r = api_client.post(
        f"/research/gaps/prompts/{prompt_id}/answer",
        json={"answer_document_id": answer["document_id"]},
    )
    assert r.status_code == 201
    assert r.json()["answer_id"].startswith("rga-")
