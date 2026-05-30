"""Public-domain book acquisition — discover, download, rights-tag, ingest
(SPR-01).

The acquisition front-half for the Read workflow's safest corpus: works
whose copyright has expired or never applied, which Antiek may serve in
full. The substrate already owns reading/chunking/embedding/graph and the
§9.0 servability gate (``acquisition.books.adapter.ingest_servable_book`` →
``substrate.books.ingest.register_book``); this module adds only discovery,
download, and — the load-bearing part — *rights provenance* on top of it.

Two sources, Gutenberg primary:

- **Project Gutenberg** via the Gutendex JSON API (``gutendex.com``). Each
  book carries a per-work ``copyright`` flag. ``copyright is False`` is
  Gutenberg's explicit assertion that the work is public domain in the
  United States — a clean, per-book, machine-readable rights signal. That
  cleanliness is why Gutenberg is the default (see module-level steelman
  in the handoff). ``copyright is True`` or ``None`` (unknown) is NOT
  rounded up to public domain.

- **archive.org** via its metadata/download API, as a secondary for works
  Gutenberg lacks. archive.org's per-item ``rights``/``licenseurl`` fields
  are uploader-supplied free text, not a normalized per-work flag, so a
  candidate from archive.org is only tagged public_domain when its rights
  field *explicitly* asserts public domain; otherwise it is skipped.

Rights discipline (rigor #1 — intellectual honesty): "public domain" is a
legal claim, never a default. A candidate is only emitted with
``pd_basis`` set when the source explicitly asserts public-domain status.
Anything ambiguous comes back with ``pd_basis=None`` and the batch layer
skips-and-logs it (it is never silently classed servable).

Format reality (verified against live Gutendex 2026-05-28): modern Project
Gutenberg advertises ``text/plain``, ``application/epub+zip``,
``text/html``, and mobipocket — but NOT ``application/pdf``. The substrate
reader is PDF-only (pypdf). So a PDF-only connector would ingest *zero*
Gutenberg works. Rather than skip the whole catalogue, we fetch the plain-
text format Gutenberg actually serves and render it to a clean text PDF
in-process (``text_to_pdf``) before handing bytes to the PDF reader. The
substrate path stays unchanged (still PDF-in); the text→PDF bridge lives
entirely in this acquisition layer. The Gutenberg license header that
prefaces every plain-text file is itself an explicit per-file public-domain
assertion, which we capture into the basis. archive.org PDFs are ingested
directly when present.
"""

from __future__ import annotations

import io
import logging
import re
import textwrap
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Optional, Sequence

import requests

if TYPE_CHECKING:
    from substrate.source_throttle import SourceThrottle as SourceThrottleT

logger = logging.getLogger("acquisition.books.public_domain")

GUTENDEX_BASE = "https://gutendex.com/books"
ARCHIVE_METADATA_BASE = "https://archive.org/metadata"
ARCHIVE_DOWNLOAD_BASE = "https://archive.org/download"

# Gutenberg advertises formats by MIME type. We ingest either a direct PDF
# (rare on Gutenberg, common on archive.org) or — the usual Gutenberg case —
# the plain-text format, rendered to PDF before ingest. ``image/*`` zips and
# the ``.zip`` HTML bundles are not ingestible.
_PDF_MIME_PREFIXES = ("application/pdf",)
_TEXT_MIME_PREFIXES = ("text/plain",)

_USER_AGENT = "Antiek/1.0 (public-domain library acquisition; +https://antiek.ai)"

DEFAULT_MIN_INTERVAL_S = 1.0  # in-process throttle; gutendex is unauthenticated
DEFAULT_MAX_RETRIES = 3
DEFAULT_TIMEOUT_S = 30.0


