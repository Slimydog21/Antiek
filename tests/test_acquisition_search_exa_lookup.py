"""Tests for the Wedge 3 — `exa_lookup_claim` verifier corroboration primitive.

Spec: `docs/integration_exa_browserbase.md` §8.

Coverage:
  - Happy path: claim_text + k → ≤k typed ExaLookupResult rows,
    exactly one VerifierLookupPayload event emitted
  - Input validation: empty claim, empty investigation_id, k bounds
  - Substrate invariant: NO graph writes. The function should NOT
    touch the DB or emit DocumentLoadedPayload
  - Budget reservation honored (same cap as discover())
  - Event records claim_text + k_requested + cost_usd
  - Empty-results call still emits the event (audit-visible)
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from acquisition.search.exa import (
    VERIFIER_LOOKUP_MAX_K,
    DiscoveryBudgetExceeded,
    ExaClient,
    exa_lookup_claim,
)
from acquisition.search.exa.budget import (
    DEFAULT_DAILY_BUDGET_USD,
    BudgetState,
    _utc_date_stamp,
    read_state,
    write_state,
)
from substrate.schemas.events import (
    EVENT_SCHEMA_VERSION,
    TYPED_PAYLOAD_ACTION_TYPES,
    ActionType,
    ExaLookupResult,
    VerifierLookupPayload,
)

# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    # Per spec §14.1, verifier_lookup events route to the
    # discovery_events dir, not the substrate events dir.
    # `ANTIEK_HOME` controls both sidecar paths AND the discovery
    # events dir default, so the test looks under both locations.
    discovery_events_dir = tmp_path / "discovery_events"
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events_dir))
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "graph.duckdb"))
    monkeypatch.setenv("EXA_API_KEY", "test-key-not-used")
    yield {
        "events_dir": str(events_dir),
        "discovery_events_dir": str(discovery_events_dir),
        "tmpdir": str(tmp_path),
    }


def _mock_exa_client(responses: list[dict], *, status: int = 200) -> ExaClient:
    it = iter(responses)
    last = [None]

    def handler(request: httpx.Request) -> httpx.Response:
        try:
            body = next(it)
            last[0] = body
        except StopIteration:
            body = last[0] or {"results": []}
        return httpx.Response(status, json=body)

    return ExaClient(
        api_key="k",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _s: None,
    )


def _exa_result(url: str, *, title=None, snippet=None, score=None, id_=None) -> dict:
    return {"url": url, "title": title, "score": score, "text": snippet, "id": id_}


def _find_events(events_dir: str, action_type: str) -> list[dict]:
    out = []
    for f in Path(events_dir).rglob("*.jsonl"):
        for line in f.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            ev = json.loads(line)
            if ev.get("action_type") == action_type:
                out.append(ev)
    return out


# ── Schema-level guarantees ────────────────────────────────────────


def test_schema_version_bumped_past_v7():
    assert EVENT_SCHEMA_VERSION >= 7


def test_verifier_lookup_in_typed_union():
    assert ActionType.VERIFIER_LOOKUP.value in TYPED_PAYLOAD_ACTION_TYPES


# ── VerifierLookupPayload / ExaLookupResult shape ──────────────────


def test_verifier_lookup_payload_roundtrips_through_union():
    from pydantic import TypeAdapter

    from substrate.schemas.events import TypedPayload

    p = VerifierLookupPayload(
        query="Tesla Q3 2025 deliveries by segment",
        claim_text="Tesla delivered 462,890 vehicles in Q3 2025",
        k_requested=3,
        results=[
            ExaLookupResult(
                url="https://ir.tesla.com/x",
                title="Q3 update",
                text_snippet="Q3 deliveries totaled 462,890 vehicles...",
                relevance_score=0.95,
                provider_response_id="exa-r1",
            ),
        ],
        cost_usd_estimate=0.005,
    )
    adapter = TypeAdapter(TypedPayload)
    re = adapter.validate_python(p.model_dump())
    assert isinstance(re, VerifierLookupPayload)
    assert re.tool == "exa.search_contents"
    assert len(re.results) == 1
    assert re.results[0].url == "https://ir.tesla.com/x"


def test_exa_lookup_result_rejects_oversized_snippet():
    """Per the schema cap (2000 chars), oversized snippets must fail."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ExaLookupResult(url="u", text_snippet="x" * 2001)


def test_verifier_lookup_k_must_be_in_bounds():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        VerifierLookupPayload(
            query="x", k_requested=0, cost_usd_estimate=0.0,
        )
    with pytest.raises(ValidationError):
        VerifierLookupPayload(
            query="x", k_requested=21, cost_usd_estimate=0.0,
        )


# ── exa_lookup_claim happy path ───────────────────────────────────


def test_lookup_returns_typed_results(isolated_env):
    cli = _mock_exa_client([
        {
            "results": [
                _exa_result(
                    "https://ir.tesla.com/q3", title="Q3", score=0.92,
                    snippet="Tesla delivered 462,890 vehicles..."
                ),
                _exa_result(
                    "https://reuters.com/tesla-q3", title="Reuters", score=0.81,
                    snippet="Reuters: Tesla Q3 was 462,890..."
                ),
                _exa_result(
                    "https://bloomberg.com/tesla", title="BBerg", score=0.79,
                    snippet="Bloomberg analysis..."
                ),
            ],
            "requestId": "exa-vl-1",
        }
    ])
    out = exa_lookup_claim(
        claim_text="Tesla delivered 462,890 vehicles in Q3 2025",
        investigation_id="inv-vl-1",
        k=3,
        client=cli,
    )
    assert len(out) == 3
    assert all(isinstance(r, ExaLookupResult) for r in out)
    assert out[0].url == "https://ir.tesla.com/q3"
    assert out[0].text_snippet is not None


