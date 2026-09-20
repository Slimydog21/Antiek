"""Tests for the eight spec-gap remediations from the 2026-05-22 audit
of `docs/integration_exa_browserbase.md`.

Each test class corresponds to one gap. The test names trace back
to the spec section the gap closes.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

# ── Gap 1: §6.6 — _CURATED_NEWS_TIER_3 lives in substrate.constants ──


class TestGap1_TierAllowlistInSubstrate:
    def test_substrate_constants_exposes_tier_3_allowlist(self):
        from substrate.constants import CURATED_NEWS_TIER_3
        assert isinstance(CURATED_NEWS_TIER_3, frozenset)
        # Seed entries (operator-edited; verify the major ones).
        for h in ("nytimes.com", "wsj.com", "bloomberg.com"):
            assert h in CURATED_NEWS_TIER_3, h

    def test_substrate_constants_exposes_tier_2_research_hosts(self):
        from substrate.constants import RESEARCH_HOSTS_TIER_2
        assert "arxiv.org" in RESEARCH_HOSTS_TIER_2

    def test_adapter_imports_from_substrate(self):
        """The adapter's tier heuristic MUST consult the substrate-level
        allowlist, not a local copy. This test fails if a future edit
        re-introduces a private allowlist in the adapter module."""
        from acquisition.search.exa.adapter import _CURATED_NEWS_TIER_3 as adapter_ref
        from substrate.constants import CURATED_NEWS_TIER_3 as substrate_set
        assert adapter_ref is substrate_set


# ── Gap 2: §7.3 — escalation_reason JS-detect casing ────────────────


class TestGap2_EscalationReasonCasing:
    def test_js_detect_literal_uses_spec_casing(self):
        from substrate.schemas.events import FetchFallbackEscalatedPayload
        p = FetchFallbackEscalatedPayload(
            url="https://example.com/x",
            primary_word_count=5,
            fallback_fetcher="browserbase",
            fallback_word_count=200,
            escalation_reason="JS-detect",
            estimated_cost_usd=0.10,
        )
        assert p.escalation_reason == "JS-detect"

    def test_old_js_detect_lowercase_rejected(self):
        from pydantic import ValidationError

        from substrate.schemas.events import FetchFallbackEscalatedPayload
        with pytest.raises(ValidationError):
            FetchFallbackEscalatedPayload(
                url="https://example.com/x",
                primary_word_count=5,
                fallback_fetcher="browserbase",
                fallback_word_count=200,
                escalation_reason="js_detect",  # old casing — rejected
                estimated_cost_usd=0.10,
            )


# ── Gap 4: §14.7 — provider_specific dict on DiscoveryProposedPayload ─


class TestGap4_ProviderSpecificDict:
    def test_provider_specific_defaults_to_empty_dict(self):
        from substrate.schemas.events import DiscoveryProposedPayload
        p = DiscoveryProposedPayload(
            discovery_id="d", provider="exa", query="q", url="u",
            suggested_tier=4,
        )
        assert p.provider_specific == {}

    def test_provider_specific_accepts_arbitrary_provider_data(self):
        from substrate.schemas.events import DiscoveryProposedPayload
        p = DiscoveryProposedPayload(
            discovery_id="d", provider="exa", query="q", url="u",
            suggested_tier=4,
            provider_specific={
                "autoprompt_string": "enriched neural query",
                "subpages": ["/path1", "/path2"],
                "exa_filter": "neural",
            },
        )
        assert p.provider_specific["autoprompt_string"] == "enriched neural query"
        assert p.provider_specific["subpages"] == ["/path1", "/path2"]

    def test_schema_version_at_or_past_9(self):
        from substrate.schemas.events import EVENT_SCHEMA_VERSION
        assert EVENT_SCHEMA_VERSION >= 9

    def test_payload_roundtrips_through_typed_union(self):
        from pydantic import TypeAdapter

        from substrate.schemas.events import DiscoveryProposedPayload, TypedPayload
        p = DiscoveryProposedPayload(
            discovery_id="d", provider="exa", query="q", url="u",
            suggested_tier=4,
            provider_specific={"x": 1},
        )
        re = TypeAdapter(TypedPayload).validate_python(p.model_dump())
        assert isinstance(re, DiscoveryProposedPayload)
        assert re.provider_specific == {"x": 1}


# ── Gap 5: §13.2 — combined DailyAcquisitionBudgetExceeded ───────────


class TestGap5_CombinedAcquisitionBudget:
    @pytest.fixture
    def tmp_home(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
        budgets = tmp_path / "budgets"
        budgets.mkdir()
        yield {"tmp": tmp_path, "budgets": budgets}

    @staticmethod
    def _write_budget(d: Path, prov: str, spent: float):
        stamp = datetime.now(UTC).strftime("%Y-%m-%d")
        (d / f"{prov}_{stamp}.json").write_text(json.dumps({
            "date_stamp": stamp, "spent_usd": spent,
        }))

    def test_total_cap_constant_defaults_to_10(self):
        from substrate.constants import TOTAL_ACQUISITION_BUDGET_USD
        assert TOTAL_ACQUISITION_BUDGET_USD == 10.0

    def test_current_total_spend_sums_across_sidecars(self, tmp_home):
        from acquisition.search import current_total_spend_usd
        self._write_budget(tmp_home["budgets"], "exa", 3.5)
        self._write_budget(tmp_home["budgets"], "browserbase", 2.0)
        self._write_budget(tmp_home["budgets"], "future_provider", 1.0)
        assert current_total_spend_usd() == 6.5

    def test_total_cap_raises_when_combined_exceeded(self, tmp_home):
        from acquisition.search import (
            DailyAcquisitionBudgetExceeded,
            assert_total_budget_ok,
        )
        self._write_budget(tmp_home["budgets"], "exa", 4.5)
        self._write_budget(tmp_home["budgets"], "browserbase", 4.5)
        # 9 spent + 1.5 next call = 10.5 > 10 cap → raises
        with pytest.raises(DailyAcquisitionBudgetExceeded):
            assert_total_budget_ok(1.5)

    def test_total_cap_env_override(self, tmp_home, monkeypatch):
        from acquisition.search import assert_total_budget_ok
        self._write_budget(tmp_home["budgets"], "exa", 9.0)
        # Raise cap to $50 via env override.
        monkeypatch.setenv("ANTIEK_TOTAL_ACQUISITION_BUDGET_USD", "50.0")
        # 9 + 10 = 19 < 50 → passes.
        assert assert_total_budget_ok(10.0) == 19.0

    def test_combined_cap_fires_before_per_provider(self, tmp_home, monkeypatch):
        """When both caps would fire, the combined cap exception
        should fire first (it's consulted first per the spec text)."""
        from acquisition.search import DailyAcquisitionBudgetExceeded
        from acquisition.search.exa.budget import DEFAULT_DAILY_BUDGET_USD, check_and_reserve
        # Both providers at the per-provider cap → combined is well
        # over. The combined check runs first.
        self._write_budget(tmp_home["budgets"], "exa", DEFAULT_DAILY_BUDGET_USD - 0.001)
        self._write_budget(tmp_home["budgets"], "browserbase", DEFAULT_DAILY_BUDGET_USD - 0.001)
        with pytest.raises(DailyAcquisitionBudgetExceeded):
            check_and_reserve(1.0)


# ── Gap 6: §14.2 — url_alias table + short-circuit ───────────────────


class TestGap6_UrlAlias:
    @pytest.fixture
    def tmp_db(self, tmp_path, monkeypatch):
        db = tmp_path / "graph.duckdb"
        monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db))
        from substrate.graph import ensure_initialized
        ensure_initialized(str(db))
        yield {"db": str(db), "tmp": tmp_path}

    def test_url_alias_table_present(self, tmp_db):
        import duckdb
        c = duckdb.connect(tmp_db["db"], read_only=True)
        try:
            tables = [r[0] for r in c.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='main'"
            ).fetchall()]
        finally:
            c.close()
        assert "url_alias" in tables

    def test_lookup_url_alias_returns_none_when_missing(self, tmp_db):
        from acquisition.urls.adapter import lookup_url_alias
        assert lookup_url_alias("https://never-seen.example", db_path=tmp_db["db"]) is None

    def test_alias_inserted_on_ingest_and_then_short_circuits(self, tmp_db, monkeypatch):
        """End-to-end: ingest once, then re-ingest the same URL and
        confirm the second call short-circuits to the canonical
        document_id without performing a fetch."""
        from acquisition.urls.adapter import ingest_url, url_doc_id
        from acquisition.urls.client import FetchedHtml

        # Stub the fetcher so we can count calls.
        call_count = {"n": 0}

        def stub_fetch(url, *, client=None):
            call_count["n"] += 1
            body = b"<html><body>" + b"hello world " * 50 + b"</body></html>"
            return FetchedHtml(
                requested_url=url, final_url=url, status_code=200,
                content_type="text/html", charset="utf-8", body=body,
            )

        import acquisition.urls.adapter as adapter_mod
        monkeypatch.setattr(adapter_mod, "fetch", stub_fetch)

        # Stub embedder so we don't need sentence-transformers.
        class _StubEmbedder:
            def encode(self, t): return [0.0] * 4

        # First ingest creates the alias.
        r1 = ingest_url(
            "https://example.com/article", investigation_id="inv-1",
            db_path=tmp_db["db"], embedder=_StubEmbedder(),
        )
        assert r1.skipped_reason is None
        assert call_count["n"] == 1
        expected_doc = url_doc_id("https://example.com/article")
        assert r1.document_id == expected_doc

        # Second ingest of the SAME requested_url should short-circuit.
        r2 = ingest_url(
            "https://example.com/article", investigation_id="inv-2",
            db_path=tmp_db["db"], embedder=_StubEmbedder(),
        )
        assert r2.document_id == expected_doc
        assert r2.skipped_reason == "alias_resolved_to_existing_document"
        # Fetch must NOT have been called the second time.
        assert call_count["n"] == 1

    def test_alias_short_circuit_skipped_when_fetched_preset(self, tmp_db, monkeypatch):
        """`fetched=` preset means the caller has bytes and is
        intentionally re-ingesting — alias short-circuit must skip."""
        from acquisition.urls.adapter import ingest_url
        from acquisition.urls.client import FetchedHtml

        class _StubEmbedder:
            def encode(self, t): return [0.0] * 4

        # Seed the alias.
        body = b"<html><body>" + b"hello world " * 50 + b"</body></html>"
        preset = FetchedHtml(
            requested_url="https://example.com/x",
            final_url="https://example.com/x",
            status_code=200, content_type="text/html",
            charset="utf-8", body=body,
        )
        r1 = ingest_url(
            "https://example.com/x", investigation_id="inv-1",
            db_path=tmp_db["db"], embedder=_StubEmbedder(), fetched=preset,
        )
        # Re-ingest with fetched= — should NOT short-circuit.
        r2 = ingest_url(
            "https://example.com/x", investigation_id="inv-2",
            db_path=tmp_db["db"], embedder=_StubEmbedder(), fetched=preset,
        )
        # The doc_id is the same (url_doc_id is deterministic) but
        # skipped_reason is None — the call actually ingested.
        assert r2.skipped_reason is None
        assert r2.document_id == r1.document_id


