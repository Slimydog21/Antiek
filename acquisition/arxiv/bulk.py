"""arXiv BULK-dataset discovery — dodges the export-API 429 (SPR-03 M4).

The 2026-05-29 prod run got the box's IP 429-banned by ``export.arxiv.org``
and stayed banned; an in-process throttle did nothing across restarts (the
dedicated ``ArxivThrottle`` now persists that ban, but a banned export API
still yields ZERO arXiv volume until the ban elapses). For MASS volume we must
not touch the export API at all.

arXiv publishes its full metadata as a bulk snapshot — the Kaggle / GCS
``arxiv-metadata-oai-snapshot.json`` dataset: one JSON object PER LINE
(JSON-Lines), ~2.5M records. This module iterates that local snapshot
line-by-line (it is multi-GB — we NEVER materialize it all in memory; the
disk budget is the operator's, the snapshot is downloaded out-of-band per the
runbook) and yields the SAME ``ArxivPaper`` shape the export adapter's
``client._parse_entry`` produces, so the downstream rights / quality / dedup
logic is byte-for-byte unchanged. The export API stays reachable for small
incremental pulls (``--arxiv-source export``); bulk is the volume path.

Per-record license is the snapshot's ``license`` field — the SAME rights
anchor the export Atom ``<license>`` element carries — so a bulk-discovered
paper gates exactly as an export-discovered one (a missing license -> None ->
deny-by-default). The per-PDF fetch (``fetch_bulk_pdf``) reuses the shared
``substrate.source_throttle.SourceThrottle`` (source key ``arxiv_pdf``) and the
shared ``acquisition.openaccess.pdf_detect.assert_pdf`` check — it does NOT
re-implement throttling or PDF sniffing.
"""

from __future__ import annotations

import gzip
import io
import json
import logging
import os
import tarfile
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, TYPE_CHECKING, Literal

from substrate.schemas.documents import ArxivOaiRecord

from .client import ArxivPaper

if TYPE_CHECKING:
    import httpx

    from substrate.source_throttle import SourceThrottle

# arXiv's PDF host throttle key — see substrate.source_throttle. arXiv PDFs are
# arxiv.org (not export.arxiv.org), but a burst can still trip an IP ban, so
# the per-PDF fetch is spaced at the documented 3s ceiling.
ARXIV_PDF_SOURCE_KEY = "arxiv_pdf"


def _parse_versions(record: dict) -> tuple[str, datetime, datetime]:
    """Derive (version_suffix, published_at, updated_at) from the snapshot's
    ``versions`` list + ``update_date``.

    ``versions`` is ``[{"version": "v1", "created": "<RFC822>"}, ...]``. The
    first entry's ``created`` is the original submission (published); the last
    entry's version is the current version suffix. ``update_date`` (an ISO
    ``YYYY-MM-DD``) is the snapshot's last-update stamp. Missing/partial data
    degrades to the epoch + empty suffix rather than crashing the stream — a
    single malformed record must not abort a 2.5M-line iteration.
    """
    versions = record.get("versions") or []
    version_suffix = ""
    published_at = _EPOCH
    if versions:
        last = versions[-1]
        if isinstance(last, dict):
            version_suffix = str(last.get("version") or "")
        first = versions[0]
        if isinstance(first, dict) and first.get("created"):
            published_at = _parse_rfc822(str(first["created"])) or _EPOCH

    updated_at = published_at
    upd = record.get("update_date")
    if upd:
        try:
            updated_at = datetime.fromisoformat(str(upd)).replace(tzinfo=UTC)
        except ValueError:
            updated_at = published_at
    return version_suffix, published_at, updated_at


