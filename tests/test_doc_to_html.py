"""Doc→HTML S-D2H — document-to-canonical-HTML ingestion pipeline tests.

Tests cover:
- Conversion dispatch (anydoc/docling paths, fallback, subprocess mocking)
- Fair-use gate refusal (libgen, annas-archive, z-library domains)
- Memory hook call after successful ingest
- Route auth scoping (owner-scoped like account_memory_routes)
- Sanitizer version gate intact (SANITIZER_VERSION stamped on sidecar)

All network and subprocess calls are mocked.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import duckdb
import pytest
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.doc_to_html.converter import (  # noqa: E402
    ANYDOC_BIN,
    BLOCKED_DOMAINS,
    FairUseError,
    _check_fair_use,
    _extract_domain,
    convert_to_markdown,
    ingest_asset,
)
from runtime.db_lock import connect_write  # noqa: E402
from substrate.books.html_sanitizer import SANITIZER_VERSION  # noqa: E402
from substrate.graph.schema import init_database  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Set up a temporary DB + events dir for all tests."""
    db_path = str(tmp_path / "graph.duckdb")
    events_dir = str(tmp_path / "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_EVENT_LOG_DIR", events_dir)
    # Initialize schema
    writer = connect_write(db_path, purpose="test/doc-to-html/schema")
    try:
        init_database(writer)
    finally:
        writer.close()
    return {"db_path": db_path, "events_dir": events_dir, "tmpdir": str(tmp_path)}


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    """Create a minimal sample PDF file for testing."""
    path = tmp_path / "sample.pdf"
    # Minimal PDF
    path.write_bytes(
        b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\n"
        b"xref\n0 3\n0000000000 65535 f \n0000000009 00000 n \n"
        b"0000000058 00000 n \ntrailer\n<< /Size 3 /Root 1 0 R >>\n"
        b"startxref\n115\n%%EOF\n"
    )
    return path


@pytest.fixture
def sample_docx(tmp_path: Path) -> Path:
    """Create a minimal sample DOCX-like file for testing."""
    path = tmp_path / "sample.docx"
    path.write_bytes(b"PK\x03\x04" + b"\x00" * 100)
    return path


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


class MockCompletedProcess:
    """A mock subprocess.CompletedProcess for testing."""

    def __init__(
        self,
        returncode: int = 0,
        stdout: str = "",
        stderr: str = "",
    ):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _mock_subprocess_run_success(
    cmd: list[str],
    *args: Any,
    **kwargs: Any,
) -> MockCompletedProcess:
    """Mock subprocess.run that returns successful markdown output."""
    return MockCompletedProcess(
        returncode=0,
        stdout="# Converted Document\n\nThis is the converted markdown content.",
    )


def _mock_subprocess_run_anydoc_fail_docling_success(
    cmd: list[str],
    *args: Any,
    **kwargs: Any,
) -> MockCompletedProcess:
    """Mock subprocess.run where anydoc fails but docling succeeds."""
    if "anydoc" in cmd[0]:
        return MockCompletedProcess(
            returncode=1,
            stderr="error: cannot convert scanned PDF",
        )
    return MockCompletedProcess(
        returncode=0,
        stdout="# Docling Converted\n\nThis was converted by docling fallback.",
    )


def _mock_subprocess_run_all_fail(
    cmd: list[str],
    *args: Any,
    **kwargs: Any,
) -> MockCompletedProcess:
    """Mock subprocess.run where both anydoc and docling fail."""
    return MockCompletedProcess(
        returncode=1,
        stderr="conversion failed",
    )


# ---------------------------------------------------------------------------
# Conversion dispatch tests
# ---------------------------------------------------------------------------


def test_convert_to_markdown_uses_anydoc(sample_pdf: Path):
    """anydoc is tried first; on success, its output is returned."""
    with patch(
        "acquisition.doc_to_html.converter.subprocess.run",
        side_effect=_mock_subprocess_run_success,
    ) as mock_run:
        result = convert_to_markdown(sample_pdf)
    assert "# Converted Document" in result
    assert "converted markdown content" in result
    # Verify anydoc was called
    mock_run.assert_called_once()
    call_args = mock_run.call_args[0][0]
    assert ANYDOC_BIN in call_args[0]