# ── Gap 7: §14.1 — separate discovery_events JSONL dir ───────────────


class TestGap7_SeparateDiscoveryEventsDir:
    @pytest.fixture
    def isolated(self, tmp_path, monkeypatch):
        substrate_events = tmp_path / "substrate_events"
        substrate_events.mkdir()
        monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
        monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(substrate_events))
        monkeypatch.setenv("EXA_API_KEY", "test-key")
        monkeypatch.setenv("ANTIEK_LEGAL_GATE_DISABLED", "1")
        monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "graph.duckdb"))
        yield {"tmp": tmp_path, "substrate_events": substrate_events}

    def test_default_discovery_events_dir_uses_antiek_home(self, isolated):
        from acquisition.search import default_discovery_events_dir
        d = default_discovery_events_dir()
        assert str(isolated["tmp"] / "discovery_events") == d
        assert os.path.isdir(d)

    def test_env_override_takes_precedence(self, isolated, monkeypatch, tmp_path):
        from acquisition.search import default_discovery_events_dir
        override = tmp_path / "elsewhere"
        monkeypatch.setenv("ANTIEK_DISCOVERY_EVENTS_DIR", str(override))
        assert default_discovery_events_dir() == str(override)

    def test_discover_writes_to_discovery_events_dir_not_substrate(self, isolated):
        """End-to-end check: a `discover()` call emits DiscoveryProposed
        into the discovery_events dir, NOT into the substrate
        events dir."""
        from acquisition.search.exa import ExaClient, discover

        # Mock Exa to return one result.
        def handler(req):
            return httpx.Response(200, json={"results": [
                {"url": "https://e.com/a", "title": "A"}
            ]})

        client = ExaClient(
            api_key="k",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            sleep=lambda _s: None,
        )
        discover(
            query="claude pricing", investigation_id="inv-route-test",
            num_results=1, client=client, use_cache=False,
        )

        # Discovery events should be in discovery_events/, not in
        # the substrate-events dir.
        disc_dir = isolated["tmp"] / "discovery_events"
        substrate_dir = isolated["substrate_events"]

        disc_files = list(disc_dir.rglob("*.jsonl"))
        substrate_files = list(substrate_dir.rglob("*.jsonl"))

        assert disc_files, "expected at least one discovery_events file"
        # discovery.proposed events should be IN disc_files
        found_in_discovery = False
        for f in disc_files:
            if "discovery.proposed" in f.read_text():
                found_in_discovery = True
                break
        assert found_in_discovery

        # And NOT in the substrate-events dir.
        for f in substrate_files:
            assert "discovery.proposed" not in f.read_text(), \
                f"discovery event leaked into substrate dir {f}"


