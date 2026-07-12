"""Tests for substrate/deep_research_quality/citation_grounding.py — defensibility."""

from __future__ import annotations

import pytest

from substrate.deep_research_quality.citation_grounding import (
    CitationGroundingError,
    GroundingReport,
    ResolvedCitation,
    SourceRecord,
    verify_citation_grounding,
)


def _src(sid, title="t", url=None):
    return SourceRecord(source_id=sid, title=title, url=url)


# ---------------------------------------------------------------------------
# grounded — the happy path
# ---------------------------------------------------------------------------


def test_grounded_when_all_citations_resolve_and_assertions_cited():
    text = "Transformers scale quadratically with sequence length [src-a]. The attention mechanism enables this [src-b]."
    report = verify_citation_grounding(
        output_text=text, sources=[_src("a"), _src("b")]
    )
    assert report.verdict == "grounded"
    assert report.has_fabricated is False
    assert report.has_unsupported is False
    assert report.resolved_count == 2


def test_grounded_no_citations_no_assertions():
    report = verify_citation_grounding(
        output_text="## Section heading\n\n- bullet point\n\nshort.",
        sources=[],
    )
    assert report.verdict == "grounded"
    assert report.total_citation_tokens == 0


# ---------------------------------------------------------------------------
# fabricated citations are FATAL — no partial credit
# ---------------------------------------------------------------------------


def test_fabricated_citation_is_ungrounded():
    text = "This is a real claim that is well supported [src-real]. But this cites a fake source [src-fake]."
    report = verify_citation_grounding(
        output_text=text, sources=[_src("real")]
    )
    assert report.verdict == "ungrounded"
    assert report.has_fabricated is True
    assert len(report.fabricated_citations) == 1
    assert report.fabricated_citations[0].source_id == "fake"


def test_fabricated_citation_lists_occurrences():
    text = "Claim one [src-fake]. Claim two [src-fake]. Claim three [src-fake]."
    report = verify_citation_grounding(output_text=text, sources=[])
    assert report.verdict == "ungrounded"
    assert report.fabricated_citations[0].occurrences == 3


def test_fabricated_overrides_unsupported():
    # both fabricated AND unsupported — fabricated is fatal (verdict = ungrounded)
    text = "This uncited assertion has no source. And this cites a fake [src-fake]."
    report = verify_citation_grounding(output_text=text, sources=[])
    assert report.verdict == "ungrounded"
    assert report.has_unsupported is True  # still detected
    assert report.has_fabricated is True


# ---------------------------------------------------------------------------
# unsupported assertions — flagged, not fatal
# ---------------------------------------------------------------------------


def test_unsupported_assertion_partial_grounded():
    text = (
        "This cited claim is well supported [src-a]. "
        "This is an uncited factual assertion that the model shows remarkable improvement."
    )
    report = verify_citation_grounding(output_text=text, sources=[_src("a")])
    assert report.verdict == "partially_grounded"
    assert report.has_fabricated is False
    assert report.has_unsupported is True
    assert len(report.unsupported_assertions) >= 1


def test_questions_not_flagged_as_assertions():
    text = "What is the mechanism? [src-a]. How does it scale? [src-b]."
    report = verify_citation_grounding(output_text=text, sources=[_src("a"), _src("b")])
    # questions are not assertions — no unsupported
    assert report.has_unsupported is False


def test_short_fragments_not_flagged():
    text = "Yes. [src-a]. No. [src-b]. OK. [src-a]."
    report = verify_citation_grounding(output_text=text, sources=[_src("a"), _src("b")])
    assert report.has_unsupported is False


# ---------------------------------------------------------------------------
# resolved citations carry source metadata
# ---------------------------------------------------------------------------


def test_resolved_citation_carries_source():
    text = "Claim [src-a] and again [src-a]."
    report = verify_citation_grounding(
        output_text=text, sources=[_src("a", title="Attention Paper", url="https://x")]
    )
    assert len(report.resolved_citations) == 1
    rc = report.resolved_citations[0]
    assert isinstance(rc, ResolvedCitation)
    assert rc.source_id == "a"
    assert rc.occurrences == 2
    assert rc.source.title == "Attention Paper"
    assert rc.source.url == "https://x"


# ---------------------------------------------------------------------------
# source registry is explicit — unregistered = unresolved
# ---------------------------------------------------------------------------


def test_unregistered_source_is_fabricated():
    # source "exists" in the caller's mind but wasn't registered → unresolved
    text = "Claim [src-unregistered]."
    report = verify_citation_grounding(output_text=text, sources=[])
    assert report.verdict == "ungrounded"
    assert report.fabricated_citations[0].source_id == "unregistered"


def test_empty_source_id_rejected():
    with pytest.raises(CitationGroundingError):
        verify_citation_grounding(
            output_text="text [src-x]",
            sources=[SourceRecord(source_id="  ")],
        )


def test_empty_output_rejected():
    with pytest.raises(CitationGroundingError):
        verify_citation_grounding(output_text="   ", sources=[])


# ---------------------------------------------------------------------------
# notes honestly declare scope (no accuracy claim)
# ---------------------------------------------------------------------------.


def test_notes_declare_accuracy_out_of_scope():
    report = verify_citation_grounding(
        output_text="Claim [src-a].", sources=[_src("a")]
    )
    assert any("ACCURACY" in n for n in report.notes)
    assert any("LLM-judge" in n for n in report.notes)


# ---------------------------------------------------------------------------
# purity + frozen values
# ---------------------------------------------------------------------------


def test_report_is_frozen_value():
    report = verify_citation_grounding(
        output_text="Claim [src-a].", sources=[_src("a")]
    )
    assert isinstance(report, GroundingReport)
    assert isinstance(report.resolved_citations, tuple)
    assert isinstance(report.unsupported_assertions, tuple)
    assert isinstance(report.notes, tuple)


def test_verify_is_pure_idempotent():
    args = dict(
        output_text="Claim [src-a]. This uncited assertion shows improvement.",
        sources=[_src("a")],
    )
    assert verify_citation_grounding(**args) == verify_citation_grounding(**args)


# ---------------------------------------------------------------------------
# multi-citation sentence
# ---------------------------------------------------------------------------


def test_sentence_with_multiple_citations_supported():
    text = "This claim is supported by multiple sources [src-a] and [src-b]."
    report = verify_citation_grounding(output_text=text, sources=[_src("a"), _src("b")])
    assert report.has_unsupported is False
    assert report.resolved_count == 2
