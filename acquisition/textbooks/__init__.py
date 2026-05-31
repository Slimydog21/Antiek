"""Open-textbook connectors (SPR-05).

Four connectors — OpenStax, LibreTexts, DOAB/OAPEN, MIT OpenCourseWare — that
ingest open-licensed full-text textbooks SERVABLE, composing the Wave-1 spine
(staging write SPR-01, rights classify SPR-02, dedup SPR-04, throttle +
extraction gate SPR-03) rather than reimplementing it.

THE BINDING (load-bearing): every connector resolves the item's DECLARED
license string from the source's own metadata and routes it through the SINGLE
classification chokepoint ``acquisition.licenses_core.classify``. The returned
``ClassificationResult.content_class`` + ``.license_basis`` are passed to
``acquisition.books.adapter.ingest_servable_book``. No connector assigns a
content_class by any other route. CC-BY/-SA -> servable
(``source_declared_open``); NC/ND/NC-SA -> whatever class classify() returns
(gated per SPR-02, NEVER flattened to ``public_domain``); unresolved ->
``GATED_DEFAULT_CONTENT_CLASS`` (deny-by-default, §9.0).

See ``LICENSES.md`` for the per-source license-field map + the SPR-02 routing
table.
"""

from __future__ import annotations

from ._common import (
    IngestOutcome,
    SourceError,
    TextbookWork,
    ThrottledClient,
    ingest_textbook,
)

__all__ = [
    "IngestOutcome",
    "SourceError",
    "TextbookWork",
    "ThrottledClient",
    "ingest_textbook",
    "openstax",
    "libretexts",
    "doab",
    "mit_ocw",
]
