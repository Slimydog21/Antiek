"""HPRJ SPR-4: the `.antiek` return leg — POST /ingest/antiek.

Every test drives the ROUTE. The defect this route fixes is that
``services/ingestion/ingest_antiek.py`` had no HTTP caller at all, so a test
that called the library would have passed against the broken tree and proved
nothing; only a request can tell the difference.

The round trip is a real one: a notebook is written to the substrate, exported
through the notebook artifact route that ships `.antiek`, and the bytes that
route returns are uploaded back. Nothing is hand-assembled in between.
"""

from __future__ import annotations

import io
import os
import zipfile

import pytest
from fastapi.testclient import TestClient

from runtime.db_lock import connect_write

OWNER = "test-owner-user"


@pytest.fixture
def api_env(tmp_path, monkeypatch) -> dict[str, str]:
    db_path = str(tmp_path / "graph.duckdb")
    events_dir = str(tmp_path / "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_EVENT_LOG_DIR", events_dir)
    from substrate.graph.schema import init_database

    writer = connect_write(db_path, purpose="test/ingest-antiek/schema")
    try:
        init_database(writer)
    finally:
        writer.close()
    return {"db_path": db_path, "events_dir": events_dir}


@pytest.fixture
def client(api_env, monkeypatch) -> TestClient:
    monkeypatch.setattr(
        "interfaces.research.api.doc_ingest_routes.distinct_signed_owner",
        lambda _request: OWNER,
    )
    from interfaces.research.api.app import create_app

    app = create_app(
        register_wrestling=False, register_providers=False, cors_origins=[]
    )
    return TestClient(app)


def _notebook(db_path: str, text: str, *, document_id: str | None = None) -> str:
    """A one-paragraph notebook in the substrate. Returns its notebook_id."""
    from substrate.notebooks import append_block, create_notebook

    with connect_write(db_path, purpose="test/ingest-antiek/notebook") as con:
        notebook_id = create_notebook(con, title="Homecoming", document_id=document_id)
        append_block(
            con,
            notebook_id,
            block_type="prose",
            content={
                "type": "paragraph",
                "content": [{"type": "text", "text": text}],
            },
        )
    return notebook_id


def _export(client: TestClient, notebook_id: str, fmt: str):
    resp = client.get(f"/api/notebooks/{notebook_id}/artifact?format={fmt}")
    assert resp.status_code == 200, resp.text
    return resp


def _upload(client: TestClient, payload: bytes, name: str = "artifact.antiek"):
    return client.post("/ingest/antiek", files={"file": (name, payload)})


