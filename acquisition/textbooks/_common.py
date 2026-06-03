"""Shared spine for the four open-textbook connectors (SPR-05).

Every textbook connector — OpenStax, LibreTexts, DOAB/OAPEN, MIT OCW — does the
SAME five-step dance:

    discover candidates (per-source metadata)
      -> resolve the DECLARED license string + a source_declaration
      -> classify() (the SPR-02 chokepoint) -> ClassificationResult
      -> fetch the body (throttled, ban-aware: SPR-03) + extraction-quality
         gate (PDF-vs-HTML landing-page reject: SPR-03)
      -> ingest_servable_book(content_class=result.content_class,
                              license_basis=result.license_basis)  (servable
         path -> substrate register_book; SPR-01 staging-DB target)

This module owns the parts that are identical across the four sources: the
throttled/ban-aware HTTP client, the connector-agnostic ``TextbookWork`` record,
and ``ingest_textbook`` — the ONE function that routes a work's declared license
through ``classify()`` and lands it via ``ingest_servable_book``. The
per-source modules only do discovery (read each source's own license field) and
hand a ``TextbookWork`` here.

THE BINDING (load-bearing): ``ingest_textbook`` derives ``content_class`` ONLY
by calling ``acquisition.licenses_core.classify`` and passing the returned
``ClassificationResult.content_class`` + ``.license_basis`` to
``ingest_servable_book``. There is NO other route. NC/ND is never flattened to
``public_domain`` — it routes to whatever class classify() returns. A work whose
license cannot be resolved lands at ``GATED_DEFAULT_CONTENT_CLASS`` (gated),
never servable-by-assumption (§9.0 deny-by-default).

§16 box-bounded: no daemon, no second runtime. All writes go through
``ingest_servable_book`` -> ``runtime.db_lock.connect_write`` (the single
writer). The throttle is the cross-process JSON sentinel under ``~/.antiek/``,
never the DuckDB lock.

Legitimate sources only: all four are open APIs / open repositories. No
shadow-library scraping.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import requests

from acquisition.licenses_core import ClassificationResult, classify

if TYPE_CHECKING:
    from substrate.source_throttle import SourceThrottle as SourceThrottleT

logger = logging.getLogger("acquisition.textbooks")

_USER_AGENT = "Antiek/1.0 (open-textbook acquisition; +https://antiek.ai)"

DEFAULT_MIN_INTERVAL_S = 1.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_TIMEOUT_S = 30.0

# These four sources are open repositories / open APIs, so the legitimacy
# judgment classify() requires is positively True for every textbook fetch.
# (It is keyword-only and has no default in classify(), so it cannot be
# silently omitted.)
LEGITIMATE_SOURCE = True


class SourceError(RuntimeError):
    """A source request failed (after retries) or returned unusable data.
    Caught per-item by the connector batch so one bad work doesn't abort the
    run."""


@dataclass(frozen=True)
class TextbookWork:
    """A discovered open-textbook candidate with everything the ingest path
    needs and the rights provenance counsel reads.

    ``declared_license`` is the license string read FROM THE SOURCE'S OWN
    metadata (a ``creativecommons.org/licenses/...`` URI or a compact code).
    It is passed verbatim to ``classify()`` — the connector never decides the
    content_class itself. ``None`` / empty means the source declared no
    resolvable license, which classify() gates by default.

    ``source_declaration`` is the extra rights context classify() consults
    (e.g. a ``rights_holder`` so a gated work can accrue escrow). For these
    open sources it is usually just ``{}`` — the license string carries the
    signal.
    """

    source: str  # "openstax" | "libretexts" | "doab" | "mit_ocw"
    source_id: str  # source-local stable id (catalog slug / book id / course id)
    title: str
    author: str | None
    source_uri: str  # canonical landing/record URL
    download_url: str  # direct URL to the body we ingest (a PDF)
    declared_license: str | None  # the license string read from source metadata
    isbn: str | None = None
    subjects: Sequence[str] = field(default_factory=tuple)
    source_declaration: Mapping[str, Any] = field(default_factory=dict)

    def classification(self) -> ClassificationResult:
        """Resolve this work's rights through the SPR-02 chokepoint.

        THE binding call site: content_class is derived ONLY here, by
        classify(). The declared license string + source_declaration go in;
        a ClassificationResult (content_class + license_basis + derived
        servable) comes out. The connector obeys it — it does not flatten
        NC/ND to public_domain and does not assume servability.
        """
        return classify(
            self.declared_license,
            dict(self.source_declaration),
            legitimate_source=LEGITIMATE_SOURCE,
        )


class ThrottledClient:
    """Throttled, retrying HTTP client shared by the textbook connectors.

    Mirrors ``acquisition.books.public_domain.SourceClient``'s surface
    (``get_json`` / ``get_bytes``) so the orchestrator + tests inject a fake
    with the same shape — no live HTTP in CI. When a shared
    ``substrate.source_throttle.SourceThrottle`` is supplied, every request
    consults ``before_request(source)`` (raising ``SourceBanned`` while the
    source is banned and enforcing the persisted min-interval across process
    restarts) and a 429/503 arms the cross-process ban sentinel via
    ``note_response`` — the SPR-03 ban-aware path. ``None`` keeps an
    in-process-only timer (the unit tests pass fakes, so they never reach
    this).
    """

    def __init__(
        self,
        *,
        min_interval_s: float = DEFAULT_MIN_INTERVAL_S,
        max_retries: int = DEFAULT_MAX_RETRIES,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        session: requests.Session | None = None,
        persistent: SourceThrottleT | None = None,
        source: str = "textbooks",
    ) -> None:
        self._min_interval_s = min_interval_s
        self._max_retries = max_retries
        self._timeout_s = timeout_s
        self._session = session or requests.Session()
        self._session.headers.update({"User-Agent": _USER_AGENT})
        self._lock = threading.Lock()
        self._last_request_at = 0.0
        self._persistent = persistent
        self._source = source

    def _throttle(self) -> None:
        if self._persistent is not None:
            # Raises SourceBanned while banned; enforces persisted spacing.
            self._persistent.before_request(self._source)
        with self._lock:
            elapsed = time.monotonic() - self._last_request_at
            wait = self._min_interval_s - elapsed
            if wait > 0:
                time.sleep(wait)
            self._last_request_at = time.monotonic()

    def get_json(self, url: str, *, params: dict | None = None) -> dict:
        resp = self._request(url, params=params)
        return resp.json()

    def get_bytes(self, url: str) -> bytes:
        return self._request(url).content

    def _request(self, url: str, *, params: dict | None = None) -> requests.Response:
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            self._throttle()
            try:
                resp = self._session.get(url, params=params, timeout=self._timeout_s)
            except requests.RequestException as exc:
                last_exc = exc
                self._backoff(attempt, reason=str(exc))
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                if self._persistent is not None and resp.status_code in (429, 503):
                    self._persistent.note_response(
                        self._source, resp.status_code, dict(resp.headers)
                    )
                last_exc = SourceError(f"{url} returned {resp.status_code}")
                self._backoff(attempt, reason=f"HTTP {resp.status_code}")
                continue
            if resp.status_code >= 400:
                raise SourceError(f"{url} returned {resp.status_code}")
            return resp
        raise SourceError(
            f"{url} failed after {self._max_retries} attempts"
        ) from last_exc

    def _backoff(self, attempt: int, *, reason: str) -> None:
        delay = min(2.0**attempt, 30.0)
        logger.warning(
            "retrying textbook source request (attempt %d, %s); backoff %.1fs",
            attempt + 1, reason, delay,
        )
        time.sleep(delay)


@dataclass(frozen=True)
class IngestOutcome:
    """Per-work result of an ingest attempt.

    ``content_class`` + ``license_basis`` are the classify() decision, echoed
    so a dry-run can report the rights verdict without re-querying the
    substrate. ``servable_full_text`` is the derived deny-by-default answer.
    A gated work is still INGESTED (chunked/embedded for private search) but
    its body is never served full-text — that is the ``servable_full_text``
    distinction, not a skip.
    """

    work: TextbookWork
    ingested: bool
    content_class: str
    license_basis: str
    servable: bool
    document_id: str | None = None
    servability: str | None = None
    servable_full_text: bool = False
    word_count: int = 0
    skipped_reason: str | None = None


def ingest_textbook(
    work: TextbookWork,
    client: ThrottledClient,
    *,
    investigation_id: str = "inv-textbooks",
    db_path: str | None = None,
    embedder: Any = None,
) -> IngestOutcome:
    """Resolve a textbook's rights via classify(), fetch + gate its body, and
    ingest it through the shared servable-book path.

    THE binding (load-bearing): ``content_class`` is derived ONLY from
    ``classify()`` (via ``work.classification()``); its ``content_class`` and
    ``license_basis`` are the EXACT values handed to ``ingest_servable_book``.
    No other route assigns a content_class.

    Flow:
      1. classify() -> ClassificationResult. ``ingest=False`` (only for a
         circumvented/illegitimate source — never the case for these open
         sources) skips before any fetch.
      2. Fetch the body (throttled, ban-aware via the client's SourceThrottle).
      3. SPR-03 extraction-quality gate: ``assert_pdf`` rejects an HTML landing
         page (bytes starting ``b'<!DO'``) BEFORE the body reaches the reader.
      4. ``ingest_servable_book(content_class=result.content_class,
         license_basis=result.license_basis)`` — the servable path; a servable
         class serves full text, a gated class is chunked/embedded but withheld.

    All fetch/extraction failures are caught and returned as a skip outcome so
    one bad work never aborts the batch. Writes go through
    ``ingest_servable_book`` -> ``connect_write`` only; this function never
    opens a write connection.
    """
    from acquisition.books.adapter import ingest_servable_book
    from acquisition.openaccess.pdf_detect import NotAPdf, assert_pdf

    result = work.classification()

    # A non-ingestible verdict (only ever a circumvented/illegitimate source —
    # impossible for these open repositories, but obeyed faithfully).
    if not result.ingest:
        return IngestOutcome(
            work=work,
            ingested=False,
            content_class=result.content_class,
            license_basis=result.license_basis,
            servable=result.servable,
            skipped_reason="classify_skip: " + result.rationale,
        )

    # Fetch the body (throttled + ban-aware).
    try:
        raw = client.get_bytes(work.download_url)
    except SourceError as exc:
        return IngestOutcome(
            work=work,
            ingested=False,
            content_class=result.content_class,
            license_basis=result.license_basis,
            servable=result.servable,
            skipped_reason=f"download_failed: {exc}",
        )
    if not raw:
        return IngestOutcome(
            work=work,
            ingested=False,
            content_class=result.content_class,
            license_basis=result.license_basis,
            servable=result.servable,
            skipped_reason="empty_download",
        )

    # SPR-03 extraction-quality gate: reject an HTML landing page masquerading
    # as a PDF (bytes start b'<!DO') BEFORE it reaches the reader. parse_check
    # is False here so the cheap header/magic-byte sniff runs even when pypdf is
    # absent; the adapter's own reader still validates the real PDF body.
    try:
        assert_pdf(raw, url=work.download_url, parse_check=False)
    except NotAPdf as exc:
        return IngestOutcome(
            work=work,
            ingested=False,
            content_class=result.content_class,
            license_basis=result.license_basis,
            servable=result.servable,
            skipped_reason=f"not_a_pdf: {exc}",
        )

    # Ingest through the shared servable path. The classify() decision —
    # content_class AND license_basis — is passed EXPLICITLY; this is the one
    # and only place the class reaches the substrate.
    try:
        ingest_result = ingest_servable_book(
            raw,
            investigation_id=investigation_id,
            content_class=result.content_class,
            license_basis=result.license_basis,
            rights_holder_name=_rights_holder_name(work),
            provenance=work.source_uri,
            source_uri=work.source_uri,
            db_path=db_path,
            embedder=embedder,
        )
    except Exception as exc:  # corrupt/unreadable PDF: fail this item, not batch
        return IngestOutcome(
            work=work,
            ingested=False,
            content_class=result.content_class,
            license_basis=result.license_basis,
            servable=result.servable,
            skipped_reason=f"ingest_failed: {exc}",
        )

    if ingest_result.ingest.skipped_reason:
        return IngestOutcome(
            work=work,
            ingested=False,
            content_class=result.content_class,
            license_basis=result.license_basis,
            servable=result.servable,
            document_id=ingest_result.document_id,
            skipped_reason=f"extract_{ingest_result.ingest.skipped_reason}",
        )

    return IngestOutcome(
        work=work,
        ingested=True,
        content_class=result.content_class,
        license_basis=result.license_basis,
        servable=result.servable,
        document_id=ingest_result.document_id,
        servability=ingest_result.servability,
        servable_full_text=ingest_result.servable_full_text,
        word_count=ingest_result.ingest.word_count,
    )


def _rights_holder_name(work: TextbookWork) -> str | None:
    """The rights-holder name to thread onto a GATED work's escrow seam, when
    the source declared one. Public-domain / source-declared-open works carry
    no rights holder to onboard; an NC/ND gated work may name one so escrow
    accrues to a pre-onboarded holder (the existing ip_holders seam — allowed).
    Never closes a money gate (G2/G3); accrual is not disbursement."""
    decl = work.source_declaration or {}
    holder = decl.get("rights_holder") or decl.get("rights_holder_name")
    return str(holder) if holder else None
