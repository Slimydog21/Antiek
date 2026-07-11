"""Safe native HTML projection for report citations and source cards."""

from __future__ import annotations

from html import escape
from urllib.parse import urlsplit

from .model import AnnotatedReport


def project_to_html(report: AnnotatedReport) -> str:
    """Render a self-contained HTML view; all report/source data is escaped."""
    if not isinstance(report, AnnotatedReport):
        raise TypeError("report must be an AnnotatedReport")
    annotation_by_range = {(a.start, a.end): a for a in report.annotations}
    body: list[str] = []
    cursor = 0
    for claim in report.claims:
        body.append(escape(report.report_text[cursor : claim.start]))
        rendered = escape(claim.text)
        annotation = annotation_by_range.get((claim.start, claim.end))
        if annotation is not None:
            card_id = f"source-{annotation.span_id}-{annotation.start}-{annotation.end}"
            rendered = (
                f'<cite class="citation-claim" data-span-id="{annotation.span_id}">'
                f'{rendered}<a href="#{card_id}" aria-label="Source">[source]</a></cite>'
            )
        body.append(rendered)
        cursor = claim.end
    body.append(escape(report.report_text[cursor:]))
    cards_parts: list[str] = []
    for annotation in report.annotations:
        for index, source_span in enumerate(annotation.supporting_spans):
            card_id = (
                f"source-{annotation.span_id}-{annotation.start}-{annotation.end}"
                if index == 0
                else f"source-{annotation.span_id}-{annotation.start}-{annotation.end}-{index}"
            )
            source_label = escape(source_span.source_url)
            source_link = source_label
            if _safe_source_url(source_span.source_url):
                source_link = (
                    f'<a class="citation-source-url" '
                    f'href="{escape(source_span.source_url, quote=True)}" '
                    f'rel="noopener noreferrer">{source_label}</a>'
                )
            cards_parts.append(
                f'<aside class="citation-source-card" id="{card_id}">'
                f"{source_link}<blockquote class=\"citation-source-excerpt\">"
                f"{escape(source_span.text)}</blockquote></aside>"
            )
    cards = "".join(cards_parts)
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\"><title>Research report</title>"
        "</head><body><article class=\"citation-report\">"
        + "".join(body)
        + "</article>"
        + cards
        + "</body></html>"
    )


def _safe_source_url(value: str) -> bool:
    parsed = urlsplit(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname)
