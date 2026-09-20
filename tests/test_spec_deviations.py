"""Tests for the three deviations from the 2026-05-22 second-pass audit
of `docs/integration_exa_browserbase.md`. Each class corresponds to
one deviation. Names trace back to the spec section the deviation
closes.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

# ── Deviation A: §6.5 — discovery_id distinguishes cross-query ───────


class TestDeviationA_DiscoveryIdIncludesQuery:
    def test_same_url_different_query_gives_different_id(self):
        from acquisition.search.exa.adapter import _discovery_id
        a = _discovery_id("https://e.com/x", "inv-1", "claude pricing")
        b = _discovery_id("https://e.com/x", "inv-1", "anthropic cost")
        assert a != b, "spec §6.5: cross-query same-URL must produce different discovery_ids"

    def test_same_url_same_query_stable(self):
        """The id stays stable within a (url, inv, query) triple so
        re-runs are deterministic for cache lookups + tests."""
        from acquisition.search.exa.adapter import _discovery_id
        a = _discovery_id("https://e.com/x", "inv-1", "same query")
        b = _discovery_id("https://e.com/x", "inv-1", "same query")
        assert a == b

    def test_backward_compat_no_query_arg(self):
        """Legacy callsites that compute discovery_id without a
        query (e.g. tests verifying within-investigation stability)
        still work — the parameter defaults to empty string."""
        from acquisition.search.exa.adapter import _discovery_id
        d = _discovery_id("https://e.com/x", "inv-1")
        assert d.startswith("disc-exa-")
        assert len(d) == len("disc-exa-") + 16

    def test_investigation_id_still_distinguishes(self):
        """The prior §6.2 distinction still holds: different
        investigation_id → different discovery_id even at fixed
        url + query."""
        from acquisition.search.exa.adapter import _discovery_id
        a = _discovery_id("https://e.com/x", "inv-1", "q")
        b = _discovery_id("https://e.com/x", "inv-2", "q")
        assert a != b

    def test_end_to_end_via_discover_two_queries_same_url(self, tmp_path, monkeypatch):
        """Two `discover()` calls with different queries that
        happen to return the same URL must produce two proposals
        with distinct discovery_ids — proves §6.5 from the
        operator API surface, not just the helper."""
        events_dir = tmp_path / "events"
        events_dir.mkdir()
        monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events_dir))
        monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
        monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "graph.duckdb"))
        monkeypatch.setenv("EXA_API_KEY", "test-key")
        monkeypatch.setenv("ANTIEK_LEGAL_GATE_DISABLED", "1")

        from acquisition.search.exa import ExaClient, discover

        same_url_response = {"results": [{"url": "https://e.com/article", "title": "T"}]}

        def handler(req):
            return httpx.Response(200, json=same_url_response)

        def make_client():
            return ExaClient(
                api_key="k",
                client=httpx.Client(transport=httpx.MockTransport(handler)),
                sleep=lambda _s: None,
            )

        [a] = discover(
            query="claude pricing", investigation_id="inv-X",
            num_results=1, client=make_client(), use_cache=False,
        )
        [b] = discover(
            query="anthropic cost", investigation_id="inv-X",
            num_results=1, client=make_client(), use_cache=False,
        )
        assert a.url == b.url == "https://e.com/article"
        assert a.discovery_id != b.discovery_id


# ── Deviation B: §14.7 — provider_response_id in provider_specific ───


class TestDeviationB_ProviderSpecificMigration:
    def test_adapter_writes_response_id_into_provider_specific(self, tmp_path, monkeypatch):
        """The adapter must write Exa's response_id under
        provider_specific["response_id"], not as a top-level
        payload field."""
        events_dir = tmp_path / "events"
        events_dir.mkdir()
        monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events_dir))
        monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
        monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "graph.duckdb"))
        monkeypatch.setenv("EXA_API_KEY", "test-key")
        monkeypatch.setenv("ANTIEK_LEGAL_GATE_DISABLED", "1")

        from acquisition.search.exa import ExaClient, discover

        def handler(req):
            return httpx.Response(200, json={
                "results": [{
                    "url": "https://e.com/a", "title": "A",
                    "id": "exa-resp-xyz",   # Exa's per-result id
                }],
                "requestId": "exa-req-1",
            })

        cli = ExaClient(
            api_key="k",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            sleep=lambda _s: None,
        )
        [p] = discover(
            query="q", investigation_id="inv-B1",
            num_results=1, client=cli, use_cache=False,
        )
        # Operator-facing dataclass surfaces both — top-level
        # mirror + dict bag.
        assert p.provider_specific.get("response_id") == "exa-resp-xyz"
        assert p.provider_response_id == "exa-resp-xyz"

        # Read the emitted event to confirm the PAYLOAD side
        # writes provider_specific (canonical), with top-level
        # provider_response_id either None or backward-compat.
        from acquisition.search import default_discovery_events_dir
        disc_dir = Path(default_discovery_events_dir())
        for f in disc_dir.rglob("*.jsonl"):
            for line in f.read_text().splitlines():
                if not line.strip():
                    continue
                ev = json.loads(line)
                if ev.get("action_type") == "discovery.proposed":
                    payload = ev["payload"]
                    assert payload.get("provider_specific", {}).get("response_id") == "exa-resp-xyz"
                    # Top-level field stays None — canonical write
                    # goes into provider_specific.
                    assert payload.get("provider_response_id") is None
                    return
        pytest.fail("expected a discovery.proposed event")

    def test_hydrate_prefers_provider_specific_over_top_level(self):
        """When both locations carry a value, the dict wins
        (forward-compat with future emitters)."""
        from acquisition.search.exa.adapter import _hydrate_proposed
        d = {
            "discovery_id": "d", "provider": "exa", "query": "q", "url": "u",
            "suggested_tier": 4,
            "provider_response_id": "OLD-top-level",
            "provider_specific": {"response_id": "NEW-dict"},
        }
        p = _hydrate_proposed(d)
        assert p.provider_response_id == "NEW-dict"

    def test_hydrate_falls_back_to_top_level_when_dict_missing(self):
        """v6-v8 cached rows that pre-date provider_specific still
        resolve via the top-level fallback."""
        from acquisition.search.exa.adapter import _hydrate_proposed
        d = {
            "discovery_id": "d", "provider": "exa", "query": "q", "url": "u",
            "suggested_tier": 4,
            "provider_response_id": "legacy-resp-id",
            # No provider_specific at all (v6-v8 shape).
        }
        p = _hydrate_proposed(d)
        assert p.provider_response_id == "legacy-resp-id"
        assert p.provider_specific == {}
    def test_dataclass_default_provider_specific_is_empty_dict(self):
        from acquisition.search.exa.adapter import DiscoveryProposed
        p = DiscoveryProposed(
            discovery_id="d", provider="exa", query="q", url="u",
            title=None, published_date=None, author=None,
            relevance_score=None, suggested_tier=4,
            text_snippet_preview=None, provider_response_id=None,
            cost_usd_estimate=0.005, proposed_event_id=None,
        )
        assert p.provider_specific == {}