@dataclass(frozen=True)
class PublicDomainWork:
    """A discovered work with everything the ingest path needs and the
    rights provenance counsel reads.

    ``pd_basis`` is the audit trail: a specific free-text statement naming
    the source + jurisdiction + how public-domain status was determined.
    It is ``None`` when the source did not explicitly assert public domain —
    such a work must NOT be ingested servable.
    """

    source: str  # "project_gutenberg" | "archive_org"
    source_id: str  # gutenberg book id / archive.org identifier
    title: str
    author: Optional[str]
    source_uri: str  # canonical landing/record URL
    download_url: str  # direct URL to the file we ingest
    download_format: str  # "pdf" | "text" — how to turn the download into PDF bytes
    pd_basis: Optional[str]  # license_basis string, or None when not asserted
    subjects: Sequence[str] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Throttled HTTP client
# ---------------------------------------------------------------------------


class SourceClient:
    """Throttled, retrying HTTP client for the public-domain sources.

    One serialized in-process throttle (a minimum interval between
    requests) keeps a batch under the unauthenticated rate ceilings of
    gutendex / archive.org. Transient failures (429, 5xx, connection
    errors) retry with exponential backoff; a request that exhausts its
    retries raises ``SourceError`` for the caller to catch per-item — it
    must NOT abort the batch.

    Tests inject a fake client with the same surface; no live HTTP runs in
    CI.
    """

    def __init__(
        self,
        *,
        min_interval_s: float = DEFAULT_MIN_INTERVAL_S,
        max_retries: int = DEFAULT_MAX_RETRIES,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        session: Optional[requests.Session] = None,
        persistent: Optional["SourceThrottleT"] = None,
        source: str = "gutendex",
    ) -> None:
        self._min_interval_s = min_interval_s
        self._max_retries = max_retries
        self._timeout_s = timeout_s
        self._session = session or requests.Session()
        self._session.headers.update({"User-Agent": _USER_AGENT})
        self._lock = threading.Lock()
        self._last_request_at = 0.0
        # Optional SHARED cross-process ban sentinel (SPR-03). When set, every
        # request consults before_request(source) — which raises SourceBanned
        # while gutendex is banned and enforces the persisted min-interval
        # across restarts — and a 429/503 arms the sentinel so a re-run does
        # not re-hit the source the prod 503s came from. None keeps the
        # pre-SPR-03 in-process-only behavior (the existing PD adapter tests).
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

    def get_json(self, url: str, *, params: Optional[dict] = None) -> dict:
        resp = self._request(url, params=params)
        return resp.json()

    def get_bytes(self, url: str) -> bytes:
        return self._request(url).content

    def _request(self, url: str, *, params: Optional[dict] = None) -> requests.Response:
        last_exc: Optional[Exception] = None
        for attempt in range(self._max_retries):
            self._throttle()
            try:
                resp = self._session.get(url, params=params, timeout=self._timeout_s)
            except requests.RequestException as exc:
                last_exc = exc
                self._backoff(attempt, reason=str(exc))
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                # Arm the cross-process ban sentinel on the "stop hitting me"
                # statuses (429 rate-limit / 503 overloaded) so a re-run honors
                # the ban — the exact failure the prod 503 run had no defense
                # against. Other 5xx are transient-only (retry-with-backoff).
                if self._persistent is not None and resp.status_code in (429, 503):
                    self._persistent.note_response(
                        self._source, resp.status_code, dict(resp.headers)
                    )
                last_exc = SourceError(
                    f"{url} returned {resp.status_code}"
                )
                self._backoff(attempt, reason=f"HTTP {resp.status_code}")
                continue
            if resp.status_code >= 400:
                raise SourceError(f"{url} returned {resp.status_code}")
            return resp
        raise SourceError(f"{url} failed after {self._max_retries} attempts") from last_exc

    def _backoff(self, attempt: int, *, reason: str) -> None:
        delay = min(2.0 ** attempt, 30.0)
        logger.warning("retrying source request (attempt %d, %s); backoff %.1fs",
                       attempt + 1, reason, delay)
        time.sleep(delay)


