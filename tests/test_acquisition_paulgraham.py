"""Tests for the Paul Graham essay discover-and-ingest driver (SPR-05).

Offline by construction (rigor #3): a checked-in ``articles.html`` fixture, a
few essay fixtures, injected ``FetchedHtml`` bodies, an injected ``sleep`` so the
throttle never blocks, and a temp DuckDB. NO live network, NO production DB.

The ``-k`` selectors used by the sprint's verification gates are baked into the
test names: ``discover``, ``owner_read``, ``attribution``, ``incremental``,
``extraction_quality``.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.urls.adapter import url_doc_id
from acquisition.urls.client import FetchedHtml
from acquisition.urls import paulgraham as pg
from substrate.constants import (
    PERSONAL_READABLE_CONTENT_CLASSES,
    PERSONAL_READING_CONTENT_CLASS,
    SERVABLE_CONTENT_CLASSES,
)


_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "paulgraham")


def _read_fixture(name: str) -> bytes:
    with open(os.path.join(_FIXTURE_DIR, name), "rb") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_substrate(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-pg-test-")
    db_path = os.path.join(tmpdir, "graph.duckdb")
    events_dir = os.path.join(tmpdir, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_EVENT_LOG_DIR", events_dir)
    monkeypatch.setenv("ANTIEK_EVENT_DIR", events_dir)
    yield {"db_path": db_path, "events_dir": events_dir, "tmpdir": tmpdir}


class _StubEmbedder:
    """Deterministic 16-d embedder — no model download in CI."""

    def encode(self, text: str) -> list[float]:
        h = abs(hash(text)) % 16
        v = [0.0] * 16
        v[h] = 1.0
        return v


def _no_sleep_throttle():
    """A throttle whose sleep is a no-op (tests never block for 3 seconds),
    while still advancing a fake clock so spacing logic is exercised."""
    clock = {"t": 0.0}

    def now() -> float:
        return clock["t"]

    def sleep(s: float) -> None:
        clock["t"] += s  # advance instead of blocking

    return pg.PoliteThrottle(now=now, sleep=sleep)


def _fetched(slug: str, body: bytes) -> FetchedHtml:
    url = f"https://paulgraham.com/{slug}.html"
    return FetchedHtml(
        requested_url=url,
        final_url=url,
        status_code=200,
        content_type="text/html; charset=utf-8",
        charset="utf-8",
        body=body,
    )


# ---------------------------------------------------------------------------
# M1 — DISCOVER (gate: -k discover)
# ---------------------------------------------------------------------------


def test_discover_count_at_least_200():
    """Parse the fixture articles.html; assert >= 200 essays discovered."""
    urls = pg.discover(articles_html=_read_fixture("articles.html"))
    assert len(urls) >= 200, f"expected >= 200 essays, got {len(urls)}"


def test_discover_urls_are_absolute_on_host_essays():
    urls = pg.discover(articles_html=_read_fixture("articles.html"))
    assert urls, "no essays discovered"
    for u in urls:
        assert u.startswith("https://paulgraham.com/")
        assert u.endswith(".html")
        # No fragments, no off-host, no subdir.
        assert "#" not in u
        assert "paulgraham.com/" in u and "paulgraham.com.evil" not in u
        assert u.count("/") == 3  # https://host/slug.html


def test_discover_drops_index_and_noise_links():
    urls = pg.discover(articles_html=_read_fixture("articles.html"))
    bad = {
        "https://paulgraham.com/index.html",
        "https://paulgraham.com/articles.html",
        "https://paulgraham.com/rss.html",
        "https://paulgraham.com/books.html",
        "https://paulgraham.com/bio.html",
        "https://paulgraham.com.evil.com/phish.html",
        "https://paulgraham.com/essays/sub.html",
    }
    assert not (set(urls) & bad), f"noise leaked into discovery: {set(urls) & bad}"


def test_discover_dedups_anchor_and_www_forms():
    urls = pg.discover(articles_html=_read_fixture("articles.html"))
    # greatwork.html#intro and the www form of wealth.html must collapse to one.
    assert urls.count("https://paulgraham.com/greatwork.html") == 1
    assert urls.count("https://paulgraham.com/wealth.html") == 1


def test_parse_article_list_is_pure_no_network():
    # Pure string in -> list out; never calls the network.
    out = pg.parse_article_list(
        '<a href="foo.html">F</a><a href="index.html">I</a>'
        '<a href="https://other.com/x.html">X</a>'
    )
    assert out == ["https://paulgraham.com/foo.html"]


# ---------------------------------------------------------------------------
# M1 — robots + throttle
# ---------------------------------------------------------------------------


def test_robots_disallow_is_honored():
    rp = pg.load_robots(robots_txt="User-agent: *\nDisallow: /private.html\n")
    assert pg.robots_allows(rp, "https://paulgraham.com/greatwork.html")
    assert not pg.robots_allows(rp, "https://paulgraham.com/private.html")


def test_robots_missing_fails_open():
    # No robots rules -> everything allowed (RFC default).
    rp = pg.load_robots(robots_txt="")
    assert pg.robots_allows(rp, "https://paulgraham.com/anything.html")


def test_throttle_spaces_without_real_sleep():
    slept: list[float] = []
    clock = {"t": 0.0}
    thr = pg.PoliteThrottle(
        min_spacing_s=3.0,
        now=lambda: clock["t"],
        sleep=lambda s: (slept.append(s), clock.__setitem__("t", clock["t"] + s)),
    )
    thr.wait_if_needed()  # first call: no wait
    thr.wait_if_needed()  # immediately after: must space by 3.0s
    assert slept and abs(slept[0] - 3.0) < 1e-9
    # The 3.0s value is the arXiv precedent, not an invented number.
    assert pg.MIN_REQUEST_SPACING_S == 3.0


def test_robots_fetch_failure_records_fail_open_warning():
    """When robots.txt cannot be fetched/parsed we fail OPEN (RFC default) but
    record WHY on the parser so the run surfaces a visible operator warning —
    silently disabling robots is the weaker posture for a lane whose lawful-
    acquisition stance is load-bearing."""

    def _boom(_u: str) -> str:
        raise OSError("connection refused")

    rp = pg.load_robots(fetch_text=_boom)
    marker = getattr(rp, "_antiek_robots_fail_open", None)
    assert marker, "fail-open must be recorded when robots.txt cannot be fetched"
    assert "failed OPEN" in marker
    # Fail-open still means everything is allowed (RFC default).
    assert pg.robots_allows(rp, "https://paulgraham.com/anything.html")


def test_robots_applied_records_no_fail_open():
    rp = pg.load_robots(robots_txt="User-agent: *\nDisallow: /x.html\n")
    assert getattr(rp, "_antiek_robots_fail_open", "sentinel") is None


def test_run_surfaces_robots_fail_open_warning(temp_substrate):
    """A run whose robots load failed open carries the warning in its summary +
    report so the operator is not misled into thinking the site allowed us."""

    def _boom(_u: str) -> str:
        raise OSError("connection refused")

    report_path = os.path.join(temp_substrate["tmpdir"], "rep.json")
    body = _read_fixture("greatwork.html")
    url = "https://paulgraham.com/greatwork.html"
    summary = pg.run(
        investigation_id="inv-pg",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        articles_html=b'<a href="greatwork.html">GW</a>',
        robots_fetch_text=_boom,
        fetched_by_url={url: _fetched("greatwork", body)},
        throttle=_no_sleep_throttle(),
        report_path=report_path,
        write_report=True,
    )
    assert any("failed OPEN" in w for w in summary.warnings)
    with open(report_path, encoding="utf-8") as fh:
        report = json.load(fh)
    assert any("failed OPEN" in w for w in report["warnings"])
    # The essay was still ingested (fail-open allows the fetch).
    assert summary.ingested_clean == 1


def test_run_robots_disallowed_essay_is_skipped_not_fetched(temp_substrate):
    body = _read_fixture("greatwork.html")
    summary = pg.run(
        investigation_id="inv-pg",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        articles_html=b'<a href="greatwork.html">GW</a>',
        robots_txt="User-agent: *\nDisallow: /greatwork.html\n",
        fetched_by_url={"https://paulgraham.com/greatwork.html": _fetched("greatwork", body)},
        throttle=_no_sleep_throttle(),
        write_report=False,
    )
    assert summary.discovered == 1
    assert summary.robots_disallowed == 1
    assert summary.fetched == 0
    assert summary.ingested_clean == 0


# ---------------------------------------------------------------------------
# M2 — INGEST into personal_reading; owner-readable (gate: -k owner_read)
# ---------------------------------------------------------------------------


def _run_one(temp_substrate, slug="greatwork", fixture="greatwork.html"):
    body = _read_fixture(fixture)
    url = f"https://paulgraham.com/{slug}.html"
    summary = pg.run(
        investigation_id="inv-pg",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        articles_html=f'<a href="{slug}.html">X</a>'.encode(),
        robots_txt="",
        fetched_by_url={url: _fetched(slug, body)},
        throttle=_no_sleep_throttle(),
        write_report=False,
    )
    return summary, url


def test_ingested_essay_lands_personal_reading_not_servable(temp_substrate):
    import duckdb

    summary, url = _run_one(temp_substrate)
    assert summary.ingested_clean == 1
    doc_id = url_doc_id(url)
    con = duckdb.connect(temp_substrate["db_path"], read_only=True)
    try:
        (content_class, document_type) = con.execute(
            "SELECT content_class, document_type FROM documents WHERE document_id = ?",
            [doc_id],
        ).fetchone()
    finally:
        con.close()
    assert content_class == PERSONAL_READING_CONTENT_CLASS, (
        f"PG essay must land personal_reading, got {content_class!r}"
    )
    assert content_class not in SERVABLE_CONTENT_CLASSES
    assert document_type == "web_article"


def test_owner_read_full_body_not_snippet(temp_substrate):
    """The owner reads the FULL essay body (not a <=500-char snippet) because
    personal_reading is in PERSONAL_READABLE_CONTENT_CLASSES — the owner/
    privileged full-body allowlist (constants.py)."""
    import duckdb

    summary, url = _run_one(temp_substrate)
    doc_id = url_doc_id(url)
    con = duckdb.connect(temp_substrate["db_path"], read_only=True)
    try:
        (content_class, raw_text) = con.execute(
            "SELECT content_class, raw_text FROM documents WHERE document_id = ?",
            [doc_id],
        ).fetchone()
    finally:
        con.close()
    # Owner full-body allowlist admits personal_reading…
    assert content_class in PERSONAL_READABLE_CONTENT_CLASSES
    # …and the stored body is the FULL essay, well beyond a 500-char snippet.
    assert raw_text is not None
    assert len(raw_text) > 500
    assert "intersection look like" in raw_text
    assert "driving your part of it" in raw_text


# ---------------------------------------------------------------------------
# M2 — non-attributable (gate: -k attribution)
# ---------------------------------------------------------------------------


def test_attribution_ineligible_for_ingested_essay(temp_substrate):
    """An ingested PG essay is non-attributable: is_attribution_eligible() is
    False and its class is absent from the public-graph ad surface."""
    from substrate.collective_graph.eligibility import (
        CollectiveGraphDocument,
        is_attribution_eligible,
    )
    from substrate.ad_inventory.attribution import (
        PUBLIC_GRAPH_CONTENT_CLASSES,
        monetization_eligible,
    )

    summary, url = _run_one(temp_substrate)
    doc_id = url_doc_id(url)

    doc = CollectiveGraphDocument(
        document_id=doc_id,
        note_id="n",
        owner_user_id="__operator__",
        content_class=PERSONAL_READING_CONTENT_CLASS,
        quality_gate_result=None,
    )
    assert is_attribution_eligible(doc) is False
    # The earn (ad) gate also excludes personal_reading.
    assert PERSONAL_READING_CONTENT_CLASS not in PUBLIC_GRAPH_CONTENT_CLASSES
    assert monetization_eligible(PERSONAL_READING_CONTENT_CLASS) is False


def test_attribution_lane_membership_invariants():
    from substrate.collective_graph.eligibility import NON_ATTRIBUTABLE_CONTENT_CLASSES
    from substrate.ad_inventory.attribution import PUBLIC_GRAPH_CONTENT_CLASSES

    assert PERSONAL_READING_CONTENT_CLASS in NON_ATTRIBUTABLE_CONTENT_CLASSES
    assert PERSONAL_READING_CONTENT_CLASS not in SERVABLE_CONTENT_CLASSES
    assert PERSONAL_READING_CONTENT_CLASS not in PUBLIC_GRAPH_CONTENT_CLASSES


# ---------------------------------------------------------------------------
# M3 — INCREMENTAL (gate: -k incremental)
# ---------------------------------------------------------------------------


def test_incremental_second_run_adds_zero_rows(temp_substrate):
    import duckdb

    body = _read_fixture("greatwork.html")
    url = "https://paulgraham.com/greatwork.html"
    fetched_by_url = {url: _fetched("greatwork", body)}
    articles = b'<a href="greatwork.html">GW</a>'

    def _run():
        return pg.run(
            investigation_id="inv-pg",
            db_path=temp_substrate["db_path"],
            embedder=_StubEmbedder(),
            articles_html=articles,
            robots_txt="",
            fetched_by_url=fetched_by_url,
            throttle=_no_sleep_throttle(),
            write_report=False,
        )

    s1 = _run()
    con = duckdb.connect(temp_substrate["db_path"], read_only=True)
    try:
        (d1,) = con.execute("SELECT COUNT(*) FROM documents").fetchone()
        (c1,) = con.execute("SELECT COUNT(*) FROM chunks").fetchone()
        (h1,) = con.execute(
            "SELECT content_hash FROM documents WHERE document_id = ?",
            [url_doc_id(url)],
        ).fetchone()
    finally:
        con.close()

    s2 = _run()
    con = duckdb.connect(temp_substrate["db_path"], read_only=True)
    try:
        (d2,) = con.execute("SELECT COUNT(*) FROM documents").fetchone()
        (c2,) = con.execute("SELECT COUNT(*) FROM chunks").fetchone()
        (h2,) = con.execute(
            "SELECT content_hash FROM documents WHERE document_id = ?",
            [url_doc_id(url)],
        ).fetchone()
    finally:
        con.close()

    assert s1.ingested_clean == 1
    assert d2 == d1, "second run added documents"
    assert c2 == c1, "second run added chunks"
    # The unchanged body is detected (its hash == the stored hash) and the
    # second run is a graph no-op — not silently re-ingested.
    assert s2.skipped_unchanged == 1
    assert s2.ingested_clean == 0
    assert h2 == h1, "unchanged second run mutated the stored content_hash"


def test_incremental_changed_content_is_reingested_same_doc_id(temp_substrate):
    import duckdb

    url = "https://paulgraham.com/greatwork.html"
    articles = b'<a href="greatwork.html">GW</a>'

    def _run(body):
        return pg.run(
            investigation_id="inv-pg",
            db_path=temp_substrate["db_path"],
            embedder=_StubEmbedder(),
            articles_html=articles,
            robots_txt="",
            fetched_by_url={url: _fetched("greatwork", body)},
            throttle=_no_sleep_throttle(),
            write_report=False,
        )

    original = _read_fixture("greatwork.html")
    s1 = _run(original)
    # A genuinely edited essay at the SAME url: append a new paragraph.
    edited = original.replace(b"</font>", b"<br><br>A newly added closing thought.</font>", 1)
    s2 = _run(edited)

    assert s1.ingested_clean == 1
    assert s2.changed_reingested == 1
    # Identity stays URL-stable — one document_id, not a fork — AND the stored
    # body must ACTUALLY be the edited one. A counter incremented while the
    # connector silently kept the stale body (the on_conflict='ignore' bug this
    # sprint fixed) is the "round a non-update up to success" dishonesty rigor
    # #1 forbids; this assertion bites on exactly that defect.
    con = duckdb.connect(temp_substrate["db_path"], read_only=True)
    try:
        (n_docs,) = con.execute(
            "SELECT COUNT(*) FROM documents WHERE document_id = ?",
            [url_doc_id(url)],
        ).fetchone()
        # No second doc-url-* row appeared for a different final_url.
        (n_url_docs,) = con.execute(
            "SELECT COUNT(*) FROM documents WHERE document_id LIKE 'doc-url-%'"
        ).fetchone()
        (stored_body,) = con.execute(
            "SELECT raw_text FROM documents WHERE document_id = ?",
            [url_doc_id(url)],
        ).fetchone()
    finally:
        con.close()
    assert n_docs == 1
    assert n_url_docs == 1
    assert "A newly added closing thought" in stored_body, (
        "changed_reingested counted but the edited body was NOT persisted"
    )


# ---------------------------------------------------------------------------
# M4 — EXTRACTION-QUALITY (gate: -k extraction_quality)
# ---------------------------------------------------------------------------


def test_extraction_quality_report_written_and_flags_degraded(temp_substrate):
    report_path = os.path.join(temp_substrate["tmpdir"], "extraction_quality.json")
    good = _read_fixture("greatwork.html")
    bad = _read_fixture("degraded_essay.html")
    articles = b'<a href="greatwork.html">GW</a><a href="spamconf.html">SC</a>'
    fetched_by_url = {
        "https://paulgraham.com/greatwork.html": _fetched("greatwork", good),
        "https://paulgraham.com/spamconf.html": _fetched("spamconf", bad),
    }

    summary = pg.run(
        investigation_id="inv-pg",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        articles_html=articles,
        robots_txt="",
        fetched_by_url=fetched_by_url,
        throttle=_no_sleep_throttle(),
        report_path=report_path,
        write_report=True,
    )

    # Report file exists and is valid JSON.
    assert os.path.exists(report_path)
    with open(report_path, encoding="utf-8") as fh:
        report = json.load(fh)

    by_url = {e["url"]: e for e in report["essays"]}
    gw = by_url["https://paulgraham.com/greatwork.html"]
    sc = by_url["https://paulgraham.com/spamconf.html"]

    # The good essay is a clean read.
    assert gw["verdict"] == "ok"
    assert gw["ingested"] is True

    # The degraded essay is FLAGGED with a reason and NOT counted as a clean read.
    assert sc["verdict"] == "flagged"
    assert sc["reason"]
    # It was skipped by the connector (low word count) → not stored as a read.
    assert sc["ingested"] is False

    # The run summary separates clean from flagged-skipped (honesty: not 2/2 clean).
    assert summary.ingested_clean == 1
    assert summary.skipped_flagged == 1
    assert summary.ingested_clean + summary.skipped_flagged == summary.discovered


def test_assess_extraction_quality_flags_markup_soup():
    # Residual HTML tags in the body ⇒ flagged (markup-soup), even if word count
    # is otherwise fine.
    q = pg.assess_extraction_quality(
        url="https://paulgraham.com/x.html",
        document_id="doc-url-x",
        word_count=600,
        markdown="word " * 600 + "<table><td>leak</td></table>",
        skipped_reason=None,
    )
    assert q.verdict == "flagged"
    assert "markup-soup" in (q.reason or "")


def test_assess_extraction_quality_short_but_clean_is_ok():
    # A genuinely-short-but-clean body that clears the floor is NOT flagged.
    q = pg.assess_extraction_quality(
        url="https://paulgraham.com/short.html",
        document_id="doc-url-s",
        word_count=80,
        markdown="A short but clean essay. " * 20,
        skipped_reason=None,
    )
    assert q.verdict == "ok"
    assert q.reason is None


def test_assess_extraction_quality_connector_skip_is_flagged_not_read():
    q = pg.assess_extraction_quality(
        url="https://paulgraham.com/stub.html",
        document_id="doc-url-st",
        word_count=3,
        markdown="too short",
        skipped_reason="low_word_count",
    )
    assert q.verdict == "flagged"
    assert q.ingested is False
    assert "low_word_count" in (q.reason or "")


# ---------------------------------------------------------------------------
# No new package / driver passes no literal content_class (gate: -k bypass)
# ---------------------------------------------------------------------------


def test_no_acquisition_web_package():
    assert not os.path.isdir(os.path.join(_REPO, "acquisition", "web")), (
        "acquisition/web/ must not exist — reuse acquisition/urls"
    )


def test_no_content_class_bypass_with_pg_driver_present():
    """The PG driver passes NO string-literal content_class (classification
    stays inside ingest_url's classify chokepoint), so the binding audit stays
    green even though the driver lives under acquisition/urls/."""
    from substrate.corpus_audit import assert_no_content_class_bypass

    result = assert_no_content_class_bypass()
    assert result.ok, f"content_class literal bypass found: {result.offending}"


def test_driver_source_has_no_content_class_literal():
    """Belt-and-suspenders: the driver's EXECUTABLE code never passes/assigns
    ``content_class`` (classification stays inside ingest_url's chokepoint).

    The check AST-parses the file so it inspects code, not prose. A crude
    full-text substring scan false-positives on the module docstring that
    *names* ``content_class`` to explain why the driver never sets it — so the
    guard mirrors ``corpus_audit``'s ast.Call / ast.Name discipline rather than
    grepping the source. It bites on exactly one defect: a real
    ``content_class=`` keyword on a call, or a ``content_class = ...``
    assignment, anywhere in real code.
    """
    import ast

    path = os.path.join(_REPO, "acquisition", "urls", "paulgraham.py")
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)

    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "content_class":
                    offenders.append(f"call kwarg content_class @ line {node.lineno}")
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "content_class":
                    offenders.append(f"assign content_class @ line {node.lineno}")
                if isinstance(tgt, ast.Attribute) and tgt.attr == "content_class":
                    offenders.append(f"assign .content_class @ line {node.lineno}")
        if isinstance(node, ast.AnnAssign):
            tgt = node.target
            if (
                isinstance(tgt, ast.Name)
                and tgt.id == "content_class"
                and node.value is not None
            ):
                offenders.append(f"annassign content_class @ line {node.lineno}")

    assert not offenders, f"driver assigns/passes content_class in code: {offenders}"
