"""Paul Graham essay discover-and-ingest driver (SPR-05).

This is a thin, operator-invoked DRIVER over the already-hardened
``acquisition.urls`` connector. It adds NO new acquisition package and does
NOT re-implement fetch/extract/chunk/identity — those stay in
``acquisition/urls/{client,extract,adapter}.py``. What it owns:

  M1 DISCOVER   — parse ``https://paulgraham.com/articles.html`` into a
                  deduplicated list of absolute, on-host, essay-only URLs;
                  honor ``robots.txt`` (urllib.robotparser) and a polite
                  >=3.0s request spacing (the arXiv precedent).
  M2 INGEST     — drive ``ingest_url()`` per essay so the document lands at
                  ``content_class='personal_reading'`` (SPR-02's hardened
                  ``web_article`` default — this driver passes NO content_class,
                  keeping classification inside the one connector chokepoint).
  M3 INCREMENTAL— a re-run over an unchanged corpus is a graph no-op via the
                  connector's ``lookup_url_alias`` short-circuit + the
                  per-essay content-hash compared to the stored document.
  M4 QUALITY    — an honest per-essay extraction-quality verdict. PG's
                  hand-rolled HTML defeats the generic extractor on some
                  essays; those are FLAGGED with a reason and never counted as
                  a clean read.

Lawful acquisition: PG runs his essays on his own public static site; we honor
robots.txt and rate-limit. This is "link, don't mirror" respected — the body is
stored in the owner's personal_reading lane (owner-readable, never publicly
served / ad-attributed / trained on), never re-published.

Box-bounded (§16): every graph write funnels through the connector's single
``runtime.db_lock.connect_write`` writer; this driver is an in-process loop, not
a daemon/queue/second-runtime.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.robotparser
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urldefrag, urljoin, urlparse

# Repo root on path for direct invocation (mirrors adapter.py).
_PKG_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from acquisition.urls.adapter import (  # noqa: E402
    MIN_INGEST_WORD_COUNT,
    IngestUrlResult,
    ingest_url,
    url_doc_id,
)
from acquisition.urls.client import DEFAULT_USER_AGENT, FetchedHtml, fetch  # noqa: E402
from acquisition.urls.extract import html_to_markdown  # noqa: E402

# --- constants -------------------------------------------------------------

PG_HOST = "paulgraham.com"
PG_BASE_URL = "https://paulgraham.com/"
PG_ARTICLES_URL = "https://paulgraham.com/articles.html"
PG_ROBOTS_URL = "https://paulgraham.com/robots.txt"

# Polite minimum request spacing. Justified by the arXiv precedent
# (acquisition/arxiv/throttle.MIN_REQUEST_SPACING_S = 3.0) — a single-operator
# tool hitting a hand-run static site has no reason to go faster, and the cost
# of being impolite (an IP block) dwarfs the per-essay latency.
MIN_REQUEST_SPACING_S = 3.0

# Index / navigation pages on paulgraham.com that are NOT essays. articles.html
# links to a handful of non-essay pages; drop them so the discovered set is
# essays only.
_NON_ESSAY_SLUGS = frozenset({
    "index.html",
    "articles.html",
    "rss.html",
    "books.html",
    "bio.html",
    "raq.html",
    "faq.html",
    "antispam.html",
    "spamconference.html",  # conference page, not an essay (kept conservative)
    "sitemap.html",
    "more.html",
})

# An essay link on articles.html is a relative ``<slug>.html`` on the same host.
_ESSAY_HREF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.html$")

# Extraction-quality: a markup-leakage heuristic. After extraction the body is
# markdown; residual raw HTML tags mean the extractor failed to strip chrome.
_RESIDUAL_TAG_RE = re.compile(r"</?(?:table|font|td|tr|div|span|img)\b", re.I)


# --- M1: discovery ---------------------------------------------------------


class _ArticleListParser(HTMLParser):
    """Collect every ``href`` from articles.html. Filtering to essays-only is
    done by the caller against the page base + the non-essay denylist, so this
    stays a dumb anchor collector (easy to test)."""

    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for name, value in attrs:
            if name.lower() == "href" and value:
                self.hrefs.append(value.strip())


def _is_essay_url(url: str) -> bool:
    """True iff ``url`` is an on-host paulgraham.com ``<slug>.html`` essay that
    is not in the non-essay denylist."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.netloc.lower()
    # Exact host or bare www.; a look-alike host (paulgraham.com.evil.com) is
    # NOT accepted.
    if host not in (PG_HOST, f"www.{PG_HOST}"):
        return False
    slug = parsed.path.lstrip("/")
    if "/" in slug:  # essays live at the site root, not in a subdir
        return False
    if not _ESSAY_HREF_RE.match(slug):
        return False
    return slug not in _NON_ESSAY_SLUGS


