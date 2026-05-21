"""Tests for the Exa & Browserbase Wedge 1 — discovery adapter.

Spec: ``docs/integration_exa_browserbase.md`` §6. Covers:

  - Legal-gate placeholder (acknowledgment-flag enforcement)
  - ``suggest_tier`` heuristic
  - ExaClient retry / error handling against ``httpx.MockTransport``
  - ``discover`` end-to-end: budget reservation → Exa call → event
    emission → typed return values
  - ``promote_discovery`` paths: ingested, rejected_by_legal_gate,
    fetch_failed
  - ``reject_discovery`` operator path
  - ``find_similar``
  - Budget cap enforcement

Test isolation: ``ANTIEK_RESEARCH_EVENTS_DIR`` redirects event log
output to ``tmp_path``; ``ANTIEK_HOME`` redirects budget sidecar
files to ``tmp_path``. No tests touch the real ``~/.antiek``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional

import httpx
import pytest

from acquisition.search.exa import (
    DEFAULT_DAILY_BUDGET_USD,
    DiscoveryBudgetExceeded,
    ExaClient,
    ExaClientError,
    discover,
    find_similar,
    promote_discovery,
    reject_discovery,
    suggest_tier,
)
from acquisition.search.exa.adapter import _discovery_id
from acquisition.search.exa.budget import (
    BudgetState,
    _budget_path,
    read_state,
    write_state,
)
from substrate.legal_gate import (
    LegalGatePlaceholderUnacknowledged,
    LegalGateVerdict,
    PermissiveLegalGate,
    default_legal_gate,
)


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """Redirect event log, budget sidecars, and DuckDB cache to
    tmp_path. ANTIEK_DUCKDB_PATH isolation is load-bearing because
    the discovery cache (spec §6.5) is keyed on (query, investigation_id);
    without isolation a prior test's cached proposals can short-
    circuit the budget-reservation branch."""
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    db_path = tmp_path / "graph.duckdb"
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events_dir))
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db_path))
    monkeypatch.setenv("EXA_API_KEY", "test-key-not-used-by-mock-transport")
    monkeypatch.setenv("ANTIEK_LEGAL_GATE_PLACEHOLDER_ACKED", "1")
    yield {"events_dir": str(events_dir), "tmpdir": str(tmp_path)}


def _mock_exa_client(
    responses: List[dict],
    *,
    status: int = 200,
) -> ExaClient:
    """Build an ExaClient backed by httpx.MockTransport that returns
    the given JSON responses in order. After the last response, all
    further calls reuse the last response."""
    responses_iter = iter(responses)
    last = [None]

    def handler(request: httpx.Request) -> httpx.Response:
        try:
            body = next(responses_iter)
            last[0] = body
        except StopIteration:
            body = last[0] or {"results": []}
        return httpx.Response(status, json=body)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    return ExaClient(api_key="test-key", client=client, sleep=lambda _s: None)


def _exa_result(
    url: str,
    *,
    title: Optional[str] = None,
    score: Optional[float] = None,
    snippet: Optional[str] = None,
    id_: Optional[str] = None,
) -> dict:
    return {
        "url": url,
        "title": title,
        "score": score,
        "text": snippet,
        "id": id_,
    }


# ── Legal-gate placeholder ────────────────────────────────────────


def test_legal_gate_placeholder_requires_ack(monkeypatch):
    monkeypatch.delenv("ANTIEK_LEGAL_GATE_PLACEHOLDER_ACKED", raising=False)
    with pytest.raises(LegalGatePlaceholderUnacknowledged):
        PermissiveLegalGate()


def test_legal_gate_placeholder_with_bypass_for_tests():
    g = PermissiveLegalGate(_bypass_acknowledgment=True)
    v = g.check_url("https://example.com/x")
    assert isinstance(v, LegalGateVerdict)
    assert v.allowed is True
    assert v.gate_kind == "placeholder"


def test_legal_gate_default_factory_respects_ack(monkeypatch):
    monkeypatch.setenv("ANTIEK_LEGAL_GATE_PLACEHOLDER_ACKED", "1")
    g = default_legal_gate()
    v = g.check_url("https://nytimes.com/anything")
    assert v.allowed is True
    assert v.gate_kind == "placeholder"


# ── suggest_tier heuristic ────────────────────────────────────────


@pytest.mark.parametrize(
    "url,expected_tier",
    [
        ("https://arxiv.org/abs/2412.12345", 2),
        ("https://www.arxiv.org/abs/2412.12345", 2),
        ("https://doi.org/10.1000/abc", 2),
        ("https://www.nih.gov/news", 2),
        ("https://mit.edu/research", 2),
        ("https://www.cam.ac.uk/dept", 2),
        ("https://www.nytimes.com/2026/03/01/whatever", 3),
        ("https://nytimes.com/article", 3),
        ("https://wsj.com/x", 3),
        ("https://reddit.com/r/x", 4),
        ("https://random-blog.example.com/post", 4),
        ("https://github.com/foo/bar", 4),
        ("", 4),
        ("not-a-url", 4),
    ],
)
def test_suggest_tier_heuristic(url, expected_tier):
    assert suggest_tier(url) == expected_tier


def test_suggest_tier_research_paper_category_forces_tier_2():
    # Even a blog URL gets tier 2 when category=research paper
    assert suggest_tier("https://random.example.com/x", category="research paper") == 2


# ── ExaClient retry / error handling ──────────────────────────────


def test_exa_client_search_happy_path():
    cli = _mock_exa_client([
        {
            "results": [
                _exa_result("https://arxiv.org/abs/x", title="A", score=0.9, id_="r1"),
                _exa_result("https://nytimes.com/y", title="B", score=0.8, id_="r2"),
            ],
            "requestId": "exa-req-1",
        }
    ])
    resp = cli.search(query="claude pricing 2026", num_results=2)
    assert len(resp.results) == 2
    assert resp.request_id == "exa-req-1"
    assert resp.results[0].url == "https://arxiv.org/abs/x"
    assert resp.results[0].title == "A"
    assert resp.results[0].relevance_score == 0.9


def test_exa_client_validates_query():
    cli = _mock_exa_client([{"results": []}])
    with pytest.raises(ExaClientError):
        cli.search(query="   ", num_results=5)


def test_exa_client_validates_num_results_bounds():
    cli = _mock_exa_client([{"results": []}])
    with pytest.raises(ExaClientError):
        cli.search(query="x", num_results=0)
    with pytest.raises(ExaClientError):
        cli.search(query="x", num_results=101)


def test_exa_client_retries_on_429_then_succeeds():
    seen = {"calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["calls"] += 1
        if seen["calls"] < 2:
            return httpx.Response(429, json={"error": "rate limited"})
        return httpx.Response(200, json={"results": [_exa_result("https://e.com/x")]})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    cli = ExaClient(api_key="k", client=client, sleep=lambda _s: None)
    resp = cli.search(query="q", num_results=1)
    assert seen["calls"] == 2
    assert resp.results[0].url == "https://e.com/x"


def test_exa_client_raises_on_400():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad request"})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    cli = ExaClient(api_key="k", client=client, sleep=lambda _s: None)
    with pytest.raises(ExaClientError) as exc:
        cli.search(query="q", num_results=1)
    assert exc.value.status == 400


def test_exa_client_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    with pytest.raises(ExaClientError):
        ExaClient()


def test_exa_client_truncates_long_snippets():
    long_text = "x" * 1000
    cli = _mock_exa_client([
        {"results": [_exa_result("https://e.com/x", snippet=long_text)]}
    ])
    resp = cli.search(query="q", num_results=1)
    assert resp.results[0].text_snippet_preview is not None
    assert len(resp.results[0].text_snippet_preview) <= 300


# ── discover() end-to-end ─────────────────────────────────────────


def test_discover_emits_one_proposed_event_per_result(isolated_env):
    client = _mock_exa_client([
        {
            "results": [
                _exa_result("https://arxiv.org/abs/r1", title="Paper 1", score=0.9),
                _exa_result("https://nytimes.com/a", title="Story A", score=0.7),
                _exa_result("https://blog.example.com/p", title="Blog", score=0.5),
            ],
            "requestId": "req-1",
        }
    ])
    proposals = discover(
        query="anthropic claude pricing",
        investigation_id="inv-test-001",
        num_results=3,
        client=client,
    )
    assert len(proposals) == 3
    # The three suggested_tier values reflect the heuristic.
    by_url = {p.url: p for p in proposals}
    assert by_url["https://arxiv.org/abs/r1"].suggested_tier == 2
    assert by_url["https://nytimes.com/a"].suggested_tier == 3
    assert by_url["https://blog.example.com/p"].suggested_tier == 4
    # Each proposal got a non-None event id.
    assert all(p.proposed_event_id for p in proposals)
    # All proposal discovery_ids are unique.
    assert len({p.discovery_id for p in proposals}) == 3


def test_discover_validates_args(isolated_env):
    cli = _mock_exa_client([{"results": []}])
    with pytest.raises(ValueError):
        discover(query="", investigation_id="inv-1", client=cli)
    with pytest.raises(ValueError):
        discover(query="q", investigation_id="", client=cli)


def test_discover_reserves_budget(isolated_env):
    cli = _mock_exa_client([
        {"results": [_exa_result("https://e.com/a")]}
    ])
    discover(query="q", investigation_id="inv-1", num_results=1, client=cli)
    state = read_state()
    assert state.spent_usd > 0
    assert state.call_count == 1


def test_discover_budget_exceeded_raises(isolated_env):
    # Pre-fill the budget to within $0.001 of the cap.
    today_path = _budget_path()
    today_path.write_text(json.dumps({
        "date_stamp": today_path.stem.replace("exa_", ""),
        "spent_usd": DEFAULT_DAILY_BUDGET_USD - 0.001,
        "call_count": 999,
        "cap_usd": DEFAULT_DAILY_BUDGET_USD,
    }))
    cli = _mock_exa_client([{"results": []}])
    with pytest.raises(DiscoveryBudgetExceeded):
        discover(query="q", investigation_id="inv-1", client=cli)


def test_discover_custom_budget_override(isolated_env):
    """A per-call ``daily_budget_usd`` overrides the env-resolved cap."""
    cli = _mock_exa_client([
        {"results": [_exa_result("https://e.com/x")]}
    ])
    # Pre-spent past the env cap, but operator passes a higher
    # per-call cap — the call succeeds.
    state = BudgetState(
        date_stamp="2026-01-01", spent_usd=4.9, call_count=1, cap_usd=5.0
    )
    # Use today's date_stamp so the read picks it up.
    from acquisition.search.exa.budget import _utc_date_stamp
    state.date_stamp = _utc_date_stamp()
    write_state(state)
    discover(
        query="q",
        investigation_id="inv-1",
        num_results=1,
        client=cli,
        daily_budget_usd=100.0,
    )


# ── promote_discovery() ───────────────────────────────────────────


class _DenyingGate:
    def check_url(self, url: str) -> LegalGateVerdict:
        return LegalGateVerdict(
            allowed=False,
            reason=f"test denial: {url}",
            gate_kind="placeholder",
        )


def test_promote_discovery_rejected_by_legal_gate(isolated_env):
    cli = _mock_exa_client([
        {"results": [_exa_result("https://example.com/banned")]}
    ])
    [proposal] = discover(
        query="q", investigation_id="inv-1", num_results=1, client=cli
    )
    result = promote_discovery(
        proposal,
        investigation_id="inv-1",
        legal_gate=_DenyingGate(),
    )
    assert result.decision == "rejected_by_legal_gate"
    assert result.document_id is None
    assert result.rejection_reason is not None
    assert "test denial" in result.rejection_reason
    assert result.selected_event_id is not None


def test_promote_discovery_ingested(isolated_env, monkeypatch):
    """Ingested-path test. Monkeypatches the ``ingest_url`` symbol
    that ``promote_discovery`` imports lazily, so the test doesn't
    spin up a real DuckDB connection."""
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class FakeIngestResult:
        document_id: str = "doc-url-fakefakefakefa"
        final_url: str = "https://example.com/x"
        chunk_ids: tuple = ()
        node_ids: tuple = ()
        document_loaded_event_id: Optional[str] = "evt-loaded"
        chunks_written: int = 5
        skipped_reason: Optional[str] = None
        title: Optional[str] = "Test"
        author: Optional[str] = None

    calls = {"n": 0, "kwargs": None}

    def fake_ingest(url, **kwargs):
        calls["n"] += 1
        calls["kwargs"] = kwargs
        return FakeIngestResult()

    import acquisition.urls.adapter as urls_adapter
    monkeypatch.setattr(urls_adapter, "ingest_url", fake_ingest)

    cli = _mock_exa_client([
        {"results": [_exa_result("https://example.com/x", title="T")]}
    ])
    [proposal] = discover(
        query="q", investigation_id="inv-1", num_results=1, client=cli
    )
    result = promote_discovery(
        proposal,
        investigation_id="inv-1",
        legal_gate=PermissiveLegalGate(_bypass_acknowledgment=True),
    )
    assert calls["n"] == 1
    assert result.decision == "ingested"
    assert result.document_id == "doc-url-fakefakefakefa"
    assert result.chunks_written == 5
    # Default tier should be the heuristic's suggestion
    assert calls["kwargs"]["source_tier"] == proposal.suggested_tier


def test_promote_discovery_tier_override(isolated_env, monkeypatch):
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class FakeIngestResult:
        document_id: str = "doc-url-x"
        final_url: str = "https://e.com/x"
        chunk_ids: tuple = ()
        node_ids: tuple = ()
        document_loaded_event_id: Optional[str] = None
        chunks_written: int = 0
        skipped_reason: Optional[str] = None
        title: Optional[str] = None
        author: Optional[str] = None

    captured = {}

    def fake_ingest(url, **kwargs):
        captured.update(kwargs)
        return FakeIngestResult()

    import acquisition.urls.adapter as urls_adapter
    monkeypatch.setattr(urls_adapter, "ingest_url", fake_ingest)

    cli = _mock_exa_client([
        {"results": [_exa_result("https://blog.example.com/x")]}
    ])
    [proposal] = discover(
        query="q", investigation_id="inv-1", num_results=1, client=cli
    )
    promote_discovery(
        proposal,
        investigation_id="inv-1",
        source_tier=1,  # operator override — promote to primary
        legal_gate=PermissiveLegalGate(_bypass_acknowledgment=True),
    )
    assert captured["source_tier"] == 1


def test_promote_discovery_fetch_failed(isolated_env, monkeypatch):
    def fake_ingest(*a, **k):
        raise RuntimeError("network exploded")

    import acquisition.urls.adapter as urls_adapter
    monkeypatch.setattr(urls_adapter, "ingest_url", fake_ingest)

    cli = _mock_exa_client([
        {"results": [_exa_result("https://example.com/x")]}
    ])
    [proposal] = discover(
        query="q", investigation_id="inv-1", num_results=1, client=cli
    )
    result = promote_discovery(
        proposal,
        investigation_id="inv-1",
        legal_gate=PermissiveLegalGate(_bypass_acknowledgment=True),
    )
    assert result.decision == "fetch_failed"
    assert result.document_id is None
    assert "network exploded" in (result.rejection_reason or "")


# ── reject_discovery() ────────────────────────────────────────────


def test_reject_discovery_emits_operator_decision_event(isolated_env):
    cli = _mock_exa_client([
        {"results": [_exa_result("https://example.com/x")]}
    ])
    [proposal] = discover(
        query="q", investigation_id="inv-1", num_results=1, client=cli
    )
    result = reject_discovery(
        proposal,
        investigation_id="inv-1",
        reason="not relevant after operator review",
    )
    assert result.decision == "rejected_by_operator"
    assert result.document_id is None
    assert "not relevant" in (result.rejection_reason or "")


# ── find_similar() ────────────────────────────────────────────────


def test_find_similar_emits_proposed_events(isolated_env):
    """Spec §17.3 — findSimilar ships in Wedge 1, same event shape
    as discover() but with the originating URL as the ``query``
    field."""
    cli = _mock_exa_client([
        {
            "results": [
                _exa_result("https://e.com/x"),
                _exa_result("https://e.com/y"),
            ]
        }
    ])
    proposals = find_similar(
        url="https://e.com/seed",
        investigation_id="inv-1",
        num_results=2,
        client=cli,
    )
    assert len(proposals) == 2
    assert all(p.query == "https://e.com/seed" for p in proposals)


# ── discovery_id stability ────────────────────────────────────────


def test_discovery_id_is_stable_across_calls():
    a = _discovery_id("https://example.com/x", "inv-1")
    b = _discovery_id("https://example.com/x", "inv-1")
    assert a == b
    assert a.startswith("disc-exa-")
    assert len(a) == len("disc-exa-") + 16


def test_discovery_id_changes_with_investigation_id():
    a = _discovery_id("https://example.com/x", "inv-1")
    b = _discovery_id("https://example.com/x", "inv-2")
    assert a != b


# ── Sanity — public surface is intact ─────────────────────────────


def test_public_surface_exports():
    """The discovery layer should expose the operator-facing names
    from the package root so callers can ``from acquisition.search
    import discover``."""
    import acquisition.search as s
    for name in (
        "discover",
        "promote_discovery",
        "DiscoveryProposed",
        "DiscoveryBudgetExceeded",
        "DiscoveryPromotionResult",
    ):
        assert hasattr(s, name), name
