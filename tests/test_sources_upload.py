"""Doc→HTML S4 — POST /sources/upload endpoint tests.

Acceptance for the lane (brief, no live network):

- uploading a small PDF fixture → stored + served as sanitized
  ``content_format="html"``;
- uploading ``.epub`` / a PK-zip body → ``409`` pointing at the authorized
  book-acquisition ceremony (magic bytes win over extension);
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

import pytest
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.api import books as books_api  # noqa: E402
from interfaces.research.api.app import create_app  # noqa: E402
from interfaces.research.api.upload_routes import sniff_kind  # noqa: E402
from runtime.db_lock import connect_write  # noqa: E402
from substrate.books.html_sanitizer import SANITIZER_VERSION  # noqa: E402

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
    resp = client.post(
        "/sources/upload",
        files={"file": ("file.docx", b"fake docx bytes", "application/octet-stream")},
        data={"acquisition_attestation": "personal_reading"},
    )
    assert resp.status_code == 415