_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _parse_rfc822(value: str) -> datetime | None:
    """arXiv ``versions[].created`` is an RFC-822 date
    (``Mon, 2 Apr 2007 19:18:42 GMT``). Parse to tz-aware UTC; return None on
    any failure so the caller can fall back to the epoch."""
    from email.utils import parsedate_to_datetime

    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def record_to_paper(record: dict) -> ArxivPaper:
    """Map ONE bulk-snapshot record to an ``ArxivPaper`` — the SAME shape the
    export adapter yields, so downstream logic is unchanged.

    Field parity with ``client._parse_entry``:
      - ``arxiv_id``      <- snapshot ``id`` (base id, no version suffix)
      - ``version``       <- last ``versions[].version`` (e.g. "v2")
      - ``title``         <- ``title`` (whitespace-collapsed, like export)
      - ``authors``       <- ``authors_parsed`` ("Last, First" rebuilt) or the
                             raw ``authors`` string split on " and "
      - ``abstract``      <- ``abstract`` (whitespace-collapsed)
      - ``categories``    <- ``categories`` (space-separated -> list)
      - ``license_uri``   <- ``license`` (the rights anchor; None -> gated)
      - ``abs_url``/``pdf_url`` <- derived from the base id, identical to export
    """
    arxiv_id = str(record.get("id") or "").strip()
    if not arxiv_id:
        raise ValueError("bulk record has no id")

    version_suffix, published_at, updated_at = _parse_versions(record)

    title = " ".join(str(record.get("title") or "").split())
    abstract = " ".join(str(record.get("abstract") or "").split())

    authors = _authors(record)
    categories = [c for c in str(record.get("categories") or "").split() if c]
    primary_category = categories[0] if categories else None

    license_uri = record.get("license")
    license_uri = str(license_uri).strip() if license_uri else None

    return ArxivPaper(
        arxiv_id=arxiv_id,
        version=version_suffix,
        title=title,
        authors=authors,
        abstract=abstract,
        categories=categories,
        primary_category=primary_category,
        published_at=published_at,
        updated_at=updated_at,
        abs_url=f"https://arxiv.org/abs/{arxiv_id}",
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
        license_uri=license_uri,
        raw_id=arxiv_id,
        metadata={"source": "arxiv_bulk", "doi": record.get("doi")},
    )


def _authors(record: dict) -> list[str]:
    """Rebuild a "First Last" author list. ``authors_parsed`` is
    ``[[last, first, suffix], ...]`` (the structured form); fall back to the
    free-text ``authors`` string split on the " and " arXiv uses."""
    parsed = record.get("authors_parsed")
    if isinstance(parsed, list) and parsed:
        out: list[str] = []
        for entry in parsed:
            if isinstance(entry, (list, tuple)) and entry:
                last = str(entry[0]).strip()
                first = str(entry[1]).strip() if len(entry) > 1 else ""
                name = f"{first} {last}".strip()
                if name:
                    out.append(name)
        if out:
            return out
    raw = record.get("authors")
    if raw:
        return [a.strip() for a in str(raw).split(" and ") if a.strip()]
    return []


def iter_bulk_candidates(
    snapshot: IO[str],
    *,
    category: str | None = None,
    limit: int | None = None,
) -> Iterator[ArxivPaper]:
    """Stream ``ArxivPaper`` candidates from an open JSON-Lines snapshot.

    ``snapshot`` is an open text file object iterated LINE BY LINE — never
    read whole — so a multi-GB dataset stays within the box's memory budget.
    ``category`` filters to records whose category list contains that exact
    category (e.g. ``cs.LG``); ``limit`` caps the number yielded.

    A malformed/blank line is skipped (a 2.5M-line dataset has occasional
    cruft; one bad line must not abort the iteration). NO export-API request
    is ever made on this path.
    """
    yielded = 0
    for line in snapshot:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        try:
            paper = record_to_paper(record)
        except ValueError:
            continue
        if category is not None and category not in paper.categories:
            continue
        yield paper
        yielded += 1
        if limit is not None and yielded >= limit:
            return


def bulk_candidates_from_path(
    snapshot_path: str,
    *,
    category: str | None = None,
    limit: int | None = None,
) -> list[ArxivPaper]:
    """Convenience: open the snapshot at ``snapshot_path`` and materialize up
    to ``limit`` candidates. The materialization is bounded by ``limit`` (the
    iterator stops early), so this never holds more than ``limit`` records —
    the streaming guarantee is preserved for any sane limit."""
    with open(snapshot_path, encoding="utf-8") as fh:
        return list(iter_bulk_candidates(fh, category=category, limit=limit))