def parse_article_list(html: bytes | str, *, base_url: str = PG_BASE_URL) -> list[str]:
    """Parse articles.html into a deduplicated, order-preserving list of
    absolute essay URLs. Fragments/anchors are stripped; off-host, non-essay,
    and index links are dropped. No network — pure string in, list out."""
    if isinstance(html, bytes):
        html = html.decode("utf-8", errors="replace")
    parser = _ArticleListParser()
    parser.feed(html)

    seen: set[str] = set()
    out: list[str] = []
    for href in parser.hrefs:
        absolute, _frag = urldefrag(urljoin(base_url, href))
        # Canonicalize www. -> bare host so the same essay under both forms
        # dedups to one URL (and one doc_id downstream).
        parsed = urlparse(absolute)
        if parsed.netloc.lower() == f"www.{PG_HOST}":
            absolute = absolute.replace(f"www.{PG_HOST}", PG_HOST, 1)
        if not _is_essay_url(absolute):
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        out.append(absolute)
    return out


def load_robots(
    *,
    robots_txt: str | None = None,
    fetch_text: Callable[[str], str] | None = None,
) -> urllib.robotparser.RobotFileParser:
    """Build a parsed RobotFileParser for paulgraham.com.

    ``robots_txt`` injects the robots body directly (tests / offline). Else
    ``fetch_text`` (or a default urllib fetch) retrieves it. A robots.txt that
    cannot be fetched fails OPEN per the standard convention (no rules → all
    allowed) — but the per-URL ``can_fetch`` check still runs, so an explicit
    Disallow is always honored when robots IS present.
    """
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(PG_ROBOTS_URL)
    # Marker the run reads to surface a VISIBLE warning when robots could not be
    # fetched/parsed and we fell open (the weaker posture for a lane whose
    # lawful-acquisition stance is load-bearing). None ⇒ robots was applied.
    rp._antiek_robots_fail_open = None  # type: ignore[attr-defined]
    if robots_txt is not None:
        rp.parse(robots_txt.splitlines())
        return rp
    if fetch_text is None:
        def fetch_text(u: str) -> str:  # pragma: no cover - real network
            page = fetch(u)
            return page.body.decode("utf-8", errors="replace")
    try:
        rp.parse(fetch_text(PG_ROBOTS_URL).splitlines())
    except Exception as exc:
        # Fail open: an unreachable robots.txt means no stated rules; the
        # subsequent can_fetch() returns True (the RFC default). But record WHY
        # so the operator SEES that robots enforcement was disabled for this run
        # rather than silently assuming the site allowed us.
        rp.parse([])
        rp._antiek_robots_fail_open = (  # type: ignore[attr-defined]
            f"robots.txt unreachable/unparseable ({type(exc).__name__}: {exc}); "
            "failed OPEN (no rules enforced this run)"
        )
    return rp


def robots_allows(rp: urllib.robotparser.RobotFileParser, url: str) -> bool:
    """True iff ``rp`` permits our User-Agent to fetch ``url``."""
    return rp.can_fetch(DEFAULT_USER_AGENT, url)


# --- polite throttle (modeled on acquisition/arxiv/throttle.ArxivThrottle) --


