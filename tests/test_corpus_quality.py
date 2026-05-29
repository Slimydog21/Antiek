"""Tests for the SPR-08 corpus-quality gate (M1), cross-source dedup (M2), and
the unified ingest orchestrator's pure planning core (M3).

The fairness rigor card is exercised directly: for the gate we assert BOTH
that bad text is rejected AND that good text passes — a gate that only ever
fails (or only ever passes) is not a gate. For dedup we assert the central
cross-source merge the precedence rule exists to catch AND that distinct works
are NOT collapsed on a coincidental key. For the orchestrator we assert the
dry-run writes NOTHING (no ingest thunk is ever invoked) while a real run does.
"""

from __future__ import annotations

import pytest

from acquisition.corpus_quality import (
    CandidateRef,
    CheckResultKind,
    DedupKeyKind,
    aggregate_verdicts,
    assess_corpus_quality,
    check_metadata_completeness,
    check_ocr_garbage,
    check_real_word_ratio,
    dedup_candidates,
)

# --------------------------------------------------------------------------
# Fixtures: representative text bodies.
# --------------------------------------------------------------------------

# Clean prose, comfortably above every threshold (28 tokens, all real words).
GOOD_PROSE = (
    "The quality of the corpus depends on careful selection of sources and "
    "rigorous evaluation of each candidate document before it enters the "
    "substrate for retrieval and synthesis tasks."
)

# Vowel-free letter runs: every token is alphabetic (so the OCR-garbage
# alpha-ratio check is happy) but NONE is a real word (no vowels) — isolates
# the real-word-ratio check.
VOWELLESS_RUNS = " ".join(
    ["zxcvb", "ttttt", "qwrtp", "bcdfg", "hjklm", "npqrs", "xkcd", "vwxz",
     "brrr", "tttt", "zzzz", "qrst", "wxyz", "bcdf", "ghjk", "lmnp", "vwxz",
     "bcfg", "hjkl", "mnpq", "rstv", "wxzb"]
)

# Single-char speckle: dominated by 1-char tokens → trips the single-char
# share sub-signal of the OCR-garbage check.
SPECKLE = "l " * 22 + "rn cl"

# Symbol/digit noise: low alphabetic-char ratio → trips the alpha-ratio
# sub-signal of the OCR-garbage check.
SYMBOL_NOISE = " ".join(
    ["##", "@@", "12", "%%", "3.4", "<<", ">>", "||", "~~", "^^", "&&", "99",
     "00", "@@", "##", "%%", "$$", "^^", "**", "((", "))", "--", "++", "=="]
)

# Below the token floor — too little text to judge either text check.
TOO_SHORT = "short text here"


# --------------------------------------------------------------------------
# M1 — individual checks.
# --------------------------------------------------------------------------


def test_real_word_ratio_passes_clean_prose() -> None:
    r = check_real_word_ratio(GOOD_PROSE)
    assert r.kind is CheckResultKind.PASS
    assert r.score >= 0.60


def test_real_word_ratio_fails_vowelless_runs() -> None:
    r = check_real_word_ratio(VOWELLESS_RUNS)
    assert r.kind is CheckResultKind.FAIL
    assert r.score < 0.60


def test_real_word_ratio_fails_below_token_floor() -> None:
    r = check_real_word_ratio(TOO_SHORT)
    assert r.kind is CheckResultKind.FAIL
    assert "token" in " ".join(r.reasons)


def test_ocr_garbage_passes_clean_prose() -> None:
    assert check_ocr_garbage(GOOD_PROSE).kind is CheckResultKind.PASS


def test_ocr_garbage_fails_single_char_speckle() -> None:
    r = check_ocr_garbage(SPECKLE)
    assert r.kind is CheckResultKind.FAIL
    assert any("single-char" in reason for reason in r.reasons)


def test_ocr_garbage_fails_symbol_noise() -> None:
    r = check_ocr_garbage(SYMBOL_NOISE)
    assert r.kind is CheckResultKind.FAIL
    assert any("alphabetic-char ratio" in reason for reason in r.reasons)


def test_metadata_completeness_passes_full_record() -> None:
    r = check_metadata_completeness(
        title="On the Origin of Species", author="Charles Darwin",
        source_id="gutenberg:1228",
    )
    assert r.kind is CheckResultKind.PASS


