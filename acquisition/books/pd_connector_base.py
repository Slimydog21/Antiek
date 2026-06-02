"""Shared spine glue for the Wave-2 public-domain book connectors (SPR-06).

The five new connectors (Standard Ebooks, Wikisource, Internet Archive,
HathiTrust, Library of Congress) all compose the SAME Wave-1 spine, so the
composition lives here once rather than being re-rolled five times:

  * **SPR-03 fetch** — :class:`ThrottledFetcher` consults
    ``substrate.source_throttle.SourceThrottle.before_request(source)`` BEFORE
    every request (raising ``SourceBanned`` while a source is banned + spacing
    requests) and feeds ``note_response(source, status, headers)`` AFTER, so a
    429/503 arms the cross-process ban sentinel. There is NO raw
    ``requests.get``/``httpx.get`` in any connector module — every byte and every
    JSON page is fetched through here.

  * **SPR-02 rights gate (THE BINDING)** — :func:`classify_and_ingest` calls
    ``acquisition.licenses_core.classify(license, source_declaration, *,
    legitimate_source=...)`` and passes the returned ``ClassificationResult``'s
    ``content_class`` + ``license_basis`` to
    ``acquisition.books.adapter.ingest_servable_book``. No connector assigns a
    ``content_class`` by any other route. The legacy direct
    ``content_class="public_domain"`` path in ``public_domain.py`` is exactly
    what this wave retires — it is not used here.

  * **SPR-01 staging write** — the ingest goes through ``ingest_servable_book``
    → ``register_book`` → ``runtime.db_lock.connect_write`` (the single writer);
    connectors never open a write connection.

  * **SPR-04 dedup** — :class:`BookCandidate` carries the identity-bearing
    fields the orchestrator maps into a ``substrate.dedup.IdentityRecord`` so the
    same work across sources collapses to one document.

A connector's job shrinks to: discover candidates from its public API/dump
(through the fetcher), positively establish PD status per item into either a
license URI or a ``source_declaration`` PD signal, and hand the bytes +
declaration to :func:`classify_and_ingest`. The verdict (servable / gated /
skip) is the rights gate's, never a local boolean.
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
    from substrate.source_throttle import SourceThrottle

logger = logging.getLogger("acquisition.books.pd_connector_base")

_USER_AGENT = "Antiek/1.0 (public-domain library acquisition; +https://antiek.ai)"

DEFAULT_MIN_INTERVAL_S = 1.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_TIMEOUT_S = 30.0

# Status codes the SPR-03 sentinel treats as "stop hitting me" (mirrors
# substrate.source_throttle._BAN_STATUS). On these the fetcher both retries
# (transient) AND, when a persistent throttle is wired, arms its ban sentinel.
_BAN_STATUS = frozenset({429, 503})


class FetchError(RuntimeError):
    """A source request failed after retries, or returned unusable data.

    Caught per-item by a connector's batch layer so one bad work does not abort
    the run — the same isolation contract ``public_domain.SourceError`` carries.
    """


class ThrottledFetcher:
    """Throttle + ban-aware HTTP client shared by the Wave-2 PD connectors.

    Every connector fetch (JSON discovery page, epub/PDF body, wikitext) goes
    through ``get_json`` / ``get_bytes`` here, so the SPR-03 throttle is the ONLY
    network edge — grepping the connector modules for ``requests.get`` /
    ``httpx.get`` finds nothing (a hard verification gate).

    ``persistent`` is the shared ``substrate.source_throttle.SourceThrottle``;
    when wired (the prod/orchestrator path) ``before_request(source)`` raises
    ``SourceBanned`` while the source is banned and enforces the persisted
    min-interval across process restarts, and a 429/503 arms the sentinel via
    ``note_response``. When ``persistent`` is None (the recorded-fixture tests)
    only the in-process spacing applies. Tests inject a fake with the same
    ``get_json`` / ``get_bytes`` surface; NO live HTTP runs in CI.
    """

    def __init__(
        self,
        *,
        source: str,
        min_interval_s: float = DEFAULT_MIN_INTERVAL_S,
        max_retries: int = DEFAULT_MAX_RETRIES,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        session: requests.Session | None = None,
        persistent: SourceThrottle | None = None,
    ) -> None:
        self._source = source
        self._min_interval_s = min_interval_s
        self._max_retries = max_retries
        self._timeout_s = timeout_s
        self._session = session or requests.Session()
        self._session.headers.update({"User-Agent": _USER_AGENT})
        self._lock = threading.Lock()
        self._last_request_at = 0.0
        self._persistent = persistent

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
        return self._request(url, params=params).json()

    def get_text(self, url: str, *, params: dict | None = None) -> str:
        return self._request(url, params=params).text

    def get_bytes(self, url: str, *, params: dict | None = None) -> bytes:
        return self._request(url, params=params).content

    def _request(
        self, url: str, *, params: dict | None = None
    ) -> requests.Response:
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            self._throttle()
            try:
                resp = self._session.get(
                    url, params=params, timeout=self._timeout_s
                )
            except requests.RequestException as exc:
                last_exc = exc
                self._backoff(attempt, reason=str(exc))
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                if (
                    self._persistent is not None
                    and resp.status_code in _BAN_STATUS
                ):
                    self._persistent.note_response(
                        self._source, resp.status_code, dict(resp.headers)
                    )
                last_exc = FetchError(f"{url} returned {resp.status_code}")
                self._backoff(attempt, reason=f"HTTP {resp.status_code}")
                continue
            if resp.status_code >= 400:
                raise FetchError(f"{url} returned {resp.status_code}")
            return resp
        raise FetchError(
            f"{url} failed after {self._max_retries} attempts"
        ) from last_exc

    def _backoff(self, attempt: int, *, reason: str) -> None:
        delay = min(2.0 ** attempt, 30.0)
        logger.warning(
            "retrying %s request (attempt %d, %s); backoff %.1fs",
            self._source, attempt + 1, reason, delay,
        )
        time.sleep(delay)


@dataclass(frozen=True)
class BookCandidate:
    """A discovered work + the positively-established rights signal.

    The connector establishes PD status into EXACTLY one of two rights inputs,
    both of which classify() consumes:

      * ``license_uri`` — a concrete license URI (a CC0/PDM mark, a CC-BY/-SA
        URI) classify() resolves against the canonical CC table; or
      * ``pd_signal`` — a positive ``source_declaration['public_domain']`` string
        naming the source field that established PD (e.g. "HathiTrust rights=pd")
        when the source exposes a per-item PD flag rather than a license URI.

    A candidate whose PD status is NOT established carries license_uri=None AND
    pd_signal=None → classify() gates it (deny-by-default). ``download_url`` +
    ``download_format`` say how to turn the body into ingestible PDF bytes
    (``"pdf"`` passthrough, ``"text"`` rendered via ``public_domain.text_to_pdf``).
    The identity fields (isbn / oclc / source_id) drive the SPR-04 dedup key.
    """

    source: str  # connector source name (e.g. "standard_ebooks")
    source_id: str  # source-local id, namespaced by source
    title: str
    author: str | None
    source_uri: str
    download_url: str
    download_format: str  # "pdf" | "text"
    license_uri: str | None = None
    pd_signal: str | None = None
    isbn: str | None = None
    oclc: str | None = None
    rights_holder_name: str | None = None
    subjects: Sequence[str] = field(default_factory=tuple)
    # When a connector already holds the body at discovery (e.g. Wikisource's
    # cleaned wikitext fetched via the API), it carries it inline so ingest
    # does NOT fetch ``download_url`` again — the SPR-03 throttle was already
    # consulted for the API call that produced it. ``download_format`` still
    # says how to turn it into PDF bytes.
    inline_body: bytes | None = None

    def source_declaration(self) -> Mapping[str, Any]:
        """The ``source_declaration`` mapping handed to classify(). Carries the
        positive PD signal (when established) + any rights-holder name so a
        GATED-in-copyright item can accrue escrow via the existing ip_holders
        seam (never disburses)."""
        decl: dict[str, Any] = {}
        if self.pd_signal:
            decl["public_domain"] = self.pd_signal
        if self.rights_holder_name:
            decl["rights_holder_name"] = self.rights_holder_name
        return decl

    def classification(self) -> ClassificationResult:
        """THE rights decision for this candidate, deny-by-default.

        Delegates the servable/gated/skip verdict to the SPR-02 chokepoint —
        the connector owns no local boolean. ``legitimate_source=True`` because
        every Wave-2 source is a public API / open PD repository (the
        legitimacy argument exists to gate circumvented access, which these are
        not). Re-checked per item before ingest (layer-2 defence in depth)."""
        return classify(
            self.license_uri,
            self.source_declaration(),
            legitimate_source=True,
        )


@dataclass(frozen=True)
class IngestOutcome:
    """Per-item ingest result. Exactly one of (ingested True + document_id) or
    (skipped_reason set) holds. ``content_class`` / ``license_basis`` /
    ``servable`` echo the rights gate's decision so a caller/auditor reads the
    verdict off the row."""

    candidate: BookCandidate
    ingested: bool
    content_class: str | None = None
    license_basis: str | None = None
    servable: bool = False
    servability: str | None = None
    document_id: str | None = None
    word_count: int = 0
    skipped_reason: str | None = None


def _to_pdf_bytes(raw: bytes, candidate: BookCandidate) -> bytes:
    """Turn a downloaded body into ingestible PDF bytes. A ``pdf`` download
    passes through; a ``text``/``html`` body is decoded and rendered to a
    byte-deterministic PDF via the existing ``public_domain.text_to_pdf`` (so
    the content-hash doc id stays stable). Boilerplate/chrome stripping is the
    connector's job before it sets ``download_format`` — done upstream."""
    fmt = candidate.download_format
    if fmt == "pdf":
        return raw
    if fmt in ("text", "html"):
        from .public_domain import text_to_pdf

        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1", "replace")
        if not text.strip():
            raise ValueError("decoded body is empty")
        return text_to_pdf(text, title=candidate.title)
    raise ValueError(f"unsupported download_format {fmt!r}")


