"""Internet Archive public-domain connector — deny-by-default filter (SPR-06 M4).

Internet Archive hosts BOTH public-domain and in-copyright works. A connector
that marked everything it found as ``public_domain`` would serve pirated full
text the moment one in-copyright item slipped in — the single catastrophic
failure §9.0 exists to prevent. So PD status is **positively established per
item** from the IA metadata, and the verdict is delegated to the SPR-02 rights
chokepoint, never a local boolean.

Two-layer PD filter (rigor #3, defence in depth):

  * **Layer 1 — discovery query.** :func:`advancedsearch` constrains the IA
    advancedsearch query to ``possible-copyright-status:NOT_IN_COPYRIGHT`` so
    the candidate set is PD-biased at the source.
  * **Layer 2 — per-item re-check.** :func:`item_candidate` re-reads the item's
    OWN metadata (a discovery query can return stale/mis-tagged records) and
    re-derives the rights input for classify() from one mapping function
    (:func:`ia_rights_input`). An item whose PD status is NOT re-established
    drops to license_uri=None/pd_signal=None → classify() GATES it
    (``restricted_pending_opt_in``, body withheld) — never servable.

PD is established from, in order: a ``licenseurl`` pointing at a CC0/PDM /
``/publicdomain/`` mark (a concrete license URI classify() resolves to
``public_domain``); else ``possible-copyright-status = NOT_IN_COPYRIGHT``; else
a ``rights`` field that explicitly asserts public domain (no negation, no
©+year). "No copyright flag" is NOT public domain — it is undetermined → gated.

NO raw ``requests``/``httpx``: every fetch is via the SPR-03 throttle.
"""

from __future__ import annotations

import logging
import re

from .pd_connector_base import BookCandidate, ThrottledFetcher

logger = logging.getLogger("acquisition.books.internet_archive")

SOURCE = "internet_archive"
ADVANCEDSEARCH_URL = "https://archive.org/advancedsearch.php"
METADATA_BASE = "https://archive.org/metadata"
DOWNLOAD_BASE = "https://archive.org/download"

# Layer-1 discovery constraint: only items IA itself flags NOT_IN_COPYRIGHT.
PD_QUERY_FILTER = "possible-copyright-status:(NOT_IN_COPYRIGHT)"

# A licenseurl substring that classify()'s canonical CC table recognizes as a
# public-domain mark. When present we hand the URL straight to classify().
_PD_LICENSE_URL_TOKENS = (
    "creativecommons.org/publicdomain/zero",  # CC0
    "creativecommons.org/publicdomain/mark",  # PDM
    "/publicdomain/",
)
# Tokens in a free-text rights/licenseurl field accepted as an explicit PD
# assertion (only when no negation / copyright claim is present).
_PD_RIGHTS_TOKENS = (
    "public domain",
    "publicdomain",
    "no known copyright",
)
# Deny-first: any of these in the free text disqualifies the item BEFORE a PD
# token can accept it. Broad on purpose — a false negation only conservatively
# GATES a genuinely-PD item (chunked/embedded for private search, body
# withheld), the §9.0-safe direction; the catastrophic error is the reverse.
_NEGATIVE_TOKENS = (
    "all rights reserved",
    "rights reserved",
    "in copyright",
    "in-copyright",
    "copyrighted",
    "under copyright",
    "permission required",
    "not in the public domain",
    "not in public domain",
    "not public domain",
)
_NEGATED_PD_RE = re.compile(
    r"\b(?:not|no|isn't|is not)\s+(?:in\s+(?:the\s+)?)?public\s+domain"
)
# Any ©/(c) symbol, "copyright <year>", or a hedged copyright assertion
# ("may be / still / possibly under/protected by copyright") denies PD even if
# a "public domain" substring is also present — the higher-cost false positive.
_COPYRIGHT_CLAIM_RE = re.compile(
    r"©|\bcopyright\s+(?:\(c\)\s*)?\d{4}|\(c\)\s*\d{4}"
    r"|\b(?:may\s+be|still|possibly|likely)\s+(?:in\s+|under\s+|protected\s+by\s+)?copyright"
)


def _as_list(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value]
    return []


