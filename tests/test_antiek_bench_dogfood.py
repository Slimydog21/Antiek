"""Competitive dogfood fixtures for Antiek-bench (residual av)."""

from __future__ import annotations

import os
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.api.settings_budget import (  # noqa: E402
    register_settings_budget_routes,
)
from substrate.antiek_bench import (  # noqa: E402
    COMPETITIVE_DOGFOOD_VERSION,
    InMemoryBenchStore,
    SuiteRegistry,
    active_suite,
    competitive_dogfood_suite,
    default_core_suite,
    dogfood_fixture_payload,
    register_competitive_dogfood_suite,
    register_suite,
    run_suite,
)
from substrate.antiek_bench.run import keyword_stub_provider  # noqa: E402


def test_dogfood_suite_covers_task_classes():
    suite = competitive_dogfood_suite()
    assert suite.suite_version == COMPETITIVE_DOGFOOD_VERSION
    classes = set(suite.task_classes())
    assert {"distill", "synthesize", "wrestle", "book_qa"} <= classes
    assert len(suite.items) >= 18
    # Residual (st): write-seed / float HTML / budget foresight postures.
    ids = {i.item_id for i in suite.items}
    assert "dogfood-wrestle-write-seed" in ids
    assert "dogfood-synth-float-evidence" in ids
    assert "dogfood-distill-budget-foresight" in ids
    # Residual (tf): Faraday book_qa electricity STEM.
    assert "dogfood-book-faraday-induction" in ids
    # Residual (tv): multi-spawn collective unit write-seed posture.
    assert "dogfood-wrestle-collective-unit-write-seed" in ids
    # Residual (tz): Boole computing/logic book_qa.
    assert "dogfood-book-boole-laws-of-thought" in ids
    # Residual (ud): Heaviside electricity engineering book_qa.
    assert "dogfood-book-heaviside-em" in ids
    # Residual (us): citation-trust ungrounded hydrate prep.
    assert "dogfood-wrestle-citation-trust-ungrounded" in ids
    # Residual (ve): twin cross-asset merge write-seed posture.
    assert "dogfood-wrestle-twin-cross-asset-merge-write-seed" in ids
    # Residual (vl): collective written analysis write-seed posture.
    assert "dogfood-wrestle-collective-written-analysis-write-seed" in ids
    # Residual (wd): Shannon information-theory book_qa.
    assert "dogfood-book-shannon-communication" in ids
    # Residual (wl): Turing computability book_qa.
    assert "dogfood-book-turing-computable-numbers" in ids
    # Residual (xi): Lovelace computing-history book_qa.
    assert "dogfood-book-lovelace-analytical-engine" in ids
    assert "dogfood-book-godel-incompleteness" in ids
    # Residual (ags): Fourier heat free PD book_qa + ResearchThis twins.
    assert "dogfood-book-fourier-heat" in ids
    assert "dogfood-wrestle-research-this-twins" in ids
    # Residual (agw): seamless spawn merge + multi-spawn collective merge path.
    assert "dogfood-wrestle-spawn-merge-path" in ids
    assert "dogfood-wrestle-collective-multi-spawn-merge" in ids
    # Residual (ahd): knowledge-dense pub quick-call matrix.
    assert "dogfood-wrestle-pub-quick-call-matrix" in ids
    assert "dogfood-wrestle-budget-foresight-pub-refs" in ids
    assert "dogfood-wrestle-purchase-seamless-port" in ids
    assert "dogfood-wrestle-domain-aware-twin-search" in ids
    assert "dogfood-wrestle-moil-deposit-twin-honesty" in ids
    assert "dogfood-wrestle-pub-ref-foresight-chrome" in ids
    assert "dogfood-wrestle-competitive-dr-scorecard" in ids
    assert "dogfood-wrestle-citation-chain" in ids
    assert "dogfood-wrestle-citation-chain-hops" in ids
    assert "dogfood-wrestle-domain-aware-stem-expanded" in ids
    assert "dogfood-wrestle-evidence-write-multi-hop" in ids
    assert "dogfood-wrestle-twin-promote-depth-graph" in ids
    assert "dogfood-wrestle-twin-promote-write-depth-graph" in ids
    assert "dogfood-wrestle-collective-unit-twin-seed" in ids
    # Residual (adn): write-seed has-body honesty → recursive rewrite.
    assert "dogfood-wrestle-write-seed-has-body" in ids
    # Residual (aeu): seamless Write path + intelligent search context Write.
    assert "dogfood-wrestle-seamless-write-path" in ids
    assert "dogfood-wrestle-intelligent-search-context-write" in ids
    assert "dogfood-wrestle-written-analysis-open-write-source" in ids
    assert "dogfood-wrestle-continue-as-unit-path" in ids
    # Residual (afo): Select open + unit restore path honesty.
    assert "dogfood-wrestle-select-open-path" in ids
    assert "dogfood-wrestle-unit-restore-path" in ids
    assert "dogfood-wrestle-select-recent-path" in ids
    assert "dogfood-wrestle-research-workstation-spine" in ids
    assert "dogfood-wrestle-highlight-deep-research-path" in ids
    assert "dogfood-wrestle-talk-to-book-twins" in ids
    assert "dogfood-wrestle-meta-reading-twins" in ids
    assert "dogfood-wrestle-talk-to-book-collective" in ids
    assert "dogfood-wrestle-meta-reading-collective" in ids
    assert "dogfood-wrestle-marketplace-host-collective" in ids
    assert "dogfood-book-nicomachean-ethics" in ids