class PoliteThrottle:
    """Minimum-request-spacing gate with injectable clock + sleep so tests
    never block. Deliberately simpler than ArxivThrottle (no cross-process ban
    sentinel) — a hand-run static site does not 429-IP-ban like the arXiv API,
    and the box-bounded single-operator run is the only writer. The >=3.0s
    spacing constant is shared rationale with the arXiv throttle."""

    def __init__(
        self,
        *,
        min_spacing_s: float = MIN_REQUEST_SPACING_S,
        now: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._min_spacing = float(min_spacing_s)
        self._now = now
        self._sleep = sleep
        self._last_request_at: float | None = None

    def wait_if_needed(self) -> None:
        now = self._now()
        if self._last_request_at is not None:
            elapsed = now - self._last_request_at
            if elapsed < self._min_spacing:
                self._sleep(self._min_spacing - elapsed)
                now = self._now()
        self._last_request_at = now


# --- M4: extraction-quality verdict ----------------------------------------


@dataclass(frozen=True)
class EssayQuality:
    """Per-essay quality verdict. ``verdict`` is 'ok' | 'flagged'. ``ingested``
    distinguishes an essay whose body landed in the graph from one the connector
    skipped (low word count) — a flagged-skipped essay is NEVER a clean read."""

    url: str
    document_id: str
    word_count: int
    verdict: str
    reason: str | None
    ingested: bool
    skipped_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "document_id": self.document_id,
            "word_count": self.word_count,
            "verdict": self.verdict,
            "reason": self.reason,
            "ingested": self.ingested,
            "skipped_reason": self.skipped_reason,
        }


def assess_extraction_quality(
    *,
    url: str,
    document_id: str,
    word_count: int,
    markdown: str,
    skipped_reason: str | None,
    min_word_count: int = MIN_INGEST_WORD_COUNT,
) -> EssayQuality:
    """Compute an honest quality verdict for one extracted essay.

    Flags (any one ⇒ 'flagged'):
      * the connector skipped graph writes for low word count (the body never
        landed — it is NOT a clean read);
      * the extracted body is below ``min_word_count`` (mis-extracted or a
        paywall stub — surfaced even if the connector did write it);
      * residual raw HTML tags leaked into the markdown body (PG's table/font
        layout defeated the extractor — markup-soup, not clean prose).

    A genuinely short essay (some PG essays ARE short) that clears the word
    floor and has no markup leakage is 'ok'. We do NOT round a mis-extraction
    up to success.
    """
    ingested = skipped_reason is None
    reasons: list[str] = []
    if skipped_reason == "low_word_count" or skipped_reason == "low_word_count_after_fallback":
        reasons.append(f"connector skipped graph writes ({skipped_reason})")
    if word_count < min_word_count:
        reasons.append(f"word_count {word_count} < min {min_word_count}")
    if _RESIDUAL_TAG_RE.search(markdown or ""):
        reasons.append("residual HTML tags leaked into body (markup-soup)")

    if reasons:
        return EssayQuality(
            url=url,
            document_id=document_id,
            word_count=word_count,
            verdict="flagged",
            reason="; ".join(reasons),
            ingested=ingested,
            skipped_reason=skipped_reason,
        )
    return EssayQuality(
        url=url,
        document_id=document_id,
        word_count=word_count,
        verdict="ok",
        reason=None,
        ingested=ingested,
        skipped_reason=skipped_reason,
    )


# --- run summary -----------------------------------------------------------


@dataclass
class RunSummary:
    """Per-run counts. ``ingested_clean`` + ``ingested_flagged`` +
    ``skipped_flagged`` + ``skipped_unchanged`` + ``robots_disallowed`` +
    ``errored`` accounts for every discovered URL that was processed."""

    discovered: int = 0
    fetched: int = 0
    ingested_clean: int = 0
    ingested_flagged: int = 0
    skipped_flagged: int = 0  # connector skipped graph write (low word count)
    skipped_unchanged: int = 0  # alias short-circuit, no re-fetch
    changed_reingested: int = 0
    robots_disallowed: int = 0
    errored: int = 0
    qualities: list[EssayQuality] = field(default_factory=list)
    robots_disallowed_urls: list[str] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)
    # Visible operator warnings (e.g. robots.txt fail-open) — surfaced rather
    # than silently degrading the lawful-acquisition posture.
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "discovered": self.discovered,
            "fetched": self.fetched,
            "ingested_clean": self.ingested_clean,
            "ingested_flagged": self.ingested_flagged,
            "skipped_flagged": self.skipped_flagged,
            "skipped_unchanged": self.skipped_unchanged,
            "changed_reingested": self.changed_reingested,
            "robots_disallowed": self.robots_disallowed,
            "errored": self.errored,
            "robots_disallowed_urls": list(self.robots_disallowed_urls),
            "errors": [{"url": u, "error": e} for u, e in self.errors],
            "warnings": list(self.warnings),
            "essays": [q.to_dict() for q in self.qualities],
        }