def ia_rights_input(meta: dict) -> tuple[str | None, str | None]:
    """THE one IA-status → classify-input mapping. Returns (license_uri,
    pd_signal); both None when PD is NOT established → classify() gates.

    Single audited place for the IA rights decision (rigor #3): the discovery
    layer and the per-item re-check both call this, so the gate logic lives
    once. Deny-by-default: any explicit copyright claim / negated-PD phrase
    disqualifies the item before a PD token can accept it.
    """
    license_urls = _as_list(meta.get("licenseurl"))
    rights_fields = _as_list(meta.get("rights"))
    status_fields = _as_list(meta.get("possible-copyright-status"))
    haystack = " ".join(license_urls + rights_fields + status_fields).lower()

    if any(tok in haystack for tok in _NEGATIVE_TOKENS):
        return None, None
    if _NEGATED_PD_RE.search(haystack):
        return None, None
    if _COPYRIGHT_CLAIM_RE.search(haystack):
        return None, None

    # 1. A concrete PD license URL → hand it to classify() (resolves PDM/CC0).
    for url in license_urls:
        if any(tok in url.lower() for tok in _PD_LICENSE_URL_TOKENS):
            return url, None

    # 2. IA's normalized copyright-status flag.
    if any("not_in_copyright" in s.lower() for s in status_fields):
        return None, (
            "Internet Archive metadata possible-copyright-status="
            "NOT_IN_COPYRIGHT"
        )

    # 3. A free-text rights field that explicitly asserts PD.
    if any(tok in haystack for tok in _PD_RIGHTS_TOKENS):
        asserted = "; ".join(f for f in (rights_fields + license_urls) if f)
        return None, (
            f"Internet Archive item rights field asserts public domain "
            f"({asserted})"
        )

    # 4. Undetermined — no positively-established PD status. Deny-by-default.
    return None, None


def _pdf_download_url(identifier: str, files) -> str | None:
    for f in files or []:
        name = f.get("name", "")
        if isinstance(name, str) and name.lower().endswith(".pdf"):
            return f"{DOWNLOAD_BASE}/{identifier}/{name}"
    return None


def item_candidate(
    fetcher: ThrottledFetcher, identifier: str
) -> BookCandidate | None:
    """Layer-2 per-item re-check: read the item's own metadata, re-derive the
    rights input via :func:`ia_rights_input`, and build a candidate. An item
    without a PDF file is skipped (None); an item without established PD status
    still becomes a candidate (license_uri=None/pd_signal=None) so classify()
    GATES it at ingest — the negative branch the tests pin."""
    record = fetcher.get_json(f"{METADATA_BASE}/{identifier}")
    meta = record.get("metadata") or {}
    license_uri, pd_signal = ia_rights_input(meta)

    pdf_url = _pdf_download_url(identifier, record.get("files"))
    if pdf_url is None:
        logger.info("internet_archive item %s skipped: no PDF file", identifier)
        return None

    title = (meta.get("title") or identifier)
    if isinstance(title, list):
        title = "; ".join(str(t) for t in title)
    title = str(title).strip()
    creator = meta.get("creator")
    if isinstance(creator, list):
        creator = "; ".join(str(c) for c in creator)

    return BookCandidate(
        source=SOURCE,
        source_id=f"{SOURCE}:{identifier}",
        title=title,
        author=str(creator) if creator else None,
        source_uri=f"https://archive.org/details/{identifier}",
        download_url=pdf_url,
        download_format="pdf",
        license_uri=license_uri,
        pd_signal=pd_signal,
        subjects=tuple(),
    )


def advancedsearch(
    fetcher: ThrottledFetcher,
    *,
    query: str | None = None,
    limit: int = 25,
) -> list[str]:
    """Layer-1 discovery: IA advancedsearch constrained to NOT_IN_COPYRIGHT.

    Returns identifiers (not candidates) — the per-item layer-2 re-check
    (:func:`item_candidate`) is what re-establishes PD before ingest. Tested
    against a recorded fixture."""
    q = PD_QUERY_FILTER
    if query:
        q = f"({query}) AND {PD_QUERY_FILTER}"
    data = fetcher.get_json(
        ADVANCEDSEARCH_URL,
        params={
            "q": q,
            "fl[]": "identifier",
            "rows": str(limit),
            "output": "json",
            "mediatype": "texts",
        },
    )
    docs = ((data.get("response") or {}).get("docs")) or []
    return [d["identifier"] for d in docs if d.get("identifier")][:limit]


def discover(
    fetcher: ThrottledFetcher,
    *,
    query: str | None = None,
    limit: int = 25,
) -> list[BookCandidate]:
    """Discover up to ``limit`` IA candidates: layer-1 NOT_IN_COPYRIGHT query
    → layer-2 per-item rights re-check. The servable/gated verdict is
    classify()'s at ingest; an item that fails the re-check comes back gated,
    never servable. Tested against recorded fixtures."""
    identifiers = advancedsearch(fetcher, query=query, limit=limit)
    out: list[BookCandidate] = []
    for ident in identifiers:
        if len(out) >= limit:
            break
        cand = item_candidate(fetcher, ident)
        if cand is not None:
            out.append(cand)
    return out