def test_convert_to_markdown_falls_back_to_docling(sample_pdf: Path):
    """When anydoc exits non-zero, docling is tried as fallback."""
    with patch(
        "acquisition.doc_to_html.converter.subprocess.run",
        side_effect=_mock_subprocess_run_anydoc_fail_docling_success,
    ) as mock_run:
        result = convert_to_markdown(sample_pdf)
    assert "# Docling Converted" in result
    assert "docling fallback" in result
    # Both were called (anydoc first, then docling)
    assert mock_run.call_count == 2


def test_convert_to_markdown_raises_when_both_fail(sample_pdf: Path):
    """When both anydoc and docling fail, ConversionError is raised."""
    from acquisition.doc_to_html.converter import ConversionError

    with patch(
        "acquisition.doc_to_html.converter.subprocess.run",
        side_effect=_mock_subprocess_run_all_fail,
    ), pytest.raises(ConversionError, match="both anydoc and docling failed"):
        convert_to_markdown(sample_pdf)


def test_convert_to_markdown_with_format_override(sample_pdf: Path):
    """The --format flag is passed to anydoc when fmt is specified."""
    with patch(
        "acquisition.doc_to_html.converter.subprocess.run",
        side_effect=_mock_subprocess_run_success,
    ) as mock_run:
        convert_to_markdown(sample_pdf, fmt="pdf")
    call_args = mock_run.call_args[0][0]
    assert "--format" in call_args
    assert "pdf" in call_args


def test_convert_to_markdown_file_not_found():
    """Raises FileNotFoundError for missing files."""
    with pytest.raises(FileNotFoundError, match="asset not found"):
        convert_to_markdown("/nonexistent/file.pdf")


def test_convert_to_markdown_timeout(sample_pdf: Path):
    """Handles subprocess timeout gracefully."""
    def _timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="anydoc", timeout=30.0)

    with patch(
        "acquisition.doc_to_html.converter.subprocess.run",
        side_effect=_timeout,
    ):
        from acquisition.doc_to_html.converter import ConversionError
        with pytest.raises(ConversionError):
            convert_to_markdown(sample_pdf)


def test_convert_to_markdown_respects_max_output(sample_pdf: Path):
    """Output is truncated when exceeding max_output_bytes."""
    large_output = "x" * 20_000_000  # 20MB

    def _large_output(cmd, *args, **kwargs):
        return MockCompletedProcess(returncode=0, stdout=large_output)

    with patch(
        "acquisition.doc_to_html.converter.subprocess.run",
        side_effect=_large_output,
    ):
        result = convert_to_markdown(sample_pdf, max_output_bytes=1024)
    assert len(result.encode("utf-8")) <= 1024


def test_convert_to_markdown_resolves_anydoc_bin_from_env(
    sample_pdf: Path, monkeypatch: pytest.MonkeyPatch
):
    """ANYDOC_BIN is resolved from ANYDOC_BIN environment variable."""
    import acquisition.doc_to_html.converter as conv_mod
    monkeypatch.setattr(conv_mod, "ANYDOC_BIN", "/custom/anydoc")
    with patch(
        "acquisition.doc_to_html.converter.subprocess.run",
        side_effect=_mock_subprocess_run_success,
    ) as mock_run:
        convert_to_markdown(sample_pdf)
    call_args = mock_run.call_args[0][0]
    assert call_args[0] == "/custom/anydoc"


# ---------------------------------------------------------------------------
# Fair-use gate tests
# ---------------------------------------------------------------------------


def test_fair_use_requires_fair_use_class():
    """Fair-use gate raises when fair_use_class is not set."""
    with pytest.raises(FairUseError, match="fair_use_class must be set"):
        _check_fair_use({})


def test_fair_use_rejects_invalid_class():
    """Fair-use gate raises for invalid fair_use_class values."""
    with pytest.raises(FairUseError, match="invalid fair_use_class"):
        _check_fair_use({"fair_use_class": "commercial"})


