"""LibreTexts open-textbook connector (SPR-05 M3).

LibreTexts content carries MIXED Creative-Commons variants per page/book
(-BY, -BY-SA, -BY-NC, -BY-ND, -BY-NC-SA). There is NO uniform source license,
so this connector resolves EACH discovered item's declared license individually
through ``classify()`` (the SPR-02 chokepoint) and obeys whatever class comes
back:

  * a clean CC-BY / CC-BY-SA book -> ``source_declared_open`` (servable);
  * a CC-BY-NC / CC-BY-ND / CC-BY-NC-SA item -> whatever class SPR-02 assigns
    (gated, per the current rights map) — NEVER silently ``public_domain``;
  * an item whose license cannot be resolved -> ``GATED_DEFAULT_CONTENT_CLASS``
    (deny-by-default, body withheld).

The connector does NOT decide the NC/ND policy — it passes the declared license
string to classify() and routes by the result. The rights field is read from
the LibreTexts page metadata ``tags`` / ``properties`` (a license code such as
``ccby`` / ``ccbync`` and/or a ``licenseurl``); we prefer the URL, else the code.

Compose, do not reimplement: shared ``ThrottledClient`` (SPR-03 ban-aware),
``classify()`` (SPR-02), ``ingest_textbook`` -> ``ingest_servable_book``
(SPR-01 staging), dedup on the page id / content-hash (SPR-04, orchestrator).
"""

from __future__ import annotations

import logging
from typing import Optional

from ._common import SourceError, TextbookWork, ThrottledClient, ingest_textbook

logger = logging.getLogger("acquisition.textbooks.libretexts")

# LibreTexts exposes per-library content listings; this is the documented
# content-listing endpoint shape. Tests inject a fake client (no live host).
LIBRETEXTS_CONTENT_URL = "https://api.libretexts.org/endpoint/content"

# Compact license codes LibreTexts emits in page tags/properties, mapped to the
# canonical CC short-code form classify() resolves. We do NOT decide the class
# here — we only normalize the source's own code into the string classify()
# already understands. NC/ND codes are normalized faithfully so classify()
# gates them; flattening them would be the exact bug this milestone guards.
_LICENSE_CODE_TO_STRING = {
    "ccby": "cc-by",
    "cc-by": "cc-by",
    "ccbysa": "cc-by-sa",
    "cc-by-sa": "cc-by-sa",
    "ccbync": "cc-by-nc",
    "cc-by-nc": "cc-by-nc",
    "ccbynd": "cc-by-nd",
    "cc-by-nd": "cc-by-nd",
    "ccbyncsa": "cc-by-nc-sa",
    "cc-by-nc-sa": "cc-by-nc-sa",
    "ccbyncnd": "cc-by-nc-nd",
    "cc-by-nc-nd": "cc-by-nc-nd",
    "ccpd": "cc0",  # LibreTexts "public domain" tag -> CC0 dedication
    "publicdomain": "cc0",
    "cc0": "cc0",
}


def _declared_license(item: dict) -> Optional[str]:
    """Read this item's DECLARED license, preferring a canonical CC URI, then a
    code normalized to the CC short-code string classify() understands.

    Returns the string verbatim for classify() to resolve. ``None`` when the
    item declared no resolvable license — classify() gates that by default."""
    # Prefer an explicit license URI.
    url = item.get("licenseurl") or item.get("license_url")
    if isinstance(url, str) and url:
        return url
    # Otherwise a license code from the page metadata.
    raw = item.get("license") or item.get("license_code")
    if isinstance(raw, dict):
        raw = raw.get("code") or raw.get("name") or raw.get("url")
    if isinstance(raw, str) and raw:
        key = raw.strip().lower().replace("_", "-").replace(" ", "")
        return _LICENSE_CODE_TO_STRING.get(key, raw.strip().lower())
    # License sometimes lives among tags.
    for tag in item.get("tags") or ():
        if isinstance(tag, str):
            t = tag.strip().lower()
            if t.startswith("license:"):
                key = t.split(":", 1)[1].replace("_", "-").replace(" ", "")
                return _LICENSE_CODE_TO_STRING.get(key, key)
    return None


def _to_work(item: dict) -> Optional[TextbookWork]:
    title = (item.get("title") or item.get("name") or "").strip()
    if not title:
        logger.info("libretexts item %s skipped: no title", item.get("id"))
        return None
    pdf_url = (
        item.get("pdf_url")
        or item.get("fullpdf")
        or item.get("download_url")
    )
    if not isinstance(pdf_url, str) or not pdf_url:
        logger.info("libretexts item %r skipped: no PDF url", title)
        return None
    page_id = str(item.get("id") or item.get("page_id") or title)
    return TextbookWork(
        source="libretexts",
        source_id=page_id,
        title=title,
        author=item.get("author") or item.get("creator") or None,
        source_uri=item.get("url") or item.get("source_uri") or pdf_url,
        download_url=pdf_url,
        declared_license=_declared_license(item),
        subjects=tuple(
            s for s in (item.get("subjects") or ()) if isinstance(s, str)
        ),
        source_declaration={},
    )


def discover(
    client: ThrottledClient, *, library: Optional[str] = None, limit: int = 25
) -> list[TextbookWork]:
    """Discover LibreTexts books/pages, each carrying its OWN declared license.

    Per-item license resolution is the point: the connector does NOT assume a
    uniform license for the source. Returns up to ``limit`` candidates; an item
    with no title or no PDF is logged and skipped. Network failures raise
    ``SourceError`` for the caller."""
    params = {"library": library} if library else None
    page = client.get_json(LIBRETEXTS_CONTENT_URL, params=params)
    items = page.get("items") or page.get("results") or page.get("pages") or []
    out: list[TextbookWork] = []
    for item in items:
        if len(out) >= limit:
            break
        if not isinstance(item, dict):
            continue
        work = _to_work(item)
        if work is not None:
            out.append(work)
    return out


__all__ = [
    "LIBRETEXTS_CONTENT_URL",
    "discover",
    "ingest_textbook",
    "SourceError",
    "TextbookWork",
    "ThrottledClient",
]
