"""Red proofs for SPR-04 offset citation binding and mandatory FACT gate."""

from __future__ import annotations

import hashlib
from html.parser import HTMLParser

import pytest

from substrate.citation_binding import (
    SUPPORT_THRESHOLD,
    AnnotatedReport,
    Blocked,
    CitationAnnotation,
    Done,
    bind_report,
    gate_report,
    project_to_html,
    segment_claims,
)
from substrate.research_spans import ExtractiveSpan


def span(text: str, *, url: str = "https://example.test/a?x=1&y=2") -> ExtractiveSpan:
    digest = hashlib.sha256(text.encode()).hexdigest()
    doc_id = hashlib.sha256((url + text).encode()).hexdigest()
    return ExtractiveSpan.from_source(
        source=text,
        document_id=doc_id,
        chunk_id="chunk-1",
        source_url=url,
        revision="v1",
        content_hash=digest,
        start=0,
        end=len(text),
        retrieval_score=1.0,
    )


class _CardParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_excerpt = False
        self.excerpts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if ("class", "citation-source-excerpt") in attrs:
            self.in_excerpt = True
            self.excerpts.append("")

    def handle_endtag(self, tag: str) -> None:
        if tag == "blockquote" and self.in_excerpt:
            self.in_excerpt = False

    def handle_data(self, data: str) -> None:
        if self.in_excerpt:
            self.excerpts[-1] += data


def test_annotation_refuses_empty_out_of_range_and_overlap_distinctly() -> None:
    report = "Alpha. Beta."
    evidence = span("source")
    with pytest.raises(ValueError, match="empty annotation range"):
        CitationAnnotation.bind(report, 2, 2, evidence)
    with pytest.raises(ValueError, match="annotation out of range"):
        CitationAnnotation.bind(report, 0, 99, evidence)
    first = CitationAnnotation.bind(report, 0, 6, evidence)
    second = CitationAnnotation.bind(report, 5, 12, evidence)
    with pytest.raises(ValueError, match="annotations overlap"):
        AnnotatedReport.create(report, (first, second))


def test_unicode_offsets_are_code_points_and_normalization_is_not_changed() -> None:
    report = "🙂 Café is open. Cafe\u0301 is decomposed."
    claims = segment_claims(report)
    assert [report[c.start : c.end] for c in claims] == [
        "🙂 Café is open.",
        "Cafe\u0301 is decomposed.",
    ]
    evidence = span("Café")
    annotation = CitationAnnotation.bind(report, claims[0].start, claims[0].end, evidence)
    assert annotation.claim_text(report) == "🙂 Café is open."
    assert evidence.text != "Cafe\u0301"


def test_segmentation_abbreviations_quotes_inline_code_lists_and_compounds() -> None:
    report = (
        "Dr. Rao said \"Revenue rose.\" Costs fell; margins grew.\n"
        "Use `x.y()` safely. It works.\n"
        "- Alpha launched and beta remained private.\n"
        "- Gamma closed."
    )
    assert [c.text for c in segment_claims(report)] == [
        'Dr. Rao said "Revenue rose."',
        "Costs fell;",
        "margins grew.",
        "Use `x.y()` safely.",
        "It works.",
        "Alpha launched",
        "beta remained private.",
        "Gamma closed.",
    ]


def test_segmentation_does_not_split_conjunction_inside_inline_code() -> None:
    claims = segment_claims("Use `left and right` and proceed. Revenue rose.")
    assert [claim.text for claim in claims] == [
        "Use `left and right`",
        "proceed.",
        "Revenue rose.",
    ]


def test_unclosed_inline_code_fails_closed_instead_of_hiding_claims() -> None:
    with pytest.raises(ValueError, match="unclosed inline-code"):
        segment_claims("Alpha is true. `Beta is false. Gamma is false.")


def test_binding_is_deterministic_and_keeps_unbound_claims_explicit() -> None:
    report = "Alpha launched. Beta failed."
    claims = segment_claims(report)
    evidence = span("Alpha launched in 2024.")
    plan = {(claims[0].start, claims[0].end): evidence}
    bound = bind_report(report, plan)
    assert bound == bind_report(report, plan)
    assert tuple(c.text for c in bound.unbound_claims) == ("Beta failed.",)
    assert bound.annotations[0].span is evidence


def test_one_compound_claim_can_carry_multiple_exact_supporting_spans() -> None:
    report = "Revenue rose."
    claim = segment_claims(report)[0]
    first, second = span("Revenue was $2m."), span("Prior revenue was $1m.")
    bound = bind_report(
        report, {(claim.start, claim.end): (first, second)}
    )
    assert bound.annotations[0].supporting_spans == (first, second)
    seen: list[tuple[ExtractiveSpan, ...]] = []

    def judge(_claim: str, spans: tuple[ExtractiveSpan, ...]) -> bool:
        seen.append(spans)
        return True

    assert isinstance(gate_report(bound, judge=judge, unattended=True), Done)
    assert seen == [(first, second)]
    parser = _CardParser()
    parser.feed(project_to_html(bound))
    assert parser.excerpts == [first.text, second.text]


def test_html_is_escaped_and_parsed_excerpt_exactly_equals_span_text() -> None:
    report = '<script>alert("x")</script> is not rendered.'
    claim = segment_claims(report)[0]
    evidence = span('<b title="x">A & B</b>')
    html = project_to_html(bind_report(report, {(claim.start, claim.end): evidence}))
    assert "<script>" not in html
    assert "<b title=" not in html
    assert "&lt;script&gt;" in html and "&amp;" in html
    parser = _CardParser()
    parser.feed(html)
    assert parser.excerpts == [evidence.text]