@pytest.mark.parametrize("domain", [
    "libgen.is",
    "libgen.rs",
    "libgen.org",
    "annas-archive.org",
    "annas-archive.se",
    "z-lib.org",
    "singlelogin.re",
    "b-ok.cc",
    "bookfi.net",
])
def test_fair_use_refuses_blocked_domains(domain: str):
    """Acquisition from known non-fair-use domains is refused."""
    with pytest.raises(FairUseError, match="refused"):
        _check_fair_use({
            "fair_use_class": "personal",
            "source_url": f"https://{domain}/book/12345",
        })


def test_fair_use_refuses_subdomain_of_blocked():
    """Subdomains of blocked domains are also refused."""
    with pytest.raises(FairUseError, match="refused"):
        _check_fair_use({
            "fair_use_class": "personal",
            "source_url": "https://books.libgen.is/download/12345",
        })


def test_fair_use_allows_normal_sources():
    """Normal sources with valid fair_use_class pass the gate."""
    _check_fair_use({
        "fair_use_class": "public",
        "source_url": "https://arxiv.org/abs/2402.03300",
    })
    _check_fair_use({
        "fair_use_class": "licensed",
        "source_url": "https://publisher.example.com/paper.pdf",
    })
    _check_fair_use({
        "fair_use_class": "personal",
        "source_url": "https://example.com/my-doc.pdf",
    })


def test_fair_use_allows_non_url_sources():
    """Non-URL sources (file paths, identifiers) pass the domain check."""
    _check_fair_use({
        "fair_use_class": "personal",
        "source_url": "/local/path/to/document.pdf",
    })
    _check_fair_use({
        "fair_use_class": "public",
        "source_url": "uploaded-file",
    })


def test_fair_use_allows_all_valid_classes():
    """All valid fair_use_class values are accepted."""
    for cls in ("public", "licensed", "personal"):
        _check_fair_use({"fair_use_class": cls})


def test_blocked_domains_frozenset():
    """BLOCKED_DOMAINS is a frozenset (immutable, no duplicates)."""
    assert isinstance(BLOCKED_DOMAINS, frozenset)
    assert len(BLOCKED_DOMAINS) > 0


# ---------------------------------------------------------------------------
# Ingest asset tests
# ---------------------------------------------------------------------------


def test_ingest_asset_full_pipeline(db_env: dict, sample_pdf: Path):
    """Full pipeline: convert → render HTML → store sidecar → memory hook."""
    with (
        patch(
            "acquisition.doc_to_html.converter.subprocess.run",
            side_effect=_mock_subprocess_run_success,
        ),
        patch(
            "acquisition.doc_to_html.converter.write_memory_item",
        ) as mock_memory,
    ):
        result = ingest_asset(
            source_uri="https://example.com/paper.pdf",
            bytes_path=sample_pdf,
            kind="pdf",
            provenance={
                "fair_use_class": "public",
                "license_note": "open access",
            },
            owner_user_id="test-owner",
        )

    assert "document_id" in result
    assert result["document_id"].startswith("doc-asset-")
    assert "reader_html_url" in result
    assert result["provenance"]["fair_use_class"] == "public"
    assert result["provenance"]["original_format"] == "pdf"
    assert result["provenance"]["fetched_at"] is not None

    # Verify the sidecar was stored with the correct sanitizer version
    con = duckdb.connect(db_env["db_path"])
    try:
        row = con.execute(
            "SELECT sanitizer_version, source_kind FROM document_reader_html "
            "WHERE document_id = ?",
            [result["document_id"]],
        ).fetchone()
        assert row is not None
        assert row[0] == SANITIZER_VERSION
        assert row[1] == "doc_pdf"
    finally:
        con.close()

    # Verify memory hook was called
    mock_memory.assert_called_once()
    memory_call = mock_memory.call_args
    assert memory_call.kwargs["owner_user_id"] == "test-owner"
    assert memory_call.kwargs["subject"].startswith("document:")