def test_dogfood_fixture_payload_includes_shannon_turing_lovelace_v12() -> None:
    """Residual (wt/xi/aeu/afo/ags): Settings payload lists STEM book_qa + v21 path fixtures."""
    from substrate.antiek_bench.dogfood_fixtures import dogfood_fixture_payload

    payload = dogfood_fixture_payload(include_html=True)
    assert payload["suite_version"] == COMPETITIVE_DOGFOOD_VERSION
    assert payload["suite_version"] == "suite-competitive-dogfood-v36"
    assert payload["item_count"] >= 53
    assert payload["auto_promoted"] is False
    assert payload["by_task_class"].get("book_qa", 0) >= 9
    ids = {i["item_id"] for i in payload["items"]}
    assert "dogfood-book-shannon-communication" in ids
    assert "dogfood-book-turing-computable-numbers" in ids
    assert "dogfood-book-lovelace-analytical-engine" in ids
    assert "dogfood-book-godel-incompleteness" in ids
    assert "dogfood-book-fourier-heat" in ids
    assert "dogfood-wrestle-research-this-twins" in ids
    assert "dogfood-wrestle-spawn-merge-path" in ids
    assert "dogfood-wrestle-collective-multi-spawn-merge" in ids
    assert "dogfood-wrestle-pub-quick-call-matrix" in ids
    assert "dogfood-wrestle-budget-foresight-pub-refs" in ids
    assert "dogfood-wrestle-purchase-seamless-port" in ids
    assert "dogfood-wrestle-domain-aware-twin-search" in ids
    assert "dogfood-wrestle-moil-deposit-twin-honesty" in ids
    assert "dogfood-wrestle-pub-ref-foresight-chrome" in ids
    assert "dogfood-wrestle-competitive-dr-scorecard" in ids
    assert "dogfood-wrestle-citation-chain" in ids
    assert "dogfood-wrestle-citation-chain-hops" in ids
    assert "dogfood-wrestle-domain-aware-stem-expanded" in ids
    assert "dogfood-wrestle-evidence-write-multi-hop" in ids
    assert "dogfood-wrestle-twin-promote-depth-graph" in ids
    assert "dogfood-wrestle-twin-promote-write-depth-graph" in ids
    assert "dogfood-wrestle-collective-unit-twin-seed" in ids
    assert "dogfood-wrestle-write-seed-has-body" in ids
    assert "dogfood-wrestle-seamless-write-path" in ids
    assert "dogfood-wrestle-intelligent-search-context-write" in ids
    assert "dogfood-wrestle-written-analysis-open-write-source" in ids
    assert "dogfood-wrestle-continue-as-unit-path" in ids
    assert "dogfood-wrestle-select-open-path" in ids
    assert "dogfood-wrestle-unit-restore-path" in ids
    assert "dogfood-wrestle-select-recent-path" in ids
    assert "dogfood-wrestle-research-workstation-spine" in ids
    assert "dogfood-wrestle-highlight-deep-research-path" in ids
    assert "dogfood-wrestle-talk-to-book-twins" in ids
    assert "dogfood-wrestle-meta-reading-twins" in ids
    assert "dogfood-wrestle-talk-to-book-collective" in ids
    assert "dogfood-wrestle-meta-reading-collective" in ids
    assert "dogfood-wrestle-marketplace-host-collective" in ids
    assert "dogfood-book-nicomachean-ethics" in ids
    html = (payload.get("html") or "").lower()
    assert (
        "v35" in html or "nicomachean" in html or "v34" in html or "talk-to-book-collective" in html or "v33" in html or "twin-promote-write-depth-graph" in html or "v32" in html or "twin-promote-depth-graph" in html or "v31" in html or "evidence-write-multi-hop" in html or "v30" in html or "domain-aware-stem-expanded" in html or "v29" in html or "citation-chain-hops" in html or "multi-hop" in html or "v28" in html or "citation-chain" in html or "scorecard" in html or "v27" in html or "foresight-chrome" in html or "v26" in html or "moil" in html or "collective-unit-twin" in html or "v25" in html or "domain-aware" in html or "v24" in html or "budget-foresight" in html or "purchase" in html or "v23" in html or "quick-call" in html or "publication" in html
        or "v22" in html or "spawn-merge" in html or "multi-spawn" in html
        or "v21" in html or "fourier" in html or "research-this" in html
        or "v20" in html or "talk-to-book" in html or "meta-reading" in html or "v19" in html or "godel" in html or "v18" in html or "highlight" in html or "v17" in html or "select-recent" in html or "workstation" in html
        or "v16" in html or "select-open" in html or "unit-restore" in html
        or "v15" in html or "written-analysis" in html or "v14" in html
        or "seamless" in html
        or "has-body" in html
        or "lovelace" in html
        or "turing" in html
        or "shannon" in html
    )