class SourceError(RuntimeError):
    """A source request failed (after retries) or returned unusable data.
    Caught per-item by the batch layer so one bad work doesn't abort the run."""


# ---------------------------------------------------------------------------
# Project Gutenberg (primary)
# ---------------------------------------------------------------------------


def _gutenberg_author(book: dict) -> Optional[str]:
    authors = book.get("authors") or []
    names = [a.get("name") for a in authors if a.get("name")]
    return "; ".join(names) if names else None


def _select_format(formats: dict) -> Optional[tuple[str, str]]:
    """Choose an ingestible (url, format-kind) from Gutendex's mime→url map.

    Prefers a direct PDF when offered; otherwise falls back to plain text,
    which we render to PDF before ingest. ``.zip`` bundles and image covers
    are not ingestible. Returns None when neither a PDF nor a plain-text
    format is advertised (caller skips the work)."""
    text_url: Optional[str] = None
    for mime, url in formats.items():
        if not isinstance(url, str) or url.endswith(".zip"):
            continue
        if any(mime.startswith(p) for p in _PDF_MIME_PREFIXES):
            return url, "pdf"
        if text_url is None and any(mime.startswith(p) for p in _TEXT_MIME_PREFIXES):
            text_url = url
    if text_url is not None:
        return text_url, "text"
    return None


# Gutenberg prefaces/suffixes every plain-text file with a boilerplate license
# block. The START marker doubles as an explicit per-file public-domain
# assertion; we trim the boilerplate from the rendered body but cite it in the
# basis.
_GUTENBERG_START_RE = re.compile(
    r"\*\*\*\s*START OF (?:THE|THIS) PROJECT GUTENBERG EBOOK.*?\*\*\*",
    re.IGNORECASE | re.DOTALL,
)
_GUTENBERG_END_RE = re.compile(
    r"\*\*\*\s*END OF (?:THE|THIS) PROJECT GUTENBERG EBOOK.*?\*\*\*",
    re.IGNORECASE | re.DOTALL,
)


def strip_gutenberg_boilerplate(text: str) -> str:
    """Trim the Gutenberg license boilerplate, leaving the work's body.

    Conservative: only trims between the canonical START/END markers when
    both are present; otherwise returns the text unchanged (better to keep a
    few lines of header than to over-trim a work that omits the markers)."""
    start = _GUTENBERG_START_RE.search(text)
    if start:
        text = text[start.end():]
    end = _GUTENBERG_END_RE.search(text)
    if end:
        text = text[: end.start()]
    return text.strip()


def _gutenberg_pd_basis(book: dict) -> Optional[str]:
    """Map Gutenberg's per-book ``copyright`` flag to a license_basis.

    Gutendex exposes ``copyright`` as a tri-state: ``False`` (Gutenberg
    asserts the work is public domain in the US), ``True`` (under
    copyright), or ``None`` (status unknown). Only the explicit ``False``
    becomes a public-domain basis. ``True``/``None`` return None so the
    work is skipped rather than rounded up.
    """
    copyright_flag = book.get("copyright", None)
    if copyright_flag is False:
        return (
            "Project Gutenberg; US public domain per Gutenberg per-book "
            f"copyright=false flag (gutendex book id {book.get('id')})"
        )
    return None


def gutenberg_candidates(
    client: SourceClient,
    *,
    subject: Optional[str] = None,
    search: Optional[str] = None,
    ids: Optional[Sequence[int]] = None,
    limit: int = 25,
) -> list[PublicDomainWork]:
    """Discover Gutenberg works matching ``subject`` / ``search`` / ``ids``.

    Returns up to ``limit`` candidates. Only works that (a) Gutenberg
    explicitly flags public domain AND (b) advertise a PDF format are
    returned; everything else is logged and skipped. Pages through
    Gutendex as needed to fill ``limit`` from public-domain PDF works.
    """
    params: dict = {}
    if subject:
        params["topic"] = subject
    if search:
        params["search"] = search
    if ids:
        params["ids"] = ",".join(str(i) for i in ids)

    out: list[PublicDomainWork] = []
    url: Optional[str] = GUTENDEX_BASE
    next_params: Optional[dict] = params
    while url and len(out) < limit:
        page = client.get_json(url, params=next_params)
        for book in page.get("results", []):
            if len(out) >= limit:
                break
            work = _gutenberg_work(book)
            if work is None:
                continue
            out.append(work)
        url = page.get("next")
        next_params = None  # the ``next`` URL already carries the query
    return out


