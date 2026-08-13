"""Doc→HTML S4 — POST /sources/upload endpoint tests.

Acceptance for the lane (brief, no live network):

- uploading a small PDF fixture → stored + served as sanitized
  ``content_format="html"``;
- uploading ``.epub`` / a PK-zip body → ``409`` pointing at the authorized
  book-acquisition ceremony (magic bytes win over extension; an EPUB container
  renamed to a ``.docx`` name still 409s — container truth beats extension);
- Office/ODF/RTF/CSV uploads route through ``extract_text`` with the anydoc
  binding MOCKED (operator gate G1 — no real wheel install): a ``.docx``
  converts to canned GFM → stored + served as sanitized ``content_format=
  "html"``; a binding ImportError (G1 state) → typed 422 with the install
  hint; a conversion whose markdown carries a ``<script>`` seed → the script
  never reaches the stored body (red-proof);
- an uploaded HTML body carrying a ``<script>`` / ``onerror=`` payload → the
  STORED sidecar body is sanitized (red-proof, same posture as
  ``test_book_html_sanitizer.py``);
- a missing or invalid ``acquisition_attestation`` → 4xx.

Plus magic-over-extension sniffing is pinned independently, and the §5.2 hazard
holds (the books full-text endpoint keeps serving an uploaded doc as
``content_format="text"`` — the sidecar is the sole HTML trust carrier).
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType

import pytest
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.api import books as books_api  # noqa: E402
from interfaces.research.api import upload_routes  # noqa: E402
from interfaces.research.api.app import create_app  # noqa: E402
from interfaces.research.api.upload_routes import sniff_kind  # noqa: E402
from runtime.db_lock import connect_write  # noqa: E402
from substrate.auth import mint_session_cookie  # noqa: E402
from substrate.books.html_sanitizer import SANITIZER_VERSION  # noqa: E402
from substrate.research_bridge import extractors  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures — same substrate/app harness as test_reader_html_api.py
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_substrate(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-sources-upload-")
    db_path = os.path.join(tmpdir, "graph.duckdb")
    events_dir = os.path.join(tmpdir, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_EVENT_LOG_DIR", events_dir)
    from substrate.graph.schema import init_database

    writer = connect_write(db_path, purpose="test/sources-upload/schema")
    try:
        init_database(writer)
    finally:
        writer.close()
    yield {"db_path": db_path, "events_dir": events_dir, "tmpdir": tmpdir}


@pytest.fixture
def client(temp_substrate):
    app = create_app(
        register_wrestling=False,
        register_providers=False,
        cors_origins=[],
    )
    return TestClient(app)


def _as_owner(monkeypatch) -> None:
    """Grant the privileged owner policy tag (same pattern as
    test_reader_html_api: the owner path releases personal_reading bodies)."""
    monkeypatch.setattr(
        books_api,
        "_owner_read_policy_tag",
        lambda _request: books_api._OWNER_READ_POLICY_TAG,
    )


def _sidecar_body(db_path: str, document_id: str) -> str | None:
    """Read the STORED sidecar html_body directly — the red-proof path that
    bypasses serve entirely to prove storage itself is sanitized."""
    import duckdb

    con = duckdb.connect(db_path)
    try:
        row = con.execute(
            "SELECT html_body, sanitizer_version FROM document_reader_html "
            "WHERE document_id = ?",
            [document_id],
        ).fetchone()
    finally:
        con.close()
    if row is None:
        return None
    assert row[1] == SANITIZER_VERSION  # version-provenance stamped on write
    return str(row[0])


def _make_pdf_bytes() -> bytes:
    """A small PDF with an extractable text layer (reportlab drawString →
    pypdf can read it back)."""
    pytest.importorskip("reportlab")
    from reportlab.pdfgen.canvas import Canvas

    buf = io.BytesIO()
    c = Canvas(buf)
    c.drawString(100, 750, "Antiek upload acceptance paragraph one.")
    c.drawString(100, 730, "A second line of cleanly extractable text.")
    c.showPage()
    c.save()
    return buf.getvalue()


# ---------------------------------------------------------------------------
# anydoc binding fixtures (MOCKED — operator gate G1, no real wheel install)
# Same pattern as tests/test_universal_ingest.py: a fake module is injected
# into sys.modules["anydoc"] so extract_text's importlib lookup resolves it.
# ---------------------------------------------------------------------------


def _make_docx_bytes() -> bytes:
    """A minimal OOXML .docx container (real PK-zip magic bytes, empty doc)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
        zf.writestr("_rels/.rels", '<?xml version="1.0"?><Relationships/>')
        zf.writestr("word/document.xml", '<?xml version="1.0"?><w:document/>')
    return buf.getvalue()


