"""Tests for substrate/deep_research_quality/citation_grounding.py — defensibility."""

from __future__ import annotations

import pytest

from substrate.deep_research_quality.citation_grounding import (
    CitationGroundingError,
    FabricatedCitation,
    GroundingReport,
    ResolvedCitation,
    SourceRecord,
    UnsupportedAssertion,
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


@pytest.mark.parametrize("source_id", [" a", "a ", "a.b", "[a]"])
def test_noncanonical_source_id_rejected(source_id):
    with pytest.raises(CitationGroundingError):
        SourceRecord(source_id=source_id)


def test_duplicate_source_id_rejected_instead_of_overwriting():
    with pytest.raises(CitationGroundingError, match="duplicate"):
        verify_citation_grounding(
            output_text="Claim [src-a].",
            sources=[_src("a", title="first"), _src("a", title="second")],
        )


@pytest.mark.parametrize(
    "token",
    [
        "[ src-a]",
        "[SRC-a]",
        "[src-a ]",
        "[src-a",
        "[[src-a]]",
        "[[src-a].",
        "[src-a]]",
        "[src-a]suffix",
        "[src-a]-suffix",
    ],
)
def test_malformed_citation_like_token_rejected(token):
    with pytest.raises(CitationGroundingError, match="malformed citation"):
        verify_citation_grounding(
            output_text=f"This is an assertion with a malformed citation {token}.",
            sources=[_src("a")],
        )


def test_overlong_citation_id_is_rejected_at_parse_boundary():
    token = f"[src-{'a' * 129}]"
    with pytest.raises(CitationGroundingError, match="malformed citation"):
        verify_citation_grounding(
            output_text=f"This is an assertion with an overlong citation {token}.",
            sources=[],
        )


def test_noncanonical_parenthetical_reference_does_not_evade_coverage():
    report = verify_citation_grounding(
        output_text="This assertion is presented as supported (src-a).",
        sources=[_src("a")],
    )
    assert report.verdict == "partially_grounded"
    assert report.has_unsupported is True


@pytest.mark.parametrize(
    ("output_text", "sources"),
    [
        (None, []),
        ("Claim [src-a].", (SourceRecord(source_id="a"),)),
        ("Claim [src-a].", [object()]),
    ],
)
def test_input_types_are_closed(output_text, sources):
    with pytest.raises(CitationGroundingError):
        verify_citation_grounding(output_text=output_text, sources=sources)


def test_source_metadata_types_are_closed_at_construction():
    with pytest.raises(CitationGroundingError):
        SourceRecord(source_id="a", title=object())
    with pytest.raises(CitationGroundingError):
        SourceRecord(source_id="a", url=object())


def test_forged_exact_source_is_revalidated_at_verification_boundary():
    forged = object.__new__(SourceRecord)
    object.__setattr__(forged, "source_id", "a")
    object.__setattr__(forged, "title", object())
    object.__setattr__(forged, "url", None)
    with pytest.raises(CitationGroundingError):
        verify_citation_grounding(
            output_text="This assertion is supported [src-a].",
            sources=[forged],
        )


def test_forged_source_field_shape_is_rejected_with_domain_error():
    missing = object.__new__(SourceRecord)
    object.__setattr__(missing, "source_id", "a")
    extra = SourceRecord(source_id="a")
    object.__setattr__(extra, "injected", "value")
    for forged in (missing, extra):
        with pytest.raises(CitationGroundingError):
            verify_citation_grounding(
                output_text="This assertion is supported [src-a].",
                sources=[forged],
            )


def test_output_and_source_count_are_bounded():
    with pytest.raises(CitationGroundingError, match="output_text"):
        verify_citation_grounding(output_text="x" * 1_000_001, sources=[])
    with pytest.raises(CitationGroundingError, match="sources"):
        verify_citation_grounding(
            output_text="short output",
            sources=[_src(str(i)) for i in range(10_001)],
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


def test_exported_report_values_reject_forged_runtime_shapes():
    source = _src("a")
    with pytest.raises(CitationGroundingError):
        ResolvedCitation(source_id="b", occurrences=1, source=source)
    with pytest.raises(CitationGroundingError):
        FabricatedCitation(source_id="a", occurrences=-1)
    with pytest.raises(CitationGroundingError):
        UnsupportedAssertion(sentence="claim", sentence_index=-1)
    with pytest.raises(CitationGroundingError):
        GroundingReport(
            verdict="grounded",
            resolved_citations=[],
            fabricated_citations=(),
            unsupported_assertions=(),
            total_citation_tokens=0,
        )


def test_report_verdict_and_token_total_are_self_consistent():
    source = _src("a")
    resolved = ResolvedCitation(source_id="a", occurrences=1, source=source)
    with pytest.raises(CitationGroundingError, match="total_citation_tokens"):
        GroundingReport(
            verdict="grounded",
            resolved_citations=(resolved,),
            fabricated_citations=(),
            unsupported_assertions=(),
            total_citation_tokens=0,
        )
    with pytest.raises(CitationGroundingError, match="verdict"):
        GroundingReport(
            verdict="ungrounded",
            resolved_citations=(resolved,),
            fabricated_citations=(),
            unsupported_assertions=(),
            total_citation_tokens=1,
        )


def test_report_revalidates_forged_exact_children():
    forged = object.__new__(FabricatedCitation)
    object.__setattr__(forged, "source_id", "a")
    object.__setattr__(forged, "occurrences", 0)
    with pytest.raises(CitationGroundingError):
        GroundingReport(
            verdict="ungrounded",
            resolved_citations=(),
            fabricated_citations=(forged,),
            unsupported_assertions=(),
            total_citation_tokens=0,
        )

    missing = object.__new__(FabricatedCitation)
    object.__setattr__(missing, "source_id", "a")
    with pytest.raises(CitationGroundingError):
        GroundingReport(
            verdict="ungrounded",
            resolved_citations=(),
            fabricated_citations=(missing,),
            unsupported_assertions=(),
            total_citation_tokens=1,
        )


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