def test_metadata_completeness_fails_missing_title() -> None:
    r = check_metadata_completeness(
        title="  ", author="Someone", source_id="x:1",
    )
    assert r.kind is CheckResultKind.FAIL
    assert any("title" in reason for reason in r.reasons)


def test_metadata_completeness_fails_missing_author_without_reason() -> None:
    r = check_metadata_completeness(
        title="A Title", author=None, source_id="x:1",
    )
    assert r.kind is CheckResultKind.FAIL
    assert any("author" in reason for reason in r.reasons)


def test_metadata_completeness_allows_null_author_with_reason() -> None:
    r = check_metadata_completeness(
        title="Beowulf", author=None, source_id="gutenberg:16328",
        allow_null_author_reason="anonymous public-domain work",
    )
    assert r.kind is CheckResultKind.PASS
    assert any("allowed" in reason for reason in r.reasons)


def test_metadata_completeness_fails_missing_source_id() -> None:
    r = check_metadata_completeness(
        title="A Title", author="An Author", source_id=None,
    )
    assert r.kind is CheckResultKind.FAIL
    assert any("source identifier" in reason for reason in r.reasons)


# --------------------------------------------------------------------------
# M1 — composed verdict (the FAIRNESS card: bad fails AND good passes).
# --------------------------------------------------------------------------


def test_assess_good_document_passes() -> None:
    v = assess_corpus_quality(
        GOOD_PROSE, title="Corpus Notes", author="An Author",
        source_id="src:1",
    )
    assert v.passed is True
    assert v.body_assessed is True
    assert v.rejection_reason is None
    assert v.failed_checks == ()


def test_assess_garbled_document_is_rejected() -> None:
    v = assess_corpus_quality(
        SYMBOL_NOISE, title="Scan", author="An Author", source_id="src:2",
    )
    assert v.passed is False
    assert v.body_assessed is True
    assert v.rejection_reason  # non-empty human summary
    assert any(c.check_name == "ocr_garbage" for c in v.failed_checks)


def test_assess_good_body_but_missing_metadata_is_rejected() -> None:
    # Good body, but no title → the metadata check must still bite.
    v = assess_corpus_quality(
        GOOD_PROSE, title=None, author="An Author", source_id="src:3",
    )
    assert v.passed is False
    assert any(c.check_name == "metadata_completeness" for c in v.failed_checks)


def test_assess_metadata_only_skips_body_checks() -> None:
    # assess_body=False: a born-digital source whose body is fetched only at
    # ingest must NOT be rejected for "too little text" on its title alone.
    v = assess_corpus_quality(
        "", title="A Real Paper Title", author=None, source_id="10.1/x",
        allow_null_author_reason="open-access record exposes no author",
        assess_body=False,
    )
    assert v.passed is True
    assert v.body_assessed is False
    # Only the metadata check ran.
    assert [c.check_name for c in v.checks] == ["metadata_completeness"]


def test_assess_metadata_only_still_enforces_metadata() -> None:
    v = assess_corpus_quality(
        "", title=None, author=None, source_id=None, assess_body=False,
    )
    assert v.passed is False
    assert v.body_assessed is False


# --------------------------------------------------------------------------
# M1 — aggregate rejection rate (the HONESTY card).
# --------------------------------------------------------------------------


def test_aggregate_reports_rejection_rate() -> None:
    good = assess_corpus_quality(
        GOOD_PROSE, title="T", author="A", source_id="s",
    )
    bad = assess_corpus_quality(
        SYMBOL_NOISE, title="T", author="A", source_id="s",
    )
    report = aggregate_verdicts([good, bad, bad])
    assert report.total == 3
    assert report.passed == 1
    assert report.rejected == 2
    assert report.rejection_rate == pytest.approx(2 / 3)
    assert len(report.rejection_reasons) == 2
    # The rate is surfaced in the rendered run report, not hidden.
    assert "66.7% rejection rate" in report.render()


def test_aggregate_empty_run_is_zero_rate() -> None:
    report = aggregate_verdicts([])
    assert report.total == 0
    assert report.rejection_rate == 0.0


# --------------------------------------------------------------------------
# M2 — cross-source dedup.
# --------------------------------------------------------------------------


def test_dedup_collapses_identical_doi() -> None:
    a = CandidateRef(ref_id="a", doi="10.1/X", title="Paper", author="Sax")
    b = CandidateRef(ref_id="b", doi="10.1/x", title="Paper", author="Sax")
    res = dedup_candidates([a, b])
    assert len(res.kept) == 1
    assert res.kept[0].ref_id == "a"  # first seen is canonical
    assert len(res.dropped) == 1
    assert res.dropped[0].key_kind is DedupKeyKind.DOI