def _make_epub_bytes() -> bytes:
    """A minimal EPUB container: a zip whose entries include the EPUB-required
    ``META-INF/container.xml`` (the container-truth signal)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?><container version="1.0"/>',
        )
        zf.writestr("OEBPS/content.opf", '<?xml version="1.0"?><package/>')
    return buf.getvalue()


_ANYDOC_GFM = """# Quarterly Report

A first paragraph that survives conversion.

## Findings

A second block with clean markdown structure.
"""


class _FakeAnydoc(ModuleType):
    """Drop-in replacement for the anydoc binding module."""

    def __init__(self, markdown: str = _ANYDOC_GFM, *, error: Exception | None = None):
        super().__init__("anydoc")
        self.markdown = markdown
        self.error = error
        self.calls: list[tuple[bytes | bytearray, str | None]] = []

    def to_markdown_bytes(
        self,
        data: bytes | bytearray,
        format: str | None = None,
    ) -> str:
        self.calls.append((data, format))
        if self.error is not None:
            raise self.error
        return self.markdown


def _install_fake_anydoc(monkeypatch, fake: _FakeAnydoc | None = None) -> _FakeAnydoc:
    binding = fake or _FakeAnydoc()
    monkeypatch.setitem(sys.modules, "anydoc", binding)
    def convert(data: bytes, filename: str | None) -> str:
        result = extractors.extract_text(data, filename=filename)
        if not result.ok or result.kind != "markdown":
            from fastapi import HTTPException
            raise HTTPException(422, {"code": "upload_conversion_failed"})
        return result.text
    monkeypatch.setattr(upload_routes, "_extract_office_bounded", convert)
    return binding


def _missing_anydoc_import(name: str):
    """Simulate the G1 state: the firecrawl-anydoc wheel is not installed."""
    assert name == "anydoc"
    raise ImportError(name)


def _install_child_anydoc(tmp_path: Path, monkeypatch, body: str) -> None:
    module_dir = tmp_path / "child-modules"
    module_dir.mkdir()
    (module_dir / "anydoc.py").write_text(body, encoding="utf-8")
    existing = os.environ.get("PYTHONPATH", "")
    monkeypatch.setenv(
        "PYTHONPATH", os.pathsep.join(filter(None, (str(module_dir), _REPO, existing)))
    )


# ---------------------------------------------------------------------------
# Magic-byte sniffing — pinned independently of the HTTP path
# ---------------------------------------------------------------------------


def test_sniff_magic_bytes_override_extension():
    # %PDF- magic wins even with a .txt name.
    assert sniff_kind(b"%PDF-1.4\nstuff", "report.txt") == "pdf"
    # PK-zip magic wins even with a .pdf name → epub ceremony.
    assert sniff_kind(b"PK\x03\x04" + b"\x00" * 40, "weird.pdf") == "epub"
    # Leading '<' → html even with no extension.
    assert sniff_kind(b"<html><body>hi", None) == "html"


def test_sniff_extension_fallback():
    assert sniff_kind(b"# Title\n\nbody", "note.md") == "md"
    assert sniff_kind(b"plain text line", "note.txt") == "txt"
    assert sniff_kind(b"plain text line", "note.markdown") == "md"
    assert sniff_kind(b"plain text line", "note.text") == "txt"


def test_sniff_unknown_is_none():
    assert sniff_kind(b"\x00\x01\x02 binary junk", "blob.bin") is None
    assert sniff_kind(b"no magic and no ext", None) is None


def test_sniff_office_extensions_by_extension():
    """Office/ODF/RTF/CSV kinds resolve by extension (no zip magic needed —
    the anydoc binding gets non-container formats like RTF/CSV too)."""
    assert sniff_kind(b"plain csv row", "data.csv") == "csv"
    assert sniff_kind(b"{\\rtf1\\ansi", "book.rtf") == "rtf"
    assert sniff_kind(b"some bytes", "deck.pptx") == "pptx"
    assert sniff_kind(b"some bytes", "notes.odt") == "odt"
    assert sniff_kind(b"some bytes", "macro.docm") == "docm"


def test_sniff_pk_zip_docx_container_is_office_not_epub():
    """A genuine Office zip is NOT the EPUB ceremony — its extension kind wins
    (Office/ODF containers start with the same PK-zip magic as EPUBs)."""
    assert sniff_kind(_make_docx_bytes(), "report.docx") == "docx"


def test_sniff_epub_container_wins_over_docx_extension():
    """Container truth beats extension: an EPUB renamed to .docx still sniffs
    as epub → the 409 ceremony, never the anydoc lane."""
    assert sniff_kind(_make_epub_bytes(), "sneaky.docx") == "epub"


def test_sniff_pk_zip_non_office_extension_still_epub():
    """A PK-zip body with a NON-office extension (or none) still 409s."""
    assert sniff_kind(b"PK\x03\x04" + b"\x00" * 40, "archive.zip") == "epub"
    assert sniff_kind(b"PK\x03\x04" + b"\x00" * 40, None) == "epub"


def test_sniff_corrupt_arbitrary_zip_renamed_docx_is_not_office():
    assert sniff_kind(b"PK\x03\x04" + b"\x00" * 40, "not-office.docx") is None


def test_sniff_high_expansion_docx_uses_central_directory_only(monkeypatch):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", b"x" * 2_000_000)
        zf.writestr("word/document.xml", b"x" * 2_000_000)
    monkeypatch.setattr(zipfile.ZipFile, "open", lambda *a, **k: pytest.fail("decompressed"))
    monkeypatch.setattr(zipfile.ZipFile, "read", lambda *a, **k: pytest.fail("decompressed"))
    assert sniff_kind(buf.getvalue(), "bomb.docx") is None


# ---------------------------------------------------------------------------
# Acceptance: PDF → stored + served as sanitized html
# ---------------------------------------------------------------------------


def test_upload_pdf_stored_and_served_as_html(temp_substrate, client, monkeypatch):
    pdf_bytes = _make_pdf_bytes()

    resp = client.post(
        "/sources/upload",
        files={"file": ("upload.pdf", pdf_bytes, "application/pdf")},
        data={"acquisition_attestation": "personal_reading"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["detected_kind"] == "pdf"
    assert body["reader_html_available"] is True
    assert body["chunk_count"] == 0
    document_id = body["document_id"]
    assert document_id.startswith("doc-upload-")

    # The STORED sidecar carries the current sanitizer version.
    stored = _sidecar_body(temp_substrate["db_path"], document_id)
    assert stored is not None
    assert "Antiek upload acceptance" in stored

    # Served as html to the owner (personal_reading is owner-only).
    _as_owner(monkeypatch)
    served = client.get(f"/sources/{document_id}/reader-html")
    assert served.status_code == 200
    sbody = served.json()
    assert sbody["content_format"] == "html"
    assert sbody["available"] is True
    assert sbody["reason"] == "ok"
    assert sbody["source_kind"] == "upload_pdf"
    assert "Antiek upload acceptance" in sbody["body"]


def test_upload_pdf_idempotent_on_reupload(temp_substrate, client):
    """Re-uploading the same bytes dedups on the doc id (on_conflict=ignore +
    sidecar upsert) — no duplicate, no error."""
    pdf_bytes = _make_pdf_bytes()
    r1 = client.post(
        "/sources/upload",
        files={"file": ("upload.pdf", pdf_bytes, "application/pdf")},
        data={"acquisition_attestation": "personal_reading"},
    )
    r2 = client.post(
        "/sources/upload",
        files={"file": ("upload.pdf", pdf_bytes, "application/pdf")},
        data={"acquisition_attestation": "personal_reading"},
    )
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json()["document_id"] == r2.json()["document_id"]


# ---------------------------------------------------------------------------
# Acceptance: EPUB / PK-zip → 409 (do not fork the book-acquisition lane)
# ---------------------------------------------------------------------------


def test_upload_epub_extension_returns_409(temp_substrate, client):
    resp = client.post(
        "/sources/upload",
        files={"file": ("book.epub", b"PK\x03\x04" + b"\x00" * 40,
                        "application/epub+zip")},
        data={"acquisition_attestation": "personal_reading"},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "EPUB goes through the authorized book-acquisition ceremony"


def test_upload_pk_zip_magic_returns_409(temp_substrate, client):
    """A PK-zip body with a NON-epub extension still 409s — magic bytes win."""
    resp = client.post(
        "/sources/upload",
        files={"file": ("archive.zip", b"PK\x03\x04" + b"\x00" * 40,
                        "application/zip")},
        data={"acquisition_attestation": "user_owned"},
    )
    assert resp.status_code == 409
    assert "book-acquisition ceremony" in resp.json()["detail"]


def test_upload_epub_container_renamed_docx_returns_409(temp_substrate, client):
    """Container truth beats extension: an EPUB (META-INF/container.xml)
    uploaded under a .docx name still hits the 409 ceremony — it never reaches
    the anydoc lane (the "EPUB/PK-zip stays 409" guardrail holds)."""
    resp = client.post(
        "/sources/upload",
        files={"file": ("sneaky.docx", _make_epub_bytes(), "application/octet-stream")},
        data={"acquisition_attestation": "personal_reading"},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "EPUB goes through the authorized book-acquisition ceremony"


# ---------------------------------------------------------------------------
# Acceptance: Office/ODF/RTF/CSV → anydoc (MOCKED) → sanitized html
# ---------------------------------------------------------------------------


def test_upload_docx_stored_and_served_as_sanitized_html(
    temp_substrate, client, monkeypatch
):
    """The anydoc binding (MOCKED) converts the .docx to GFM; the upload stores
    the markdown→safe-HTML body through the same trusted sidecar path as every
    other format (version-provenance stamped) and serves it as
    content_format="html"."""
    _install_fake_anydoc(monkeypatch)
    resp = client.post(
        "/sources/upload",
        files={"file": ("report.docx", _make_docx_bytes(),
                        "application/vnd.openxmlformats-officedocument."
                        "wordprocessingml.document")},
        data={"acquisition_attestation": "personal_reading"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["detected_kind"] == "docx"
    assert body["reader_html_available"] is True
    assert body["chunk_count"] == 0
    document_id = body["document_id"]
    assert document_id.startswith("doc-upload-")

    # Conversion runs in an isolated process so a wedged native converter can
    # be killed; the successful markdown below proves the binding was used.

    # The STORED sidecar is the converted GFM rendered to safe HTML, stamped
    # with the current sanitizer version.
    stored = _sidecar_body(temp_substrate["db_path"], document_id)
    assert stored is not None
    assert "<h1>Quarterly Report</h1>" in stored
    assert "<h2>Findings</h2>" in stored
    assert "A first paragraph that survives conversion." in stored

    # Served as html to the owner (personal_reading is owner-only).
    _as_owner(monkeypatch)
    served = client.get(f"/sources/{document_id}/reader-html")
    assert served.status_code == 200
    sbody = served.json()
    assert sbody["content_format"] == "html"
    assert sbody["available"] is True
    assert sbody["reason"] == "ok"
    assert sbody["source_kind"] == "upload_office"
    assert "<h1>Quarterly Report</h1>" in sbody["body"]


def test_upload_docx_without_anydoc_returns_stable_422(
    temp_substrate, client, monkeypatch
):
    """G1 state: a missing anydoc binding returns a stable public code — no
    dependency details, crash, or poison row."""
    monkeypatch.setattr(extractors, "import_module", _missing_anydoc_import)
    resp = client.post(
        "/sources/upload",
        files={"file": ("report.docx", _make_docx_bytes(),
                        "application/octet-stream")},
        data={"acquisition_attestation": "personal_reading"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == {"code": "upload_conversion_failed"}


def test_upload_docx_conversion_failure_returns_422(temp_substrate, client, monkeypatch):
    """anydoc installed but the file is corrupt → typed 422 with the reason,
    surfaced from the ExtractionResult (never an unhandled exception)."""
    _install_fake_anydoc(monkeypatch, _FakeAnydoc(error=ValueError("corrupt document")))
    resp = client.post(
        "/sources/upload",
        files={"file": ("report.docx", b"not a real docx", "application/octet-stream")},
        data={"acquisition_attestation": "personal_reading"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == {"code": "upload_conversion_failed"}


def test_upload_docx_conversion_timeout_is_stable_and_reaped(
    temp_substrate, client, monkeypatch
):
    monkeypatch.setattr(upload_routes, "ANYDOC_CONVERSION_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(upload_routes, "_EXTRACT_SUBPROCESS", "import time; time.sleep(2)")
    resp = client.post(
        "/sources/upload",
        files={"file": ("report.docx", _make_docx_bytes(), "application/octet-stream")},
        data={"acquisition_attestation": "personal_reading"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == {"code": "upload_conversion_timeout"}


@pytest.mark.parametrize(
    "worker",
    [
        "from pathlib import Path; import sys; Path(sys.argv[2]).write_text('{')",
        (
            "from pathlib import Path; import json,sys; "
            "Path(sys.argv[2]).write_text(json.dumps({'ok':False,'kind':'',"
            "'text':'','oversize':True}))"
        ),
    ],
)
def test_upload_docx_partial_or_oversize_converter_result_is_stable(
    temp_substrate, client, monkeypatch, worker
):
    monkeypatch.setattr(upload_routes, "_EXTRACT_SUBPROCESS", worker)
    resp = client.post(
        "/sources/upload",
        files={"file": ("report.docx", _make_docx_bytes(), "application/octet-stream")},
        data={"acquisition_attestation": "personal_reading"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == {"code": "upload_conversion_failed"}


def test_real_converter_protocol_sanitizes_env_and_cleans_tempdir(
    temp_substrate, client, monkeypatch, tmp_path
):
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "must-not-reach-child")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-reach-child")
    _install_child_anydoc(
        tmp_path,
        monkeypatch,
        """import os