def _gutenberg_work(book: dict) -> Optional[PublicDomainWork]:
    title = (book.get("title") or "").strip()
    if not title:
        logger.info("gutenberg book %s skipped: no title", book.get("id"))
        return None
    pd_basis = _gutenberg_pd_basis(book)
    if pd_basis is None:
        logger.info(
            "gutenberg book %s (%s) skipped: copyright flag is %r, not an "
            "explicit public-domain assertion",
            book.get("id"), title, book.get("copyright"),
        )
        return None
    selected = _select_format(book.get("formats") or {})
    if selected is None:
        logger.info(
            "gutenberg book %s (%s) skipped: no PDF or plain-text format "
            "advertised", book.get("id"), title,
        )
        return None
    download_url, download_format = selected
    book_id = book.get("id")
    return PublicDomainWork(
        source="project_gutenberg",
        source_id=str(book_id),
        title=title,
        author=_gutenberg_author(book),
        source_uri=f"https://www.gutenberg.org/ebooks/{book_id}",
        download_url=download_url,
        download_format=download_format,
        pd_basis=pd_basis,
        subjects=tuple(book.get("subjects") or ()),
    )


# ---------------------------------------------------------------------------
# archive.org (secondary)
# ---------------------------------------------------------------------------

# Tokens in an archive.org ``rights``/``licenseurl`` field that we accept as
# an explicit public-domain assertion. Anything else is treated as ambiguous
# and the work is skipped — archive.org rights are uploader free text, so we
# only trust an unambiguous statement.
_ARCHIVE_PD_TOKENS = (
    "public domain",
    "publicdomain",
    "/publicdomain/",  # creativecommons.org/publicdomain/... (CC0 / PDM)
    "no known copyright",
)

# Explicit negative / copyright signals. These are deny-by-default: if any of
# them appears we skip the item even when a PD token also matches, because
# ``_ARCHIVE_PD_TOKENS`` substring-matches "public domain" and would otherwise
# accept text like "NOT in the public domain". A negated PD phrase reads as a
# rights *denial*, not an assertion.
_ARCHIVE_NEGATIVE_TOKENS = (
    "all rights reserved",
    "all rights",
    "in copyright",
    "copyrighted",
    "not in the public domain",
    "not in public domain",
    "not public domain",
)
# A negation immediately preceding "public domain" ("not", "no", "isn't",
# "is not" public domain) also denies the claim.
_ARCHIVE_NEGATED_PD_RE = re.compile(
    r"\b(?:not|no|isn't|is not)\s+(?:in\s+(?:the\s+)?)?public\s+domain",
)
# An affirmative copyright claim — the © symbol, or "copyright"/"(c)" followed
# by a year — denies PD even when "public domain" also appears (e.g.
# "© 2021 Penguin. Public domain text reproduced."). The year anchor is what
# keeps this from clobbering the legitimate PD token "no known copyright
# restrictions", which carries no year. CC0/PDM rights never assert ©+year.
_ARCHIVE_COPYRIGHT_CLAIM_RE = re.compile(
    r"©|\bcopyright\s+(?:\(c\)\s*)?\d{4}|\(c\)\s*\d{4}",
)


