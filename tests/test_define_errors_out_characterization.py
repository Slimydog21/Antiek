"""Characterization + defined-behavior tests for AOD SPR-03 (define errors out).

Three seams remove the "count < 1 is an error" variant: a request for <= 0
results is a DEFINED empty result, not a ValueError. The <1 guard is the first
statement in each function (before any DB/model use), so these tests need only a
minimal fake model — the normal-input path stays locked by the existing
`test_retrieval_substrate_interface.py` / `test_book_curate.py` suites.

This file was written asserting the CURRENT (raising) behavior first and run
green BEFORE the redesign (the characterization lock); it now asserts the
defined post-redesign behavior.
"""

from __future__ import annotations

from substrate.books.curate import curate_reading_list
from substrate.graph.retrieval_substrate import DuckDbVssSubstrate
from substrate.graph.search import search


class _FakeModel:
    """Minimal EmbeddingModel double. Never reached on the <1 path (the guard
    is first), present only so signatures type-check."""

    dimension = 3

    def encode(self, text: str) -> list[float]:
        return [0.0, 0.0, 0.0]


EMPTY_SEARCH = {"query": "q", "top_k": 0, "results": [], "node_matches": []}


# --------------------------------------------------------------------------- #
# Seam 1 — search() top_k < 1 → defined empty result                          #
# --------------------------------------------------------------------------- #

def test_search_top_k_zero_is_defined_empty() -> None:
    assert search(None, "q", model=_FakeModel(), top_k=0) == EMPTY_SEARCH


def test_search_negative_top_k_is_defined_empty() -> None:
    result = search(None, "q", model=_FakeModel(), top_k=-5)
    assert result["results"] == [] and result["node_matches"] == []


# --------------------------------------------------------------------------- #
# Seam 2 — DuckDbVssSubstrate._vss_query() top_k < 1 → same empty (vss path)   #
# --------------------------------------------------------------------------- #

def test_vss_query_top_k_zero_matches_search_empty() -> None:
    sub = DuckDbVssSubstrate(None, model=_FakeModel(), vss_active=True)
    result = sub._vss_query(
        "q", top_k=0, source_tier_max=None, document_ids=None,
        policy_tag="attribution_eligible",
    )
    # identical defined empty to search()'s — the two backends must not diverge
    assert result == {"query": "q", "top_k": 0, "results": [], "node_matches": []}


# --------------------------------------------------------------------------- #
# Seam 3 — curate_reading_list() limit < 1 → defined empty list               #
# --------------------------------------------------------------------------- #

def test_curate_limit_zero_is_defined_empty() -> None:
    # non-empty prompt so we pass the prompt guard and reach the limit guard
    assert curate_reading_list(None, "some prompt", model=_FakeModel(), limit=0) == []


def test_curate_negative_limit_is_defined_empty() -> None:
    assert curate_reading_list(None, "some prompt", model=_FakeModel(), limit=-3) == []


# --------------------------------------------------------------------------- #
# Narrowed-not-suppressed: the model-contract error still raises (must-stay)   #
# --------------------------------------------------------------------------- #

def test_dim_mismatch_still_raises_on_valid_top_k() -> None:
    import pytest

    class _WrongDimModel:
        dimension = 5

        def encode(self, text: str) -> list[float]:
            return [0.0, 0.0, 0.0]  # 3 != 5

    # a real (>=1) request with a broken model still raises — we narrowed the
    # error surface deliberately, we did not blanket-suppress it. (con=None is
    # never reached: the dim check precedes any DB use.)
    with pytest.raises(ValueError, match="dims"):
        search(None, "q", model=_WrongDimModel(), top_k=3)