def test_register_does_not_auto_activate():
    reg = SuiteRegistry()
    register_suite(default_core_suite(), registry=reg, make_active=True)
    before = active_suite(registry=reg).suite_version
    dog = register_competitive_dogfood_suite(registry=reg, make_active=False)
    assert dog.suite_version == COMPETITIVE_DOGFOOD_VERSION
    assert active_suite(registry=reg).suite_version == before
    assert before != COMPETITIVE_DOGFOOD_VERSION


def test_run_dogfood_offline():
    reg = SuiteRegistry()
    suite = register_competitive_dogfood_suite(registry=reg, make_active=True)
    store = InMemoryBenchStore()
    result = run_suite(
        model_id="stub",
        week_id="2026-W28",
        store=store,
        registry=reg,
        provider_fn=keyword_stub_provider("stub", quality=0.9),
    )
    assert result.mean_score >= 0.0
    assert len(result.scores) == len(suite.items)
    assert result.suite_version == COMPETITIVE_DOGFOOD_VERSION


def test_payload_and_api_html():
    payload = dogfood_fixture_payload(include_html=True)
    assert payload["auto_promoted"] is False
    assert payload["view_format"] == "html"
    # Residual (zj/adn/aeu/afo/ags): v21 STEM + Fourier + ResearchThis twins dogfood.
    assert payload["suite_version"] == COMPETITIVE_DOGFOOD_VERSION
    assert payload["suite_version"] == "suite-competitive-dogfood-v36"
    assert payload["item_count"] >= 53
    assert payload["settings_panel"] == "antiek_bench_dogfood_fixtures"
    assert payload["source"] == "antiek_bench.dogfood_fixtures"
    assert payload["html"]
    assert "application/pdf" not in payload["html"].lower()
    # Residual (st/tf/tv/tz/ud/us/ve/vl/wd/wl/xi/adn/aeu/afo/ags/agw): fixtures visible in HTML listing.
    assert "dogfood-wrestle-write-seed" in payload["html"]
    assert "dogfood-wrestle-write-seed-has-body" in payload["html"]
    assert "dogfood-wrestle-seamless-write-path" in payload["html"]
    assert "dogfood-wrestle-intelligent-search-context-write" in payload["html"]
    assert "dogfood-wrestle-written-analysis-open-write-source" in payload["html"]
    assert "dogfood-wrestle-continue-as-unit-path" in payload["html"]
    assert "dogfood-wrestle-select-open-path" in payload["html"]
    assert "dogfood-wrestle-unit-restore-path" in payload["html"]
    assert "dogfood-wrestle-select-recent-path" in payload["html"]
    assert "dogfood-wrestle-research-workstation-spine" in payload["html"]
    assert "dogfood-wrestle-highlight-deep-research-path" in payload["html"]
    assert "dogfood-wrestle-talk-to-book-twins" in payload["html"]
    assert "dogfood-wrestle-meta-reading-twins" in payload["html"]
    assert "dogfood-wrestle-research-this-twins" in payload["html"]
    assert "dogfood-wrestle-spawn-merge-path" in payload["html"]
    assert "dogfood-wrestle-collective-multi-spawn-merge" in payload["html"]
    assert "dogfood-wrestle-pub-quick-call-matrix" in payload["html"]
    assert "dogfood-wrestle-budget-foresight-pub-refs" in payload["html"]
    assert "dogfood-wrestle-purchase-seamless-port" in payload["html"]
    assert "twin_seed" in payload["html"]
    assert "dogfood-book-faraday-induction" in payload["html"]
    assert "faraday" in payload["html"].lower()
    assert "dogfood-wrestle-collective-unit-write-seed" in payload["html"]
    assert "collective_unit_prompt" in payload["html"]
    assert "dogfood-book-boole-laws-of-thought" in payload["html"]
    assert "boole" in payload["html"].lower()
    assert "dogfood-book-heaviside-em" in payload["html"]
    assert "heaviside" in payload["html"].lower()
    assert "dogfood-wrestle-citation-trust-ungrounded" in payload["html"]
    assert "ungrounded" in payload["html"].lower()
    assert "dogfood-wrestle-twin-cross-asset-merge-write-seed" in payload["html"]
    assert "twin_cross_asset_merge" in payload["html"]
    assert "dogfood-wrestle-collective-written-analysis-write-seed" in payload["html"]
    assert "collective_written_analysis" in payload["html"]
    assert "dogfood-book-shannon-communication" in payload["html"]
    assert "shannon" in payload["html"].lower()
    assert "dogfood-book-turing-computable-numbers" in payload["html"]
    assert "turing" in payload["html"].lower()
    assert "dogfood-book-lovelace-analytical-engine" in payload["html"]
    assert "dogfood-book-godel-incompleteness" in payload["html"]
    assert "dogfood-book-fourier-heat" in payload["html"]
    assert "fourier" in payload["html"].lower()
    assert "lovelace" in payload["html"].lower()
    assert "dogfood-wrestle-write-seed-has-body" in payload["html"]
    # Residual (ais/air): multi-hop citation chain hops dogfood.
    assert "dogfood-wrestle-citation-chain-hops" in payload["html"]
    assert "dogfood-wrestle-citation-chain" in payload["html"]
    # Residual (ajb/aiy): expanded domain-aware STEM twin search.
    assert "dogfood-wrestle-domain-aware-stem-expanded" in payload["html"]
    assert "dogfood-wrestle-evidence-write-multi-hop" in payload["html"]
    assert "dogfood-wrestle-twin-promote-depth-graph" in payload["html"]
    assert "dogfood-wrestle-twin-promote-write-depth-graph" in payload["html"]

    app = FastAPI()
    register_settings_budget_routes(app)
    client = TestClient(app)
    r1 = client.get("/settings/antiek-bench/dogfood-fixtures?include_html=true")
    r2 = client.get("/settings/antiek-bench/dogfood-fixtures?include_html=true")
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["suite_version"] == r2.json()["suite_version"]
    assert r1.json()["suite_version"] == "suite-competitive-dogfood-v36"
    assert r1.json()["item_count"] == r2.json()["item_count"]
    assert r1.json()["item_count"] >= 49
    assert r1.json()["by_task_class"]["book_qa"] == 11
    assert r1.json()["by_task_class"]["wrestle"] == 41
