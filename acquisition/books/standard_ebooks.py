"""Standard Ebooks public-domain connector (SPR-06 M2).

Standard Ebooks (https://standardebooks.org) publishes carefully-formatted
editions of works that are in the **public domain in the United States** — its
entire catalogue is US-PD by editorial policy, and each OPDS/Atom entry carries
a rights dedication to that effect. The connector discovers works from the OPDS
feed (through the SPR-03 throttle), establishes PD per item from the entry's
rights field + the source-level guarantee, and hands the body to the SPR-02
rights chokepoint via :func:`acquisition.books.pd_connector_base.classify_and_ingest`.

PD discipline (rigor #1): the PD status is RECORDED, not assumed. Even though
the source is wholesale-PD, classify() still decides the verdict — the
``source_declaration`` PD signal names Standard Ebooks AND the per-entry rights
field, so the resulting ``license_basis`` answers "why is this servable?" from
the row alone (defensibility #5). No connector-local ``content_class``.

NO raw ``requests``/``httpx``: every fetch is via the shared
:class:`ThrottledFetcher` (SPR-03).
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from .pd_connector_base import BookCandidate, ThrottledFetcher

logger = logging.getLogger("acquisition.books.standard_ebooks")

SOURCE = "standard_ebooks"
OPDS_FEED_URL = "https://standardebooks.org/feeds/opds/all"

# Atom/OPDS uses XML namespaces; we parse with a namespace-agnostic local-name
# match so we are not brittle to prefix choices across feed revisions.
_ENTRY_RE = re.compile(r"<entry\b.*?</entry>", re.IGNORECASE | re.DOTALL)


def _tag_text(entry_xml: str, local_name: str) -> Optional[str]:
    """First inner text of an element with the given local name (ignoring any
    namespace prefix), or None."""
    m = re.search(
        rf"<(?:\w+:)?{local_name}\b[^>]*>(.*?)</(?:\w+:)?{local_name}>",
        entry_xml,
        re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return None
    text = re.sub(r"<[^>]+>", " ", m.group(1))
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _link_href(entry_xml: str, *, predicate) -> Optional[str]:
    for m in re.finditer(r"<(?:\w+:)?link\b([^>]*)/?>", entry_xml, re.IGNORECASE):
        attrs = m.group(1)
        href_m = re.search(r'href\s*=\s*"([^"]+)"', attrs, re.IGNORECASE)
        if not href_m:
            continue
        href = href_m.group(1)
        if predicate(attrs, href):
            return href
    return None


def _slug_from_id(id_text: Optional[str], source_uri: str) -> str:
    """Stable SE book slug for the dedup source-id. SE entry ids look like
    ``url:https://standardebooks.org/ebooks/<author>/<title>``; fall back to the
    acquisition link path."""
    candidate = id_text or source_uri
    candidate = candidate.split("standardebooks.org/ebooks/")[-1]
    candidate = candidate.strip().strip("/")
    candidate = candidate.split("?")[0]
    return candidate or source_uri


def _entry_to_candidate(entry_xml: str) -> Optional[BookCandidate]:
    title = _tag_text(entry_xml, "title")
    if not title:
        return None
    author = _tag_text(entry_xml, "name") or _tag_text(entry_xml, "author")
    id_text = _tag_text(entry_xml, "id")
    # The canonical landing page (rel="alternate" or the entry's own id URL).
    source_uri = _link_href(
        entry_xml,
        predicate=lambda attrs, href: 'rel="alternate"' in attrs.lower()
        or "/ebooks/" in href,
    ) or (id_text.replace("url:", "") if id_text else OPDS_FEED_URL)

    # The epub acquisition link. We render the epub's text to PDF at ingest;
    # SE serves a compatible epub at an acquisition rel.
    epub_url = _link_href(
        entry_xml,
        predicate=lambda attrs, href: "epub" in href.lower()
        or "acquisition" in attrs.lower(),
    )
    if not epub_url:
        logger.info("standard_ebooks entry %r skipped: no epub link", title)
        return None

    rights = _tag_text(entry_xml, "rights")
    slug = _slug_from_id(id_text, source_uri)

    # Establishment: Standard Ebooks publishes only US-PD works; the per-entry
    # rights field is recorded as the item-specific basis. This is a positive
    # source_declaration PD signal (NOT a local content_class) — classify()
    # turns it into the public_domain verdict + a license_basis that names BOTH
    # the source guarantee and the entry's rights statement.
    pd_signal = (
        "Standard Ebooks: source publishes US-public-domain works only; "
        f"entry rights={rights!r}"
        if rights
        else "Standard Ebooks: source publishes US-public-domain works only"
    )

    return BookCandidate(
        source=SOURCE,
        source_id=f"{SOURCE}:{slug}",
        title=title,
        author=author,
        source_uri=source_uri,
        download_url=epub_url,
        download_format="text",  # epub body rendered to PDF at ingest
        license_uri=None,
        pd_signal=pd_signal,
        subjects=tuple(),
    )


def discover(
    fetcher: ThrottledFetcher, *, limit: int = 25
) -> list[BookCandidate]:
    """Discover up to ``limit`` Standard Ebooks works from the OPDS feed.

    Tested against a recorded OPDS fixture, never the live network. Returns
    candidates whose PD status is positively established (every SE work is
    US-PD); the verdict is still classify()'s, applied at ingest.
    """
    feed_xml = fetcher.get_text(OPDS_FEED_URL)
    out: list[BookCandidate] = []
    for entry_xml in _ENTRY_RE.findall(feed_xml):
        if len(out) >= limit:
            break
        cand = _entry_to_candidate(entry_xml)
        if cand is not None:
            out.append(cand)
    return out
