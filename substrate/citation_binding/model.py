"""Immutable report-offset annotations bound to exact SPR-03 spans.

Offsets are Python ``str`` code-point indices and are never normalized.
``Blocked.unsupported_claims`` (in :mod:`gate`) is the operator audit surface.
"""

from __future__ import annotations

from dataclasses import dataclass

from substrate.research_spans import ExtractiveSpan


@dataclass(frozen=True, slots=True)
class Claim:
    """One atomic claim occupying ``report_text[start:end]``."""

    start: int
    end: int
    text: str

    def __post_init__(self) -> None:
        if isinstance(self.start, bool) or not isinstance(self.start, int):
            raise TypeError("claim start must be an int")
        if isinstance(self.end, bool) or not isinstance(self.end, int):
            raise TypeError("claim end must be an int")
        if self.start < 0 or self.end <= self.start:
            raise ValueError("claim range must be non-empty and non-negative")
        if not self.text:
            raise ValueError("claim text must be non-empty")
        if len(self.text) != self.end - self.start:
            raise ValueError("claim text length does not match its range")


@dataclass(frozen=True, slots=True)
class CitationAnnotation:
    """A report range and its exact, immutable source-span provenance."""

    start: int
    end: int
    span_id: str
    source_url: str
    span: ExtractiveSpan
    additional_spans: tuple[ExtractiveSpan, ...] = ()

    @classmethod
    def bind(
        cls, report_text: str, start: int, end: int, span: ExtractiveSpan
    ) -> CitationAnnotation:
        """Validate a report range and bind it to ``span`` without copying text."""
        if not isinstance(report_text, str):
            raise TypeError("report_text must be str")
        if isinstance(start, bool) or not isinstance(start, int):
            raise TypeError("annotation start must be an int")
        if isinstance(end, bool) or not isinstance(end, int):
            raise TypeError("annotation end must be an int")
        if start == end:
            raise ValueError("empty annotation range")
        if start < 0 or end < start or end > len(report_text):
            raise ValueError("annotation out of range")
        if not report_text[start:end].strip():
            raise ValueError("annotation range must contain non-whitespace text")
        if not isinstance(span, ExtractiveSpan):
            raise TypeError("span must be an ExtractiveSpan")
        return cls(start, end, span.span_id, span.source_url, span)

    @classmethod
    def bind_many(
        cls,
        report_text: str,
        start: int,
        end: int,
        spans: tuple[ExtractiveSpan, ...],
    ) -> CitationAnnotation:
        """Bind one report range to one or more exact supporting spans."""
        if not spans:
            raise ValueError("supporting spans must be non-empty")
        annotation = cls.bind(report_text, start, end, spans[0])
        return cls(
            annotation.start,
            annotation.end,
            annotation.span_id,
            annotation.source_url,
            annotation.span,
            spans[1:],
        )

    def __post_init__(self) -> None:
        if isinstance(self.start, bool) or not isinstance(self.start, int):
            raise TypeError("annotation start must be an int")
        if isinstance(self.end, bool) or not isinstance(self.end, int):
            raise TypeError("annotation end must be an int")
        if self.start < 0 or self.end <= self.start:
            raise ValueError("empty annotation range")
        if not isinstance(self.span, ExtractiveSpan):
            raise TypeError("span must be an ExtractiveSpan")
        if not isinstance(self.additional_spans, tuple) or not all(
            isinstance(item, ExtractiveSpan) for item in self.additional_spans
        ):
            raise TypeError("additional_spans must be a tuple of ExtractiveSpan")
        if self.span_id != self.span.span_id or self.source_url != self.span.source_url:
            raise ValueError("annotation provenance does not match bound span")
        span_ids = [item.span_id for item in self.supporting_spans]
        if len(span_ids) != len(set(span_ids)):
            raise ValueError("supporting spans must be unique")

    @property
    def supporting_spans(self) -> tuple[ExtractiveSpan, ...]:
        """All exact spans supporting the annotated claim, primary first."""
        return (self.span, *self.additional_spans)

    def claim_text(self, report_text: str) -> str:
        """Return the exact annotated report slice."""
        if self.end > len(report_text):
            raise ValueError("annotation out of range for report")
        return report_text[self.start : self.end]


@dataclass(frozen=True, slots=True)
class AnnotatedReport:
    """Validated report, deterministic claims, citations, and explicit gaps."""

    report_text: str
    claims: tuple[Claim, ...]
    annotations: tuple[CitationAnnotation, ...]
    unbound_claims: tuple[Claim, ...]

    def __post_init__(self) -> None:
        from .bind import segment_claims

        if not self.report_text:
            raise ValueError("report_text must be non-empty")
        if not all(
            isinstance(item, tuple)
            for item in (self.claims, self.annotations, self.unbound_claims)
        ):
            raise TypeError("claims, annotations, and unbound_claims must be tuples")
        if not all(type(item) is Claim for item in self.claims):
            raise TypeError("claims must contain only Claim instances")
        if not all(type(item) is CitationAnnotation for item in self.annotations):
            raise TypeError(
                "annotations must contain only CitationAnnotation instances"
            )
        if not all(type(item) is Claim for item in self.unbound_claims):
            raise TypeError("unbound_claims must contain only Claim instances")
        canonical_claims = segment_claims(self.report_text)
        if self.claims != canonical_claims:
            raise ValueError("claims must equal canonical report segmentation")
        canonical_ranges = {(claim.start, claim.end) for claim in canonical_claims}
        previous_end = -1
        annotation_ranges: set[tuple[int, int]] = set()
        for annotation in self.annotations:
            annotation.claim_text(self.report_text)
            annotation_range = (annotation.start, annotation.end)
            if annotation.start < previous_end:
                raise ValueError("annotations overlap")
            if annotation_range not in canonical_ranges:
                raise ValueError("annotation must bind one canonical claim")
            if annotation_range in annotation_ranges:
                raise ValueError("duplicate annotation range")
            previous_end = annotation.end
            annotation_ranges.add(annotation_range)
        for claim in (*self.claims, *self.unbound_claims):
            if self.report_text[claim.start : claim.end] != claim.text:
                raise ValueError("claim does not match report offsets")
        expected_unbound = tuple(
            claim
            for claim in canonical_claims
            if (claim.start, claim.end) not in annotation_ranges
        )
        if self.unbound_claims != expected_unbound:
            raise ValueError("unbound claims must be the exact annotation complement")

    @classmethod
    def create(
        cls,
        report_text: str,
        annotations: tuple[CitationAnnotation, ...],
        claims: tuple[Claim, ...] | None = None,
        unbound_claims: tuple[Claim, ...] | None = None,
    ) -> AnnotatedReport:
        from .bind import segment_claims

        if not isinstance(report_text, str) or not report_text:
            raise ValueError("report_text must be non-empty")
        if not isinstance(annotations, tuple):
            raise TypeError("annotations must be a tuple")
        if not all(type(item) is CitationAnnotation for item in annotations):
            raise TypeError(
                "annotations must contain only CitationAnnotation instances"
            )
        ordered = tuple(sorted(annotations, key=lambda item: (item.start, item.end)))
        if claims is None:
            claims = segment_claims(report_text)
        if unbound_claims is None:
            bound_ranges = {(item.start, item.end) for item in ordered}
            unbound_claims = tuple(
                claim
                for claim in claims
                if (claim.start, claim.end) not in bound_ranges
            )
        return cls(report_text, claims, ordered, unbound_claims)