def fetch_bulk_pdf(
    paper: ArxivPaper,
    *,
    throttle: SourceThrottle,
    client: httpx.Client | None = None,
    _arxiv_throttle: object | None = None,
) -> bytes:
    """Fetch a bulk-discovered paper's PDF, reusing the shared SourceThrottle
    (key ``arxiv_pdf``) for cross-process spacing/ban-safety and the shared
    ``assert_pdf`` layered check. Raises ``NotAPdf`` on a landing page / corrupt
    PDF (a counted per-item miss) and ``SourceBanned`` while the PDF host is
    banned. ``client`` is an injectable httpx.Client for tests.

    Deliberately NOT a re-implementation: throttling lives in SourceThrottle,
    PDF detection in pdf_detect, the URL convention in ArxivPaper.pdf_url.

    HOST-GLOBAL arXiv GOVERNANCE (SPR-09 root fix): ``url = paper.pdf_url`` IS an
    ``https://arxiv.org/pdf/<id>`` URL — the EXISTENTIAL arXiv egress. The two
    throttles are layered, not duplicative:

      * ``throttle`` (the per-source ``SourceThrottle``, key ``arxiv_pdf``) remains
        the in-job ban sentinel — ``before_request`` raises ``SourceBanned``
        BEFORE any send while the PDF host is banned, and ``note_response`` arms
        that sentinel on a 429/503. Kept verbatim (the bulk path's own ban book).
      * The canonical arXiv governor adds the HOST-GLOBAL ``fcntl.flock`` + >=3s
        spacing + 429 sentinel on the SHARED ``~/.antiek/arxiv_throttle.json`` ON
        TOP of the send, so this bulk fetch is concurrency-safe against the OAI
        harvest / on-demand pdf_fetch / OA fetchers that may also land arxiv.org —
        the un-spaced-parallel-stream race that historically IP-banned the box.

    The actual send is routed through ``govern_if_arxiv(url, _send, ...)`` (an
    arxiv.org host → the host-global gate; a non-arXiv host would be a no-op).

    REDIRECT-SAFE: the client carries the per-hop arXiv request/response hooks
    (``install_arxiv_request_hook`` / ``arxiv_governed_client``) so EVERY hop whose
    host is arXiv — initial OR a redirect target — is governed by construction; the
    outer ``govern_if_arxiv`` governs the initial hop (re-entrant, no double-wait,
    no deadlock).

    ``_arxiv_throttle`` is a TEST seam only: it overrides the canonical arXiv
    governor throttle so a test injects one with a fake clock + tmp shared state
    (the production path passes nothing → the real canonical throttle on the
    shared ``~/.antiek/arxiv_throttle.json``).
    """

    from acquisition.arxiv.rate_governor import (
        canonical_arxiv_throttle,
        govern_if_arxiv,
        install_arxiv_request_hook,
    )
    from acquisition.openaccess.pdf_detect import assert_pdf

    from .client import DEFAULT_TIMEOUT_S, DEFAULT_USER_AGENT

    arxiv_throttle = (
        _arxiv_throttle if _arxiv_throttle is not None else canonical_arxiv_throttle()
    )

    # Cross-process gate: spacing + ban sentinel for the arXiv PDF host.
    throttle.before_request(ARXIV_PDF_SOURCE_KEY)

    headers = {"User-Agent": DEFAULT_USER_AGENT}
    url = paper.pdf_url
    if client is not None:
        # Govern every arXiv hop the CALLER's client follows, too.
        install_arxiv_request_hook(client, throttle=arxiv_throttle)

        def _send() -> httpx.Response:
            return client.get(url, headers=headers, timeout=DEFAULT_TIMEOUT_S)

        r = govern_if_arxiv(url, _send, throttle=arxiv_throttle)
    else:
        from acquisition.arxiv.rate_governor import arxiv_governed_client

        with arxiv_governed_client(throttle=arxiv_throttle) as c:
            def _send() -> httpx.Response:
                return c.get(url, headers=headers, timeout=DEFAULT_TIMEOUT_S)

            r = govern_if_arxiv(url, _send, throttle=arxiv_throttle)
    if r.status_code in (429, 503):
        throttle.note_response(ARXIV_PDF_SOURCE_KEY, r.status_code, dict(r.headers))
    r.raise_for_status()
    content = r.content
    assert_pdf(content, content_type=r.headers.get("content-type"), url=url)
    return content



# ---------------------------------------------------------------------------
# Bulk metadata feed (GCS / Kaggle snapshot) — OAI-sync throughput path
# ---------------------------------------------------------------------------
#
# The nightly OAI-PMH ListRecords crawl is STRUCTURALLY too slow for a full
# corpus under arXiv's 1-req/3s rule: ~1000 records/page × 3.5s spacing
# ≈ 50 min/page → ~22h for a 26K-doc window, well past the 6h systemd
# TimeoutStartSec. The bulk metadata snapshot is the designated mass path:
# one free JSON-Lines file (no per-page OAI requests) that carries the same
# per-paper ``license`` field the OAI ``arXiv`` prefix does.
#
# Public free feed (no AWS requester-pays): the Cornell Kaggle mirror on
# Google Cloud Storage, prefix ``metadata-v5/``. Operators may also point
# ``--bulk-snapshot`` at a pre-downloaded file (Kaggle download, HuggingFace
# mirror, etc.). We NEVER re-implement OAI rate-limiting here — bulk is
# offline/local once the snapshot is on disk.