# --- M2 + M3 + M4 orchestration --------------------------------------------


def default_report_path() -> str:
    """Deterministic operator artifact path for the quality report."""
    return os.path.join(_PKG_ROOT, "artifacts", "paulgraham", "extraction_quality.json")


def write_quality_report(summary: RunSummary, *, path: str | None = None) -> str:
    """Write the per-essay extraction-quality report as JSON. Returns the path."""
    out_path = path or default_report_path()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(summary.to_dict(), fh, indent=2, sort_keys=True)
    return out_path


def discover(
    *,
    articles_html: bytes | str | None = None,
    fetch_html: Callable[[str], FetchedHtml] | None = None,
) -> list[str]:
    """Return the deduplicated absolute essay-URL list.

    ``articles_html`` injects the page body directly (tests/offline). Else
    ``fetch_html`` (or the connector's ``fetch``) retrieves articles.html.
    """
    if articles_html is None:
        fetcher = fetch_html or fetch
        page = fetcher(PG_ARTICLES_URL)
        articles_html = page.body
    return parse_article_list(articles_html, base_url=PG_BASE_URL)


def run(
    *,
    investigation_id: str,
    db_path: str | None = None,
    embedder: Any | None = None,
    # M1 injection seams (tests/offline):
    articles_html: bytes | str | None = None,
    robots_txt: str | None = None,
    robots_fetch_text: Callable[[str], str] | None = None,
    # Map URL -> FetchedHtml so the run never touches the live network in tests.
    fetched_by_url: dict[str, FetchedHtml] | None = None,
    http_client: object | None = None,
    throttle: PoliteThrottle | None = None,
    report_path: str | None = None,
    write_report: bool = True,
    limit: int | None = None,
    min_word_count: int = MIN_INGEST_WORD_COUNT,
) -> RunSummary:
    """Discover + ingest the PG essays into the personal_reading lane.

    Every graph write goes through ``ingest_url`` (single-writer
    ``connect_write``); this function never calls ``insert_document`` and never
    passes a ``content_class`` — the connector owns classification, so the
    corpus_audit literal-content_class bypass scanner stays satisfied.
    """
    summary = RunSummary()
    urls = discover(articles_html=articles_html)
    if limit is not None:
        urls = urls[:limit]
    summary.discovered = len(urls)

    rp = load_robots(robots_txt=robots_txt, fetch_text=robots_fetch_text)
    fail_open = getattr(rp, "_antiek_robots_fail_open", None)
    if fail_open:
        summary.warnings.append(fail_open)
    thr = throttle or PoliteThrottle()
    fetched_by_url = fetched_by_url or {}

    for url in urls:
        if not robots_allows(rp, url):
            summary.robots_disallowed += 1
            summary.robots_disallowed_urls.append(url)
            continue

        # M3 — alias short-circuit (no re-fetch) for already-seen URLs whose
        # stored content hasn't changed. We pass a bare URL (no fetched=) so
        # ingest_url consults lookup_url_alias first.
        injected = fetched_by_url.get(url)

        # Throttle only when we are actually going to hit the network. The
        # alias short-circuit path does not fetch, so it does not need spacing;
        # but ingest_url decides that internally, so we space before any call
        # that MIGHT fetch (i.e. when we did not inject a pre-fetched body for
        # a test). Conservative: spacing a no-op call is harmless.
        if injected is None:
            thr.wait_if_needed()

        try:
            if injected is not None:
                # Test/offline path: decide alias vs (re)ingest ourselves so we
                # mirror the connector's idempotency without a live fetch.
                existing = _stored_content_hash(url, db_path=db_path)
                new_hash = "sha256:" + _content_hash_of(injected)
                if existing is not None and existing == new_hash:
                    summary.skipped_unchanged += 1
                    q = _quality_for_injected(
                        url, injected, skipped_reason="unchanged",
                        min_word_count=min_word_count,
                    )
                    # An unchanged skip is not re-graded as a read; record it
                    # as the prior verdict shape but mark not-ingested-now.
                    summary.qualities.append(q)
                    continue
                changed = existing is not None and existing != new_hash
                # A first ingest or an unchanged re-ingest is a graph no-op under
                # the connector's deterministic ids (``ignore``). A genuinely
                # CHANGED body must actually OVERWRITE the stored row + chunks
                # under the same document_id (``replace``) — counting it as
                # "changed_reingested" while the connector silently kept the
                # stale body is the "round a non-update up to success" dishonesty
                # rigor #1 forbids.
                result = ingest_url(
                    url,
                    investigation_id=investigation_id,
                    db_path=db_path,
                    embedder=embedder,
                    fetched=injected,
                    min_word_count=min_word_count,
                    on_conflict="replace" if changed else "ignore",
                )
                summary.fetched += 1
                if changed:
                    summary.changed_reingested += 1
            else:
                result = ingest_url(
                    url,
                    investigation_id=investigation_id,
                    db_path=db_path,
                    embedder=embedder,
                    http_client=http_client,
                    min_word_count=min_word_count,
                )
                if result.skipped_reason == "alias_resolved_to_existing_document":
                    summary.skipped_unchanged += 1
                    continue
                summary.fetched += 1
        except Exception as exc:  # network/extract failure for one essay
            summary.errored += 1
            summary.errors.append((url, f"{type(exc).__name__}: {exc}"))
            continue

        # M4 — quality verdict from the markdown the connector extracted.
        md_word_count, md_text = _extracted_md(url, injected, result, db_path=db_path)
        q = assess_extraction_quality(
            url=url,
            document_id=result.document_id,
            word_count=md_word_count,
            markdown=md_text,
            skipped_reason=result.skipped_reason,
            min_word_count=min_word_count,
        )
        summary.qualities.append(q)

        if result.skipped_reason is not None:
            # Connector did not write the body (low word count). Flagged,
            # not-stored — never a clean read.
            summary.skipped_flagged += 1
        elif q.verdict == "flagged":
            summary.ingested_flagged += 1
        else:
            summary.ingested_clean += 1

    if write_report:
        write_quality_report(summary, path=report_path)
    return summary