def classify_and_ingest(
    candidate: BookCandidate,
    fetcher: ThrottledFetcher,
    *,
    investigation_id: str = "inv-library",
    db_path: str | None = None,
    embedder: Any = None,
) -> IngestOutcome:
    """Classify ``candidate`` through the SPR-02 chokepoint, then ingest it
    through the SPR-01 servable-book path with the gate's verdict.

    THE BINDING: ``content_class`` + ``license_basis`` come from
    ``classify(...)`` — never hardcoded. A servable verdict ingests servable
    full text with the gate's ``license_basis`` (which names the PD source/field
    by construction); a gated verdict ingests GATED (body stored, withheld,
    chunked/embedded for private search); a skip verdict (circumvented access —
    never the case for these legitimate sources) is not ingested at all.

    All download/extraction failures are caught and returned as a skip outcome
    so a batch continues; the write goes through ``ingest_servable_book`` →
    ``connect_write`` only — this function never opens a write connection.
    """
    decision = candidate.classification()

    if not decision.ingest:
        # Circumvented-access skip (never ingested). Not reachable for the
        # Wave-2 legitimate sources, but we honor the gate's verdict rather
        # than assume.
        return IngestOutcome(
            candidate=candidate,
            ingested=False,
            content_class=decision.content_class,
            license_basis=decision.license_basis,
            servable=False,
            skipped_reason=f"classify_skip: {decision.license_basis}",
        )

    from .adapter import ingest_servable_book

    if candidate.inline_body is not None:
        # Body already in hand (fetched through the SPR-03 throttle at
        # discovery); do not re-fetch.
        raw = candidate.inline_body
    else:
        try:
            raw = fetcher.get_bytes(candidate.download_url)
        except FetchError as exc:
            return IngestOutcome(
                candidate=candidate, ingested=False,
                content_class=decision.content_class,
                license_basis=decision.license_basis,
                servable=decision.servable,
                skipped_reason=f"download_failed: {exc}",
            )
    if not raw:
        return IngestOutcome(
            candidate=candidate, ingested=False,
            content_class=decision.content_class,
            license_basis=decision.license_basis,
            servable=decision.servable,
            skipped_reason="empty_download",
        )

    try:
        pdf_bytes = _to_pdf_bytes(raw, candidate)
    except Exception as exc:
        return IngestOutcome(
            candidate=candidate, ingested=False,
            content_class=decision.content_class,
            license_basis=decision.license_basis,
            servable=decision.servable,
            skipped_reason=f"convert_failed: {exc}",
        )

    try:
        result = ingest_servable_book(
            pdf_bytes,
            investigation_id=investigation_id,
            # THE BINDING: the gate's content_class + license_basis, not a
            # hardcoded "public_domain".
            content_class=decision.content_class,
            rights_holder_name=candidate.rights_holder_name,
            license_basis=decision.license_basis,
            provenance=candidate.source_uri,
            source_uri=candidate.source_uri,
            db_path=db_path,
            embedder=embedder,
        )
    except Exception as exc:  # corrupt/unreadable PDF: skip item, not batch
        return IngestOutcome(
            candidate=candidate, ingested=False,
            content_class=decision.content_class,
            license_basis=decision.license_basis,
            servable=decision.servable,
            skipped_reason=f"ingest_failed: {exc}",
        )

    if result.ingest.skipped_reason:
        return IngestOutcome(
            candidate=candidate, ingested=False,
            content_class=decision.content_class,
            license_basis=decision.license_basis,
            servable=decision.servable,
            document_id=result.document_id,
            skipped_reason=f"extract_{result.ingest.skipped_reason}",
        )

    return IngestOutcome(
        candidate=candidate,
        ingested=True,
        content_class=decision.content_class,
        license_basis=decision.license_basis,
        servable=result.servable_full_text,
        servability=result.servability,
        document_id=result.document_id,
        word_count=result.ingest.word_count,
    )