def _archive_pd_basis(meta: dict, identifier: str) -> Optional[str]:
    fields = []
    for key in ("rights", "licenseurl", "possible-copyright-status"):
        val = meta.get(key)
        if isinstance(val, str):
            fields.append(val)
        elif isinstance(val, list):
            fields.extend(str(v) for v in val)
    haystack = " ".join(fields).lower()
    # Deny-by-default: any explicit copyright assertion or negated PD phrase
    # disqualifies the item before a PD token can accept it.
    if any(tok in haystack for tok in _ARCHIVE_NEGATIVE_TOKENS):
        return None
    if _ARCHIVE_NEGATED_PD_RE.search(haystack):
        return None
    if _ARCHIVE_COPYRIGHT_CLAIM_RE.search(haystack):
        return None
    if any(tok in haystack for tok in _ARCHIVE_PD_TOKENS):
        asserted = "; ".join(f for f in fields if f)
        return (
            f"archive.org item {identifier}; public domain per item rights "
            f"field ({asserted})"
        )
    return None


def _archive_pdf_url(identifier: str, files: Iterable[dict]) -> Optional[str]:
    for f in files:
        name = f.get("name", "")
        if isinstance(name, str) and name.lower().endswith(".pdf"):
            return f"{ARCHIVE_DOWNLOAD_BASE}/{identifier}/{name}"
    return None


def archive_candidate(client: SourceClient, identifier: str) -> Optional[PublicDomainWork]:
    """Resolve one archive.org item to a candidate, or None when it lacks an
    explicit public-domain rights assertion or a PDF file.

    archive.org is the secondary source — used to fill in works Gutenberg
    lacks, by explicit identifier. We do not free-text-search it for rights
    we'd then have to guess at.
    """
    record = client.get_json(f"{ARCHIVE_METADATA_BASE}/{identifier}")
    meta = record.get("metadata") or {}
    pd_basis = _archive_pd_basis(meta, identifier)
    if pd_basis is None:
        logger.info(
            "archive.org item %s skipped: no explicit public-domain rights "
            "assertion in metadata", identifier,
        )
        return None
    pdf_url = _archive_pdf_url(identifier, record.get("files") or [])
    if pdf_url is None:
        logger.info("archive.org item %s skipped: no PDF file", identifier)
        return None
    title = (meta.get("title") or identifier).strip()
    creator = meta.get("creator")
    if isinstance(creator, list):
        creator = "; ".join(str(c) for c in creator)
    return PublicDomainWork(
        source="archive_org",
        source_id=identifier,
        title=title,
        author=str(creator) if creator else None,
        source_uri=f"https://archive.org/details/{identifier}",
        download_url=pdf_url,
        download_format="pdf",
        pd_basis=pd_basis,
        subjects=tuple(),
    )


# ---------------------------------------------------------------------------
# Text → PDF bridge (Gutenberg serves text; the substrate reader wants PDF)
# ---------------------------------------------------------------------------


_VENDORED_FONT_NAME = "DejaVuSans"
_VENDORED_FONT_PATH = Path(__file__).parent / "fonts" / "DejaVuSans.ttf"


