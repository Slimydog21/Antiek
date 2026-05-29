"""Tests for OA discovery/resolution adapters + ingest + CLI (SPR-03 M3-M5).

NO live HTTP: every adapter parser is tested against a RECORDED response
(captured from the real API shape, trimmed to the load-bearing fields), and
the HTTP path uses ``httpx.MockTransport``. The PDF is injected as fixture
bytes built via ``acquisition.books.public_domain.text_to_pdf``.

The asserted split is the invariant in action across all four sources:
  - a CC-BY item -> opt_in_licensed, servable_full_text True;
  - a bronze / CC-BY-NC / no-license item -> gated, servable_full_text False.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

import httpx
import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.books.public_domain import text_to_pdf  # noqa: E402
from acquisition.openaccess import OAThrottle  # noqa: E402
from acquisition.openaccess import doaj, openalex, pmc, unpaywall  # noqa: E402
from acquisition.openaccess.ingest import (  # noqa: E402
    build_license_basis,
    ingest_oa_item,
)
from acquisition.openaccess.licenses import resolve_oa_license  # noqa: E402
from substrate.constants import GATED_DEFAULT_CONTENT_CLASS  # noqa: E402
from tools import ingest_open_access  # noqa: E402


# A throttle that never actually sleeps — deterministic + fast in CI.
def _no_sleep_throttle() -> OAThrottle:
    return OAThrottle(min_spacing_s=0.0, sleep=lambda _s: None)


_PDF_TEXT = (
    "This is a synthetic open-access paper body used as an ingest fixture. "
    * 40
)
_PDF_BYTES = text_to_pdf(_PDF_TEXT, title="OA Test Paper")


class _StubEmbedder:
    def encode(self, text: str) -> list[float]:
        h = abs(hash(text)) % 64
        v = [0.0] * 16
        v[h % 16] = 1.0
        return v


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)


@pytest.fixture
def temp_db_and_events(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-oa-ingest-")
    db_path = os.path.join(tmpdir, "graph.duckdb")
    events_dir = os.path.join(tmpdir, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_EVENT_LOG_DIR", events_dir)
    yield {"db_path": db_path, "events_dir": events_dir, "tmpdir": tmpdir}


# ---------------------------------------------------------------------------
# Recorded responses (real API shapes, trimmed to load-bearing fields)
# ---------------------------------------------------------------------------

_OPENALEX_CC_BY = {
    "results": [
        {
            "id": "https://openalex.org/W2741809807",
            "doi": "https://doi.org/10.1371/journal.pone.0000308",
            "title": "Sharing detailed research data",
            "open_access": {"is_oa": True, "oa_status": "gold",
                            "oa_url": "https://example.org/x.pdf"},
            "best_oa_location": {
                "is_oa": True, "license": "cc-by", "version": "publishedVersion",
                "pdf_url": "https://example.org/x.pdf",
                "landing_page_url": "https://example.org/x",
            },
        }
    ]
}

# A bronze work: is_oa True, oa_status bronze, license None. The trap.
_OPENALEX_BRONZE = {
    "results": [
        {
            "id": "https://openalex.org/W999",
            "doi": "https://doi.org/10.9999/bronze",
            "title": "Bronze free-to-read paper",
            "open_access": {"is_oa": True, "oa_status": "bronze",
                            "oa_url": "https://publisher.example/b.pdf"},
            "best_oa_location": {
                "is_oa": True, "license": None, "version": "publishedVersion",
                "pdf_url": "https://publisher.example/b.pdf",
                "landing_page_url": "https://publisher.example/b",
            },
        }
    ]
}

_UNPAYWALL_CC_BY = {
    "is_oa": True, "oa_status": "gold",
    "best_oa_location": {
        "url_for_pdf": "https://journals.example/article.pdf",
        "url": "https://journals.example/article",
        "license": "cc-by", "version": "publishedVersion", "host_type": "publisher",
    },
}

_UNPAYWALL_BRONZE = {
    "is_oa": True, "oa_status": "bronze",
    "best_oa_location": {
        "url_for_pdf": "https://publisher.example/free.pdf",
        "url": "https://publisher.example/free",
        "license": None, "version": "publishedVersion", "host_type": "publisher",
    },
}

_PMC_CC_BY = {
    "resultList": {"result": [
        {
            "pmcid": "PMC1817752", "doi": "10.1371/journal.pone.0000308",
            "title": "Sharing detailed research data", "isOpenAccess": "Y",
            "license": "cc by",
            "fullTextUrlList": {"fullTextUrl": [
                {"documentStyle": "doi", "availability": "Subscription required",
                 "url": "https://doi.org/10.1371/journal.pone.0000308"},
                {"documentStyle": "pdf", "availability": "Open access",
                 "url": "https://europepmc.org/articles/PMC1817752?pdf=render"},
            ]},
        }
    ]}
}

# A PMC article whose only full-text row is subscription-required: no open PDF.
_PMC_SUBSCRIPTION_ONLY = {
    "resultList": {"result": [
        {
            "pmcid": "PMC2", "doi": "10.1/closed", "title": "Closed",
            "isOpenAccess": "N", "license": None,
            "fullTextUrlList": {"fullTextUrl": [
                {"documentStyle": "doi", "availability": "Subscription required",
                 "url": "https://doi.org/10.1/closed"},
            ]},
        }
    ]}
}

_DOAJ_CC_BY = {
    "total": 1,
    "results": [
        {"bibjson": {
            "title": "An open journal article",
            "identifier": [{"type": "doi", "id": "10.1234/openj.1"}],
            "journal": {"license": [
                {"type": "CC BY", "url": "https://creativecommons.org/licenses/by/4.0/",
                 "BY": True, "NC": False, "ND": False, "SA": False},
            ]},
            "link": [{"type": "fulltext", "url": "https://journal.example/a"}],
        }}
    ],
}

_DOAJ_CC_BY_NC = {
    "total": 1,
    "results": [
        {"bibjson": {
            "title": "A non-commercial journal article",
            "identifier": [{"type": "doi", "id": "10.1234/ncj.1"}],
            "journal": {"license": [
                {"type": "CC BY-NC", "url": "https://creativecommons.org/licenses/by-nc/4.0/"},
            ]},
            "link": [{"type": "fulltext", "url": "https://journal.example/nc"}],
        }}
    ],
}


# ---------------------------------------------------------------------------
# M3: OpenAlex discovery parsing
# ---------------------------------------------------------------------------


def test_openalex_parse_cc_by_work():
    works = openalex.parse_works_response(_OPENALEX_CC_BY)
    assert len(works) == 1
    w = works[0]
    assert w.doi == "10.1371/journal.pone.0000308"  # normalized off the URL
    assert w.is_oa is True
    assert w.best_oa_pdf_url == "https://example.org/x.pdf"
    assert resolve_oa_license(w.license_uri).redistributable is True


def test_openalex_bronze_work_resolves_gated():
    w = openalex.parse_works_response(_OPENALEX_BRONZE)[0]
    assert w.oa_status == "bronze"
    assert w.license_uri is None
    assert resolve_oa_license(w.license_uri).redistributable is False


def test_openalex_search_polite_pool_and_oa_filter():
    """The request must carry the mailto polite-pool param + the is_oa filter
    so closed works are never paged."""
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        return httpx.Response(200, json=_OPENALEX_CC_BY)

    works = openalex.search_works(
        search="x", client=_mock_client(handler), throttle=_no_sleep_throttle()
    )
    assert "mailto=" in seen["url"]
    assert "open_access.is_oa%3Atrue" in seen["url"] or "open_access.is_oa:true" in seen["url"]
    assert len(works) == 1


# ---------------------------------------------------------------------------
# M4: Unpaywall / PMC / DOAJ resolution parsing
# ---------------------------------------------------------------------------


def test_unpaywall_cc_by_is_servable():
    ft = unpaywall.parse_response(_UNPAYWALL_CC_BY, "10.1371/journal.pone.0000308")
    assert ft.pdf_url == "https://journals.example/article.pdf"
    assert ft.resolution.redistributable is True
    assert ft.resolution.content_class == "opt_in_licensed"


def test_unpaywall_bronze_is_gated():
    ft = unpaywall.parse_response(_UNPAYWALL_BRONZE, "10.9999/bronze")
    assert ft.oa_status == "bronze"
    assert ft.license_uri is None
    assert ft.resolution.redistributable is False
    assert ft.resolution.content_class == GATED_DEFAULT_CONTENT_CLASS


def test_unpaywall_404_propagates():
    def handler(req): return httpx.Response(404, json={"error": "not found"})
    with pytest.raises(httpx.HTTPStatusError):
        unpaywall.resolve_doi("10.0/missing", client=_mock_client(handler))


def test_pmc_picks_open_access_pdf_only():
    """The subscription-required DOI row must be ignored; only the Open-access
    PDF row is taken."""
    art = pmc.parse_search_response(_PMC_CC_BY)[0]
    assert art.pdf_url == "https://europepmc.org/articles/PMC1817752?pdf=render"
    assert art.resolution.redistributable is True


def test_pmc_subscription_only_has_no_pdf():
    art = pmc.parse_search_response(_PMC_SUBSCRIPTION_ONLY)[0]
    assert art.pdf_url is None
    assert art.resolution.redistributable is False  # no license -> gated


def test_doaj_journal_cc_by_is_servable():
    art = doaj.parse_search_response(_DOAJ_CC_BY)[0]
    assert art.in_doaj is True
    assert art.license_uri == "https://creativecommons.org/licenses/by/4.0/"
    assert art.resolution.redistributable is True


def test_doaj_journal_cc_by_nc_is_gated():
    """A DOAJ-confirmed OA journal can still be NC -> gated. 'In DOAJ' is not
    a redistribution grant."""
    art = doaj.parse_search_response(_DOAJ_CC_BY_NC)[0]
    assert art.in_doaj is True
    assert art.resolution.redistributable is False
    assert art.resolution.content_class == GATED_DEFAULT_CONTENT_CLASS


# The article-search shape DOAJ actually returns: ISSN present, NO license.
_DOAJ_ARTICLE_NO_LICENSE = {
    "total": 1,
    "results": [
        {"bibjson": {
            "title": "Sharing detailed research data",
            "identifier": [{"type": "doi", "id": "10.1371/journal.pone.0000308"}],
            "journal": {"issns": ["1932-6203"], "title": "PLOS ONE"},
            "link": [{"type": "fulltext", "url": "https://journals.example/a"}],
        }}
    ],
}

# The /search/journals shape: license is on the journal bibjson.
_DOAJ_JOURNAL_CC_BY = {
    "results": [
        {"bibjson": {
            "title": "PLOS ONE",
            "license": [
                {"type": "CC BY", "url": "https://creativecommons.org/licenses/by/4.0/"},
            ],
        }}
    ]
}


def test_doaj_article_carries_issn_but_no_license():
    """Measured in the spike: article search returns the ISSN, not the license."""
    art = doaj.parse_search_response(_DOAJ_ARTICLE_NO_LICENSE)[0]
    assert art.license_uri is None
    assert art.issns == ("1932-6203",)
    assert art.resolution.redistributable is False  # gated until journal resolves it


def test_doaj_journal_response_yields_license():
    assert (
        doaj.parse_journal_response(_DOAJ_JOURNAL_CC_BY)
        == "https://creativecommons.org/licenses/by/4.0/"
    )


def test_doaj_confirm_follows_up_to_journal_license():
    """When the article has no license, confirm_by_doi must follow the ISSN to
    the journal record and resolve the journal-level license to servable."""
    def handler(req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        if "search/journals" in url:
            return httpx.Response(200, json=_DOAJ_JOURNAL_CC_BY)
        return httpx.Response(200, json=_DOAJ_ARTICLE_NO_LICENSE)

    art = doaj.confirm_by_doi(
        "10.1371/journal.pone.0000308",
        client=_mock_client(handler), throttle=_no_sleep_throttle(),
    )
    assert art is not None
    assert art.license_uri == "https://creativecommons.org/licenses/by/4.0/"
    assert art.resolution.redistributable is True


def test_unpaywall_http_path_with_throttle():
    def handler(req: httpx.Request) -> httpx.Response:
        assert "email=" in str(req.url)
        return httpx.Response(200, json=_UNPAYWALL_CC_BY)

    ft = unpaywall.resolve_doi(
        "10.1371/journal.pone.0000308",
        client=_mock_client(handler), throttle=_no_sleep_throttle(),
    )
    assert ft.resolution.redistributable is True


# ---------------------------------------------------------------------------
# M4: throttle retry-with-backoff on transient errors
# ---------------------------------------------------------------------------


def test_throttle_retries_transient_then_succeeds():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            req = httpx.Request("GET", "https://x")
            raise httpx.HTTPStatusError(
                "503", request=req, response=httpx.Response(503, request=req)
            )
        return "ok"

    t = OAThrottle(min_spacing_s=0.0, backoff_base_s=0.0, sleep=lambda _s: None)
    assert t.run_with_retry(flaky) == "ok"
    assert calls["n"] == 3


def test_throttle_does_not_retry_permanent_4xx():
    def not_found():
        req = httpx.Request("GET", "https://x")
        raise httpx.HTTPStatusError(
            "404", request=req, response=httpx.Response(404, request=req)
        )

    t = OAThrottle(min_spacing_s=0.0, sleep=lambda _s: None)
    with pytest.raises(httpx.HTTPStatusError):
        t.run_with_retry(not_found)


# ---------------------------------------------------------------------------
# M5: ingest_oa_item routing (injected PDF bytes; no network)
# ---------------------------------------------------------------------------


def test_ingest_cc_by_is_servable(temp_db_and_events):
    res = resolve_oa_license("cc-by")
    out = ingest_oa_item(
        investigation_id="inv-test",
        doi="10.1/servable",
        pdf_url="https://x/a.pdf",
        resolution=res,
        license_basis=build_license_basis(res, source="Unpaywall", how="best_oa"),
        pdf_bytes=_PDF_BYTES,
        db_path=temp_db_and_events["db_path"],
        embedder=_StubEmbedder(),
    )
    assert out.content_class == "opt_in_licensed"
    assert out.servable_full_text is True


def test_ingest_bronze_is_gated(temp_db_and_events):
    res = resolve_oa_license(None)  # bronze: no declared license
    out = ingest_oa_item(
        investigation_id="inv-test",
        doi="10.1/bronze",
        pdf_url="https://x/b.pdf",
        resolution=res,
        license_basis=build_license_basis(res, source="Unpaywall", how="best_oa"),
        pdf_bytes=_PDF_BYTES,
        db_path=temp_db_and_events["db_path"],
        embedder=_StubEmbedder(),
    )
    assert out.content_class == GATED_DEFAULT_CONTENT_CLASS
    assert out.servable_full_text is False
    assert out.license_basis.startswith("Unpaywall;")


def test_ingest_persists_basis_and_class(temp_db_and_events):
    import duckdb

    # Use a full CC URI (as PMC/DOAJ emit) so the basis echoes the URI; this
    # asserts the basis carries the source + license name + URI.
    res = resolve_oa_license("https://creativecommons.org/licenses/by/4.0/")
    out = ingest_oa_item(
        investigation_id="inv-test",
        doi="10.1/persisted",
        pdf_url="https://x/c.pdf",
        resolution=res,
        license_basis=build_license_basis(
            res, source="Unpaywall best-OA-location", how="per best_oa_location.license"
        ),
        pdf_bytes=_PDF_BYTES,
        db_path=temp_db_and_events["db_path"],
        embedder=_StubEmbedder(),
    )
    con = duckdb.connect(temp_db_and_events["db_path"])
    try:
        (basis,) = con.execute(
            "SELECT license_basis FROM book_assets WHERE document_id = ?",
            [out.document_id],
        ).fetchone()
        (cc,) = con.execute(
            "SELECT content_class FROM documents WHERE document_id = ?",
            [out.document_id],
        ).fetchone()
    finally:
        con.close()
    assert "Unpaywall" in basis
    assert "creativecommons.org/licenses/by/4.0" in basis
    assert cc == "opt_in_licensed"


def test_ingest_empty_pdf_raises(temp_db_and_events):
    res = resolve_oa_license("cc-by")
    with pytest.raises(ValueError, match="empty PDF"):
        ingest_oa_item(
            investigation_id="inv-test",
            doi="10.1/empty",
            pdf_url="https://x/d.pdf",
            resolution=res,
            license_basis="b",
            pdf_bytes=b"",
            db_path=temp_db_and_events["db_path"],
            embedder=_StubEmbedder(),
        )


def test_ingest_idempotent_on_reingest(temp_db_and_events):
    res = resolve_oa_license("cc-by")
    kwargs = dict(
        investigation_id="inv-test",
        doi="10.1/dedup",
        pdf_url="https://x/e.pdf",
        resolution=res,
        license_basis="b",
        pdf_bytes=_PDF_BYTES,
        db_path=temp_db_and_events["db_path"],
        embedder=_StubEmbedder(),
    )
    a = ingest_oa_item(**kwargs)
    b = ingest_oa_item(**kwargs)
    assert a.document_id == b.document_id  # content-hash doc id is stable


# ---------------------------------------------------------------------------
# M5: CLI
# ---------------------------------------------------------------------------


def test_cli_dry_run_writes_nothing(temp_db_and_events, capsys, monkeypatch):
    # Resolve offline via the parser; the CLI must not open the substrate.
    monkeypatch.setattr(
        unpaywall, "resolve_doi",
        lambda doi, **kw: unpaywall.parse_response(_UNPAYWALL_CC_BY, doi),
    )

    rc = ingest_open_access.main(
        ["--source", "unpaywall", "--dois", "10.1/x", "--dry-run"]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert "SERVABLE" in out
    assert not os.path.exists(temp_db_and_events["db_path"])


def test_cli_real_run_splits_servable_and_gated(temp_db_and_events, monkeypatch):
    import duckdb

    # Two DOIs: one CC-BY (servable), one bronze (gated). Resolve via parser
    # directly (offline); fetch returns DISTINCT bytes so the content-hash doc
    # ids don't collide.
    responses = {
        "10.1/servable": _UNPAYWALL_CC_BY,
        "10.1/bronze": _UNPAYWALL_BRONZE,
    }
    monkeypatch.setattr(
        unpaywall, "resolve_doi",
        lambda doi, **kw: unpaywall.parse_response(responses[doi], doi),
    )
    per_url_pdf = {
        "https://journals.example/article.pdf": text_to_pdf(_PDF_TEXT + " a", title="A"),
        "https://publisher.example/free.pdf": text_to_pdf(_PDF_TEXT + " b", title="B"),
    }
    monkeypatch.setattr(
        unpaywall, "download_pdf", lambda url, **kw: per_url_pdf[url]
    )

    cli_db = os.path.join(temp_db_and_events["tmpdir"], "cli.duckdb")
    rc = ingest_open_access.main(
        ["--source", "unpaywall", "--dois", "10.1/servable,10.1/bronze",
         "--db-path", cli_db]
    )
    assert rc == 0
    con = duckdb.connect(cli_db)
    try:
        classes = sorted(
            r[0] for r in con.execute("SELECT content_class FROM documents").fetchall()
        )
    finally:
        con.close()
    assert "opt_in_licensed" in classes
    assert GATED_DEFAULT_CONTENT_CLASS in classes


def test_cli_rejects_prod_db(monkeypatch, capsys):
    from substrate.graph import default_db_path

    rc = ingest_open_access.main(
        ["--source", "unpaywall", "--dois", "10.1/x", "--db-path", default_db_path()]
    )
    assert rc == 2
    assert "prod" in capsys.readouterr().err.lower()


def test_cli_doaj_rejected_for_real_run(capsys):
    """DOAJ hosts no PDFs; a real (writing) run on it must be rejected."""
    rc = ingest_open_access.main(
        ["--source", "doaj", "--dois", "10.1/x", "--db-path", "/tmp/x.duckdb"]
    )
    assert rc == 2
    assert "doaj" in capsys.readouterr().err.lower()


def test_cli_requires_db_path_for_real_run(capsys):
    rc = ingest_open_access.main(["--source", "unpaywall", "--dois", "10.1/x"])
    assert rc == 2
    assert "db-path" in capsys.readouterr().err.lower()


def test_cli_openalex_requires_query(capsys):
    rc = ingest_open_access.main(["--source", "openalex", "--dry-run"])
    assert rc == 2
    assert "query" in capsys.readouterr().err.lower()