# ── Gap 8: §14.1 — 30-day retention + discovery_summary ──────────────


class TestGap8_RetentionAndRollup:
    @pytest.fixture
    def isolated(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
        monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "graph.duckdb"))
        from substrate.graph import ensure_initialized
        ensure_initialized(str(tmp_path / "graph.duckdb"))
        events_dir = tmp_path / "discovery_events"
        events_dir.mkdir()
        yield {"tmp": tmp_path, "events_dir": events_dir,
               "db": str(tmp_path / "graph.duckdb")}

    @staticmethod
    def _write_old_events(events_dir: Path, *, days_ago: int = 45, n: int = 3,
                          provider: str = "exa", query: str = "old query"):
        ts = (datetime.now(UTC) - timedelta(days=days_ago)).replace(tzinfo=None).isoformat() + "Z"
        path = events_dir / f"inv-{days_ago}d.jsonl"
        lines = []
        for i in range(n):
            lines.append(json.dumps({
                "action_type": "discovery.proposed",
                "emitted_at": ts,
                "payload": {
                    "provider": provider, "query": query,
                    "url": f"https://e.com/{i}",
                    "cost_usd_estimate": 0.001,
                },
            }))
        path.write_text("\n".join(lines))
        return path

    def test_discovery_summary_table_present(self, isolated):
        import duckdb
        c = duckdb.connect(isolated["db"], read_only=True)
        try:
            tables = [r[0] for r in c.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
            ).fetchall()]
        finally:
            c.close()
        assert "discovery_summary" in tables

    def test_rollup_summarizes_and_truncates_old_files(self, isolated):
        from acquisition.search.retention import recent_summary, rollup_expired
        f = self._write_old_events(isolated["events_dir"], days_ago=45, n=3)
        r = rollup_expired(retention_days=30, db_path=isolated["db"],
                            events_dir=str(isolated["events_dir"]))
        assert r.files_rolled_up == 1
        assert r.raw_events_rolled_up == 3
        assert r.summary_rows_written == 1
        assert f.read_text() == ""  # truncated
        rows = recent_summary(days=60, db_path=isolated["db"])
        assert len(rows) == 1
        assert rows[0]["proposal_count"] == 3
        assert abs(rows[0]["total_cost_usd"] - 0.003) < 1e-9

    def test_rollup_skips_files_within_retention(self, isolated):
        from acquisition.search.retention import rollup_expired
        # Mostly-old file but one event is recent — must skip the whole file
        # so we don't lose data on a future re-rollup.
        recent_ts = datetime.now(UTC).replace(tzinfo=None).isoformat() + "Z"
        old_ts = (datetime.now(UTC) - timedelta(days=45)).replace(tzinfo=None).isoformat() + "Z"
        f = isolated["events_dir"] / "mixed.jsonl"
        f.write_text(
            json.dumps({"action_type": "discovery.proposed", "emitted_at": old_ts,
                        "payload": {"provider": "exa", "query": "q", "url": "u1",
                                    "cost_usd_estimate": 0.001}}) + "\n" +
            json.dumps({"action_type": "discovery.proposed", "emitted_at": recent_ts,
                        "payload": {"provider": "exa", "query": "q", "url": "u2",
                                    "cost_usd_estimate": 0.001}}) + "\n"
        )
        r = rollup_expired(retention_days=30, db_path=isolated["db"],
                           events_dir=str(isolated["events_dir"]))
        assert r.files_rolled_up == 0  # nothing to summarize — recent event present
        assert f.read_text() != ""

    def test_rollup_is_idempotent_via_on_conflict(self, isolated):
        """Re-running rollup against the same input must NOT double-count.
        The second run sees the file empty + nothing to roll up."""
        from acquisition.search.retention import recent_summary, rollup_expired
        self._write_old_events(isolated["events_dir"], days_ago=45, n=2)
        rollup_expired(retention_days=30, db_path=isolated["db"],
                       events_dir=str(isolated["events_dir"]))
        # Second run — file is now empty, no events to process.
        rollup_expired(retention_days=30, db_path=isolated["db"],
                       events_dir=str(isolated["events_dir"]))
        # The empty file isn't "expired" (no parseable timestamps), but
        # the summary row count should remain 1.
        rows = recent_summary(days=60, db_path=isolated["db"])
        assert len(rows) == 1
        assert rows[0]["proposal_count"] == 2  # not 4

    def test_rollup_handles_selected_events(self, isolated):
        from acquisition.search.retention import recent_summary, rollup_expired
        old_ts = (datetime.now(UTC) - timedelta(days=45)).replace(tzinfo=None).isoformat() + "Z"
        f = isolated["events_dir"] / "selected.jsonl"
        f.write_text(
            json.dumps({"action_type": "discovery.proposed", "emitted_at": old_ts,
                        "payload": {"provider": "exa", "query": "q", "url": "u1",
                                    "cost_usd_estimate": 0.001}}) + "\n" +
            json.dumps({"action_type": "discovery.selected", "emitted_at": old_ts,
                        "payload": {"provider": "exa", "query": "q",
                                    "decision": "ingested"}}) + "\n" +
            json.dumps({"action_type": "discovery.selected", "emitted_at": old_ts,
                        "payload": {"provider": "exa", "query": "q",
                                    "decision": "rejected_by_legal_gate"}}) + "\n"
        )
        rollup_expired(retention_days=30, db_path=isolated["db"],
                       events_dir=str(isolated["events_dir"]))
        rows = recent_summary(days=60, db_path=isolated["db"])
        assert len(rows) == 1
        assert rows[0]["proposal_count"] == 1
        assert rows[0]["selected_count"] == 1
        assert rows[0]["rejected_by_gate"] == 1