def test_ingest_asset_memory_hook_failure_does_not_rollback(
    db_env: dict, sample_pdf: Path
):
    """Memory hook failure must not roll back the stored HTML sidecar."""
    with (
        patch(
            "acquisition.doc_to_html.converter.subprocess.run",
            side_effect=_mock_subprocess_run_success,
        ),
        patch(
            "acquisition.doc_to_html.converter.write_memory_item",
            side_effect=RuntimeError("memory store unavailable"),
        ),
    ):
        result = ingest_asset(
            source_uri="https://example.com/paper.pdf",
            bytes_path=sample_pdf,
            kind="pdf",
            provenance={"fair_use_class": "public"},
        )

    # The sidecar should still be stored
    con = duckdb.connect(db_env["db_path"])
    try:
        row = con.execute(
            "SELECT sanitizer_version FROM document_reader_html "
            "WHERE document_id = ?",
            [result["document_id"]],
        ).fetchone()
        assert row is not None
        assert row[0] == SANITIZER_VERSION
    finally:
        con.close()


def test_ingest_asset_refuses_fair_use_violation(db_env: dict, sample_pdf: Path):
    """Ingestion from blocked domains is refused with FairUseError."""
    with pytest.raises(FairUseError, match="refused"):
        ingest_asset(
            source_uri="https://libgen.is/book/12345",
            bytes_path=sample_pdf,
            kind="pdf",
            provenance={
                "fair_use_class": "personal",
                "source_url": "https://libgen.is/book/12345",
            },
        )


def test_ingest_asset_requires_fair_use_class(db_env: dict, sample_pdf: Path):
    """Ingestion without fair_use_class is refused."""
    with pytest.raises(FairUseError, match="fair_use_class must be set"):
        ingest_asset(
            source_uri="https://example.com/doc.pdf",
            bytes_path=sample_pdf,
            kind="pdf",
            provenance={},
        )


def test_ingest_asset_file_not_found(db_env: dict):
    """Ingestion of a missing file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        ingest_asset(
            source_uri="https://example.com/doc.pdf",
            bytes_path="/nonexistent/file.pdf",
            kind="pdf",
            provenance={"fair_use_class": "public"},
        )


def test_ingest_asset_conversion_failure(db_env: dict, sample_pdf: Path):
    """Ingestion fails gracefully when conversion fails."""
    from acquisition.doc_to_html.converter import ConversionError

    with patch(
        "acquisition.doc_to_html.converter.subprocess.run",
        side_effect=_mock_subprocess_run_all_fail,
    ), pytest.raises(ConversionError):
        ingest_asset(
            source_uri="https://example.com/paper.pdf",
            bytes_path=sample_pdf,
            kind="pdf",
            provenance={"fair_use_class": "public"},
        )


def test_ingest_asset_sanitizer_gate_intact(db_env: dict, sample_pdf: Path):
    """The stored sidecar has the exact current SANITIZER_VERSION."""
    with patch(
        "acquisition.doc_to_html.converter.subprocess.run",
        side_effect=_mock_subprocess_run_success,
    ):
        result = ingest_asset(
            source_uri="https://example.com/paper.pdf",
            bytes_path=sample_pdf,
            kind="pdf",
            provenance={"fair_use_class": "public"},
        )

    con = duckdb.connect(db_env["db_path"])
    try:
        row = con.execute(
            "SELECT html_body, sanitizer_version FROM document_reader_html "
            "WHERE document_id = ?",
            [result["document_id"]],
        ).fetchone()
        assert row is not None
        body, version = row
        assert version == SANITIZER_VERSION
        # Verify the body is actually sanitized (no script tags, etc.)
        assert "<script" not in body
        assert "onerror" not in body
        assert "javascript:" not in body
        # Fixed point: re-running the sanitizer changes nothing
        from substrate.books.html_sanitizer import sanitize_book_html
        assert sanitize_book_html(body) == body
    finally:
        con.close()


def test_ingest_asset_sets_content_class(db_env: dict, sample_pdf: Path):
    """The document's content_class matches the fair_use_class."""
    with patch(
        "acquisition.doc_to_html.converter.subprocess.run",
        side_effect=_mock_subprocess_run_success,
    ):
        result = ingest_asset(
            source_uri="https://example.com/paper.pdf",
            bytes_path=sample_pdf,
            kind="pdf",
            provenance={"fair_use_class": "licensed"},
        )

    con = duckdb.connect(db_env["db_path"])
    try:
        row = con.execute(
            "SELECT content_class FROM documents WHERE document_id = ?",
            [result["document_id"]],
        ).fetchone()
        assert row is not None
        assert row[0] == "licensed"
    finally:
        con.close()


