"""Library of Congress public-domain connector (SPR-06 M5).

The Library of Congress exposes its digital collections via the loc.gov JSON
API. Many items are public domain (US government works, expired copyright,
explicit "no known copyright" rights statements), but LoC also hosts items with
rights restrictions, so PD is established **per item from the rights
statement**, not assumed.

PD establishment, in order:

  * a ``rights`` URL pointing at a CC0/PDM / ``/publicdomain/`` mark → a
    concrete license URI handed to classify() (resolves ``public_domain``);
  * else a rights statement that explicitly asserts no known copyright / public
    domain (no negation, no ©+year) → a positive pd_signal naming the
    statement.

An unclear / blank / restrictive rights statement → license_uri=None,
pd_signal=None → classify() gates it (deny-by-default). The LCCN drives the
SPR-04 dedup source-id. The servable/gated verdict is the SPR-02 chokepoint's.

NO raw ``requests``/``httpx``: every fetch is via the SPR-03 throttle.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from .pd_connector_base import BookCandidate, ThrottledFetcher

logger = logging.getLogger("acquisition.books.library_of_congress")

SOURCE = "library_of_congress"
LOC_SEARCH_BASE = "https://www.loc.gov"

_PD_LICENSE_URL_TOKENS = (
    "creativecommons.org/publicdomain/zero",
    "creativecommons.org/publicdomain/mark",
    "/publicdomain/",
)
_PD_RIGHTS_TOKENS = (
    "no known copyright",
    "public domain",
    "no copyright restriction",
    "rights status: free to use",
)
_NEGATIVE_TOKENS = (
    "all rights reserved",
    "in copyright",
    "copyrighted",
    "rights restricted",
    "permission required",
    "not in the public domain",
)
_NEGATED_PD_RE = re.compile(
    r"\b(?:not|no|isn't|is not)\s+(?:in\s+(?:the\s+)?)?public\s+domain"
)
_COPYRIGHT_CLAIM_RE = re.compile(
    r"©|\bcopyright\s+(?:\(c\)\s*)?\d{4}|\(c\)\s*\d{4}"
)


def _rights_strings(item: dict) -> list[str]:
    out: list[str] = []
    for key in ("rights", "rights_information", "rights_advisory"):
        val = item.get(key)
        if isinstance(val, str):
            out.append(val)
        elif isinstance(val, list):
            out.extend(str(v) for v in val)
        elif isinstance(val, dict):
            out.extend(str(v) for v in val.values())
    return out


def loc_rights_input(item: dict) -> tuple[Optional[str], Optional[str]]:
    """THE one LoC rights-statement → classify-input mapping. Returns
    (license_uri, pd_signal); both None when PD is NOT established → classify()
    gates. Deny-by-default: an explicit copyright claim / negated-PD phrase /
    restriction disqualifies the item before a PD token can accept it."""
    rights = _rights_strings(item)
    haystack = " ".join(rights).lower()

    if any(tok in haystack for tok in _NEGATIVE_TOKENS):
        return None, None
    if _NEGATED_PD_RE.search(haystack):
        return None, None
    if _COPYRIGHT_CLAIM_RE.search(haystack):
        return None, None

    for r in rights:
        if any(tok in r.lower() for tok in _PD_LICENSE_URL_TOKENS):
            return r, None

    if any(tok in haystack for tok in _PD_RIGHTS_TOKENS):
        stmt = "; ".join(s for s in rights if s)
        return None, f"Library of Congress rights statement: {stmt}"

    return None, None


def _pdf_url(item: dict) -> Optional[str]:
    """Find a PDF resource URL on a loc.gov item record."""
    for res in item.get("resources") or []:
        if not isinstance(res, dict):
            continue
        pdf = res.get("pdf") or res.get("fulltext_file")
        if isinstance(pdf, str) and pdf:
            return pdf
    # Some records expose a top-level 'pdf' field.
    pdf = item.get("pdf")
    return pdf if isinstance(pdf, str) and pdf else None


def item_to_candidate(item: dict) -> Optional[BookCandidate]:
    """Build a candidate from one loc.gov item record. A non-PD/unclear rights
    statement still yields a candidate (gated by classify at ingest) so the
    negative branch is testable; an item with no PDF resource is skipped."""
    pdf_url = _pdf_url(item)
    if not pdf_url:
        logger.info("loc item %s skipped: no PDF resource", item.get("id"))
        return None

    license_uri, pd_signal = loc_rights_input(item)

    title = item.get("title") or item.get("id") or "Library of Congress item"
    if isinstance(title, list):
        title = "; ".join(str(t) for t in title)
    lccn = None
    numbers = item.get("number_lccn") or item.get("lccn")
    if isinstance(numbers, list) and numbers:
        lccn = str(numbers[0])
    elif isinstance(numbers, str):
        lccn = numbers
    item_id = lccn or str(item.get("id") or title)

    return BookCandidate(
        source=SOURCE,
        source_id=f"{SOURCE}:{item_id}",
        title=str(title).strip(),
        author=None,
        source_uri=str(item.get("url") or item.get("id") or LOC_SEARCH_BASE),
        download_url=pdf_url,
        download_format="pdf",
        license_uri=license_uri,
        pd_signal=pd_signal,
        subjects=tuple(),
    )


def discover(
    fetcher: ThrottledFetcher,
    *,
    collection: str = "selected-digitized-books",
    limit: int = 25,
) -> list[BookCandidate]:
    """Discover candidates from a loc.gov collection JSON listing.

    Tested against a recorded fixture. PD is established per item from its
    rights statement; the servable/gated verdict is classify()'s at ingest (an
    unclear-rights item comes back gated)."""
    data = fetcher.get_json(
        f"{LOC_SEARCH_BASE}/collections/{collection}/",
        params={"fo": "json", "c": str(limit)},
    )
    results = data.get("results") or []
    out: list[BookCandidate] = []
    for item in results:
        if len(out) >= limit:
            break
        cand = item_to_candidate(item)
        if cand is not None:
            out.append(cand)
    return out