def _tampered_container(artifact: bytes) -> bytes:
    """A structurally VALID `.antiek` whose rendered shell was edited.

    The container still reads cleanly and the SIGNATURE is what refuses it.
    That is deliberately not the same thing as flipping a byte in the raw zip,
    which corrupts a CRC and quarantines as `malformed_container` before any
    signature check runs — both are refused, and the route has to say which.
    """
    from services.antiek_format.native_writer import ENTRY_PROJECTION, _build_deterministic_zip

    with zipfile.ZipFile(io.BytesIO(artifact)) as zf:
        entries = [(n, zf.read(n)) for n in zf.namelist()]
    tampered = []
    for name, payload in entries:
        if name == ENTRY_PROJECTION:
            mutated = bytearray(payload)
            mutated[len(mutated) // 2] ^= 0x20
            payload = bytes(mutated)
        tampered.append((name, payload))
    return _build_deterministic_zip(tampered)


def _documents(db_path: str) -> set[str]:
    from runtime.db_lock import connect_read

    con = connect_read(db_path)
    try:
        return {str(r[0]) for r in con.execute("SELECT document_id FROM documents").fetchall()}
    finally:
        con.close()


def _reader_bodies(db_path: str) -> dict[str, str]:
    from runtime.db_lock import connect_read

    con = connect_read(db_path)
    try:
        rows = con.execute(
            "SELECT document_id, html_body FROM document_reader_html"
        ).fetchall()
        return {str(r[0]): str(r[1]) for r in rows}
    finally:
        con.close()


# ── done-bar 1: the artifact comes home and is recognised ──


def test_round_tripped_container_classifies_returned_unmodified(client, api_env):
    notebook_id = _notebook(api_env["db_path"], "The passage that travelled.")
    artifact = _export(client, notebook_id, "antiek").content

    resp = _upload(client, artifact)

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["roundtrip"] == "returned_unmodified"
    # Proved ours, so it lands on its own document rather than a stranger's id.
    assert body["document_id"] == notebook_id
    assert body["content_class"] == "user_owned"
    assert body["render_url"] == f"/documents/{notebook_id}/render"
    # The stored reader body carries the artifact's content, not its markup.
    assert "The passage that travelled." in _reader_bodies(api_env["db_path"])[notebook_id]


def test_the_returned_artifact_is_readable_where_the_response_says(client, api_env):
    """The leg is only complete if the URL it hands back opens. A store write
    that no reader can resolve would look identical in the response."""
    notebook_id = _notebook(api_env["db_path"], "Readable after the journey.")
    artifact = _export(client, notebook_id, "antiek").content

    body = _upload(client, artifact).json()
    rendered = client.get(body["render_url"])

    assert rendered.status_code == 200, rendered.text
    assert "Readable after the journey." in rendered.text


def test_round_tripped_single_file_is_ingested(client, api_env):
    notebook_id = _notebook(api_env["db_path"], "Single file came home.")
    artifact = _export(client, notebook_id, "antiek_html").text.encode("utf-8")

    resp = _upload(client, artifact, name="artifact.antiek.html")

    assert resp.status_code == 201, resp.text
    body = resp.json()
    # A single-file projection built by the export path carries no `source`
    # block, so it cannot name its own document. It is stored under a
    # content-derived id rather than a guessed one, and as personal_reading:
    # nothing here proves Antiek authored it.
    assert body["document_id"].startswith("doc-antiek-")
    assert body["content_class"] == "personal_reading"
    assert "Single file came home." in _reader_bodies(api_env["db_path"])[body["document_id"]]


def test_externally_edited_container_is_the_strongest_signal(client, api_env):
    notebook_id = _notebook(api_env["db_path"], "The original passage.")
    artifact = _export(client, notebook_id, "antiek").content

    # Edit the notebook so the substrate no longer matches the exported bytes.
    # This is the detector's "travelled and changed" from the other direction —
    # what matters to the route is that the content hash no longer agrees.
    from substrate.notebooks import append_block

    with connect_write(api_env["db_path"], purpose="test/ingest-antiek/edit") as con:
        append_block(
            con,
            notebook_id,
            block_type="prose",
            content={"type": "paragraph", "content": [{"type": "text", "text": "Added."}]},
        )

    resp = _upload(client, artifact)

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["roundtrip"] == "traveled_and_changed"
    # Content this instance does not currently produce never claims the id on
    # the manifest, and never upgrades out of personal_reading.
    assert body["document_id"] != notebook_id
    assert body["document_id"].startswith("doc-antiek-")
    assert body["content_class"] == "personal_reading"
    # The notebook's own reader body was not overwritten by the upload.
    assert notebook_id not in _reader_bodies(api_env["db_path"])


def test_a_bound_notebook_never_overwrites_its_documents_reader_body(client, api_env):
    """The clobber case. A notebook bound to a document exports an artifact
    claiming that DOCUMENT's id, so honouring the claim on re-import would
    replace the document's reader body with the notebook's prose."""
    from substrate.graph.ops import insert_document
    from substrate.reader_html.store import store_reader_html

    db_path = api_env["db_path"]
    bound_id = "doc-a-real-book"
    with connect_write(db_path, purpose="test/ingest-antiek/bound") as con:
        insert_document(
            con,
            document_id=bound_id,
            source_tier=2,
            document_type="upload",
            raw_text="THE BOOK BODY",
            content_class="public_domain",
        )
        store_reader_html(
            con,
            document_id=bound_id,
            main_html="<p>THE BOOK BODY</p>",
            source_kind="upload",
        )

    notebook_id = _notebook(db_path, "Notebook prose.", document_id=bound_id)
    artifact = _export(client, notebook_id, "antiek").content

    body = _upload(client, artifact).json()

    assert body["document_id"] != bound_id
    assert body["document_id"].startswith("doc-antiek-")
    assert body["content_class"] == "personal_reading"
    bodies = _reader_bodies(db_path)
    assert "THE BOOK BODY" in bodies[bound_id]
    assert "Notebook prose." not in bodies[bound_id]


def test_a_bound_notebook_never_takes_over_a_book_with_no_reader_body_yet(client, api_env):
    """The same clobber, one step earlier. A document and its reader body are
    written separately, so a book routinely exists before it has been projected.
    Asking only the sidecar reads that book as "nothing is there" and hands the
    notebook's prose the book's id, its title and its servable rights class."""
    from substrate.graph.ops import insert_document

    db_path = api_env["db_path"]
    bound_id = "doc-a-book-not-projected-yet"
    with connect_write(db_path, purpose="test/ingest-antiek/unprojected") as con:
        insert_document(
            con,
            document_id=bound_id,
            source_tier=2,
            document_type="upload",
            title="A Real Book",
            raw_text="THE BOOK BODY",
            content_class="public_domain",
        )

    notebook_id = _notebook(db_path, "Notebook prose.", document_id=bound_id)
    artifact = _export(client, notebook_id, "antiek").content

    body = _upload(client, artifact).json()

    assert body["document_id"] != bound_id
    assert body["content_class"] == "personal_reading"
    # The book had no reader body and must still have none: a servable document
    # cannot acquire one from an upload.
    assert bound_id not in _reader_bodies(db_path)
    # And the book is still what it was.
    assert client.get(f"/documents/{bound_id}/render").status_code != 200


def test_a_reader_body_this_route_did_not_write_is_never_replaced(client, api_env):
    """The other half of the same guard. A document row and a reader body are
    separate rows, so a document this route DID create can still hold a body
    some other lane wrote — a re-projection, a repair. Owning the document is
    not owning the body, and the body is what an import would destroy."""
    from substrate.graph.ops import insert_document
    from substrate.reader_html.store import store_reader_html

    db_path = api_env["db_path"]
    bound_id = "doc-reprojected-elsewhere"
    with connect_write(db_path, purpose="test/ingest-antiek/foreign-body") as con:
        insert_document(
            con,
            document_id=bound_id,
            source_tier=2,
            document_type="antiek_artifact",
            raw_text="SOMEONE ELSE'S BODY",
            content_class="user_owned",
        )
        store_reader_html(
            con,
            document_id=bound_id,
            main_html="<p>SOMEONE ELSE'S BODY</p>",
            source_kind="upload",
        )

    notebook_id = _notebook(db_path, "Notebook prose.", document_id=bound_id)
    artifact = _export(client, notebook_id, "antiek").content

    body = _upload(client, artifact).json()

    assert body["document_id"] != bound_id
    assert body["content_class"] == "personal_reading"
    assert "SOMEONE ELSE'S BODY" in _reader_bodies(db_path)[bound_id]


def test_two_different_artifacts_never_share_a_minted_id(client, api_env):
    """The minted id is derived from the artifact's own content. A constant —
    or anything the manifest can steer — would let one upload overwrite the
    reader body of an unrelated one."""
    first = _export(client, _notebook(api_env["db_path"], "First body."), "antiek_html")
    second = _export(client, _notebook(api_env["db_path"], "Second body."), "antiek_html")

    one = _upload(client, first.text.encode("utf-8"), name="a.antiek.html").json()
    two = _upload(client, second.text.encode("utf-8"), name="b.antiek.html").json()

    assert one["document_id"] != two["document_id"]
    bodies = _reader_bodies(api_env["db_path"])
    assert "First body." in bodies[one["document_id"]]
    assert "Second body." in bodies[two["document_id"]]


def test_an_oversize_upload_is_refused_before_it_is_parsed(client, api_env, monkeypatch):
    monkeypatch.setattr(
        "interfaces.research.api.doc_ingest_routes._MAX_UPLOAD_BYTES", 64
    )
    notebook_id = _notebook(api_env["db_path"], "Too big to come home.")
    artifact = _export(client, notebook_id, "antiek").content
    assert len(artifact) > 64

    resp = _upload(client, artifact)

    assert resp.status_code == 413
    assert _documents(api_env["db_path"]) == set()


def test_the_stored_document_carries_the_artifacts_text(client, api_env):
    """A document stored with no raw_text is invisible to search while looking
    ingested, which is worse than a refusal."""
    from runtime.db_lock import connect_read

    notebook_id = _notebook(api_env["db_path"], "Findable after the journey.")
    artifact = _export(client, notebook_id, "antiek").content

    body = _upload(client, artifact).json()

    con = connect_read(api_env["db_path"])
    try:
        row = con.execute(
            "SELECT raw_text FROM documents WHERE document_id = ?",
            [body["document_id"]],
        ).fetchone()
    finally:
        con.close()
    assert row is not None
    assert "Findable after the journey." in str(row[0])


def test_a_second_import_of_the_same_artifact_is_idempotent(client, api_env):
    notebook_id = _notebook(api_env["db_path"], "Came home twice.")
    artifact = _export(client, notebook_id, "antiek").content

    first = _upload(client, artifact).json()
    second = _upload(client, artifact).json()

    assert first["document_id"] == second["document_id"] == notebook_id
    assert second["roundtrip"] == "returned_unmodified"
    assert len(_reader_bodies(api_env["db_path"])) == 1


# ── done-bar 2: a tampered artifact quarantines with its typed reason ──


def test_tampered_container_quarantines_and_is_never_stored(client, api_env):
    notebook_id = _notebook(api_env["db_path"], "Benign content.")
    artifact = _export(client, notebook_id, "antiek").content
    before = _documents(api_env["db_path"])

    resp = _upload(client, _tampered_container(artifact))

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["disposition"] == "tampered"
    assert detail["reason_code"] == "container_signature_invalid"
    # Never rendered, never stored — not under the claimed id, not anywhere.
    assert _documents(api_env["db_path"]) == before
    assert _reader_bodies(api_env["db_path"]) == {}


def test_tampered_single_file_quarantines_as_tampered(client, api_env):
    notebook_id = _notebook(api_env["db_path"], "Hi")
    artifact = _export(client, notebook_id, "antiek_html").text
    tampered = artifact.replace("Hi", "Hacked", 1).encode("utf-8")

    resp = _upload(client, tampered, name="artifact.antiek.html")

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["disposition"] == "tampered"
    assert detail["reason_code"] == "single_file_signature_invalid"
    assert _reader_bodies(api_env["db_path"]) == {}


# ── done-bar 3: malformed is distinguishable from tampered ──


def test_malformed_container_is_not_reported_as_tampered(client, api_env):
    resp = _upload(client, b"PK\x03\x04 not really a zip at all")

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["reason_code"] == "malformed_container"
    # The whole point: an operator (or an agent) can act differently on a file
    # that was corrupted in transit than on one somebody edited.
    assert detail["disposition"] == "malformed"
    assert detail["disposition"] != "tampered"


def test_unsigned_projection_is_refused_as_unsigned(client, api_env):
    notebook_id = _notebook(api_env["db_path"], "Unsigned.")
    # The plain HTML export: a doc-model island, no signature island.
    projection = _export(client, notebook_id, "html").text.encode("utf-8")

    resp = _upload(client, projection, name="artifact.html")

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["reason_code"] == "unsigned_single_file"
    assert detail["disposition"] == "unsigned"


def test_ordinary_bytes_are_not_antiek(client, api_env):
    resp = _upload(client, b"just some prose, no island", name="notes.txt")

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["reason_code"] == "no_doc_model_island"
    assert detail["disposition"] == "not_antiek"


def test_binary_junk_is_not_antiek(client, api_env):
    # Neither a zip nor decodable text: it never claimed to be an artifact.
    resp = _upload(client, b"\xff\xfe\x00\x01 binary junk", name="blob.bin")

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["reason_code"] == "not_antiek_bytes"
    assert detail["disposition"] == "not_antiek"


def test_a_validly_signed_file_with_a_broken_island_is_malformed(client, api_env, tmp_path):
    """Signed, verifies, and still unreadable. The signature says nobody edited
    it after signing; it says nothing about the payload being parseable, and
    the route has to report that as malformed rather than as tampering."""
    from services.antiek_format.signature import ensure_keypair
    from services.antiek_format.single_file import build_single_file

    notebook_id = _notebook(api_env["db_path"], "Broken island.")
    projection = _export(client, notebook_id, "html").text
    # Corrupt the island payload, THEN sign — so verification passes and the
    # extractor is what refuses it.
    broken = projection.replace('data-schema-version="1">', 'data-schema-version="1">{{{', 1)
    keypair = ensure_keypair("island-test", db_path=str(tmp_path / "k.duckdb"))
    signed = build_single_file(broken, keypair=keypair).encode("utf-8")

    resp = _upload(client, signed, name="broken.antiek.html")

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["reason_code"] == "island_unreadable"
    assert detail["disposition"] == "malformed"


def test_every_refusal_names_a_distinct_reason_code(client, api_env):
    """The four failure shapes an uploader can actually hit must not collapse
    into one message. This is the assertion that would have failed against a
    generic 422."""
    notebook_id = _notebook(api_env["db_path"], "Distinct.")
    valid = _export(client, notebook_id, "antiek").content

    codes = {
        _upload(client, b"PK\x03\x04 garbage").json()["detail"]["reason_code"],
        _upload(client, b"plain text").json()["detail"]["reason_code"],
        _upload(
            client, _export(client, notebook_id, "html").text.encode("utf-8")
        ).json()["detail"]["reason_code"],
        _upload(client, _tampered_container(valid)).json()["detail"]["reason_code"],
    }
    assert len(codes) == 4, codes


# ── boundaries the neighbouring route already holds ──


def test_empty_upload_is_refused(client, api_env):
    resp = _upload(client, b"")
    assert resp.status_code == 422
    assert resp.json()["detail"] == "file body must not be empty"


def test_unsigned_owner_is_refused(api_env, monkeypatch):
    monkeypatch.setattr(
        "interfaces.research.api.doc_ingest_routes.distinct_signed_owner",
        lambda _request: None,
    )
    from interfaces.research.api.app import create_app

    app = create_app(
        register_wrestling=False, register_providers=False, cors_origins=[]
    )
    resp = TestClient(app).post(
        "/ingest/antiek", files={"file": ("a.antiek", b"PK\x03\x04")}
    )
    assert resp.status_code == 401