logger = logging.getLogger("antiek.acquisition.arxiv.bulk")

# Public free metadata snapshot on the arXiv Kaggle GCS mirror. The object is
# plain JSON-Lines (~4.5 GB, not gzipped at this key). A tar.gz of the same
# content is also accepted by the stream parser (stdlib tarfile + gzip).
DEFAULT_BULK_METADATA_URL = (
    "https://storage.googleapis.com/arxiv-dataset/metadata-v5/arxiv-metadata-oai.json"
)
# Alternate keys / mirrors an operator may point at via env / CLI. Kept as a
# tuple so discovery can try them in order when the primary 404s.
BULK_METADATA_CANDIDATE_URLS: tuple[str, ...] = (
    DEFAULT_BULK_METADATA_URL,
    # Older key name some mirrors still publish:
    "https://storage.googleapis.com/arxiv-dataset/metadata-v5/"
    "arxiv-metadata-oai-snapshot.json",
)


def default_bulk_snapshot_path() -> str:
    """Default on-disk cache for the downloaded snapshot. Honors
    ``ANTIEK_ARXIV_BULK_SNAPSHOT`` so operators / tests pin a path."""
    env = os.environ.get("ANTIEK_ARXIV_BULK_SNAPSHOT")
    if env:
        return env
    return str(Path.home() / ".antiek" / "arxiv-metadata-oai-snapshot.json")


def default_bulk_cache_dir() -> str:
    env = os.environ.get("ANTIEK_ARXIV_BULK_CACHE_DIR")
    if env:
        return env
    return str(Path.home() / ".antiek" / "arxiv_bulk")


@dataclass
class BulkFeedInfo:
    """Discovery result for the bulk metadata feed.

    ``url`` is the absolute HTTP(S) location of the latest snapshot; ``etag`` /
    ``content_length`` / ``last_modified`` are the response headers when known
    (used for cache revalidation — a matching local file is reused). ``None``
    fields mean the HEAD/GET did not supply them (still usable).
    """

    url: str
    etag: str | None = None
    content_length: int | None = None
    last_modified: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "url": self.url,
            "etag": self.etag,
            "content_length": self.content_length,
            "last_modified": self.last_modified,
        }


def discover_bulk_feed(
    *,
    candidate_urls: tuple[str, ...] | list[str] | None = None,
    opener: object | None = None,
    timeout_s: float = 30.0,
) -> BulkFeedInfo:
    """HEAD the bulk-metadata candidate URLs and return the first live one.

    ``opener`` is an injectable ``urllib.request``-compatible callable
    ``(Request, timeout=...) -> addinfourl`` (tests pass a mock); production
    uses ``urllib.request.urlopen``. Raises ``FileNotFoundError`` if no
    candidate responds 2xx — the sync then falls back to pure OAI rather than
    crashing the nightly.
    """
    urls = (
        tuple(candidate_urls)
        if candidate_urls is not None
        else BULK_METADATA_CANDIDATE_URLS
    )
    open_fn = opener if opener is not None else urllib.request.urlopen
    last_err: Exception | None = None
    for url in urls:
        try:
            req = urllib.request.Request(
                url,
                method="HEAD",
                headers={
                    "User-Agent": (
                        "Antiek/0.1 (acquisition.arxiv.bulk; "
                        "+https://antiek.ai/contact)"
                    )
                },
            )
            with open_fn(req, timeout=timeout_s) as resp:  # type: ignore[operator]
                status = getattr(resp, "status", None) or resp.getcode()
                if int(status) >= 400:
                    last_err = urllib.error.HTTPError(
                        url, int(status), f"HEAD {status}", resp.headers, None
                    )
                    continue
                headers = resp.headers
                length_raw = headers.get("Content-Length") or headers.get(
                    "content-length"
                )
                length = (
                    int(length_raw)
                    if length_raw and str(length_raw).isdigit()
                    else None
                )
                return BulkFeedInfo(
                    url=url,
                    etag=headers.get("ETag") or headers.get("etag"),
                    content_length=length,
                    last_modified=headers.get("Last-Modified")
                    or headers.get("last-modified"),
                )
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            TimeoutError,
            OSError,
            ValueError,
        ) as exc:
            last_err = exc
            logger.info("bulk feed HEAD failed for %s: %s", url, exc)
            continue
    raise FileNotFoundError(
        f"no bulk metadata feed reachable among {len(urls)} candidates"
        + (f" (last error: {last_err})" if last_err else "")
    )


