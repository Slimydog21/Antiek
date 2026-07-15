"""Tests for per-title free-copy lookup (acquisition.books.lookup).

Fixtures only (recorded JSON per source), injectable stub fetcher; ZERO live
network.  The stub fetcher FAILS the test on any unexpected URL — that is the
contract.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any
from unittest.mock import patch

import pytest

from acquisition.books.internet_archive import (
    ADVANCEDSEARCH_URL as IA_SEARCH_URL,
)
from acquisition.books.internet_archive import (
    DOWNLOAD_BASE as IA_DOWNLOAD_BASE,
)
from acquisition.books.internet_archive import (
    METADATA_BASE as IA_META_BASE,
)
from acquisition.books.lookup import (
    FreeCopyFound,
    NotFreelyAvailable,
    SourceOutcome,
    ingest_found_copy,
    search_free_copy,
)
from acquisition.books.pd_connector_base import BookCandidate, FetchError
from acquisition.books.public_domain import GUTENDEX_BASE, PublicDomainWork

# ---------------------------------------------------------------------------
# Stub fetcher — FAILS on any URL not explicitly registered
# ---------------------------------------------------------------------------


class StubFetcher:
    """Records canned JSON/bytes by URL.  Same surface as ``ThrottledFetcher``
    (``get_json`` / ``get_bytes``).  A missing URL raises ``FetchError`` so
    the test FAILS on any request to an unregistered URL — the zero-live-
    network contract."""

    def __init__(
        self,
        *,
        json_by_url: dict[str, Any] | None = None,
        bytes_by_url: dict[str, bytes] | None = None,
    ):
        self._json = json_by_url or {}
        self._bytes = bytes_by_url or {}
        self.json_calls: list[str] = []
        self.json_requests: list[tuple[str, dict | None]] = []
        self.bytes_calls: list[str] = []

    def get_json(self, url: str, *, params: dict | None = None) -> dict:
        self.json_calls.append(url)
        self.json_requests.append((url, params))
        if url not in self._json:
            raise FetchError(
                f"StubFetcher: unexpected URL {url!r} — test will fail. "
                "Register the URL in json_by_url."
            )
        return self._json[url]

    def get_bytes(self, url: str, *, params: dict | None = None) -> bytes:
        self.bytes_calls.append(url)
        if url not in self._bytes:
            raise FetchError(
                f"StubFetcher: unexpected URL {url!r} — test will fail. "
                "Register the URL in bytes_by_url."
            )
        return self._bytes[url]


# ---------------------------------------------------------------------------
# Gutendex fixtures
# ---------------------------------------------------------------------------

_GUTENDEX_WALDEN_SEARCH = {
    "count": 1,
    "next": None,
    "previous": None,
    "results": [
        {
            "id": 2098,
            "title": "Walden; Or, Life in the Woods",
            "authors": [{"name": "Thoreau, Henry David"}],
            "copyright": False,
            "subjects": ["Philosophy"],
            "formats": {
                "text/plain": "https://www.gutenberg.org/files/2098/2098-0.txt",
            },
        },
    ],
}


def _make_gutendex_pdf_bytes() -> bytes:
    """Minimal PDF bytes for the Gutendex download URL."""
    return b"%PDF-1.4 fake-pdf-bytes-for-testing"


def _make_gutendex_fetcher(search_response):
    return StubFetcher(
        json_by_url={GUTENDEX_BASE: search_response},
        bytes_by_url={
            "https://www.gutenberg.org/files/2098/2098-0.txt": b"Walden text body"
        },
    )


# ---------------------------------------------------------------------------
# Internet Archive fixtures
# ---------------------------------------------------------------------------

_IA_SEARCH_WALDEN = {
    "response": {"docs": [{"identifier": "waldenpd"}]},
}
_IA_META_WALDEN = {
    "metadata": {
        "title": "Walden",
        "creator": "Henry David Thoreau",
        "possible-copyright-status": "NOT_IN_COPYRIGHT",
    },
    "files": [{"name": "waldenpd.pdf"}],
}


def _make_ia_fetcher(identifiers, metas):
    """Build a StubFetcher for IA advancedsearch + per-item metadata."""
    json_by_url = {IA_SEARCH_URL: {"response": {"docs": [{"identifier": i} for i in identifiers]}}}
    bytes_by_url = {}
    for ident in identifiers:
        json_by_url[f"{IA_META_BASE}/{ident}"] = metas[ident]
        bytes_by_url[f"{IA_DOWNLOAD_BASE}/{ident}/{ident}.pdf"] = _make_gutendex_pdf_bytes()
    return StubFetcher(json_by_url=json_by_url, bytes_by_url=bytes_by_url)


def _make_combined_fetcher(gutendex_response, ia_identifiers, ia_metas):
    """StubFetcher with both Gutendex and IA canned responses."""
    json_by_url = {GUTENDEX_BASE: gutendex_response}
    bytes_by_url = {}
    # Gutendex download
    if gutendex_response.get("results"):
        for book in gutendex_response["results"]:
            for url in book.get("formats", {}).values():
                if isinstance(url, str):
                    bytes_by_url[url] = _make_gutendex_pdf_bytes()
    # IA
    json_by_url[IA_SEARCH_URL] = {
        "response": {"docs": [{"identifier": i} for i in ia_identifiers]}
    }
    for ident in ia_identifiers:
        json_by_url[f"{IA_META_BASE}/{ident}"] = ia_metas[ident]
        bytes_by_url[f"{IA_DOWNLOAD_BASE}/{ident}/{ident}.pdf"] = _make_gutendex_pdf_bytes()
    return StubFetcher(json_by_url=json_by_url, bytes_by_url=bytes_by_url)


# ---------------------------------------------------------------------------
# Tests — found at first source
# ---------------------------------------------------------------------------


def test_found_at_first_source_gutenberg():
    """Gutenberg returns a PD match on the first source queried."""
    fetcher = _make_gutendex_fetcher(_GUTENDEX_WALDEN_SEARCH)
    result = search_free_copy("Walden", fetcher=fetcher)
    assert isinstance(result, FreeCopyFound)
    assert result.source == "gutenberg"
    assert result.candidate_ref.title == "Walden; Or, Life in the Woods"
    assert result.candidate_ref.author == "Thoreau, Henry David"
    assert "Gutenberg" in result.rights_basis
    assert result.retrieved_at  # non-empty ISO timestamp
    # Gutendex was queried.
    assert GUTENDEX_BASE in fetcher.json_calls


def test_ia_search_runs_once_and_quotes_operator_text():
    """Raw title syntax cannot widen the rights-constrained IA query."""
    fetcher = _make_ia_fetcher([], {})

    result = search_free_copy(
        'A title" OR mediatype:*',
        "An \\ Author",
        sources=("internet_archive",),
        fetcher=fetcher,
    )

    assert isinstance(result, NotFreelyAvailable)
    requests = [request for request in fetcher.json_requests if request[0] == IA_SEARCH_URL]
    assert len(requests) == 1
    params = requests[0][1]
    assert params is not None
    assert params["q"].startswith(
        '(title:"A title\\" OR mediatype:*" AND creator:"An \\\\ Author") AND '
    )


@pytest.mark.parametrize(
    ("title", "author"),
    [("   ", None), ("Walden", "Tho\nreau"), ("x" * 501, None)],
)
def test_rejects_invalid_operator_query_text(title, author):
    fetcher = _make_ia_fetcher([], {})

    with pytest.raises((TypeError, ValueError)):
        search_free_copy(
            title,
            author,
            sources=("internet_archive",),
            fetcher=fetcher,
        )

    assert fetcher.json_calls == []


# ---------------------------------------------------------------------------
# Tests — found at later source
# ---------------------------------------------------------------------------


def test_found_at_later_source_ia():
    """Gutenberg returns nothing; IA returns a PD item → FreeCopyFound from IA."""
    empty_gutendex = {"count": 0, "next": None, "previous": None, "results": []}
    ia_metas = {"republicpd": {
        "metadata": {
            "title": "The Republic",
            "creator": "Plato",
            "possible-copyright-status": "NOT_IN_COPYRIGHT",
        },
        "files": [{"name": "republicpd.pdf"}],
    }}
    fetcher = _make_combined_fetcher(empty_gutendex, ["republicpd"], ia_metas)
    result = search_free_copy("The Republic", "Plato", fetcher=fetcher)
    assert isinstance(result, FreeCopyFound)
    assert result.source == "internet_archive"
    assert result.candidate_ref.title == "The Republic"
    assert "NOT_IN_COPYRIGHT" in result.rights_basis
    # Both sources were queried.
    assert GUTENDEX_BASE in fetcher.json_calls
    assert IA_SEARCH_URL in fetcher.json_calls


# ---------------------------------------------------------------------------
# Tests — nothing found
# ---------------------------------------------------------------------------


def test_nothing_found_returns_not_freely_available():
    """Both sources return nothing → NotFreelyAvailable with per-source outcomes."""
    empty_gutendex = {"count": 0, "next": None, "previous": None, "results": []}
    fetcher = _make_combined_fetcher(empty_gutendex, [], {})
    # Empty identifiers → IA search returns empty → no candidates.
    # We need at least the search URL registered.
    result = search_free_copy("NonexistentTitle", fetcher=fetcher)
    assert isinstance(result, NotFreelyAvailable)
    assert result.title == "NonexistentTitle"
    assert result.author is None
    assert len(result.outcomes) == 2
    sources_hit = {o.source for o in result.outcomes}
    assert sources_hit == {"gutenberg", "internet_archive"}
    for o in result.outcomes:
        assert o.found is False
        assert o.query  # non-empty
        assert o.timestamp
        assert o.error is None  # no errors, just no results
    assert result.checked_at


# ---------------------------------------------------------------------------
# Tests — connector error isolation
# ---------------------------------------------------------------------------


def test_gutenberg_errors_ia_succeeds():
    """Gutendex throws; IA returns a PD item → FreeCopyFound from IA.
    Gutendex error is NOT recorded as a SourceOutcome (it threw before we
    could build one) but the sweep continues to IA."""
    # Gutendex URL not registered → FetchError on get_json.
    fetcher = StubFetcher(
        json_by_url={
            IA_SEARCH_URL: _IA_SEARCH_WALDEN,
            f"{IA_META_BASE}/waldenpd": _IA_META_WALDEN,
        },
        bytes_by_url={
            f"{IA_DOWNLOAD_BASE}/waldenpd/waldenpd.pdf": _make_gutendex_pdf_bytes(),
        },
    )
    result = search_free_copy("Walden", fetcher=fetcher)
    assert isinstance(result, FreeCopyFound)
    assert result.source == "internet_archive"


def test_ia_errors_gutenberg_succeeds():
    """IA search throws; Gutendex returns a PD item → FreeCopyFound from Gutenberg."""
    # IA search URL not registered → FetchError.
    fetcher = StubFetcher(
        json_by_url={GUTENDEX_BASE: _GUTENDEX_WALDEN_SEARCH},
        bytes_by_url={
            "https://www.gutenberg.org/files/2098/2098-0.txt": b"Walden text body",
        },
    )
    result = search_free_copy("Walden", fetcher=fetcher)
    assert isinstance(result, FreeCopyFound)
    assert result.source == "gutenberg"


def test_all_sources_error():
    """All sources error → NotFreelyAvailable with error strings in outcomes."""
    # No URLs registered → every get_json raises FetchError.
    fetcher = StubFetcher()
    result = search_free_copy("Walden", fetcher=fetcher)
    assert isinstance(result, NotFreelyAvailable)
    assert len(result.outcomes) == 2
    for o in result.outcomes:
        assert o.found is False
        assert o.error is not None  # error recorded


def test_unexpected_url_fails_the_test():
    """The stub fetcher raises FetchError on any URL not explicitly registered,
    which is the zero-live-network contract."""
    fetcher = StubFetcher()
    with pytest.raises(FetchError, match="unexpected URL"):
        fetcher.get_json("https://totally-unexpected.example.com/book")
    with pytest.raises(FetchError, match="unexpected URL"):
        fetcher.get_bytes("https://totally-unexpected.example.com/book.pdf")


# ---------------------------------------------------------------------------
# Tests — ingest handoff
# ---------------------------------------------------------------------------


def test_ingest_handoff_calls_classify_and_ingest():
    """ingest_found_copy delegates to classify_and_ingest with the BookCandidate."""
    candidate = BookCandidate(
        source="internet_archive",
        source_id="internet_archive:testpd",
        title="Test PD Book",
        author="Test Author",
        source_uri="https://archive.org/details/testpd",
        download_url="https://archive.org/download/testpd/testpd.pdf",
        download_format="pdf",
        license_uri=None,
        pd_signal="NOT_IN_COPYRIGHT",
        subjects=tuple(),
    )
    found = FreeCopyFound(
        source="internet_archive",
        candidate_ref=candidate,
        rights_basis="NOT_IN_COPYRIGHT",
        retrieved_at=_dt.datetime.now(_dt.UTC).isoformat(),
    )
    fetcher = StubFetcher(bytes_by_url={
        "https://archive.org/download/testpd/testpd.pdf": b"%PDF-1.4 fake",
    })
    with patch("acquisition.books.lookup.classify_and_ingest") as mock_ci:
        mock_ci.return_value = type("Outcome", (), {
            "ingested": True, "document_id": "doc-123", "skipped_reason": None
        })()
        ingest_found_copy(found, fetcher, db_path="/tmp/test.duckdb")
    mock_ci.assert_called_once()
    call_args = mock_ci.call_args
    assert call_args[0][0] is candidate  # first positional arg
    assert call_args[1]["db_path"] == "/tmp/test.duckdb"


# ---------------------------------------------------------------------------
# Tests — CLI exit codes
# ---------------------------------------------------------------------------


def test_cli_exit_code_0_on_found():
    """CLI exits 0 when a free copy is found."""
    from tools.book_lookup import main as cli_main

    mock_result = FreeCopyFound(
        source="gutenberg",
        candidate_ref=PublicDomainWork(
            source="project_gutenberg",
            source_id="123",
            title="T",
            author="A",
            source_uri="https://www.gutenberg.org/ebooks/123",
            download_url="https://www.gutenberg.org/files/123/123-0.txt",
            download_format="text",
            pd_basis="Gutenberg PD",
        ),
        rights_basis="PD",
        retrieved_at=_dt.datetime.now(_dt.UTC).isoformat(),
    )
    with patch("tools.book_lookup.search_free_copy", return_value=mock_result):
        assert cli_main(["The Republic"]) == 0


def test_cli_exit_code_3_on_not_found():
    """CLI exits 3 when no free copy is found."""
    from tools.book_lookup import main as cli_main

    mock_result = NotFreelyAvailable(
        title="Obscure Title",
        author=None,
        outcomes=(
            SourceOutcome("gutenberg", False, "q", _dt.datetime.now(_dt.UTC).isoformat()),
            SourceOutcome("internet_archive", False, "q", _dt.datetime.now(_dt.UTC).isoformat()),
        ),
        checked_at=_dt.datetime.now(_dt.UTC).isoformat(),
    )
    with patch("tools.book_lookup.search_free_copy", return_value=mock_result):
        assert cli_main(["Obscure Title"]) == 3


def test_cli_exit_code_2_on_error():
    """CLI exits 2 when an exception propagates."""
    from tools.book_lookup import main as cli_main

    with patch("tools.book_lookup.search_free_copy", side_effect=RuntimeError("boom")):
        assert cli_main(["Anything"]) == 2


def test_cli_json_output_found(capsys):
    """CLI --json output is valid JSON on found."""
    import json as json_mod

    from tools.book_lookup import main as cli_main

    mock_result = FreeCopyFound(
        source="gutenberg",
        candidate_ref=PublicDomainWork(
            source="project_gutenberg",
            source_id="123",
            title="T",
            author="A",
            source_uri="https://www.gutenberg.org/ebooks/123",
            download_url="https://www.gutenberg.org/files/123/123-0.txt",
            download_format="text",
            pd_basis="Gutenberg PD",
        ),
        rights_basis="PD",
        retrieved_at=_dt.datetime.now(_dt.UTC).isoformat(),
    )
    with patch("tools.book_lookup.search_free_copy", return_value=mock_result):
        cli_main(["Republic", "--json"])
    out = capsys.readouterr().out
    data = json_mod.loads(out)
    assert data["status"] == "found"
    assert data["source"] == "gutenberg"


# ---------------------------------------------------------------------------
# Tests — --ingest regression (BLOCKER 1 fixes)
# ---------------------------------------------------------------------------


def test_cli_ingest_ia_hit_passes_real_fetcher():
    """IA hit + --ingest → ingest_found_copy is called with a NON-None fetcher
    (the SourceClientFetcher instance)."""
    from tools.book_lookup import main as cli_main

    ia_candidate = BookCandidate(
        source="internet_archive",
        source_id="internet_archive:testpd",
        title="Test PD Book",
        author="Test Author",
        source_uri="https://archive.org/details/testpd",
        download_url="https://archive.org/download/testpd/testpd.pdf",
        download_format="pdf",
        license_uri=None,
        pd_signal="NOT_IN_COPYRIGHT",
        subjects=tuple(),
    )
    mock_result = FreeCopyFound(
        source="internet_archive",
        candidate_ref=ia_candidate,
        rights_basis="NOT_IN_COPYRIGHT",
        retrieved_at=_dt.datetime.now(_dt.UTC).isoformat(),
    )
    mock_outcome = type("Outcome", (), {
        "ingested": True, "document_id": "doc-456", "skipped_reason": None
    })()
    with (
        patch("tools.book_lookup.search_free_copy", return_value=mock_result),
        patch("tools.book_lookup.ingest_found_copy", return_value=mock_outcome) as mock_ingest,
    ):
        exit_code = cli_main(["Test Book", "--ingest", "--db-path", "/tmp/test.duckdb"])
    assert exit_code == 0
    mock_ingest.assert_called_once()
    # The fetcher kwarg must be a real SourceClientFetcher, not None.
    call_kwargs = mock_ingest.call_args
    fetcher_arg = call_kwargs[1].get("fetcher") or call_kwargs[0][1]
    from acquisition.books.lookup import SourceClientFetcher
    assert isinstance(fetcher_arg, SourceClientFetcher)
    assert call_kwargs[1].get("db_path") == "/tmp/test.duckdb"


def test_cli_ingest_gutenberg_hit_reports_limitation(capsys):
    """Gutenberg hit + --ingest → clean message about tools/ingest_public_domain
    and exit code 4, NOT a crash and NOT a generic error."""
    from tools.book_lookup import main as cli_main

    gutenberg_work = PublicDomainWork(
        source="project_gutenberg",
        source_id="2098",
        title="Walden; Or, Life in the Woods",
        author="Thoreau, Henry David",
        source_uri="https://www.gutenberg.org/ebooks/2098",
        download_url="https://www.gutenberg.org/files/2098/2098-0.txt",
        download_format="text",
        pd_basis="Gutenberg PD (US public domain)",
    )
    mock_result = FreeCopyFound(
        source="gutenberg",
        candidate_ref=gutenberg_work,
        rights_basis="Gutenberg PD (US public domain)",
        retrieved_at=_dt.datetime.now(_dt.UTC).isoformat(),
    )
    with patch("tools.book_lookup.search_free_copy", return_value=mock_result):
        exit_code = cli_main(["Walden", "--ingest", "--db-path", "/tmp/test.duckdb"])
    assert exit_code == 4
    out = capsys.readouterr().out
    assert "tools/ingest_public_domain" in out
    assert "2098" in out


def test_cli_ingest_gutenberg_json_reports_limitation(capsys):
    """Gutenberg hit + --ingest + --json → JSON with reason about routing."""
    import json as json_mod

    from tools.book_lookup import main as cli_main

    gutenberg_work = PublicDomainWork(
        source="project_gutenberg",
        source_id="2098",
        title="Walden; Or, Life in the Woods",
        author="Thoreau, Henry David",
        source_uri="https://www.gutenberg.org/ebooks/2098",
        download_url="https://www.gutenberg.org/files/2098/2098-0.txt",
        download_format="text",
        pd_basis="Gutenberg PD (US public domain)",
    )
    mock_result = FreeCopyFound(
        source="gutenberg",
        candidate_ref=gutenberg_work,
        rights_basis="Gutenberg PD (US public domain)",
        retrieved_at=_dt.datetime.now(_dt.UTC).isoformat(),
    )
    with patch("tools.book_lookup.search_free_copy", return_value=mock_result):
        exit_code = cli_main(["Walden", "--ingest", "--db-path", "/tmp/test.duckdb", "--json"])
    assert exit_code == 4
    out = capsys.readouterr().out
    # CLI emits two JSON objects on separate lines: "found" then "ingest".
    lines = [line for line in out.strip().splitlines() if line.strip().startswith("{")]
    second = json_mod.loads(lines[1])
    assert second["ingested"] is False
    assert "tools/ingest_public_domain" in second["reason"]