def test_dedup_does_not_merge_distinct_dois_on_shared_title() -> None:
    # Two genuinely different papers that happen to share a title must NOT be
    # collapsed: the highest SHARED key is DOI, and the DOIs differ.
    a = CandidateRef(ref_id="a", doi="10.1/AAA", title="Methods", author="X")
    b = CandidateRef(ref_id="b", doi="10.1/BBB", title="Methods", author="X")
    res = dedup_candidates([a, b])
    assert len(res.kept) == 2
    assert res.dropped == ()


def test_dedup_cross_source_arxiv_and_oa_merge_on_title_author() -> None:
    # THE central case the precedence rule exists to catch: the same paper
    # found on arXiv (arxiv_id, no DOI) and via an OA aggregator (DOI, no
    # arxiv_id). Neither shares the other's high key, so the highest key BOTH
    # possess is title+author — and they must collapse.
    arxiv = CandidateRef(
        ref_id="arxiv:2401.001", arxiv_id="2401.001",
        title="Scaling Laws for Corpora", author="Ada Lovelace",
    )
    oa = CandidateRef(
        ref_id="oa:10.1/z", doi="10.1/z",
        title="Scaling Laws for Corpora", author="Ada Lovelace",
    )
    res = dedup_candidates([arxiv, oa])
    assert len(res.kept) == 1
    assert res.kept[0].ref_id == "arxiv:2401.001"
    assert len(res.dropped) == 1
    assert res.dropped[0].key_kind is DedupKeyKind.TITLE_AUTHOR


def test_dedup_cross_source_merge_is_order_insensitive() -> None:
    arxiv = CandidateRef(
        ref_id="arxiv:2401.001", arxiv_id="2401.001",
        title="Scaling Laws for Corpora", author="Ada Lovelace",
    )
    oa = CandidateRef(
        ref_id="oa:10.1/z", doi="10.1/z",
        title="Scaling Laws for Corpora", author="Ada Lovelace",
    )
    fwd = dedup_candidates([arxiv, oa])
    rev = dedup_candidates([oa, arxiv])
    # Same number kept either way; the canonical is just whichever came first.
    assert len(fwd.kept) == len(rev.kept) == 1
    assert rev.kept[0].ref_id == "oa:10.1/z"


def test_dedup_different_titles_are_kept_apart() -> None:
    a = CandidateRef(ref_id="a", arxiv_id="1", title="Alpha", author="Z")
    b = CandidateRef(ref_id="b", doi="10.1/q", title="Beta", author="Z")
    res = dedup_candidates([a, b])
    assert len(res.kept) == 2


def test_dedup_no_shared_key_cannot_merge() -> None:
    # One carries only an arxiv_id, the other only a source_id, and neither
    # has a usable title → no shared key at any level → both kept.
    a = CandidateRef(ref_id="a", arxiv_id="2401.5")
    b = CandidateRef(ref_id="b", source_id="gutenberg:1")
    res = dedup_candidates([a, b])
    assert len(res.kept) == 2


def test_dedup_records_drops_by_key_and_renders() -> None:
    a = CandidateRef(ref_id="a", doi="10.1/x", title="P", author="Q")
    b = CandidateRef(ref_id="b", doi="10.1/x", title="P", author="Q")
    res = dedup_candidates([a, b])
    assert res.drops_by_key.get(DedupKeyKind.DOI) == 1
    rendered = res.render()
    assert "1 kept" in rendered and "1 dropped" in rendered


# --------------------------------------------------------------------------
# M3 — orchestrator pure core: plan + execute (dry-run writes NOTHING).
# --------------------------------------------------------------------------


def _make_planned(ref, *, text, assess_body, sink, source="test", reason=None):
    """Build a PlannedCandidate whose ingest thunk records that it ran into
    ``sink`` (so a test can prove the dry-run never calls it)."""
    from tools.run_corpus_ingest import PlannedCandidate

    def _ingest(db_path: str) -> str:
        sink.append((ref.ref_id, db_path))
        return f"wrote {ref.ref_id}"

    return PlannedCandidate(
        ref=ref, source=source, assessable_text=text,
        assess_body=assess_body, ingest=_ingest,
        allow_null_author_reason=reason,
    )


