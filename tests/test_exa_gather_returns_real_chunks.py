"""Real-Exa gather rigor gate (CK-2) — proves the cascade agent retrieves
ACTUAL content, not roleplay retrieval.

This encodes the cursor-for-knowledge CK-2 rigor gate ("a test that gather
returns >=1 real chunk"). It is OPT-IN and skipped in CI: when ``EXA_API_KEY``
is absent the whole module skips, so the gate never spends money or hits the
network in CI. Run by an operator who has the key, it calls the real Exa
``discover`` on an ISOLATED scratch graph (``tmp_path``) and asserts the
cascade gather returns at least one real, URL-bearing proposal — the agent
mode is genuinely grounded. The real ``research_graph.duckdb`` is never
touched (``db_path`` is always under ``tmp_path``).
"""

from __future__ import annotations

import os

import pytest

if not os.environ.get("EXA_API_KEY"):
    pytest.skip(
        "EXA_API_KEY not set; real-Exa gather test is opt-in (CI never spends)",
        allow_module_level=True,
    )

from acquisition.search.exa.adapter import discover


def test_discover_returns_real_chunks(tmp_path):
    """Real Exa discover returns >=1 URL-bearing proposal on a scratch graph."""
    proposals = discover(
        query="retrieval-augmented generation",
        investigation_id="ck2-rigor-smoke",
        num_results=3,
        daily_budget_usd=0.20,
        events_dir=str(tmp_path / "events"),
        db_path=str(tmp_path / "scratch-graph.duckdb"),
    )
    assert len(proposals) >= 1, "gather returned no proposals — agent mode is not grounded"
    assert proposals[0].url, "first proposal has no URL — not a real chunk"