def _resolve_unicode_font() -> str:
    """Register (once) and return the name of a Unicode TrueType font for the
    text→PDF bridge.

    The built-in Helvetica is Latin-1-only, which silently mangled every
    out-of-range glyph (œ ligatures, smart quotes, em-dashes, accents, Greek)
    into "?" and corrupted the corpus. A registered embedded TTF draws the
    real Unicode string instead.

    The font is the **vendored** ``acquisition/books/fonts/DejaVuSans.ttf``,
    resolved relative to this module — NOT probed from any external package's
    install dir. DejaVu Sans covers œ ligatures, smart quotes, em-dashes,
    accents AND Greek (the corpus is philosophy: Kant/Hegel/Aurelius, whose
    *Meditations* carries hundreds of Greek codepoints). Vendoring it means
    the Greek-glyph guarantee depends on nothing but this repository — not on
    matplotlib (which is NOT an Antiek dependency) or any other incidentally
    installed package. The earlier matplotlib/Vera fallback was the real
    BLOCKER: on a clean install matplotlib is absent and reportlab's bundled
    Vera has no Greek glyphs, so Greek rendered as ``.notdef`` and extracted
    back as NUL — silently losing the corpus's Greek while a "?"-only check
    passed.

    The register-once guard (via ``pdfmetrics.getRegisteredFontNames()``)
    keeps the embedded-font bytes stable across calls (idempotency). If the
    vendored font is somehow missing we raise rather than silently degrade to
    a non-Greek font.
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if _VENDORED_FONT_NAME in pdfmetrics.getRegisteredFontNames():
        return _VENDORED_FONT_NAME
    if not _VENDORED_FONT_PATH.exists():
        raise RuntimeError(
            f"vendored Unicode font missing at {_VENDORED_FONT_PATH}; "
            "text_to_pdf cannot guarantee Greek/Unicode coverage"
        )
    pdfmetrics.registerFont(TTFont(_VENDORED_FONT_NAME, str(_VENDORED_FONT_PATH)))
    return _VENDORED_FONT_NAME


def text_to_pdf(text: str, *, title: Optional[str] = None) -> bytes:
    """Render plain text to a simple, cleanly-extractable PDF.

    The substrate reader (pypdf) extracts text back out per page; this is a
    lossless-enough round-trip for prose (we are not preserving original
    typesetting, only producing an ingestible carrier the reader can chunk).
    Long lines are wrapped; the title is set in the PDF info dict so
    ``read_pdf`` recovers it.
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas

    font_name = _resolve_unicode_font()
    buf = io.BytesIO()
    # invariant=1 strips the creation timestamp so the same text renders to
    # byte-identical PDF every time — which is what makes the adapter's
    # content-hash doc id (and thus idempotency) stable across re-runs.
    c = canvas.Canvas(buf, pagesize=letter, invariant=1)
    if title:
        c.setTitle(title)
    width, height = letter
    left, top, bottom = inch, height - inch, inch
    line_height = 12.0
    font_size = 9.5
    max_chars = 95
    y = top
    c.setFont(font_name, font_size)

    def _newpage():
        nonlocal y
        c.showPage()
        c.setFont(font_name, font_size)
        y = top

    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        wrapped = textwrap.wrap(raw_line, width=max_chars) or [""]
        for piece in wrapped:
            if y <= bottom:
                _newpage()
            # Registered Unicode TTF (see _resolve_unicode_font) draws the
            # real text — no Latin-1 coercion, so œ/smart-quotes/em-dash/
            # accents/Greek survive instead of becoming "?".
            c.drawString(left, y, piece)
            y -= line_height
    c.save()
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Ingest one work through the existing servable-book path
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IngestOutcome:
    """Per-work result of an ingest attempt. Exactly one of
    (``document_id`` populated + ``ingested`` True) or (``skipped_reason``
    set) holds."""

    work: PublicDomainWork
    ingested: bool
    document_id: Optional[str] = None
    servability: Optional[str] = None
    servable_full_text: bool = False
    word_count: int = 0
    skipped_reason: Optional[str] = None


def _to_pdf_bytes(raw: bytes, work: PublicDomainWork) -> bytes:
    """Turn a downloaded file into ingestible PDF bytes.

    A ``pdf`` download passes through unchanged. A ``text`` download is
    decoded (UTF-8, latin-1 fallback), stripped of Gutenberg license
    boilerplate, and rendered to a byte-deterministic PDF so the adapter's
    content-hash doc id stays stable across re-runs."""
    if work.download_format == "pdf":
        return raw
    if work.download_format == "text":
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1", "replace")
        if work.source == "project_gutenberg":
            text = strip_gutenberg_boilerplate(text)
        if not text.strip():
            raise ValueError("decoded text is empty after boilerplate strip")
        return text_to_pdf(text, title=work.title)
    raise ValueError(f"unsupported download_format {work.download_format!r}")