def to_markdown_bytes(data, format=None):
    assert 'ANTIEK_OPERATOR_TOKEN' not in os.environ
    assert 'OPENAI_API_KEY' not in os.environ
    assert os.path.basename(os.getcwd()).startswith('antiek-anydoc-')
    return '# Sanitized child environment'
""",
    )
    before = set(Path(tempfile.gettempdir()).glob("antiek-anydoc-*"))
    resp = client.post(
        "/sources/upload",
        headers={"Authorization": "Bearer must-not-reach-child"},
        files={"file": ("report.docx", _make_docx_bytes(), "application/octet-stream")},
        data={"acquisition_attestation": "personal_reading"},
    )
    assert resp.status_code == 201, resp.text
    assert set(Path(tempfile.gettempdir()).glob("antiek-anydoc-*")) == before


def test_converter_resource_limit_failure_is_stable(
    temp_substrate, client, monkeypatch, tmp_path
):
    _install_child_anydoc(
        tmp_path, monkeypatch, "def to_markdown_bytes(data, format=None): return '# ok'"
    )
    monkeypatch.setattr(upload_routes, "CONVERTER_FILE_SIZE_BYTES", 1)
    resp = client.post(
        "/sources/upload",
        files={"file": ("report.docx", _make_docx_bytes(), "application/octet-stream")},
        data={"acquisition_attestation": "personal_reading"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == {"code": "upload_conversion_failed"}


def test_slow_office_conversion_does_not_block_health(
    temp_substrate, client, monkeypatch, tmp_path
):
    _install_child_anydoc(
        tmp_path,
        monkeypatch,
        """import time
