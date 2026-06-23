"""Open-access resolved-item → substrate ingest (SPR-03 M5).

Routes a resolved OA full-text item (a DOI + best-OA PDF URL + license
verdict) through the shared servable-book path
(``acquisition.books.ingest_servable_book`` -> substrate's deny-by-default
``register_book``), so the OA channel has the SAME single home for the legal
classification as arXiv. There is no parallel ingest path.

The flow mirrors ``acquisition.arxiv.adapter.ingest_paper_with_rights``:
resolve license -> build a ``license_basis`` audit string naming source +
license + how determined -> fetch PDF -> ingest with the resolved
content_class passed EXPLICITLY (so a gated item is an auditable decision,
not a silent None).
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass

from processing.embedding.embed import EmbeddingProvider

from .licenses import LicenseResolution, license_basis_string

logger = logging.getLogger(__name__)

# An arXiv PDF URL is ``https://arxiv.org/pdf/<id>`` (optionally ``v<n>`` and/or a
# ``.pdf`` suffix). When the OA channel's resolved ``pdf_url`` is such a URL, the
# servable body we just landed is an arXiv-mirrored work fetched FROM an arXiv host
# — so its compliance trace needs the ``arxiv.fetch`` leg keyed by that arXiv id,
# exactly like the native arXiv adapter path.
_ARXIV_PDF_ID_RE = re.compile(
    r"^https?://(?:[a-z0-9.-]+\.)?arxiv\.org/(?:pdf|abs)/(?P<id>[^?#]+?)(?:\.pdf)?/?$",
    re.IGNORECASE,
)


def _arxiv_id_from_pdf_url(pdf_url: str) -> str | None:
    """Extract the arXiv id from an ``arxiv.org/pdf/<id>`` (or ``/abs/<id>``) URL,
    or ``None`` when the URL is not an arXiv host. The id keeps its version suffix
    (``2401.00001v2``) — the same surface ``trace`` is keyed by. Used only to
    label the OA fetch-audit leg; never to gate fetching (that is host-based in
    ``govern_if_arxiv``)."""
    m = _ARXIV_PDF_ID_RE.match(pdf_url.strip())
    if not m:
        return None
    arxiv_id = m.group("id").strip().strip("/")
    return arxiv_id or None


def _record_oa_arxiv_fetch_audit(
    *,
    db_path: str | None,
    arxiv_id: str,
    document_id: str,
    source_url: str,
    pdf_bytes: bytes,
) -> None:
    """SPR-09 M4 (round-4) — emit the ``arxiv.fetch`` leg when the OA channel
    lands an arXiv-HOST servable body.

    An OA ingest of an arXiv-mirrored work fetches ``arxiv.org/pdf/<id>`` and
    stores a servable body — the SAME ToS-relevant event the native adapter path
    audits, just reached via the OA resolver. So ``trace(con, arxiv_id)`` must
    show this fetch leg too, or the compliance trace is blind to OA-sourced arXiv
    fetches.

    Defensively isolated (mirrors ``adapter._record_fetch_audit``): a failure here
    must NEVER break the OA ingest, so the whole body is wrapped + logged. The
    audit takes its OWN write lock. §9.0: provenance refs ONLY (source_url /
    sha256 / byte_size) — never the body."""
    try:
        from runtime.db_lock import connect_write
        from substrate.audit.arxiv_audit import ARXIV_FETCH, record_event
        from substrate.graph import default_db_path, ensure_initialized

        resolved = ensure_initialized(db_path or default_db_path())
        con = connect_write(resolved, purpose="oa_arxiv_fetch_audit")
        try:
            record_event(
                con,
                arxiv_id=arxiv_id,
                document_id=document_id,
                kind=ARXIV_FETCH,
                detail={
                    "source_url": source_url,
                    "sha256": hashlib.sha256(pdf_bytes).hexdigest(),
                    "byte_size": len(pdf_bytes),
                    "via": "openaccess",
                },
            )
        finally:
            con.close()
    except Exception:
        logger.exception(
            "oa arxiv_audit fetch-leg failed for arxiv_id=%s; OA ingest unaffected",
            arxiv_id,
        )

# OA full text from publisher/repository sources is peer-reviewed primary or
# repository copies; tier 2 matches the books default (higher signal than web,
# below an explicitly-curated tier-1 set). Caller can override.
DEFAULT_OA_SOURCE_TIER = 2

# arxiv_id -> not relevant; OA fetchers take a PDF URL.
PdfUrlFetcher = Callable[[str], bytes]


@dataclass(frozen=True)
class OAIngestResult:
    """What ``ingest_oa_item`` returns. ``servable_full_text`` is the derived
    deny-by-default answer; ``content_class`` + ``license_basis`` are echoed
    so a dry-run can report the decision without re-querying the substrate."""

    document_id: str
    content_class: str
    redistributable: bool
    servability: str
    servable_full_text: bool
    doi: str | None
    license_uri: str | None
    license_basis: str


def build_license_basis(
    resolution: LicenseResolution, *, source: str, how: str
) -> str:
    """Compose the OA ``license_basis`` audit string: it names the SOURCE +
    license + HOW the license was determined, e.g.
    "Unpaywall best-OA-location; CC BY (...); per best_oa_location.license".
    Wraps the shared ``license_basis_string`` (which states the license/why)
    with the source-provenance prefix."""
    return f"{source}; {how}; {license_basis_string(resolution)}"


def ingest_oa_item(
    *,
    investigation_id: str,
    doi: str | None,
    pdf_url: str,
    resolution: LicenseResolution,
    license_basis: str,
    source_uri: str | None = None,
    pdf_bytes: bytes | None = None,
    fetch_pdf: PdfUrlFetcher | None = None,
    source_tier: int = DEFAULT_OA_SOURCE_TIER,
    db_path: str | None = None,
    embedder: EmbeddingProvider | None = None,
) -> OAIngestResult:
    """Ingest one resolved OA item's full text through the shared servable
    path, gated on ``resolution``.

    ``pdf_bytes`` short-circuits the fetch (CI passes fixture bytes). When
    omitted, ``fetch_pdf(pdf_url)`` is called. The resolved ``content_class``
    is passed EXPLICITLY so a gated item lands as an auditable decision.
    """
    from acquisition.books.adapter import ingest_servable_book

    if pdf_bytes is None:
        if fetch_pdf is None:
            raise ValueError("ingest_oa_item needs pdf_bytes or fetch_pdf")
        pdf_bytes = fetch_pdf(pdf_url)
    if not pdf_bytes:
        # An empty PDF would land a 0-word husk that looks like a rights
        # decision; surface the fetch failure instead.
        raise ValueError(
            f"empty PDF bytes for {doi or pdf_url} — fetch failed or the OA "
            "URL was a landing page, not a PDF"
        )

    result = ingest_servable_book(
        pdf_bytes,
        investigation_id=investigation_id,
        content_class=resolution.content_class,
        license_basis=license_basis,
        source_uri=source_uri or pdf_url,
        source_tier=int(source_tier),
        provenance=pdf_url,
        db_path=db_path,
        embedder=embedder,
    )

    # SPR-09 M4 (round-4) — when the OA channel landed an arXiv-HOST servable
    # body (``pdf_url`` is arxiv.org/pdf/<id>), emit the ``arxiv.fetch`` leg so
    # the paper's compliance trace records the OA-sourced arXiv fetch too. Only
    # when the body is genuinely servable (a redistributable store), mirroring the
    # adapter path's "gated → no fetch leg" guard. A non-arXiv OA ingest derives
    # no arxiv_id and emits no arXiv leg. Defensively isolated; §9.0 refs-only.
    arxiv_id = _arxiv_id_from_pdf_url(pdf_url)
    if arxiv_id and result.servable_full_text:
        _record_oa_arxiv_fetch_audit(
            db_path=db_path,
            arxiv_id=arxiv_id,
            document_id=result.document_id,
            source_url=pdf_url,
            pdf_bytes=pdf_bytes,
        )

    return OAIngestResult(
        document_id=result.document_id,
        content_class=resolution.content_class,
        redistributable=resolution.redistributable,
        servability=result.servability,
        servable_full_text=result.servable_full_text,
        doi=doi,
        license_uri=resolution.license_uri,
        license_basis=license_basis,
    )
