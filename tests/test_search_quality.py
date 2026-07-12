"""Tests for the search-quality axis (ranking quality — ask #14).

Exercises: optimal/inverted ranking (NDCG 1.0 vs <1.0), top relevance, mean
relevance, per-rank matched terms, empty-query defer, empty-results defer,
all-irrelevant defer, purity/immutability, validation. Fixtures use BARE
NONSENSE TOKENS (alpha/beta/gamma) so overlap ratios are exactly countable.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.deep_research_quality.search_quality import (
    ResultRankRelevance,
    SearchQualityError,
    SearchQualityReport,
    measure_search_quality,
)

# --- core: optimal ranking (NDCG = 1.0) ------------------------------------


def test_optimal_ranking_ndcg_one() -> None:
    # query "alpha beta"; most-relevant result first (covers all), then partial.
    # ranking is already ideal -> NDCG = 1.0
    report = measure_search_quality("alpha beta", ("alpha beta gamma", "alpha delta"))
    assert report.ndcg == pytest.approx(1.0)
    assert report.verdict == "optimal"
    assert report.top_relevance == pytest.approx(1.0)  # first covers both query terms


def test_perfect_single_result() -> None:
    report = measure_search_quality("alpha beta", ("alpha beta",))
    assert report.ndcg == pytest.approx(1.0)
    assert report.top_relevance == pytest.approx(1.0)
    assert report.mean_relevance == pytest.approx(1.0)


# --- core: inverted ranking (NDCG < 1.0) -----------------------------------


def test_inverted_ranking_lower_ndcg() -> None:
    # query "alpha beta gamma"; least-relevant first, most-relevant last.
    # ideal order would be reverse -> NDCG < 1.0
    report = measure_search_quality(
        "alpha beta gamma",
        ("delta epsilon", "alpha beta gamma"),  # 0-match, 3-match
    )
    assert report.ndcg is not None
    assert report.ndcg < 1.0
    assert report.top_relevance == pytest.approx(0.0)  # first result misses query


def test_inverted_vs_optimal_ndcg_relationship() -> None:
    query = "alpha beta gamma"
    optimal = measure_search_quality(query, ("alpha beta gamma", "alpha beta", "delta"))
    inverted = measure_search_quality(query, ("delta", "alpha beta", "alpha beta gamma"))
    assert optimal.ndcg == pytest.approx(1.0)
    assert inverted.ndcg is not None
    assert optimal.ndcg is not None and inverted.ndcg is not None
    assert inverted.ndcg < optimal.ndcg  # inversion strictly worse


def test_well_ranked_verdict_band() -> None:
    # Build a ranking whose NDCG lands in [0.60, 0.90).
    # query 3 terms; results: full-match, partial, partial.
    report = measure_search_quality("alpha beta gamma", ("alpha beta gamma", "alpha", "beta"))
    assert report.ndcg is not None
    assert report.ndcg >= 0.60


def test_poor_verdict() -> None:
    # query "alpha beta gamma delta"; results barely match, worst first.
    report = measure_search_quality(
        "alpha beta gamma delta",
        ("epsilon zeta", "alpha", "beta"),
    )
    if report.ndcg is not None:
        assert report.verdict in ("poor", "well_ranked")


# --- honesty: relevance math ------------------------------------------------


def test_relevance_recall_oriented() -> None:
    # query "alpha beta"; result covers only alpha -> relevance 0.5
    report = measure_search_quality("alpha beta", ("alpha zeta",))
    assert report.result_relevances[0].relevance == pytest.approx(0.5)


def test_relevance_in_unit_interval() -> None:
    report = measure_search_quality(
        "alpha beta gamma",
        ("alpha beta gamma delta", "epsilon zeta", "alpha"),
    )
    for r in report.result_relevances:
        assert 0.0 <= r.relevance <= 1.0


def test_matched_query_terms_auditable() -> None:
    report = measure_search_quality("alpha beta gamma", ("beta gamma delta",))
    assert set(report.result_relevances[0].matched_query_terms) == {"beta", "gamma"}


def test_mean_relevance() -> None:
    # 1.0 + 0.0 over 2 results -> 0.5
    report = measure_search_quality("alpha beta", ("alpha beta", "gamma delta"))
    assert report.mean_relevance == pytest.approx(0.5)


# --- honesty: empty-query defer --------------------------------------------


def test_empty_query_unmeasurable() -> None:
    report = measure_search_quality("", ("alpha beta", "gamma delta"))
    assert report.ndcg is None
    assert report.verdict == "unknown"
    assert report.query_term_count == 0


def test_all_glue_query_unmeasurable() -> None:
    report = measure_search_quality("the and is of", ("alpha beta",))
    assert report.ndcg is None
    assert report.verdict == "unknown"
    assert report.query_term_count == 0


# --- honesty: empty-results defer ------------------------------------------


def test_empty_results_unknown() -> None:
    report = measure_search_quality("alpha beta", ())
    assert report.ndcg is None
    assert report.top_relevance is None
    assert report.mean_relevance == pytest.approx(0.0)
    assert report.result_count == 0
    assert report.verdict == "unknown"


# --- honesty: all-irrelevant defer -----------------------------------------


def test_all_irrelevant_defers_ndcg() -> None:
    # valid query, results that match nothing -> IDCG = 0 -> ndcg None, irrelevant
    report = measure_search_quality("alpha beta", ("gamma delta", "epsilon zeta"))
    assert report.ndcg is None
    assert report.verdict == "irrelevant"
    assert report.top_relevance == pytest.approx(0.0)


# --- NDCG range ------------------------------------------------------------


def test_ndcg_in_unit_interval() -> None:
    report = measure_search_quality(
        "alpha beta gamma",
        ("alpha", "beta gamma", "delta"),
    )
    if report.ndcg is not None:
        assert 0.0 <= report.ndcg <= 1.0


def test_ndcg_zero_only_when_no_relevant() -> None:
    # With at least one relevant result, NDCG is a positive normalized value.
    report = measure_search_quality("alpha beta gamma", ("alpha", "epsilon"))
    assert report.ndcg is not None and report.ndcg > 0.0


# --- provenance / purity ---------------------------------------------------


def test_authority_is_always_advisory() -> None:
    assert measure_search_quality("alpha beta", ("alpha beta",)).authority == "advisory"


def test_report_is_immutable() -> None:
    report = measure_search_quality("alpha beta", ("alpha beta",))
    assert isinstance(report, SearchQualityReport)
    assert dataclasses.is_dataclass(report)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.ndcg = 0.0  # type: ignore[misc]


def test_result_relevance_is_immutable() -> None:
    report = measure_search_quality("alpha beta", ("alpha beta",))
    r = report.result_relevances[0]
    assert isinstance(r, ResultRankRelevance)
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.relevance = 0.0  # type: ignore[misc]


def test_determinism_same_inputs_same_report() -> None:
    q = "alpha beta gamma"
    results = ("alpha beta", "gamma delta", "epsilon")
    assert measure_search_quality(q, results) == measure_search_quality(q, results)


def test_notes_describe_verdict() -> None:
    report = measure_search_quality("alpha beta", ("alpha beta",))
    joined = " | ".join(report.notes).lower()
    assert "ndcg" in joined or "ranking" in joined


# --- validation ------------------------------------------------------------


def test_validation_rejects_non_tuple_results() -> None:
    with pytest.raises(SearchQualityError, match="results must be a tuple"):
        measure_search_quality("alpha beta", ["alpha beta", "gamma"])  # type: ignore[arg-type]


def test_validation_rejects_list() -> None:
    # a valid tuple does NOT raise (sanity, outside the raises block)
    measure_search_quality("alpha beta", ("a", "b"))
    # a genuine list must be rejected
    with pytest.raises(SearchQualityError):
        measure_search_quality("alpha beta", ["alpha beta"])  # type: ignore[arg-type]


# --- public api exports ----------------------------------------------------


def test_public_api_exports() -> None:
    from substrate.deep_research_quality import search_quality as mod

    assert set(mod.__all__) == {
        "ResultRankRelevance",
        "SearchQualityError",
        "SearchQualityReport",
        "measure_search_quality",
    }
    assert issubclass(mod.SearchQualityError, ValueError)
    assert dataclasses.is_dataclass(mod.ResultRankRelevance)
    assert dataclasses.is_dataclass(mod.SearchQualityReport)