def ingest_work(
    work: PublicDomainWork,
    client: SourceClient,
    *,
    investigation_id: str = "inv-library",
    db_path: Optional[str] = None,
    embedder=None,
) -> IngestOutcome:
    """Download ``work`` and ingest it as a servable public-domain book.

    Rights discipline (rigor #1): a work with no explicit public-domain
    basis (``pd_basis is None``) is NEVER ingested servable — it returns a
    skip outcome.

    THE BINDING (SPR-02 / SPR-10): the ``content_class`` + ``license_basis``
    stamped on the asset come from the ONE classification chokepoint —
    ``acquisition.licenses_core.classify()`` — exactly as
    ``pd_connector_base.classify_and_ingest`` does, never a hardcoded
    ``"public_domain"`` literal. We turn ``work.pd_basis`` (the source's
    positive public-domain signal) into a ``source_declaration['public_domain']``
    and call classify(); for a curated-Gutenberg PD work classify() returns the
    servable ``public_domain`` verdict, so the existing servable outcome is
    preserved while the rights decision stays single-source. (If classify() ever
    GATED a work this path currently serves, the gate's verdict wins — we never
    silently override servability.)

    All download / extraction failures are caught and returned as a skip
    outcome so the batch continues (M3 AC). Writes go through
    ``ingest_servable_book`` → ``connect_write`` only; this function never
    opens a write connection.
    """
    if work.pd_basis is None:
        return IngestOutcome(
            work=work,
            ingested=False,
            skipped_reason="no_explicit_public_domain_basis",
        )

    from acquisition.licenses_core import classify

    from .adapter import ingest_servable_book

    # THE BINDING: route the rights decision through classify(). The source's
    # per-work public-domain signal (work.pd_basis, set only when the source
    # explicitly asserted PD) is the positive source_declaration['public_domain']
    # classify() consumes; legitimate_source=True because Gutenberg/archive.org
    # are open PD repositories (the legitimacy argument gates circumvented
    # access, which these are not). The verdict's content_class + license_basis
    # are forwarded into ingest_servable_book — no local literal.
    decision = classify(
        None,
        {"public_domain": work.pd_basis},
        legitimate_source=True,
    )
    if not decision.ingest:
        # Never reached for a legitimate PD source, but honour the gate rather
        # than assume — a non-servable, circumvented-access verdict is a skip.
        return IngestOutcome(
            work=work,
            ingested=False,
            skipped_reason=f"classify_skip: {decision.license_basis}",
        )

    try:
        raw = client.get_bytes(work.download_url)
    except SourceError as exc:
        return IngestOutcome(
            work=work, ingested=False, skipped_reason=f"download_failed: {exc}"
        )
    if not raw:
        return IngestOutcome(
            work=work, ingested=False, skipped_reason="empty_download"
        )

    try:
        pdf_bytes = _to_pdf_bytes(raw, work)
    except Exception as exc:
        return IngestOutcome(
            work=work, ingested=False, skipped_reason=f"convert_failed: {exc}"
        )

    try:
        result = ingest_servable_book(
            pdf_bytes,
            investigation_id=investigation_id,
            # THE BINDING: the classify() verdict, not a hardcoded literal.
            content_class=decision.content_class,
            rights_holder_name=None,  # public domain has no rights holder to onboard
            license_basis=decision.license_basis,
            provenance=work.source_uri,
            source_uri=work.source_uri,
            db_path=db_path,
            embedder=embedder,
        )
    except Exception as exc:  # corrupt/unreadable PDF: fail this item, not the batch
        return IngestOutcome(
            work=work, ingested=False, skipped_reason=f"ingest_failed: {exc}"
        )

    if result.ingest.skipped_reason:
        return IngestOutcome(
            work=work,
            ingested=False,
            document_id=result.document_id,
            skipped_reason=f"extract_{result.ingest.skipped_reason}",
        )

    return IngestOutcome(
        work=work,
        ingested=True,
        document_id=result.document_id,
        servability=result.servability,
        servable_full_text=result.servable_full_text,
        word_count=result.ingest.word_count,
    )