def test_plan_gates_and_dedups() -> None:
    from tools.run_corpus_ingest import plan_corpus

    sink: list = []
    good = _make_planned(
        CandidateRef(ref_id="g", doi="10.1/good", title="Good", author="A"),
        text=GOOD_PROSE, assess_body=True, sink=sink,
    )
    bad = _make_planned(
        CandidateRef(ref_id="bad", doi="10.1/bad", title="Bad", author="A"),
        text=SYMBOL_NOISE, assess_body=True, sink=sink,
    )
    dup = _make_planned(  # duplicate of good on DOI → dropped before gating
        CandidateRef(ref_id="g2", doi="10.1/good", title="Good", author="A"),
        text=GOOD_PROSE, assess_body=True, sink=sink,
    )
    plan = plan_corpus([good, bad, dup])

    assert len(plan.deduped.kept) == 2  # dup collapsed
    assert {pc.ref.ref_id for pc in plan.to_ingest} == {"g"}
    assert len(plan.quality_rejected) == 1
    assert plan.quality_rejected[0][0].ref.ref_id == "bad"
    # rejection rate is over the GATED (post-dedup) set: 1 of 2.
    assert plan.quality_report.total == 2
    assert plan.quality_report.rejected == 1
    # Planning is pure — no thunk fired.
    assert sink == []


def test_execute_dry_run_writes_nothing() -> None:
    from tools.run_corpus_ingest import execute_plan, plan_corpus

    sink: list = []
    good = _make_planned(
        CandidateRef(ref_id="g", doi="10.1/good", title="Good", author="A"),
        text=GOOD_PROSE, assess_body=True, sink=sink,
    )
    plan = plan_corpus([good])
    report = execute_plan(plan, db_path="/tmp/should-not-be-touched", dry_run=True)

    assert report.dry_run is True
    assert report.ingested == 0
    assert report.failed == 0
    assert report.planned == 1
    # The cardinal dry-run invariant: NO ingest thunk was ever called.
    assert sink == []


def test_execute_real_run_calls_thunks() -> None:
    from tools.run_corpus_ingest import execute_plan, plan_corpus

    sink: list = []
    good = _make_planned(
        CandidateRef(ref_id="g", doi="10.1/good", title="Good", author="A"),
        text=GOOD_PROSE, assess_body=True, sink=sink,
    )
    plan = plan_corpus([good])
    report = execute_plan(plan, db_path="/tmp/local.duckdb", dry_run=False)

    assert report.dry_run is False
    assert report.ingested == 1
    assert report.failed == 0
    assert sink == [("g", "/tmp/local.duckdb")]


def test_execute_isolates_per_item_failure() -> None:
    from tools.run_corpus_ingest import PlannedCandidate, execute_plan, plan_corpus

    sink: list = []
    ok = _make_planned(
        CandidateRef(ref_id="ok", doi="10.1/ok", title="Ok", author="A"),
        text=GOOD_PROSE, assess_body=True, sink=sink,
    )

    def _boom(db_path: str) -> str:
        raise RuntimeError("simulated ingest failure")

    boomer = PlannedCandidate(
        ref=CandidateRef(ref_id="boom", doi="10.1/boom", title="Boom", author="A"),
        source="test", assessable_text=GOOD_PROSE, assess_body=True,
        ingest=_boom,
    )
    plan = plan_corpus([ok, boomer])
    report = execute_plan(plan, db_path="/tmp/local.duckdb", dry_run=False)

    assert report.planned == 2
    assert report.ingested == 1  # the good one still landed
    assert report.failed == 1    # the failure was isolated, not fatal


def test_metadata_only_candidate_survives_plan() -> None:
    # An OA-style candidate with no pre-ingest body (assess_body=False) must
    # plan through to ingest on metadata alone, flagged body-not-assessed.
    from tools.run_corpus_ingest import plan_corpus

    sink: list = []
    oa = _make_planned(
        CandidateRef(ref_id="oa", doi="10.1/oa", title="A Paper", author=None),
        text="", assess_body=False, sink=sink, source="open_access",
        reason="open-access record exposes no author",
    )
    plan = plan_corpus([oa])
    assert len(plan.to_ingest) == 1
    assert plan.to_ingest[0].ref.ref_id == "oa"
    assert "body not assessed" in plan.render()