def download_bulk_snapshot(
    dest_path: str,
    *,
    url: str | None = None,
    feed: BulkFeedInfo | None = None,
    opener: object | None = None,
    timeout_s: float = 600.0,
    chunk_size: int = 1 << 20,
    progress: object | None = None,
) -> str:
    """Stream-download the bulk metadata snapshot to ``dest_path`` (atomic).

    Writes to ``dest_path.tmp`` then ``os.replace`` so a crash mid-download
    never leaves a half-file that a later run would treat as complete. Returns
    the absolute path written. ``opener`` is injectable for tests (a callable
    taking a Request and returning a file-like with ``.read(n)`` + headers).
    ``progress`` if provided is called as ``progress(bytes_so_far, total_or_None)``
    per chunk (operator observability; ignored when None).

    NO arXiv rate governor is applied: this is a single GET of a public GCS
    object, not an arXiv-host request (GCS is not in the arXiv IP-ban scope).
    """
    target = Path(dest_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    src = url or (feed.url if feed is not None else DEFAULT_BULK_METADATA_URL)
    open_fn = opener if opener is not None else urllib.request.urlopen
    req = urllib.request.Request(
        src,
        headers={
            "User-Agent": (
                "Antiek/0.1 (acquisition.arxiv.bulk; +https://antiek.ai/contact)"
            )
        },
    )
    tmp = target.with_suffix(target.suffix + ".tmp")
    total = feed.content_length if feed is not None else None
    written = 0
    with open_fn(req, timeout=timeout_s) as resp:  # type: ignore[operator]
        try:
            cl = resp.headers.get("Content-Length") or resp.headers.get(
                "content-length"
            )
            if cl and str(cl).isdigit():
                total = int(cl)
        except Exception:
            pass
        with open(tmp, "wb") as out:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                out.write(chunk)
                written += len(chunk)
                if progress is not None:
                    progress(written, total)  # type: ignore[operator]
    os.replace(tmp, target)
    logger.info(
        "bulk snapshot downloaded: %s (%d bytes) from %s", target, written, src
    )
    return str(target.resolve())


def ensure_bulk_snapshot(
    *,
    snapshot_path: str | None = None,
    force: bool = False,
    candidate_urls: tuple[str, ...] | list[str] | None = None,
    opener: object | None = None,
    discover_timeout_s: float = 30.0,
    download_timeout_s: float = 600.0,
) -> str:
    """Return a local path to a bulk metadata snapshot, downloading if needed.

    If ``snapshot_path`` already exists and is non-empty and ``force`` is
    False, it is reused (no network). Otherwise the bulk feed is discovered
    and streamed to that path. Returns the absolute path.
    """
    path = Path(snapshot_path or default_bulk_snapshot_path())
    if path.exists() and path.stat().st_size > 0 and not force:
        return str(path.resolve())
    feed = discover_bulk_feed(
        candidate_urls=candidate_urls,
        opener=opener,
        timeout_s=discover_timeout_s,
    )
    return download_bulk_snapshot(
        str(path),
        feed=feed,
        opener=opener,
        timeout_s=download_timeout_s,
    )


def paper_to_oai_record(paper: ArxivPaper) -> ArxivOaiRecord:
    """Map a bulk-discovered ``ArxivPaper`` onto the OAI record shape the
    sync's persist tap + census fold consume.

    ``datestamp`` is the paper's ``updated_at`` (ISO date) — the closest bulk
    equivalent of the OAI header datestamp, and what the high-water mark
    advances on. A missing/epoch updated_at falls back to published_at, then
    to the empty string (which does not advance the mark — safer than inventing
    a date).
    """
    ds = ""
    for candidate in (paper.updated_at, paper.published_at):
        if candidate is not None and candidate.year > 1970:
            ds = candidate.date().isoformat()
            break
    return ArxivOaiRecord(
        arxiv_id=paper.arxiv_id,
        datestamp=ds,
        license_uri=paper.license_uri,
        title=paper.title or None,
        categories=tuple(paper.categories),
        deleted=False,
    )


def record_dict_to_oai_record(record: dict[str, object]) -> ArxivOaiRecord:
    """Map ONE bulk-snapshot JSON dict directly to ``ArxivOaiRecord`` without
    the intermediate ``ArxivPaper`` (cheaper for the multi-million-line stream
    the nightly bulk mode walks). Raises ``ValueError`` on a missing id.
    """
    arxiv_id = str(record.get("id") or "").strip()
    if not arxiv_id:
        raise ValueError("bulk record has no id")
    license_uri = record.get("license")
    license_uri = str(license_uri).strip() if license_uri else None
    title = " ".join(str(record.get("title") or "").split()) or None
    categories = tuple(
        c for c in str(record.get("categories") or "").split() if c
    )
    # Datestamp preference: update_date (ISO YYYY-MM-DD) > last versions[].created
    ds = ""
    upd = record.get("update_date")
    if upd:
        ds = str(upd).strip()[:10]  # tolerate a full ISO datetime
        if len(ds) != 10 or ds[4] != "-" or ds[7] != "-":
            ds = ""
    if not ds:
        versions = record.get("versions") or []
        if (
            isinstance(versions, list)
            and versions
            and isinstance(versions[-1], dict)
            and versions[-1].get("created")
        ):
            parsed = _parse_rfc822(str(versions[-1]["created"]))
            if parsed is not None:
                ds = parsed.date().isoformat()
    return ArxivOaiRecord(
        arxiv_id=arxiv_id,
        datestamp=ds,
        license_uri=license_uri,
        title=title,
        categories=categories,
        deleted=False,
    )


def iter_bulk_oai_records(
    snapshot: IO[str],
    *,
    since: str | None = None,
    until: str | None = None,
    category: str | None = None,
    limit: int | None = None,
) -> Iterator[ArxivOaiRecord]:
    """Stream ``ArxivOaiRecord``s from an open JSON-Lines bulk snapshot.

    ``since`` / ``until`` are inclusive ISO date bounds (``YYYY-MM-DD``)
    applied to each record's datestamp; records with no datestamp pass the
    filter (better to re-cover than to silently drop). ``category`` and
    ``limit`` match ``iter_bulk_candidates``. Malformed lines are skipped.

    This is the bulk half of the nightly sync: same record shape the OAI
    harvester yields, so the persist tap + census + high-water tracker need
    no bulk-specific branch.
    """
    yielded = 0
    for line in snapshot:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        try:
            oai = record_dict_to_oai_record(record)
        except ValueError:
            continue
        if category is not None and category not in oai.categories:
            continue
        if since is not None and oai.datestamp and oai.datestamp < since:
            continue
        if until is not None and oai.datestamp and oai.datestamp > until:
            continue
        yield oai
        yielded += 1
        if limit is not None and yielded >= limit:
            return


@contextmanager
def open_bulk_snapshot(path: str) -> Iterator[IO[str]]:
    """Open a bulk snapshot for streaming, handling plain JSON-Lines, ``.gz``,
    and ``.tar`` / ``.tar.gz`` wrappers (stdlib only — no new heavy deps).

    A tar archive is expected to contain exactly one JSON/JSON-Lines member
    (the Kaggle/GCS snapshot layout); the first ``.json`` / ``.jsonl`` member
    is streamed. Yields a text file object. Always closes underlying handles.
    """
    p = Path(path)
    name = p.name.lower()
    if name.endswith((".tar.gz", ".tgz", ".tar")):
        mode: Literal["r:gz", "r:"] = "r:gz" if name.endswith((".gz", ".tgz")) else "r:"
        with tarfile.open(path, mode) as tf:
            member = None
            for m in tf.getmembers():
                if not m.isfile():
                    continue
                lower = m.name.lower()
                if lower.endswith((".json", ".jsonl", ".json.gz")):
                    member = m
                    break
            if member is None:
                raise FileNotFoundError(
                    f"bulk tar {path!r} has no .json/.jsonl member"
                )
            raw = tf.extractfile(member)
            if raw is None:
                raise FileNotFoundError(
                    f"bulk tar member {member.name!r} is not readable"
                )
            if member.name.lower().endswith(".gz"):
                gz = gzip.GzipFile(fileobj=raw)
                text_fh: IO[str] = io.TextIOWrapper(gz, encoding="utf-8")
            else:
                text_fh = io.TextIOWrapper(raw, encoding="utf-8")
            try:
                yield text_fh
            finally:
                text_fh.close()
        return
    if name.endswith(".gz") and not name.endswith(".tar.gz"):
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            yield fh
        return
    with open(path, encoding="utf-8") as fh:
        yield fh