def test_lookup_emits_exactly_one_event(isolated_env):
    cli = _mock_exa_client([
        {"results": [_exa_result("https://e.com/a")]}
    ])
    exa_lookup_claim(
        claim_text="some claim",
        investigation_id="inv-vl-2",
        k=1,
        client=cli,
    )
    events = _find_events(isolated_env["discovery_events_dir"], "verifier.lookup")
    assert len(events) == 1
    p = events[0]["payload"]
    assert p["tool"] == "exa.search_contents"
    assert p["k_requested"] == 1
    assert p["claim_text"] == "some claim"
    assert len(p["results"]) == 1


def test_lookup_emits_event_even_on_empty_results(isolated_env):
    """Per spec §8.2 — record that the verifier considered the
    lookup, even if Exa returned nothing."""
    cli = _mock_exa_client([{"results": []}])
    out = exa_lookup_claim(
        claim_text="some unknown claim",
        investigation_id="inv-vl-3",
        k=3,
        client=cli,
    )
    assert out == []
    events = _find_events(isolated_env["discovery_events_dir"], "verifier.lookup")
    assert len(events) == 1
    assert events[0]["payload"]["results"] == []


# ── Input validation ───────────────────────────────────────────────


def test_lookup_rejects_empty_claim(isolated_env):
    with pytest.raises(ValueError):
        exa_lookup_claim(
            claim_text="", investigation_id="inv-x", k=3,
            client=_mock_exa_client([{"results": []}]),
        )


def test_lookup_rejects_empty_investigation(isolated_env):
    with pytest.raises(ValueError):
        exa_lookup_claim(
            claim_text="x", investigation_id="", k=3,
            client=_mock_exa_client([{"results": []}]),
        )


def test_lookup_rejects_out_of_range_k(isolated_env):
    with pytest.raises(ValueError):
        exa_lookup_claim(
            claim_text="x", investigation_id="i", k=0,
            client=_mock_exa_client([{"results": []}]),
        )
    with pytest.raises(ValueError):
        exa_lookup_claim(
            claim_text="x", investigation_id="i", k=VERIFIER_LOOKUP_MAX_K + 1,
            client=_mock_exa_client([{"results": []}]),
        )


# ── Substrate-grounding invariant: NO graph writes ───────────────


def test_lookup_does_not_emit_document_loaded(isolated_env):
    """Spec §8.3 — snippets stay out of the graph. No
    DocumentLoadedPayload should be emitted."""
    cli = _mock_exa_client([
        {"results": [_exa_result("https://e.com/x")]}
    ])
    exa_lookup_claim(
        claim_text="x", investigation_id="inv-vl-no-doc",
        k=1, client=cli,
    )
    doc_events = _find_events(isolated_env["events_dir"], "document.loaded")
    assert doc_events == []


def test_lookup_does_not_emit_discovery_proposed(isolated_env):
    """The lookup is distinct from discovery. No
    DiscoveryProposedPayload either."""
    cli = _mock_exa_client([
        {"results": [_exa_result("https://e.com/x")]}
    ])
    exa_lookup_claim(
        claim_text="x", investigation_id="inv-vl-no-disc",
        k=1, client=cli,
    )
    disc_events = _find_events(isolated_env["events_dir"], "discovery.proposed")
    assert disc_events == []


# ── Budget integration ────────────────────────────────────────────


def test_lookup_consumes_budget(isolated_env):
    cli = _mock_exa_client([
        {"results": [_exa_result("https://e.com/a")]}
    ])
    exa_lookup_claim(
        claim_text="x", investigation_id="i", k=1, client=cli,
    )
    state = read_state()
    assert state.spent_usd > 0


def test_lookup_budget_exceeded_raises(isolated_env):
    """Shares the daily cap with discover() — both consume the
    same `~/.antiek/budgets/exa_<date>.json` sidecar."""
    # Pre-fill the budget to within $0.001 of the cap.
    s = BudgetState(
        date_stamp=_utc_date_stamp(),
        spent_usd=DEFAULT_DAILY_BUDGET_USD - 0.001,
        call_count=999,
        cap_usd=DEFAULT_DAILY_BUDGET_USD,
    )
    write_state(s)
    cli = _mock_exa_client([{"results": []}])
    with pytest.raises(DiscoveryBudgetExceeded):
        exa_lookup_claim(
            claim_text="x", investigation_id="i", k=1, client=cli,
        )


def test_lookup_budget_override(isolated_env):
    """Operator-explicit cap relaxes the per-call check."""
    s = BudgetState(
        date_stamp=_utc_date_stamp(),
        spent_usd=DEFAULT_DAILY_BUDGET_USD,  # at cap
        call_count=999,
        cap_usd=DEFAULT_DAILY_BUDGET_USD,
    )
    write_state(s)
    cli = _mock_exa_client([
        {"results": [_exa_result("https://e.com/x")]}
    ])
    out = exa_lookup_claim(
        claim_text="x", investigation_id="i", k=1, client=cli,
        daily_budget_usd=100.0,
    )
    assert len(out) == 1


# ── k > returned results — function handles gracefully ────────────


def test_lookup_returns_fewer_when_exa_returns_fewer(isolated_env):
    """Operator asked for k=5, Exa returned 2; we return 2."""
    cli = _mock_exa_client([
        {"results": [
            _exa_result("https://a"), _exa_result("https://b"),
        ]}
    ])
    out = exa_lookup_claim(
        claim_text="x", investigation_id="i", k=5, client=cli,
    )
    assert len(out) == 2
    events = _find_events(isolated_env["discovery_events_dir"], "verifier.lookup")
    assert events[0]["payload"]["k_requested"] == 5
    assert len(events[0]["payload"]["results"]) == 2
