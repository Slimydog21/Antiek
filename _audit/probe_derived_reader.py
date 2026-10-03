"""Reproducer for the reader metadata gap (audit R6 checkpoint 2).

A derived document whose full text IS servable and whose provenance EXISTS
must be openable in the reader: GET /books/{document_id} must not answer
404 book_not_found. Negative control: an id that exists nowhere must still
answer book_not_found with the same status and body shape.

Real dependencies only: the repository fixture generator, the real reformat
pipeline, real DuckDB, and the real create_app/TestClient. No mocks.

Usage: uv run python _audit/probe_derived_reader.py
Exit 0 always; the printed statuses ARE the evidence.
"""
import json
import os
from pathlib import Path

root = Path(__file__).parent / "derived-reader-fixture"
root.mkdir(exist_ok=True)
for var, value in {
    "ANTIEK_DUCKDB_PATH": str(root / "reader.duckdb"),
    "ANTIEK_RESEARCH_EVENTS_DIR": str(root / "events"),
    "ANTIEK_RESEARCH_ARTIFACTS_DIR": str(root / "artifacts"),
    "ANTIEK_EMBEDDING_PROVIDER": "hash",
}.items():
    os.environ[var] = value

from substrate.graph import ensure_initialized  # noqa: E402
from substrate.reformat.pipeline import reformat_document  # noqa: E402
from tests.test_reformat_pipeline import (  # noqa: E402
    ACCEPTANCE_PROMPT,
    _fixture_generator,
    _seed_source,
    _source_body_hash,
)

ensure_initialized(os.environ["ANTIEK_DUCKDB_PATH"])
db = os.environ["ANTIEK_DUCKDB_PATH"]
_seed_source(db)
before = _source_body_hash(db, "doc-1")
result = reformat_document(
    db,
    owner_user_id="__operator__",
    source_document_id="doc-1",
    prompt=ACCEPTANCE_PROMPT,
    generate_fn=_fixture_generator,
)
print("SOURCE_UNCHANGED", before == _source_body_hash(db, "doc-1"))
print("DERIVED", result.derived_document_id)

# Scrub the operator-auth env: the probe must pass on the operator's own
# machine, where the login shell exports these and the middleware would
# answer 401 (same invariance as tests/test_reformat_routes.py).
for key in (
    "ANTIEK_AUTH_SECRET",
    "ANTIEK_OPERATOR_TOKEN",
    "ANTIEK_DEV_LOGIN_TOKEN",
    "ANTIEK_OPERATOR_EMAIL",
    "ANTIEK_COOKIE_INSECURE",
):
    os.environ.pop(key, None)

from fastapi.testclient import TestClient  # noqa: E402

from interfaces.research.api.app import create_app  # noqa: E402

# Gate-control fixtures, written through the real single-writer path: three
# documents rows with NO book_assets row and nothing publicly servable,
# plus one registered book (book_assets row) as the regression control.
from runtime.db_lock import connect_write  # noqa: E402
from substrate.books.ingest import register_book  # noqa: E402
from substrate.graph.ops import insert_document  # noqa: E402

with connect_write(db, purpose="probe/gate-controls") as con:
    insert_document(
        con, document_id="doc-gated-no-asset", source_tier=2,
        document_type="web", title="A gated web page",
        raw_text="gated body text that must never be served in full",
        content_class="restricted_pending_opt_in", on_conflict="error",
    )
    insert_document(
        con, document_id="doc-personal-no-asset", source_tier=2,
        document_type="web", title="A personal-reading page",
        raw_text="the operator's private third-party reading body",
        content_class="personal_reading", on_conflict="error",
    )
    insert_document(
        con, document_id="doc-empty-body-no-asset", source_tier=2,
        document_type="web", title="A servable-class page with no body",
        raw_text=None, content_class="public_domain", on_conflict="error",
    )
    insert_document(
        con, document_id="doc-registered-book", source_tier=2,
        document_type="book", title="A Registered Book",
        raw_text="registered book body", content_class="public_domain",
        on_conflict="error",
    )
    register_book(con, document_id="doc-registered-book",
                  content_class="public_domain")

with TestClient(create_app(register_wrestling=False)) as client:
    probes = [
        f"/books/{result.derived_document_id}",
        f"/books/{result.derived_document_id}/full-text",
        f"/documents/{result.derived_document_id}/provenance",
        # Negative control: an id that exists NOWHERE must still 404.
        "/books/doc-id-exists-nowhere",
        # Gate controls: a documents row with nothing servable must still
        # 404 (the fallback must not weaken the gate).
        "/books/doc-gated-no-asset",
        "/books/doc-personal-no-asset",
        "/books/doc-empty-body-no-asset",
        # Regression control: a registered book resolves exactly as before.
        "/books/doc-registered-book",
    ]
    for path in probes:
        r = client.get(path)
        body = r.text
        if len(body) > 400:
            body = body[:400] + "...[truncated]"
        print(json.dumps({"path": path, "status": r.status_code, "body": body}))
