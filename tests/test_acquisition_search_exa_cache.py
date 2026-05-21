"""Tests for the discovery cache (spec §6.5).

Schema: substrate/graph/schema.py — ANTIEK_GRAPH_SCHEMA_V3_DISCOVERY_CACHE_SQL.
Behavior: acquisition/search/exa/cache.py + adapter integration.

Coverage:
  - cache_key stability + parameter sensitivity
  - lookup miss + lookup expired + lookup hit
  - store + idempotent upsert
  - purge_expired returns the count
  - discover() integration: cache hit skips Exa + skips event emission;
    cache miss runs Exa + stores
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

import httpx
import pytest

from acquisition.search.exa import (
    DiscoveryProposed,
    discover,
)
from acquisition.search.exa.adapter import _hydrate_proposed
from acquisition.search.exa.cache import (
    DEFAULT_TTL_SECONDS,
    cache_key,
    lookup,
    purge_expired,
    store,
)
from acquisition.search.exa.client import ExaClient
from substrate.graph import ensure_initialized


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def db_path(tmp_path):
    p = str(tmp_path / "graph.duckdb")
    ensure_initialized(p)
    return p


@pytest.fixture
def isolated_env(tmp_path, monkeypatch, db_path):
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events_dir))
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("EXA_API_KEY", "test-key-not-used")
    monkeypatch.setenv("ANTIEK_LEGAL_GATE_PLACEHOLDER_ACKED", "1")
    yield {
        "events_dir": str(events_dir),
        "tmpdir": str(tmp_path),
        "db_path": db_path,
    }


def _mock_exa_client(
    responses: List[dict], *, status: int = 200,
) -> ExaClient:
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


# ── cache_key ─────────────────────────────────────────────────────


def test_cache_key_stable_across_calls():
    a = cache_key(query="q", investigation_id="inv-1", num_results=5)
    b = cache_key(query="q", investigation_id="inv-1", num_results=5)
    assert a == b
    assert len(a) == 32


def test_cache_key_distinguishes_query():
    a = cache_key(query="q1", investigation_id="inv-1")
    b = cache_key(query="q2", investigation_id="inv-1")
    assert a != b


def test_cache_key_distinguishes_investigation():
    a = cache_key(query="q", investigation_id="inv-1")
    b = cache_key(query="q", investigation_id="inv-2")
    assert a != b


def test_cache_key_distinguishes_num_results():
    a = cache_key(query="q", investigation_id="inv-1", num_results=5)
    b = cache_key(query="q", investigation_id="inv-1", num_results=10)
    assert a != b


def test_cache_key_distinguishes_category():
    a = cache_key(query="q", investigation_id="inv-1", category="news")
    b = cache_key(query="q", investigation_id="inv-1", category="research paper")
    assert a != b


def test_cache_key_order_invariant_for_domain_lists():
    a = cache_key(
        query="q", investigation_id="inv-1",
        include_domains=["a.com", "b.com"],
    )
    b = cache_key(
        query="q", investigation_id="inv-1",
        include_domains=["b.com", "a.com"],
    )
    assert a == b  # sorted internally


# ── lookup / store ────────────────────────────────────────────────


def test_lookup_miss_returns_none(db_path):
    k = cache_key(query="never-stored", investigation_id="inv-x")
    assert lookup(k, db_path=db_path) is None


def test_store_then_lookup_roundtrips(db_path):
    k = cache_key(query="q", investigation_id="inv-1")
    proposals = [
        DiscoveryProposed(
            discovery_id="disc-exa-aaaaaaaaaaaa1234",
            provider="exa",
            query="q",
            url="https://e.com/x",
            title="Title X",
            published_date=None,
            author=None,
            relevance_score=0.7,
            suggested_tier=4,
            text_snippet_preview="...",
            provider_response_id="exa-r1",
            cost_usd_estimate=0.005,
            proposed_event_id="evt-1",
        )
    ]
    store(
        k, proposals=proposals,
        query="q", investigation_id="inv-1",
        db_path=db_path,
    )
    got = lookup(k, db_path=db_path)
    assert got is not None
    assert len(got) == 1
    assert got[0]["discovery_id"] == "disc-exa-aaaaaaaaaaaa1234"
    assert got[0]["title"] == "Title X"


def test_store_is_idempotent_upsert(db_path):
    k = cache_key(query="q", investigation_id="inv-1")
    store(
        k, proposals=[{"discovery_id": "d1", "url": "u1", "suggested_tier": 4,
                       "cost_usd_estimate": 0.005}],
        query="q", investigation_id="inv-1",
        db_path=db_path,
    )
    # Second store with different proposals should replace.
    store(
        k, proposals=[{"discovery_id": "d2", "url": "u2", "suggested_tier": 4,
                       "cost_usd_estimate": 0.005}],
        query="q", investigation_id="inv-1",
        db_path=db_path,
    )
    got = lookup(k, db_path=db_path)
    assert len(got) == 1
    assert got[0]["discovery_id"] == "d2"


def test_lookup_expired_returns_none(db_path):
    k = cache_key(query="q", investigation_id="inv-1")
    past = datetime.now(timezone.utc) - timedelta(hours=25)
    # Store with negative ttl so the entry is born expired.
    store(
        k, proposals=[{"discovery_id": "d", "url": "u",
                       "suggested_tier": 4, "cost_usd_estimate": 0.005}],
        query="q", investigation_id="inv-1",
        ttl_seconds=-100,
        db_path=db_path,
    )
    assert lookup(k, db_path=db_path) is None


def test_purge_expired_removes_only_expired_rows(db_path):
    k_old = cache_key(query="old", investigation_id="inv-old")
    k_new = cache_key(query="new", investigation_id="inv-new")
    store(
        k_old, proposals=[{"discovery_id": "d-old", "url": "u",
                           "suggested_tier": 4, "cost_usd_estimate": 0.005}],
        query="old", investigation_id="inv-old",
        ttl_seconds=-100, db_path=db_path,
    )
    store(
        k_new, proposals=[{"discovery_id": "d-new", "url": "u",
                           "suggested_tier": 4, "cost_usd_estimate": 0.005}],
        query="new", investigation_id="inv-new",
        ttl_seconds=3600, db_path=db_path,
    )
    purged = purge_expired(db_path=db_path)
    assert purged == 1
    assert lookup(k_new, db_path=db_path) is not None


def test_lookup_against_missing_db_returns_none(tmp_path):
    """A missing substrate DB falls through (cache fails open)."""
    missing = str(tmp_path / "does-not-exist.duckdb")
    k = cache_key(query="q", investigation_id="inv-1")
    assert lookup(k, db_path=missing) is None


# ── discover() cache integration ──────────────────────────────────


def test_discover_caches_results_on_first_call(isolated_env):
    cli = _mock_exa_client([{
        "results": [{"url": "https://e.com/x", "title": "T"}],
        "requestId": "exa-1",
    }])
    [p] = discover(
        query="claude pricing 2026",
        investigation_id="inv-cache-1",
        num_results=1,
        client=cli,
        db_path=isolated_env["db_path"],
    )
    # The cache should now hold this proposal.
    k = cache_key(
        query="claude pricing 2026", investigation_id="inv-cache-1",
        num_results=1,
    )
    got = lookup(k, db_path=isolated_env["db_path"])
    assert got is not None
    assert got[0]["url"] == "https://e.com/x"


def test_discover_cache_hit_short_circuits_exa(isolated_env):
    """Second identical call returns cached proposals without
    hitting Exa or emitting new events."""
    # First call — populates cache.
    cli1 = _mock_exa_client([{
        "results": [{"url": "https://e.com/x", "title": "T"}],
    }])
    first = discover(
        query="q-cache-hit",
        investigation_id="inv-c2",
        num_results=1,
        client=cli1,
        db_path=isolated_env["db_path"],
    )
    # Second call — Exa client raises if invoked (proves the cache
    # served the request).
    def explode_handler(request):
        raise AssertionError("Exa client must not be called on cache hit")

    cli2 = ExaClient(
        api_key="k",
        client=httpx.Client(transport=httpx.MockTransport(explode_handler)),
        sleep=lambda _s: None,
    )
    second = discover(
        query="q-cache-hit",
        investigation_id="inv-c2",
        num_results=1,
        client=cli2,
        db_path=isolated_env["db_path"],
    )
    assert [p.url for p in second] == [p.url for p in first]
    assert [p.discovery_id for p in second] == [p.discovery_id for p in first]


def test_discover_use_cache_false_bypasses(isolated_env):
    """`use_cache=False` always calls Exa even when a cached entry
    exists."""
    cli1 = _mock_exa_client([{
        "results": [{"url": "https://e.com/x", "title": "First"}],
    }])
    discover(
        query="q-bypass",
        investigation_id="inv-c3",
        num_results=1,
        client=cli1,
        db_path=isolated_env["db_path"],
    )
    cli2 = _mock_exa_client([{
        "results": [{"url": "https://e.com/x", "title": "Second"}],
    }])
    second = discover(
        query="q-bypass",
        investigation_id="inv-c3",
        num_results=1,
        client=cli2,
        db_path=isolated_env["db_path"],
        use_cache=False,
    )
    # The second call ran live Exa, returning the freshly-mocked title.
    assert second[0].title == "Second"


def test_discover_cache_keyed_per_investigation(isolated_env):
    """The same query under different investigation_ids does not
    share cache (per spec §6.5 — cache key includes investigation_id)."""
    cli1 = _mock_exa_client([{
        "results": [{"url": "https://e.com/x", "title": "Inv1"}],
    }])
    discover(
        query="q-iso",
        investigation_id="inv-A",
        num_results=1,
        client=cli1,
        db_path=isolated_env["db_path"],
    )
    cli2 = _mock_exa_client([{
        "results": [{"url": "https://e.com/x", "title": "Inv2"}],
    }])
    second = discover(
        query="q-iso",
        investigation_id="inv-B",  # different investigation
        num_results=1,
        client=cli2,
        db_path=isolated_env["db_path"],
    )
    # Second call ran live; if the cache had been keyed on query
    # alone, this would have returned "Inv1" from the cache.
    assert second[0].title == "Inv2"


def test_hydrate_proposed_roundtrips():
    p = DiscoveryProposed(
        discovery_id="disc-x",
        provider="exa",
        query="q",
        url="u",
        title="T",
        published_date=None,
        author=None,
        relevance_score=None,
        suggested_tier=4,
        text_snippet_preview=None,
        provider_response_id=None,
        cost_usd_estimate=0.005,
        proposed_event_id="evt-1",
    )
    from dataclasses import asdict
    rebuilt = _hydrate_proposed(asdict(p))
    assert rebuilt == p
