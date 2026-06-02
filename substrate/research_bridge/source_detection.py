"""Source-provider detection by structural fingerprint."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

KNOWN_SOURCES: tuple[str, ...] = ("chatgpt", "anthropic", "grok", "alphasense", "other")
MIN_CONFIDENCE: float = 0.5
PARSER_VERSION: int = 1


@dataclass(frozen=True)
class SourceDetectionResult:
    source: str
    confidence: float
    parser_version: int
    per_source: dict[str, float]


def _frac(matches: int, denom: int) -> float:
    return min(1.0, matches / denom) if denom > 0 else 0.0


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


_CHATGPT_CITATION_RE = re.compile(r"\[\d+\]|\(\d+\)|\[\^\d+\]")
_CHATGPT_REFERENCES_HEADER_RE = re.compile(
    r"^\s*(References|Sources|Bibliography|Footnotes)\s*[:\n]",
    re.IGNORECASE | re.MULTILINE,
)


def _score_chatgpt(text: str) -> float:
    if len(text) < 200:
        return 0.0
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    n_para = len(paragraphs)
    n_citations = len(_CHATGPT_CITATION_RE.findall(text))
    citation_density = _frac(n_citations, max(n_para, 1))
    has_refs = 1.0 if _CHATGPT_REFERENCES_HEADER_RE.search(text) else 0.0
    has_headers = 1.0 if re.search(r"^#{1,4}\s+\S", text, re.MULTILINE) else 0.0
    has_early_header = 1.0 if re.search(r"\n#{1,4}\s+\S", text[:2000]) else 0.0
    return _clamp(
        0.30 * has_refs + 0.20 * has_headers + 0.20 * has_early_header
        + 0.30 * _clamp(citation_density)
    )


_ANTHROPIC_BOLD_HEADER_RE = re.compile(r"^\*\*[^*\n]+\*\*\s*$", re.MULTILINE)
_ANTHROPIC_HEDGES_RE = re.compile(
    r"\b(However|That said|Importantly|It's worth noting|Notably|"
    r"On balance|To be clear|Crucially)\b",
)
_ANTHROPIC_CITATION_RE = re.compile(r"\[Citation:.*?\]|\[\d+\](?!\d)", re.IGNORECASE)


def _score_anthropic(text: str) -> float:
    if len(text) < 200:
        return 0.0
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    n_para = max(len(paragraphs), 1)
    n_hedges = len(_ANTHROPIC_HEDGES_RE.findall(text))
    hedge_density = _frac(n_hedges, n_para)
    has_bold_headers = 1.0 if _ANTHROPIC_BOLD_HEADER_RE.search(text) else 0.0
    has_a_citation = 1.0 if _ANTHROPIC_CITATION_RE.search(text) else 0.0
    avg_para_len = (sum(len(p) for p in paragraphs) / n_para) if n_para else 0
    long_paragraphs = _clamp((avg_para_len - 400) / 600)
    return _clamp(
        0.30 * _clamp(hedge_density * 2) + 0.25 * has_bold_headers
        + 0.20 * has_a_citation + 0.25 * long_paragraphs
    )


_GROK_TLDR_RE = re.compile(r"^\s*(TL;DR|Tl;dr|tl;dr)[:\s]", re.MULTILINE)
_GROK_X_LINK_RE = re.compile(r"https?://(?:www\.)?(?:x\.com|twitter\.com)/")
_GROK_CONVERSATIONAL_RE = re.compile(
    r"\b(Let me|Here's what I (found|dug up)|Diving in|As of \[?\d{4})\b",
    re.IGNORECASE,
)


def _score_grok(text: str) -> float:
    if len(text) < 200:
        return 0.0
    has_tldr = 1.0 if _GROK_TLDR_RE.search(text) else 0.0
    has_x_link = 1.0 if _GROK_X_LINK_RE.search(text) else 0.0
    has_conv = 1.0 if _GROK_CONVERSATIONAL_RE.search(text) else 0.0
    return _clamp(0.40 * has_tldr + 0.35 * has_x_link + 0.25 * has_conv)


_ALPHASENSE_FILING_RE = re.compile(
    r"\b(?:10-?K|10-?Q|8-?K|S-?1|earnings call|investor day|sell-side|"
    r"price target|consensus estimate)\b",
    re.IGNORECASE,
)
_ALPHASENSE_SELL_SIDE_RE = re.compile(
    r"\b(Goldman Sachs|Morgan Stanley|JPMorgan|J\.P\. Morgan|"
    r"Bank of America|BofA|Citi|Citigroup|Barclays|UBS|Credit Suisse|"
    r"Deutsche Bank|Wells Fargo|Jefferies|Cowen|Evercore|Piper Sandler|"
    r"Wedbush|Bernstein|Raymond James)\b",
)
_ALPHASENSE_MONEY_RE = re.compile(r"\$\s?[\d,]+(?:\.\d+)?\s?(?:[MBK]|million|billion|thousand)?")
_ALPHASENSE_PERCENT_RE = re.compile(r"\b\d+(?:\.\d+)?\s?%")


def _score_alphasense(text: str) -> float:
    if len(text) < 200:
        return 0.0
    has_filing = 1.0 if _ALPHASENSE_FILING_RE.search(text) else 0.0
    has_sell = 1.0 if _ALPHASENSE_SELL_SIDE_RE.search(text) else 0.0
    n_money = len(_ALPHASENSE_MONEY_RE.findall(text))
    n_pct = len(_ALPHASENSE_PERCENT_RE.findall(text))
    n_para = max(len([p for p in text.split("\n\n") if p.strip()]), 1)
    finance_density = _frac(n_money + n_pct, n_para * 2)
    return _clamp(
        0.40 * has_filing + 0.30 * has_sell + 0.30 * _clamp(finance_density)
    )


_SCORERS: dict[str, Callable[[str], float]] = {
    "chatgpt": _score_chatgpt,
    "anthropic": _score_anthropic,
    "grok": _score_grok,
    "alphasense": _score_alphasense,
}


def detect_source(text: str) -> SourceDetectionResult:
    per_source = {name: scorer(text) for name, scorer in _SCORERS.items()}
    best_source, best_score = max(per_source.items(), key=lambda kv: kv[1])
    chosen = "other" if best_score < MIN_CONFIDENCE else best_source
    return SourceDetectionResult(
        source=chosen,
        confidence=float(best_score),
        parser_version=PARSER_VERSION,
        per_source=per_source,
    )
