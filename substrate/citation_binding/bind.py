"""Deterministic claim segmentation and explicit assembly-time binding.

Conventions: Unicode is untouched; bullets are structural (their marker is not
part of a claim); terminal punctuation and closing quotes stay with the claim;
common title/Latin abbreviations do not terminate; inline backtick code is
opaque; semicolons and the conjunction ``and`` split compound claims. The
conjunction convention intentionally favors gate recall over polished NLP.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from substrate.research_spans import ExtractiveSpan

from .model import AnnotatedReport, CitationAnnotation, Claim

_ABBREVIATIONS = frozenset(
    {
        "co.",
        "dr.",
        "e.g.",
        "etc.",
        "fig.",
        "i.e.",
        "inc.",
        "ltd.",
        "mr.",
        "mrs.",
        "ms.",
        "no.",
        "prof.",
        "u.s.",
        "vs.",
    }
)
_BULLET = re.compile(r"(?m)^[ \t]*(?:[-*+] |\d+[.)] )")
_AND = re.compile(r"\s+and\s+", re.IGNORECASE)


def segment_claims(report_text: str) -> tuple[Claim, ...]:
    """Return stable atomic claim slices into ``report_text``."""
    if not isinstance(report_text, str):
        raise TypeError("report_text must be str")
    claims: list[Claim] = []
    start = 0
    code = False
    index = 0
    while index < len(report_text):
        char = report_text[index]
        if char == "`":
            code = not code
        boundary = False
        end = index + 1
        if not code and char == ";":
            boundary = True
        elif not code and char in ".!?":
            token_start = report_text.rfind(" ", start, index) + 1
            token = report_text[token_start : index + 1].lower()
            boundary = token not in _ABBREVIATIONS and not (
                char == "." and index + 1 < len(report_text) and report_text[index + 1].isalnum()
            )
            while boundary and end < len(report_text) and report_text[end] in "\"'”’)]}":
                end += 1
        elif not code and char == "\n":
            boundary = True
        if boundary:
            _append_compound_claims(report_text, start, end, claims)
            start = end
            index = end
            continue
        index += 1
    if code:
        raise ValueError("report contains an unclosed inline-code delimiter")
    _append_compound_claims(report_text, start, len(report_text), claims)
    return tuple(claims)


def _append_compound_claims(text: str, start: int, end: int, out: list[Claim]) -> None:
    while start < end and text[start].isspace():
        start += 1
    bullet = _BULLET.match(text, start, end)
    if bullet is not None:
        start = bullet.end()
    while end > start and text[end - 1].isspace():
        end -= 1
    cursor = start
    scan_cursor = start
    code = False
    for match in _AND.finditer(text, start, end):
        code = _code_state_between(text, scan_cursor, match.start(), code)
        if not code:
            _append_claim(text, cursor, match.start(), out)
            cursor = match.end()
        scan_cursor = match.end()
    _append_claim(text, cursor, end, out)


def _code_state_between(text: str, start: int, end: int, initial: bool) -> bool:
    state = initial
    for char in text[start:end]:
        if char == "`":
            state = not state
    return state


def _append_claim(text: str, start: int, end: int, out: list[Claim]) -> None:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    if start < end:
        out.append(Claim(start, end, text[start:end]))


def bind_report(
    report_text: str,
    bindings: Mapping[
        tuple[int, int], ExtractiveSpan | tuple[ExtractiveSpan, ...]
    ],
) -> AnnotatedReport:
    """Bind segmented claims from an explicit offset-to-span assembly plan."""
    if not report_text:
        raise ValueError("report_text must be non-empty")
    claims = segment_claims(report_text)
    ranges = {(claim.start, claim.end): claim for claim in claims}
    unknown = set(bindings).difference(ranges)
    if unknown:
        raise ValueError("binding range does not identify a segmented claim")
    annotations_list: list[CitationAnnotation] = []
    for claim in claims:
        key = (claim.start, claim.end)
        if key not in bindings:
            continue
        value = bindings[key]
        spans = value if isinstance(value, tuple) else (value,)
        annotations_list.append(
            CitationAnnotation.bind_many(report_text, claim.start, claim.end, spans)
        )
    annotations = tuple(annotations_list)
    unbound = tuple(
        claim for claim in claims if (claim.start, claim.end) not in bindings
    )
    return AnnotatedReport.create(report_text, annotations, claims, unbound)