def test_annotation_free_projection_has_no_cards() -> None:
    html = project_to_html(bind_report("A plain note.", {}))
    assert "citation-source-card" not in html
    assert "A plain note." in html


def test_projection_never_links_an_unsafe_source_scheme() -> None:
    report = "Claim."
    claim = segment_claims(report)[0]
    evidence = span("proof", url="javascript:alert(1)")
    html = project_to_html(bind_report(report, {(claim.start, claim.end): evidence}))
    assert 'href="javascript:' not in html
    assert "javascript:alert(1)" in html


def test_forged_report_partitions_refuse() -> None:
    report = "Alpha. Beta."
    claims = segment_claims(report)
    evidence = span("proof")
    annotation = CitationAnnotation.bind(report, claims[1].start, claims[1].end, evidence)
    with pytest.raises(ValueError, match="claims must equal canonical"):
        AnnotatedReport(report, (), (), ())
    with pytest.raises(ValueError, match="unbound claims must be"):
        AnnotatedReport(report, claims, (annotation,), ())


def test_duck_typed_annotation_cannot_forge_exact_span_provenance() -> None:
    invoked = False

    class ForgedAnnotation:
        start = 0
        end = 6
        span_id = "fake"
        supporting_spans: tuple[ExtractiveSpan, ...] = ()

        def claim_text(self, report_text: str) -> str:
            nonlocal invoked
            invoked = True
            return report_text[self.start : self.end]

    with pytest.raises(TypeError, match="CitationAnnotation"):
        AnnotatedReport.create("Claim.", (ForgedAnnotation(),))  # type: ignore[arg-type]
    assert invoked is False


def test_duplicate_supporting_span_refuses() -> None:
    report = "Claim."
    claim = segment_claims(report)[0]
    evidence = span("proof")
    with pytest.raises(ValueError, match="must be unique"):
        bind_report(report, {(claim.start, claim.end): (evidence, evidence)})


def test_gate_threshold_boundary_and_exact_unsupported_claims() -> None:
    report = "One. Two. Three. Four. Five. Six. Seven. Eight. Nine. Ten."
    claims = segment_claims(report)
    evidence = span("evidence")
    nine = bind_report(report, {(c.start, c.end): evidence for c in claims[:9]})
    judge = lambda claim, spans: True  # noqa: E731
    assert SUPPORT_THRESHOLD == 0.9
    result = gate_report(nine, judge=judge, unattended=True)
    assert isinstance(result, Done) and result.support_rate == 0.9
    eight = bind_report(report, {(c.start, c.end): evidence for c in claims[:8]})
    blocked = gate_report(eight, judge=judge, unattended=True)
    assert isinstance(blocked, Blocked)
    assert blocked.unsupported_claims == tuple(c.text for c in claims[8:])


def test_zero_claim_report_cannot_be_forged_or_completed() -> None:
    with pytest.raises(ValueError, match="claims must equal canonical"):
        AnnotatedReport("The moon is cheese.", (), (), ())
    empty = AnnotatedReport.create("   ", (), (), ())
    result = gate_report(empty, judge=lambda _claim, _spans: True, unattended=True)
    assert isinstance(result, Blocked)
    assert result.reason == "report contains no claim sentences"


@pytest.mark.parametrize("threshold", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_threshold_refuses(threshold: float) -> None:
    report = bind_report("Claim.", {})
    with pytest.raises(ValueError, match="threshold must be"):
        gate_report(report, judge=lambda _claim, _spans: True, unattended=True, threshold=threshold)


def test_zero_threshold_cannot_nullify_the_support_gate() -> None:
    report = bind_report("Unsupported claim.", {})
    with pytest.raises(ValueError, match="threshold must be"):
        gate_report(report, judge=lambda _claim, _spans: False, unattended=True, threshold=0)


@pytest.mark.parametrize("hostile", ["yes", 1, 0, None, {"supported": True}])
def test_hostile_judge_outputs_block_instead_of_coercing(hostile: object) -> None:
    report = "Claim."
    claim = segment_claims(report)[0]
    bound = bind_report(report, {(claim.start, claim.end): span("proof")})
    result = gate_report(bound, judge=lambda _claim, _spans: hostile, unattended=True)
    assert isinstance(result, Blocked)
    assert result.unsupported_claims == ("Claim.",)
    assert "invalid judge output" in result.reason


def test_judge_exception_blocks_and_unattended_cannot_bypass_gate() -> None:
    report = "Claim."
    claim = segment_claims(report)[0]
    bound = bind_report(report, {(claim.start, claim.end): span("proof")})

    def exploding(_claim: str, _spans: tuple[ExtractiveSpan, ...]) -> bool:
        raise RuntimeError("secret detail")

    assert isinstance(gate_report(bound, judge=exploding, unattended=True), Blocked)
    with pytest.raises(ValueError, match="mandatory"):
        gate_report(bound, judge=exploding, unattended=True, enforce=False)


def test_empty_report_and_bad_binding_plan_refuse() -> None:
    with pytest.raises(ValueError, match="report_text must be non-empty"):
        bind_report("", {})
    report = "Claim."
    with pytest.raises(ValueError, match="does not identify a segmented claim"):
        bind_report(report, {(1, 3): span("proof")})
