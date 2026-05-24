"""Source-detection tests.

Two kinds: (1) drift tests that prove the Python constants and the
SQL CHECK list agree; (2) precision tests that prove each fixture
gets detected as its own source at >= MIN_CONFIDENCE.

The precision test is what determines whether SPR-02 can trust the
``source`` column. If a fixture falls back to ``other`` at confidence
< MIN_CONFIDENCE, we surface that loudly via assertion — the rigor
rule from the sprint spec says NOT to silently retune the detector
until the test passes.
"""

from __future__ import annotations

import re
from typing import Callable

import pytest

from substrate.research_bridge import schema as bridge_schema
from substrate.research_bridge.source_detection import (
    KNOWN_SOURCES,
    MIN_CONFIDENCE,
    PARSER_VERSION,
    SourceDetectionResult,
    detect_source,
)


# ---------------------------------------------------------------------------
# Constants-in-sync drift test
# ---------------------------------------------------------------------------


def test_known_sources_match_sql_check() -> None:
    """The Python KNOWN_SOURCES tuple and the SQL CHECK list in
    schema.py must agree. If they drift, ingest will write a row with
    a source the CHECK rejects and the whole ingest path breaks.
    """
    sql = bridge_schema.ANTIEK_RESEARCH_BRIDGE_SCHEMA_V1_SQL
    m = re.search(r"source\s+TEXT NOT NULL CHECK \(source IN \(([^)]+)\)\)", sql)
    assert m, "could not find source CHECK in schema SQL"
    sql_sources = tuple(
        s.strip().strip("'") for s in m.group(1).split(",")
    )
    assert tuple(sorted(sql_sources)) == tuple(sorted(KNOWN_SOURCES)), (
        f"SQL CHECK {sql_sources!r} disagrees with KNOWN_SOURCES {KNOWN_SOURCES!r}"
    )


def test_parser_version_is_int() -> None:
    assert isinstance(PARSER_VERSION, int)
    assert PARSER_VERSION >= 1


# ---------------------------------------------------------------------------
# Per-fixture precision
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("source", ["chatgpt", "anthropic", "grok", "alphasense"])
def test_fixture_detects_as_its_own_source(fixture_text, source: str) -> None:
    text = fixture_text(source)
    result = detect_source(text)
    assert isinstance(result, SourceDetectionResult)
    # Whichever source got the max score, it should be THIS source.
    best = max(result.per_source.items(), key=lambda kv: kv[1])
    assert best[0] == source, (
        f"fixture '{source}' was best-matched as '{best[0]}'\n"
        f"  per_source = {result.per_source}"
    )


@pytest.mark.parametrize("source", ["chatgpt", "anthropic", "grok", "alphasense"])
def test_fixture_clears_min_confidence(fixture_text, source: str) -> None:
    """Fixture must score >= MIN_CONFIDENCE for its own source. This
    is the gate that decides whether the row gets ``source='other'``
    in production. Failing this test for a fixture means the detector
    is too weak for that provider.
    """
    text = fixture_text(source)
    result = detect_source(text)
    assert result.per_source[source] >= MIN_CONFIDENCE, (
        f"fixture '{source}' scored {result.per_source[source]:.3f} for its own "
        f"source, below MIN_CONFIDENCE={MIN_CONFIDENCE}.\n"
        f"  per_source = {result.per_source}"
    )


@pytest.mark.parametrize("source", ["chatgpt", "anthropic", "grok", "alphasense"])
def test_fixture_chosen_source_is_own(fixture_text, source: str) -> None:
    """End-to-end: detect_source returns the right ``source`` (not
    'other') for each fixture.
    """
    text = fixture_text(source)
    result = detect_source(text)
    assert result.source == source, (
        f"fixture '{source}' was classified as '{result.source}' at "
        f"confidence {result.confidence:.3f}\n"
        f"  per_source = {result.per_source}"
    )


# ---------------------------------------------------------------------------
# Negative / edge cases
# ---------------------------------------------------------------------------


def test_short_text_returns_other() -> None:
    """Very-short pastes can't be classified honestly; they should
    fall through to ``other``.
    """
    result = detect_source("hello world")
    assert result.source == "other"
    assert result.confidence < MIN_CONFIDENCE


def test_empty_text_returns_other() -> None:
    result = detect_source("")
    assert result.source == "other"


def test_random_prose_returns_other() -> None:
    """Generic prose with no provider-specific fingerprint should
    fall to ``other`` rather than aggressively assigning a provider.
    """
    text = (
        "The economy grew by 2 percent. People bought things. "
        "Companies hired workers. The weather was generally fine. "
        "Sometimes it rained.\n\n"
        "Other things happened too. Most of them were unremarkable. "
        "There was no clear pattern to any of it.\n\n"
        "Cats are nice."
    ) * 5
    result = detect_source(text)
    assert result.source == "other", (
        f"generic prose got classified as '{result.source}' at "
        f"confidence {result.confidence:.3f}\n"
        f"  per_source = {result.per_source}"
    )