# --- internals -------------------------------------------------------------


def _content_hash_of(page: FetchedHtml) -> str:
    """The content hash for a pre-fetched body (extract then hash). Matches the
    hash ``_stored_content_hash`` recomputes from the persisted
    ``documents.raw_text`` exactly — both are
    ``content_hash(html_to_markdown(body).markdown)`` and ``raw_text`` IS that
    markdown — so an unchanged re-fetch compares equal and a changed one differs."""
    from processing.chunking.chunker import content_hash

    md = html_to_markdown(page.body, base_url=page.final_url)
    return content_hash(md.markdown)


def _extracted_md(
    url: str,
    injected: FetchedHtml | None,
    result: IngestUrlResult,
    *,
    db_path: str | None = None,
) -> tuple[int, str]:
    """Recover the extracted markdown + word count for the quality verdict.

    Injected (test) path: re-extract from the body we hold.

    LIVE operator path: the connector already extracted and stored the body, but
    this driver does not hold it. We read the persisted ``documents.raw_text``
    back (it IS the extracted markdown) and count its words, so the M4
    markup-leakage + word-count heuristics inspect the ACTUAL extracted prose of
    a hostile PG essay on the real run — not an empty-string placeholder that
    could never flag (the M4 rigor centerpiece must fire in production, not only
    under test). If the body cannot be read back (e.g. the connector skipped the
    write for low word count), we fall back to an empty body; the
    connector-skip + low-word-count flags still fire off ``skipped_reason``.
    """
    if injected is not None:
        md = html_to_markdown(injected.body, base_url=injected.final_url)
        return md.word_count, md.markdown
    # Live path.
    stored = _stored_raw_text(url, db_path=db_path)
    if stored:
        return len(stored.split()), stored
    return 0, ""


