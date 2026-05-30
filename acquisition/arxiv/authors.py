"""Author disambiguation: OpenAlex authorships -> ORCID-keyed identity (SPR-03 M2).

OpenAlex's per-work ``authorships`` array carries the one thing arXiv's own
metadata cannot give us: a per-author ORCID (when the author has claimed one)
plus OpenAlex's author disambiguation. SPR-07's claim flow needs the ORCID to
let a real person claim a paper; this module is where the raw OpenAlex shape is
turned into the typed ``EnrichedAuthor`` rows stored under
``documents.metadata["openalex_enrichment"]["authors"]``.

Discipline:

  * PURE. ``parse_authorships`` takes the raw work dict and returns a list — no
    network, no DB. The HTTP fetch is the connector's job
    (``acquisition.openaccess.openalex.fetch_work_record``); this is just the
    mapping, so the recorded-fixture tests target it directly.
  * ORCID is stored ONLY when present, never invented (rigor #1 / defensibility):
    an author with no ``author.orcid`` lands with ``orcid=None``, so a reviewer
    can tell a disambiguated identity from an absent one.
  * ORDER IS PRESERVED. ``author_position`` is the authorship's 0-based index in
    OpenAlex's ``authorships`` list, which mirrors the byline order arXiv
    publishes. We do NOT re-sort by the textual ``author_position`` label
    ("first"/"middle"/"last") — the array order is the authoritative byline order
    and first/last authorship carries academic-credit meaning.

Edge cases handled (named per the rigor bar):
  * no ``authorships`` key / empty list -> ``[]`` (a work OpenAlex has but with no
    parsed authors; the caller still records a match, just zero enriched authors).
  * an authorship with no ``author`` sub-object -> skipped (malformed; cannot key
    or name it).
  * missing / empty ORCID -> ``orcid=None`` (never fabricated).
  * a display name absent on both ``author.display_name`` and ``raw_author_name``
    -> empty string (the ORCID, when present, is still the useful key).
"""

from __future__ import annotations

from typing import Any, List

from substrate.schemas.documents import EnrichedAuthor


def _clean(value: Any) -> str:
    """A string value, stripped; non-strings / None -> empty string."""
    return value.strip() if isinstance(value, str) else ""


def _orcid_or_none(author: dict) -> str | None:
    """The author's ORCID, normalised to a non-empty string or ``None``.

    Never invents one: an absent / empty ``author.orcid`` returns ``None`` so the
    "no identity found" case is distinguishable from a disambiguated identity."""
    orcid = _clean(author.get("orcid"))
    return orcid or None


def parse_authorships(raw_work: dict) -> List[EnrichedAuthor]:
    """Map an OpenAlex work's ``authorships`` -> ordered ``EnrichedAuthor`` rows.

    ``raw_work`` is the FULL raw OpenAlex work dict (as returned by
    ``acquisition.openaccess.openalex.fetch_work_record``), NOT the reduced
    ``OpenAlexWork`` — the authorships only survive on the raw JSON.

    Ordering: ``author_position`` is the 0-based index into ``authorships``,
    preserving OpenAlex's (== arXiv's) byline order. The textual
    ``author_position`` label OpenAlex also carries ("first"/"middle"/"last") is
    NOT used as the index — the array order is the byline order.
    """
    authorships = raw_work.get("authorships")
    if not isinstance(authorships, list):
        return []

    authors: List[EnrichedAuthor] = []
    position = 0
    for entry in authorships:
        if not isinstance(entry, dict):
            continue
        author = entry.get("author")
        if not isinstance(author, dict):
            # Malformed authorship with no author sub-object: cannot key it.
            continue
        display_name = _clean(author.get("display_name")) or _clean(
            entry.get("raw_author_name")
        )
        authors.append(
            EnrichedAuthor(
                orcid=_orcid_or_none(author),
                author_position=position,
                display_name=display_name,
            )
        )
        position += 1
    return authors
