"""Parse OAI-PMH ``<record>`` elements (metadataPrefix=arXiv) into
``ArxivOaiRecord``s, and fold a stream of them into a ``RightsCensus``.

The OAI-PMH ``arXiv`` metadata format is the ONLY arXiv interface carrying the
per-paper ``<license>`` element (https://info.arxiv.org/help/oa/index.html);
the Atom search API and OpenAlex do not. The license element's text is the
authoritative rights anchor, copied verbatim onto ``ArxivOaiRecord.license_uri``
and never inferred from anything else.

Pure XML → dataclass + a fold. No HTTP, no DB — the harvester
(``acquisition.arxiv.oai_pmh``) does the network and feeds element fragments in
here, so the parse + census are unit-testable against recorded XML with no
network.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Iterable, List, Optional

from substrate.schemas.documents import (
    ArxivOaiRecord,
    RightsCensus,
    _TierTally,
)

# OAI-PMH protocol namespace + arXiv's metadata-format namespace. arXiv's
# ``arXiv`` format namespaces its body under ``http://arxiv.org/OAI/arXiv/``;
# the ``<license>`` element lives there.
_OAI_NS = "{http://www.openarchives.org/OAI/2.0/}"
_ARXIV_NS = "{http://arxiv.org/OAI/arXiv/}"


def _text(el: Optional[ET.Element]) -> Optional[str]:
    """Stripped element text, or ``None`` for a missing/empty element. An
    empty ``<license/>`` therefore reads as ``None`` — the deny-by-default
    input that lands a record in T3-ambiguous, exactly as an absent element
    does."""
    if el is None or el.text is None:
        return None
    t = el.text.strip()
    return t or None


def parse_record(record_el: ET.Element) -> ArxivOaiRecord:
    """One OAI ``<record>`` → ``ArxivOaiRecord``.

    A ``<header status="deleted">`` record carries no ``<metadata>`` block; it
    is returned as a tombstone (``deleted=True``) so the census can exclude it
    from the denominator rather than miscount it as an unknown-license paper.
    """
    header = record_el.find(f"{_OAI_NS}header")
    if header is None:
        raise ValueError("OAI record missing <header>")

    datestamp = _text(header.find(f"{_OAI_NS}datestamp")) or ""
    deleted = header.get("status") == "deleted"

    if deleted:
        # The OAI identifier on a tombstone is ``oai:arXiv.org:<id>``; the bare
        # id is the load-bearing part for the cursor/dedup.
        identifier = _text(header.find(f"{_OAI_NS}identifier")) or ""
        return ArxivOaiRecord(
            arxiv_id=identifier.rsplit(":", 1)[-1],
            datestamp=datestamp,
            deleted=True,
        )

    body = record_el.find(f"{_OAI_NS}metadata/{_ARXIV_NS}arXiv")
    if body is None:
        raise ValueError(
            "live OAI record missing <metadata><arXiv> body "
            "(wrong metadataPrefix? expected 'arXiv')"
        )

    license_uri = _text(body.find(f"{_ARXIV_NS}license"))
    arxiv_id = _text(body.find(f"{_ARXIV_NS}id")) or ""
    title = _text(body.find(f"{_ARXIV_NS}title"))
    categories_text = _text(body.find(f"{_ARXIV_NS}categories"))
    categories = tuple(categories_text.split()) if categories_text else ()

    return ArxivOaiRecord(
        arxiv_id=arxiv_id,
        datestamp=datestamp,
        license_uri=license_uri,
        title=title,
        categories=categories,
    )


def parse_records(xml_fragment: bytes | str) -> List[ArxivOaiRecord]:
    """Parse all ``<record>`` elements under a ``<ListRecords>`` (or a bare
    ``<OAI-PMH>`` envelope) into records. Raises ``ValueError`` on malformed
    XML or on an OAI ``<error>`` response so a protocol error never silently
    yields an empty census."""
    if isinstance(xml_fragment, str):
        xml_fragment = xml_fragment.encode("utf-8")
    try:
        root = ET.fromstring(xml_fragment)
    except ET.ParseError as e:
        raise ValueError(f"OAI-PMH response is not valid XML: {e!r}") from e

    error = root.find(f"{_OAI_NS}error")
    if error is not None:
        code = error.get("code", "unknown")
        raise ValueError(f"OAI-PMH error [{code}]: {(error.text or '').strip()}")

    return [parse_record(r) for r in root.iter(f"{_OAI_NS}record")]


def build_census(
    records: Iterable[ArxivOaiRecord],
    *,
    metadata_prefix: str = "arXiv",
    from_date: Optional[str] = None,
    until_date: Optional[str] = None,
    harvested_at: Optional[datetime] = None,
) -> RightsCensus:
    """Fold a stream of records into a self-checking ``RightsCensus``.

    The query parameters are recorded ON the census (rigor bar 5: a harvest is
    reproducible from the prefix + window stamped here). ``harvested_at``
    defaults to now in UTC; tests inject a fixed clock for determinism.
    Deleted-tombstone records are excluded from the tier counts and tallied
    separately. The returned census's ``__post_init__`` asserts the partition
    is exhaustive.
    """
    tally = _TierTally()
    for record in records:
        tally.add(record)
    return tally.freeze(
        metadata_prefix=metadata_prefix,
        from_date=from_date,
        until_date=until_date,
        harvested_at=harvested_at or datetime.now(timezone.utc),
    )