def _stored_raw_text(url: str, *, db_path: str | None) -> str | None:
    """Read back the persisted ``documents.raw_text`` (the extracted markdown)
    for this URL's document so the live-path quality verdict inspects the real
    extracted body. Returns None when the doc/DB is absent."""

    from substrate.graph import default_db_path

    resolved = db_path or default_db_path()
    document_id = url_doc_id(url)
    try:
        from runtime.db_lock import connect_read

        con = connect_read(resolved)
    except Exception:
        return None
    try:
        try:
            row = con.execute(
                "SELECT raw_text FROM documents WHERE document_id = ?",
                [document_id],
            ).fetchone()
        except Exception:
            return None
        return row[0] if row and row[0] else None
    finally:
        con.close()


def _quality_for_injected(
    url: str,
    injected: FetchedHtml,
    *,
    skipped_reason: str | None,
    min_word_count: int,
) -> EssayQuality:
    md = html_to_markdown(injected.body, base_url=injected.final_url)
    base = assess_extraction_quality(
        url=url,
        document_id=url_doc_id(injected.final_url),
        word_count=md.word_count,
        markdown=md.markdown,
        skipped_reason=None,
        min_word_count=min_word_count,
    )
    # Re-stamp as an unchanged skip (not ingested now).
    return EssayQuality(
        url=base.url,
        document_id=base.document_id,
        word_count=base.word_count,
        verdict=base.verdict,
        reason=base.reason,
        ingested=False,
        skipped_reason=skipped_reason,
    )


def _stored_content_hash(url: str, *, db_path: str | None) -> str | None:
    """The content hash of this URL's already-stored document body, if any.

    The hash the connector emits lives only on the ``document.loaded`` EVENT
    (``DocumentLoadedPayload.content_hash``), not as a column on the ``documents``
    table (whose columns are document_id / source_uri / title / author /
    published_at / source_tier / document_type / investigation_id / raw_text /
    metadata / content_class / ip_holder_id / owner_user_id — verified, NO
    content_hash column, NO events table in this graph DB). The robust,
    schema-change-free source of truth is therefore to RECOMPUTE the hash from
    the persisted body: ``documents.raw_text`` IS exactly the extracted markdown
    the connector chunked, so ``"sha256:" + content_hash(raw_text)`` equals the
    ``new_hash`` the driver computes for a freshly-fetched identical body
    (verified: content_hash(raw_text) == content_hash(html_to_markdown(body))).
    Returns None when the doc/DB is absent so a first run treats every essay as
    new.
    """

    from processing.chunking.chunker import content_hash
    from substrate.graph import default_db_path

    resolved = db_path or default_db_path()
    document_id = url_doc_id(url)
    try:
        from runtime.db_lock import connect_read

        con = connect_read(resolved)
    except Exception:
        return None
    try:
        try:
            row = con.execute(
                "SELECT raw_text FROM documents WHERE document_id = ?",
                [document_id],
            ).fetchone()
        except Exception:
            return None
        if row and row[0]:
            return "sha256:" + content_hash(row[0])
        return None
    finally:
        con.close()


# --- CLI -------------------------------------------------------------------


def _main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m acquisition.urls.paulgraham",
        description="Discover + ingest Paul Graham essays into the "
        "personal_reading lane via the hardened acquisition/urls connector.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_disc = sub.add_parser("discover", help="parse articles.html, print URLs")
    p_disc.add_argument(
        "--articles-file",
        help="path to a local articles.html (offline); else fetch live",
    )

    p_run = sub.add_parser("run", help="discover + ingest into personal_reading")
    p_run.add_argument("--investigation-id", required=True)
    p_run.add_argument("--db-path", default=None)
    p_run.add_argument("--report-path", default=None)
    p_run.add_argument("--limit", type=int, default=None)

    args = parser.parse_args(argv)

    if args.cmd == "discover":
        body: bytes | None = None
        if args.articles_file:
            with open(args.articles_file, "rb") as fh:
                body = fh.read()
        urls = discover(articles_html=body)
        for u in urls:
            print(u)
        print(f"\n# discovered {len(urls)} essays", file=sys.stderr)
        return 0

    if args.cmd == "run":
        summary = run(
            investigation_id=args.investigation_id,
            db_path=args.db_path,
            report_path=args.report_path,
            limit=args.limit,
        )
        print(json.dumps(summary.to_dict(), indent=2))
        return 0

    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