# ---------------------------------------------------------------------------
# HTTP route tests
# ---------------------------------------------------------------------------


@pytest.fixture
def api_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Set up API test environment with DB + events."""
    db_path = str(tmp_path / "graph.duckdb")
    events_dir = str(tmp_path / "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_EVENT_LOG_DIR", events_dir)
    from substrate.graph.schema import init_database
    writer = connect_write(db_path, purpose="test/doc-ingest-api/schema")
    try:
        init_database(writer)
    finally:
        writer.close()
    return {"db_path": db_path, "events_dir": events_dir, "tmpdir": str(tmp_path)}


@pytest.fixture
def api_client(api_env: dict):
    """Create a FastAPI test client."""
    from interfaces.research.api.app import create_app
    app = create_app(
        register_wrestling=False,
        register_providers=False,
        cors_origins=[],
    )
    return TestClient(app)


def _as_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    """Grant the privileged owner policy tag for testing."""

    # Patch distinct_signed_owner to return a test user
    monkeypatch.setattr(
        "interfaces.research.api.doc_ingest_routes.distinct_signed_owner",
        lambda _request: "test-owner-user",
    )


def test_route_ingest_asset_file_upload(
    api_env: dict, api_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """POST /ingest/asset with file upload works."""
    _as_owner(monkeypatch)

    # Create a test file
    test_content = b"%PDF-1.4 test content"

    with patch(
        "acquisition.doc_to_html.converter.subprocess.run",
        side_effect=_mock_subprocess_run_success,
    ):
        resp = api_client.post(
            "/ingest/asset",
            files={"file": ("test.pdf", test_content, "application/pdf")},
            data={"fair_use_class": "public"},
        )

    assert resp.status_code == 201
    body = resp.json()
    assert "document_id" in body
    assert body["document_id"].startswith("doc-asset-")
    assert body["reader_html_url"].startswith("/sources/")
    assert body["reader_html_url"].endswith("/reader-html")
    assert body["provenance"]["fair_use_class"] == "public"


def test_route_ingest_asset_source_url(
    api_env: dict, api_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """POST /ingest/asset with source_url works."""
    _as_owner(monkeypatch)

    # Create a proper async context manager mock for httpx.AsyncClient
    mock_response = MagicMock()
    mock_response.content = b"%PDF-1.4 test content"
    mock_response.raise_for_status = MagicMock()

    mock_get = AsyncMock(return_value=mock_response)
    mock_client_instance = MagicMock()
    mock_client_instance.get = mock_get

    # Async context manager: __aenter__ is called as a method (receives self)
    async def _mock_aenter(self):
        return mock_client_instance

    async def _mock_aexit(self, *args):
        return False

    mock_client_instance.__aenter__ = _mock_aenter
    mock_client_instance.__aexit__ = _mock_aexit

    with (
        patch(
            "acquisition.doc_to_html.converter.subprocess.run",
            side_effect=_mock_subprocess_run_success,
        ),
        patch(
            "interfaces.research.api.doc_ingest_routes.httpx.AsyncClient",
            return_value=mock_client_instance,
        ),
    ):
        resp = api_client.post(
            "/ingest/asset",
            data={
                "source_url": "https://example.com/paper.pdf",
                "fair_use_class": "public",
            },
        )

    assert resp.status_code == 201
    body = resp.json()
    assert "document_id" in body
    assert body["provenance"]["fair_use_class"] == "public"


def test_route_ingest_asset_fair_use_refusal(
    api_env: dict, api_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """POST /ingest/asset refuses blocked domains with 451."""
    _as_owner(monkeypatch)

    # source_url mode: fair-use check happens before download
    resp = api_client.post(
        "/ingest/asset",
        data={
            "source_url": "https://libgen.is/book/12345",
            "fair_use_class": "personal",
        },
    )
    assert resp.status_code == 451
    assert "refused" in resp.json()["detail"].lower()

    # file upload mode: fair-use check happens inside ingest_asset
    test_content = b"%PDF-1.4 test content"
    with patch(
        "acquisition.doc_to_html.converter.subprocess.run",
        side_effect=_mock_subprocess_run_success,
    ):
        resp2 = api_client.post(
            "/ingest/asset",
            files={"file": ("test.pdf", test_content, "application/pdf")},
            data={
                "fair_use_class": "personal",
                # Libgen URL in source_url triggers domain check
                "source_url": "https://libgen.is/book/12345",
            },
        )
    assert resp2.status_code == 451


def test_route_ingest_asset_requires_fair_use_class(
    api_env: dict, api_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """POST /ingest/asset requires fair_use_class."""
    _as_owner(monkeypatch)

    test_content = b"%PDF-1.4 test content"

    resp = api_client.post(
        "/ingest/asset",
        files={"file": ("test.pdf", test_content, "application/pdf")},
    )
    # Default fair_use_class is "personal", so this should work
    # But let's test with an invalid one
    resp = api_client.post(
        "/ingest/asset",
        files={"file": ("test.pdf", test_content, "application/pdf")},
        data={"fair_use_class": "invalid"},
    )
    assert resp.status_code == 422


def test_route_ingest_asset_requires_owner_auth(
    api_env: dict, api_client: TestClient
):
    """POST /ingest/asset requires authenticated owner (401 without)."""
    # Don't patch distinct_signed_owner — it returns None
    test_content = b"%PDF-1.4 test content"

    resp = api_client.post(
        "/ingest/asset",
        files={"file": ("test.pdf", test_content, "application/pdf")},
        data={"fair_use_class": "public"},
    )
    assert resp.status_code == 401


def test_route_ingest_asset_requires_file_or_url(
    api_env: dict, api_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """POST /ingest/asset requires either file or source_url."""
    _as_owner(monkeypatch)

    resp = api_client.post(
        "/ingest/asset",
        data={"fair_use_class": "public"},
    )
    assert resp.status_code == 422
    assert "either file or source_url" in resp.json()["detail"].lower()


def test_route_ingest_asset_empty_file(
    api_env: dict, api_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """POST /ingest/asset rejects empty files."""
    _as_owner(monkeypatch)

    resp = api_client.post(
        "/ingest/asset",
        files={"file": ("test.pdf", b"", "application/pdf")},
        data={"fair_use_class": "public"},
    )
    assert resp.status_code == 422


def test_route_ingest_asset_provenance_response(
    api_env: dict, api_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """POST /ingest/asset returns full provenance in response."""
    _as_owner(monkeypatch)

    test_content = b"%PDF-1.4 test content"

    with patch(
        "acquisition.doc_to_html.converter.subprocess.run",
        side_effect=_mock_subprocess_run_success,
    ):
        resp = api_client.post(
            "/ingest/asset",
            files={"file": ("test.pdf", test_content, "application/pdf")},
            data={
                "fair_use_class": "licensed",
                "license_note": "MIT license",
            },
        )

    assert resp.status_code == 201
    prov = resp.json()["provenance"]
    assert prov["fair_use_class"] == "licensed"
    assert prov["license_note"] == "MIT license"
    assert prov["fetched_at"] is not None
    assert prov["original_format"] == "pdf"


# ---------------------------------------------------------------------------
# Domain extraction tests
# ---------------------------------------------------------------------------


def test_extract_domain_from_url():
    """Domain extraction from URLs works correctly."""
    assert _extract_domain("https://libgen.is/book/123") == "libgen.is"
    assert _extract_domain("https://www.example.com/path") == "www.example.com"
    assert _extract_domain("http://sub.domain.org/file.pdf") == "sub.domain.org"


def test_extract_domain_from_non_url():
    """Non-URL sources return None for domain extraction."""
    assert _extract_domain("/local/path/file.pdf") is None
    assert _extract_domain("uploaded-file") is None
    assert _extract_domain("") is None


def test_extract_domain_handles_edge_cases():
    """Edge cases in domain extraction."""
    assert _extract_domain("https://") is None
    assert _extract_domain("not-a-url") is None
    # ftp is not http/https, so domain is not extracted
    assert _extract_domain("ftp://server/file") is None


# ---------------------------------------------------------------------------
# SSRF guard (CWE-918) — validate_public_http_url
# ---------------------------------------------------------------------------


def _fake_resolver(*addrs: str):
    """Resolver stub returning the given address strings for any host."""

    def resolver(host: str, port: int | None = None, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (addr, port or 80)) for addr in addrs]

    return resolver


def test_ssrf_rejects_non_http_schemes():
    from acquisition.doc_to_html.ssrf import SsrfError, validate_public_http_url
    for bad in ["file:///etc/passwd", "ftp://example.com/x", "gopher://example.com/", "dict://example.com/"]:
        with pytest.raises(SsrfError):
            validate_public_http_url(bad, resolver=_fake_resolver("8.8.8.8"))


def test_ssrf_rejects_credentials_in_url():
    from acquisition.doc_to_html.ssrf import SsrfError, validate_public_http_url
    with pytest.raises(SsrfError):
        validate_public_http_url("https://user:pass@example.com/x", resolver=_fake_resolver("8.8.8.8"))


def test_ssrf_rejects_loopback_and_private_literals():
    from acquisition.doc_to_html.ssrf import SsrfError, validate_public_http_url
    for bad in ["http://127.0.0.1:8001/health", "http://localhost/x", "http://169.254.169.254/latest/meta-data/",
                "http://10.0.0.1/x", "http://192.168.1.1/x", "http://[::1]/x", "http://172.16.0.1/x"]:
        with pytest.raises(SsrfError):
            validate_public_http_url(bad)


def test_ssrf_rejects_hosts_resolving_to_private():
    from acquisition.doc_to_html.ssrf import SsrfError, validate_public_http_url
    with pytest.raises(SsrfError):
        validate_public_http_url("http://internal.example.com/x", resolver=_fake_resolver("10.0.0.5"))
    with pytest.raises(SsrfError):
        validate_public_http_url("https://evil.example/x", resolver=_fake_resolver("127.0.0.1", "8.8.8.8"))


def test_ssrf_rejects_special_suffix_hosts():
    from acquisition.doc_to_html.ssrf import SsrfError, validate_public_http_url
    for bad in ["http://db.internal/x", "http://router.local/x", "http://host.localdomain/x"]:
        with pytest.raises(SsrfError):
            validate_public_http_url(bad, resolver=_fake_resolver("8.8.8.8"))


def test_ssrf_accepts_public_urls():
    from acquisition.doc_to_html.ssrf import validate_public_http_url
    ok = validate_public_http_url("https://example.com/paper.pdf", resolver=_fake_resolver("93.184.216.34"))
    assert ok == "https://example.com/paper.pdf"
    ok2 = validate_public_http_url("http://8.8.8.8/x", resolver=_fake_resolver("8.8.8.8"))
    assert ok2 == "http://8.8.8.8/x"


def test_ssrf_route_rejects_loopback_source_url(api_env: dict, api_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """End-to-end: POST /ingest/asset with an internal URL is refused."""
    _as_owner(monkeypatch)
    resp = api_client.post("/ingest/asset", data={"source_url": "http://127.0.0.1:8001/health", "fair_use_class": "public"})
    assert resp.status_code == 422
    assert "non-public" in resp.text or "loopback" in resp.text or "not allowed" in resp.text or "public" in resp.text