def to_markdown_bytes(data, format=None):
    time.sleep(0.5)
    return '# slow but bounded'
""",
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        upload = pool.submit(
            client.post,
            "/sources/upload",
            files={"file": ("report.docx", _make_docx_bytes(), "application/octet-stream")},
            data={"acquisition_attestation": "personal_reading"},
        )
        # The converter itself sleeps for 500 ms.  Waiting long enough for the
        # request to enter that window makes the assertion about ordering, not
        # scheduler speed: health must finish while conversion is still live.
        time.sleep(0.1)
        health = client.get("/health")
        assert health.status_code == 200
        assert not upload.done()
        assert upload.result().status_code == 201


_XSS_DOCX_GFM = """# Infected Upload

A clean paragraph that must survive.

<script>alert('xss')</script>

<img src="x" onerror="steal()">
"""


def test_uploaded_docx_script_seed_stripped_in_storage(
    temp_substrate, client, monkeypatch
):
    """Red-proof for the anydoc lane: conversion output carrying a <script>
    element never reaches the STORED sidecar as live markup. The markdown is
    html-escaped before it becomes HTML and the sidecar store sanitizes again
    + stamps SANITIZER_VERSION — the script dies before storage, the benign
    content survives."""
    _install_fake_anydoc(monkeypatch, _FakeAnydoc(_XSS_DOCX_GFM))
    resp = client.post(
        "/sources/upload",
        files={"file": ("infected.docx", _make_docx_bytes(),
                        "application/octet-stream")},
        data={"acquisition_attestation": "personal_reading"},
    )
    assert resp.status_code == 201, resp.text
    document_id = resp.json()["document_id"]

    stored = _sidecar_body(temp_substrate["db_path"], document_id)
    assert stored is not None
    # The benign converted content survives …
    assert "<h1>Infected Upload</h1>" in stored
    assert "A clean paragraph that must survive." in stored
    # … and the script/img elements are gone from the stored body — escaped
    # to inert text at most, never a live tag.
    assert "<script" not in stored.lower()
    assert "<img" not in stored.lower()


# ---------------------------------------------------------------------------
# Acceptance: uploaded HTML with a <script> → STORED body sanitized (red-proof)
# ---------------------------------------------------------------------------


_XSS_HTML = b"""<!DOCTYPE html>
<html><body>
<h1>Real Heading</h1>
<p>A normal paragraph the reader should keep.</p>
<script>alert('xss')</script>
<img src="x" onerror="steal()">
<a href="javascript:owned()">link</a>
<p onclick="bad()">click me</p>
</body></html>"""


def test_uploaded_html_script_is_sanitized_in_storage(temp_substrate, client):
    """The CRITICAL guardrail: the STORED sidecar body never carries the script
    / event-handler / javascript: payload, even though the upload sent it raw."""
    resp = client.post(
        "/sources/upload",
        files={"file": ("page.html", _XSS_HTML, "text/html")},
        data={"acquisition_attestation": "personal_reading"},
    )
    assert resp.status_code == 201, resp.text
    document_id = resp.json()["document_id"]
    assert resp.json()["detected_kind"] == "html"

    stored = _sidecar_body(temp_substrate["db_path"], document_id)
    assert stored is not None
    # The benign content survives …
    assert "Real Heading" in stored
    assert "A normal paragraph the reader should keep." in stored
    # … and every XSS vector dies before storage.
    assert "<script" not in stored.lower()
    assert "alert(" not in stored
    assert "onerror" not in stored.lower()
    assert "onclick" not in stored.lower()
    assert "javascript:" not in stored.lower()

    # And the document raw_text (the text-fallback path) is ALSO the sanitized
    # body — never the raw upload.
    import duckdb

    con = duckdb.connect(temp_substrate["db_path"])
    try:
        row = con.execute(
            "SELECT raw_text FROM documents WHERE document_id = ?",
            [document_id],
        ).fetchone()
    finally:
        con.close()
    assert row is not None
    raw_text = str(row[0])
    assert "<script" not in raw_text.lower()
    assert "onerror" not in raw_text.lower()


def test_uploaded_html_served_sanitized(temp_substrate, client, monkeypatch):
    resp = client.post(
        "/sources/upload",
        files={"file": ("page.html", _XSS_HTML, "text/html")},
        data={"acquisition_attestation": "personal_reading"},
    )
    document_id = resp.json()["document_id"]
    _as_owner(monkeypatch)
    served = client.get(f"/sources/{document_id}/reader-html")
    assert served.status_code == 200
    sbody = served.json()
    assert sbody["content_format"] == "html"
    assert "<script" not in sbody["body"].lower()
    assert "onerror" not in sbody["body"].lower()
    assert "Real Heading" in sbody["body"]


# ---------------------------------------------------------------------------
# Markdown / text upload
# ---------------------------------------------------------------------------


def test_upload_markdown_served_as_html(temp_substrate, client, monkeypatch):
    md = b"# Title\n\nFirst paragraph of markdown.\n\n## Section\n\nSecond block."
    resp = client.post(
        "/sources/upload",
        files={"file": ("note.md", md, "text/markdown")},
        data={"acquisition_attestation": "personal_reading"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["detected_kind"] == "md"
    document_id = body["document_id"]

    _as_owner(monkeypatch)
    served = client.get(f"/sources/{document_id}/reader-html")
    assert served.status_code == 200
    sbody = served.json()
    assert sbody["content_format"] == "html"
    assert sbody["source_kind"] == "upload_md"
    # markdown_to_safe_html turns # / ## into h1/h2.
    assert "<h1>Title</h1>" in sbody["body"]
    assert "<h2>Section</h2>" in sbody["body"]


def test_upload_txt_served_as_html(temp_substrate, client, monkeypatch):
    resp = client.post(
        "/sources/upload",
        files={"file": ("note.txt", b"A short text upload body.", "text/plain")},
        data={"acquisition_attestation": "personal_reading"},
    )
    assert resp.status_code == 201
    document_id = resp.json()["document_id"]
    assert resp.json()["detected_kind"] == "txt"

    _as_owner(monkeypatch)
    served = client.get(f"/sources/{document_id}/reader-html")
    assert served.json()["content_format"] == "html"
    assert "A short text upload body." in served.json()["body"]


# ---------------------------------------------------------------------------
# Attestation: missing / invalid → 4xx
# ---------------------------------------------------------------------------


def test_upload_missing_attestation_returns_4xx(temp_substrate, client):
    """No acquisition_attestation field at all → FastAPI form validation 422."""
    resp = client.post(
        "/sources/upload",
        files={"file": ("note.txt", b"some text", "text/plain")},
    )
    assert 400 <= resp.status_code < 500
    assert resp.status_code == 422


def test_upload_invalid_attestation_returns_4xx(temp_substrate, client):
    """An attestation value outside the allowed set → 422 (our explicit guard)."""
    resp = client.post(
        "/sources/upload",
        files={"file": ("note.txt", b"some text", "text/plain")},
        data={"acquisition_attestation": "i_swear_its_fine"},
    )
    assert resp.status_code == 422
    assert "acquisition_attestation" in resp.json()["detail"]


def test_upload_missing_file_returns_4xx(temp_substrate, client):
    resp = client.post(
        "/sources/upload",
        data={"acquisition_attestation": "personal_reading"},
    )
    assert 400 <= resp.status_code < 500


def test_upload_exact_64_mib_boundary_and_plus_one(temp_substrate, client):
    at_limit = b"x" * upload_routes.DEFAULT_MAX_UPLOAD_BYTES
    accepted = client.post(
        "/sources/upload",
        files={"file": ("limit.txt", at_limit, "text/plain")},
        data={"acquisition_attestation": "personal_reading"},
    )
    assert accepted.status_code == 201
    rejected = client.post(
        "/sources/upload",
        files={"file": ("over.txt", at_limit + b"x", "text/plain")},
        data={"acquisition_attestation": "personal_reading"},
    )
    assert rejected.status_code == 413


def test_upload_auth_required_and_signed_cookie_origin_policy(temp_substrate, monkeypatch):
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "test-auth-secret-that-is-at-least-thirty-two-bytes")
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "owner@example.test")
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    protected = TestClient(app)
    payload = {
        "files": {"file": ("note.txt", b"authenticated", "text/plain")},
        "data": {"acquisition_attestation": "personal_reading"},
    }
    assert protected.post("/sources/upload", **payload).status_code == 401

    cookie = mint_session_cookie(user_id="owner", email="owner@example.test")
    protected.cookies.set("ANTIEK_SESSION", cookie)
    missing_provenance = protected.post("/sources/upload", **payload)
    assert missing_provenance.status_code == 403
    cross_origin = protected.post(
        "/sources/upload", headers={"Origin": "https://evil.example"}, **payload
    )
    assert cross_origin.status_code == 403
    assert cross_origin.json()["detail"] == {"code": "cross_origin_request"}
    assert "evil.example" not in cross_origin.text

    accepted = protected.post(
        "/sources/upload", headers={"Origin": "https://antiek.ai"}, **payload
    )
    assert accepted.status_code == 201
    accepted_referer = protected.post(
        "/sources/upload",
        headers={"Referer": "https://antiek.ai/library/upload"},
        **payload,
    )
    assert accepted_referer.status_code == 201


def test_upload_bearer_auth_does_not_require_browser_origin(temp_substrate, monkeypatch):
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "machine-upload-token")
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    protected = TestClient(app)
    response = protected.post(
        "/sources/upload",
        headers={"Authorization": "Bearer machine-upload-token"},
        files={"file": ("note.txt", b"machine upload", "text/plain")},
        data={"acquisition_attestation": "personal_reading"},
    )
    assert response.status_code == 201


def test_upload_cf_service_token_does_not_require_browser_origin(temp_substrate, monkeypatch):
    monkeypatch.setenv("ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", "service-client")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "service-secret")
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    response = TestClient(app).post(
        "/sources/upload",
        headers={
            "Cf-Access-Client-Id": "service-client",
            "Cf-Access-Client-Secret": "service-secret",
        },
        files={"file": ("note.txt", b"service upload", "text/plain")},
        data={"acquisition_attestation": "personal_reading"},
    )
    assert response.status_code == 201


def test_upload_unauthenticated_local_does_not_require_origin(temp_substrate):
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    response = TestClient(app).post(
        "/sources/upload",
        files={"file": ("note.txt", b"local upload", "text/plain")},
        data={"acquisition_attestation": "personal_reading"},
    )
    assert response.status_code == 201


def test_upload_cookie_accepts_normalized_configured_origin(temp_substrate, monkeypatch):
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "test-auth-secret-that-is-at-least-thirty-two-bytes")
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "owner@example.test")
    monkeypatch.setenv(
        "ANTIEK_CORS_ORIGINS", "  https://custom.example/ , http://localhost:9911/  "
    )
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    protected = TestClient(app)
    protected.cookies.set(
        "ANTIEK_SESSION", mint_session_cookie(user_id="owner", email="owner@example.test")
    )
    response = protected.post(
        "/sources/upload",
        headers={"Origin": "https://custom.example"},
        files={"file": ("note.txt", b"configured origin", "text/plain")},
        data={"acquisition_attestation": "personal_reading"},
    )
    assert response.status_code == 201


# ---------------------------------------------------------------------------
# content_class: user_owned is publicly servable; personal_reading is owner-only
# ---------------------------------------------------------------------------


def test_user_owned_upload_is_publicly_servable_as_html(temp_substrate, client):
    """user_owned is in SERVABLE_CONTENT_CLASSES, so the PUBLIC (non-owner)
    reader-html path releases the sanitized html — no owner grant needed."""
    resp = client.post(
        "/sources/upload",
        files={"file": ("page.html", b"<p>Publicly owned body.</p>", "text/html")},
        data={"acquisition_attestation": "user_owned"},
    )
    assert resp.status_code == 201
    document_id = resp.json()["document_id"]

    served = client.get(f"/sources/{document_id}/reader-html")
    assert served.status_code == 200
    sbody = served.json()
    assert sbody["content_format"] == "html"
    assert sbody["available"] is True
    assert "Publicly owned body." in sbody["body"]


def test_personal_reading_upload_not_publicly_servable(temp_substrate, client):
    """personal_reading is owner-only: the public path withholds the html body —
    it never serves content_format="html". (The public path degrades to the
    bounded text snippet, which for a tiny doc may coincidentally equal the short
    raw_text; the security property is format=text + available=False, not the
    snippet bytes.)"""
    resp = client.post(
        "/sources/upload",
        files={"file": ("page.html", b"<p>Private owner body.</p>", "text/html")},
        data={"acquisition_attestation": "personal_reading"},
    )
    document_id = resp.json()["document_id"]

    served = client.get(f"/sources/{document_id}/reader-html")
    assert served.status_code == 200
    sbody = served.json()
    assert sbody["content_format"] == "text"
    assert sbody["available"] is False
    assert sbody["reason"] == "rights_denied"


# ---------------------------------------------------------------------------
# §5.2 hazard: the books full-text endpoint keeps serving uploads as "text"
# ---------------------------------------------------------------------------


def test_uploaded_doc_books_fulltext_still_text(temp_substrate, client, monkeypatch):
    """Storing the sidecar must NOT stamp documents.metadata with the trusted
    bit, or the books full-text endpoint would label the raw_text as html and
    the reader would innerHTML it (the stored-XSS-adjacent defect this lane
    guards). The two trust contracts stay disjoint."""
    resp = client.post(
        "/sources/upload",
        files={"file": ("page.html", b"<p>Body for hazard test.</p>", "text/html")},
        data={"acquisition_attestation": "personal_reading"},
    )
    document_id = resp.json()["document_id"]
    _as_owner(monkeypatch)

    owner = client.get(f"/books/{document_id}/owner-full-text")
    assert owner.status_code == 200
    ob = owner.json()
    assert ob["content_format"] == "text"  # NOT html — metadata not trust-stamped


# ---------------------------------------------------------------------------
# Unsupported type → 415
# ---------------------------------------------------------------------------


def test_upload_unsupported_type_returns_415(temp_substrate, client):
    """A genuinely unsupported extension (no magic, not in any supported set)
    is still a typed 415. NOTE: .docx no longer lives here — Office/ODF/RTF/CSV
    are supported via the anydoc lane (see the office section above)."""
    resp = client.post(
        "/sources/upload",
        files={"file": ("blob.bin", b"\x00\x01\x02 binary junk",
                        "application/octet-stream")},
        data={"acquisition_attestation": "personal_reading"},
    )
    assert resp.status_code == 415
