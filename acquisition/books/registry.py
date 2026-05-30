"""Connector registry for the Wave-2 public-domain book sources (SPR-06 M5).

SPR-09 rotates over the PD sources; this module is the single documented list
it (and the orchestrator's ``--pd-curated`` curated spine) rotates over. Each
entry names the source key (the SPR-03 throttle key + dedup source namespace),
the module's ``discover`` entrypoint, and a one-line PD-establishment summary
for the SPR-10 audit. Importing this module imports all five connectors, so the
"connectors importable/registered" verification gate is a single import.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from . import (
    hathitrust,
    internet_archive,
    library_of_congress,
    standard_ebooks,
    wikisource,
)
from .pd_connector_base import BookCandidate, ThrottledFetcher


@dataclass(frozen=True)
class PdSource:
    """One registered PD book source. ``discover(fetcher, limit=...)`` returns
    candidates; the servable/gated verdict is classify()'s at ingest, never
    this registry's."""

    key: str  # SPR-03 throttle key + dedup source namespace
    module: str  # import path
    discover: Callable[..., list[BookCandidate]]
    establishment: str  # one-line "how PD is established" for the SPR-10 audit


PD_CURATED_SOURCES: tuple[PdSource, ...] = (
    PdSource(
        key="standard_ebooks",
        module="acquisition.books.standard_ebooks",
        discover=standard_ebooks.discover,
        establishment="source publishes US-public-domain works only; per-entry rights field recorded",
    ),
    PdSource(
        key="wikisource",
        module="acquisition.books.wikisource",
        discover=wikisource.discover,
        establishment="page PD/free-license maintenance category (PD-* / No restrictions / CC-BY-SA)",
    ),
    PdSource(
        key="internet_archive",
        module="acquisition.books.internet_archive",
        discover=internet_archive.discover,
        establishment="metadata possible-copyright-status=NOT_IN_COPYRIGHT / PD licenseurl (two-layer filter)",
    ),
    PdSource(
        key="hathitrust",
        module="acquisition.books.hathitrust",
        discover=hathitrust.discover,
        establishment="Bibliographic API rights code pd/pdus (ic/icus/und/unknown -> gated)",
    ),
    PdSource(
        key="library_of_congress",
        module="acquisition.books.library_of_congress",
        discover=library_of_congress.discover,
        establishment="item rights statement asserts no-known-copyright / public domain",
    ),
)

PD_CURATED_SOURCE_KEYS: tuple[str, ...] = tuple(s.key for s in PD_CURATED_SOURCES)

__all__ = [
    "PdSource",
    "PD_CURATED_SOURCES",
    "PD_CURATED_SOURCE_KEYS",
    "BookCandidate",
    "ThrottledFetcher",
]
