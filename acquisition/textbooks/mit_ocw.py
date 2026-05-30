"""MIT OpenCourseWare open-textbook connector (SPR-05 M5).

MIT OpenCourseWare publishes course materials uniformly under **CC-BY-NC-SA** —
the canonical NC test for this sprint. This connector reads the course's
declared CC-BY-NC-SA license and routes it through ``classify()`` (the SPR-02
chokepoint), then OBEYS whatever class comes back. It does NOT decide the NC/ND
policy: if SPR-02 maps NC-SA to a servable-with-attribution class the work is
servable; if to gated, the body is withheld. The test asserts whatever
classify() actually returns and FAILS if it is ever ``public_domain``.

This milestone is the load-bearing proof that the NC nuance is honored
end-to-end: the connector passes the declared ``CC-BY-NC-SA`` string to
classify() and never flattens it.

Compose, do not reimplement: shared ``ThrottledClient`` (SPR-03 ban-aware),
``classify()`` (SPR-02), ``ingest_textbook`` -> ``ingest_servable_book``
(SPR-01 staging), dedup on the course id / content-hash (SPR-04, orchestrator).
"""

from __future__ import annotations

import logging
from typing import Optional

from ._common import SourceError, TextbookWork, ThrottledClient, ingest_textbook

logger = logging.getLogger("acquisition.textbooks.mit_ocw")

# MIT OCW's public search API (the documented open-courseware listing endpoint).
# Tests inject a fake client, so no live host is contacted in CI.
MIT_OCW_SEARCH_URL = "https://ocw.mit.edu/api/v0/search/"

# MIT OCW is uniformly CC-BY-NC-SA 4.0. We still READ the per-course declared
# license field (never hardcode the class) so a course that ever carried a
# different license is resolved honestly; this canonical URI is the fallback
# only when a record omits the field.
_OCW_DEFAULT_LICENSE = "https://creativecommons.org/licenses/by-nc-sa/4.0/"


def _declared_license(course: dict) -> Optional[str]:
    """Read the course's DECLARED license, preferring the record's own field.

    Falls back to the canonical CC-BY-NC-SA URI only when the record omits a
    license string — OCW's site-wide license. Returned verbatim for classify()
    to resolve; the connector never assigns the class itself."""
    for key in ("license", "license_url", "license_cc"):
        val = course.get(key)
        if isinstance(val, dict):
            val = val.get("url") or val.get("name")
        if isinstance(val, str) and val.strip():
            return val.strip()
    return _OCW_DEFAULT_LICENSE


def _pdf_url(course: dict) -> Optional[str]:
    """The course's textbook/material PDF URL."""
    for key in ("pdf_url", "resource_pdf_url", "download_url"):
        url = course.get(key)
        if isinstance(url, str) and url:
            return url
    return None


def _to_work(course: dict) -> Optional[TextbookWork]:
    title = (course.get("title") or course.get("course_title") or "").strip()
    if not title:
        logger.info("mit_ocw course %s skipped: no title", course.get("id"))
        return None
    pdf_url = _pdf_url(course)
    if not pdf_url:
        logger.info("mit_ocw course %r skipped: no PDF url", title)
        return None
    course_id = str(course.get("id") or course.get("course_id") or title)
    instructors = course.get("instructors") or course.get("authors") or []
    if isinstance(instructors, list):
        author = "; ".join(str(i) for i in instructors if i) or None
    else:
        author = str(instructors) if instructors else None
    return TextbookWork(
        source="mit_ocw",
        source_id=course_id,
        title=title,
        author=author,
        source_uri=course.get("url") or f"https://ocw.mit.edu/courses/{course_id}/",
        download_url=pdf_url,
        declared_license=_declared_license(course),
        subjects=tuple(
            s for s in (course.get("topics") or course.get("subjects") or ())
            if isinstance(s, str)
        ),
        # CC-BY-NC-SA gates (per the current SPR-02 map): name MIT as the
        # rights holder so a gated course can accrue escrow on the existing
        # ip_holders seam (accrual is not disbursement; no money gate touched).
        source_declaration={"rights_holder": "MIT OpenCourseWare"},
    )


def discover(
    client: ThrottledClient, *, query: Optional[str] = None, limit: int = 25
) -> list[TextbookWork]:
    """Discover MIT OCW course materials, each carrying its declared
    CC-BY-NC-SA license. Returns up to ``limit`` candidates; a record with no
    title or no PDF is logged and skipped. Network failures raise
    ``SourceError`` for the caller."""
    params = {"q": query} if query else None
    page = client.get_json(MIT_OCW_SEARCH_URL, params=params)
    items = page.get("results") or page.get("items") or page.get("courses")
    if not items and isinstance(page.get("hits"), dict):
        items = page["hits"].get("hits")
    if not isinstance(items, list):
        items = []
    out: list[TextbookWork] = []
    for course in items:
        if len(out) >= limit:
            break
        if not isinstance(course, dict):
            continue
        # ES-style hits wrap the doc in ``_source``.
        doc = course.get("_source") if isinstance(course.get("_source"), dict) else course
        work = _to_work(doc)
        if work is not None:
            out.append(work)
    return out


__all__ = [
    "MIT_OCW_SEARCH_URL",
    "discover",
    "ingest_textbook",
    "SourceError",
    "TextbookWork",
    "ThrottledClient",
]
