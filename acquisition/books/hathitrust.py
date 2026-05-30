"""HathiTrust public-domain connector — rights-code filter (SPR-06 M5).

HathiTrust, like Internet Archive, mixes public-domain and in-copyright works.
The HathiTrust Bibliographic API exposes a per-item **rights code** that is the
authoritative PD signal:

  * ``pd`` / ``pdus`` → public domain → servable;
  * ``ic`` / ``icus`` / ``und`` (in-copyright / undetermined) → NOT public
    domain → gated or skip, never servable;
  * any UNRECOGNIZED code → treated as undetermined → gated (deny-by-default;
    an unknown code is never rounded up to servable).

The rights-code → classify-input mapping lives in one function
(:func:`hathi_rights_input`); the servable/gated/skip verdict is the SPR-02
chokepoint's, not a local boolean. The bib record's OCLC/ISBN drives the SPR-04
dedup key when present (so a HathiTrust PD work and the same work from another
source collapse to one document); otherwise the HathiTrust item id (``htid``).

NO raw ``requests``/``httpx``: every fetch is via the SPR-03 throttle.
"""

from __future__ import annotations

import logging
from typing import Optional

from .pd_connector_base import BookCandidate, ThrottledFetcher

logger = logging.getLogger("acquisition.books.hathitrust")

SOURCE = "hathitrust"
# HathiTrust Bibliographic API (volumes/brief by record id / oclc / etc.).
BIB_API_BASE = "https://catalog.hathitrust.org/api/volumes/brief"
# Public-domain page-image/text delivery (Data API requires a key in prod; the
# connector treats the body as a PDF download whose URL is recorded — fixtures
# supply the bytes, and a real run uses the operator's keyed endpoint).
PT_DOWNLOAD_BASE = "https://babel.hathitrust.org/cgi/imgsrv/download/pdf"

# Rights codes that POSITIVELY establish public domain.
_PD_RIGHTS_CODES = frozenset({"pd", "pdus"})
# Rights codes that explicitly do NOT (in-copyright / undetermined). Listed so
# the mapping is exhaustive + auditable; functionally identical to "not in the
# PD set" because of deny-by-default, but naming them documents intent.
_NON_PD_RIGHTS_CODES = frozenset({"ic", "icus", "und", "nobody", "pdus-land"})


def hathi_rights_input(rights_code: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """THE one rights-code → classify-input mapping. Returns (license_uri,
    pd_signal). ``pd``/``pdus`` → a positive pd_signal (classify resolves
    public_domain); everything else (including UNRECOGNIZED codes) → (None,
    None) → classify() gates it. Deny-by-default: an unknown code is never
    servable."""
    code = (rights_code or "").strip().lower()
    if code in _PD_RIGHTS_CODES:
        return None, f"HathiTrust rights={code}"
    # ic / icus / und / unknown -> no PD signal -> classify() gates.
    return None, None


def _normalize_bib_item(item: dict) -> Optional[dict]:
    """Pull (htid, rights_code) out of a HathiTrust bib 'items' entry."""
    htid = item.get("htid") or item.get("fromRecord")
    rights = item.get("rightsCode") or item.get("rights")
    if not htid:
        return None
    return {"htid": str(htid), "rights": rights}


def candidate_from_bib(record: dict, *, record_id: str) -> Optional[BookCandidate]:
    """Build a candidate from one HathiTrust bib record. The record's first
    item's rights code drives :func:`hathi_rights_input`; OCLC/ISBN from the bib
    record drive dedup. A non-PD record still becomes a candidate (gated by
    classify at ingest) so the negative branch is testable."""
    records = record.get("records") or {}
    items = record.get("items") or []
    bib = records.get(record_id) or (next(iter(records.values()), {}) if records else {})

    norm_items = [n for n in (_normalize_bib_item(i) for i in items) if n]
    if not norm_items:
        logger.info("hathitrust record %s skipped: no items", record_id)
        return None
    first = norm_items[0]
    license_uri, pd_signal = hathi_rights_input(first.get("rights"))

    title = (bib.get("titles") or [None])[0] if isinstance(bib.get("titles"), list) else bib.get("title")
    title = (title or record_id).strip() if isinstance(title, str) else str(record_id)
    isbns = bib.get("isbns") or []
    oclcs = bib.get("oclcs") or []
    isbn = isbns[0] if isbns else None
    oclc = str(oclcs[0]) if oclcs else None
    htid = first["htid"]

    return BookCandidate(
        source=SOURCE,
        source_id=f"{SOURCE}:{htid}",
        title=title,
        author=None,
        source_uri=f"https://catalog.hathitrust.org/Record/{record_id}",
        download_url=f"{PT_DOWNLOAD_BASE}?id={htid}",
        download_format="pdf",
        license_uri=license_uri,
        pd_signal=pd_signal,
        isbn=isbn,
        oclc=oclc,
        subjects=tuple(),
    )


def discover(
    fetcher: ThrottledFetcher,
    *,
    record_ids: Optional[list[str]] = None,
    limit: int = 25,
) -> list[BookCandidate]:
    """Discover candidates from the HathiTrust Bibliographic API by record id.

    Tested against a recorded fixture. Each record's rights code is mapped to
    the classify() input; the servable/gated verdict is classify()'s at ingest
    (pd/pdus → servable, ic/icus/und/unknown → gated)."""
    ids = list(record_ids or [])[:limit]
    out: list[BookCandidate] = []
    for record_id in ids:
        if len(out) >= limit:
            break
        record = fetcher.get_json(f"{BIB_API_BASE}/recordnumber/{record_id}.json")
        cand = candidate_from_bib(record, record_id=record_id)
        if cand is not None:
            out.append(cand)
    return out
