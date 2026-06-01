"""Read-side proof for the Personal-Reading Lane (SPR-02 backstop).

The lane is two-sided. The WRITE side (the connector tests in
``test_acquisition_{urls,youtube,twitter}.py``) proves a third-party document
LANDS ``content_class='personal_reading'``. THIS module proves the READ side:
once landed, a ``personal_reading`` body
  * NEVER serves full text on the PUBLIC serve path (``serve_full_text`` with
    ``owner=False``) — the §9.0 (Hachette / Bartz) catastrophe the whole spec
    exists to prevent;
  * DOES serve full body on the OWNER path (``owner=True``) — the lane's whole
    point is that the owner reads their own fetched reading in full;
  * is caught by the standing ``corpus_audit`` backstop
    (``CHECK_THIRD_PARTY_SERVABLE``) if it ever sits on a SERVABLE class without
    a basis — the DB-level proof that a leak introduced by ANY route (a future
    connector, a merge, a manual reclassify) is refused.

These three together are the read-side half of the lane invariant. The write
side lands it; this side proves it can never escape onto the monetized public
path. No live network: every row is seeded by hand into a temp DuckDB.

This module is the named ``harness_check_that_now_catches`` for the two
regression fixtures
``tests/regression/agent_failures/web-article-served-at-user-owned.yaml`` and
``youtube-transcript-at-user-owned.yaml`` — it is the mechanism that now blocks
the "third-party document inherits a servable default and serves publicly"
failure they document.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from runtime.db_lock import connect_write
from substrate.books.serve import serve_full_text
from substrate.constants import (
    PERSONAL_READING_CONTENT_CLASS,
    SERVABLE_CONTENT_CLASSES,
)
from substrate.corpus_audit import CHECK_THIRD_PARTY_SERVABLE, run_audit
from substrate.graph.schema import init_database_at_path


_PERSONAL_BODY = (
    "A Paul Graham essay the owner fetched for their own reading, long enough to "
    "be a real body and not a stub, repeated to clear any length floor. " * 6
)


@pytest.fixture
def db_path():
    tmpdir = tempfile.mkdtemp(prefix="antiek-lane-read-test-")
    path = os.path.join(tmpdir, "graph.duckdb")
    init_database_at_path(path)
    yield path


def _insert_personal_reading_doc(con, *, document_id, document_type, raw_text):
    """Seed a third-party document on the lane class personal_reading — exactly
    what the connectors now write."""
    con.execute(
        """
        INSERT INTO documents
            (document_id, source_uri, title, author, source_tier,
             document_type, raw_text, content_class)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            document_id,
            "https://paulgraham.com/essay.html",
            "A Third-Party Essay",
            "An Author",
            4,
            document_type,
            raw_text,
            PERSONAL_READING_CONTENT_CLASS,
        ],
    )


# ---------------------------------------------------------------------------
# Read side (1): personal_reading NEVER serves full text on the PUBLIC path.
# ---------------------------------------------------------------------------


def test_personal_reading_does_not_serve_on_public_path(db_path):
    with connect_write(db_path, purpose="test-seed") as con:
        _insert_personal_reading_doc(
            con,
            document_id="doc-web-personal",
            document_type="web_article",
            raw_text=_PERSONAL_BODY,
        )
    # Public path: owner defaults to False.
    served = serve_full_text(db_path_con(db_path), "doc-web-personal")
    assert served.found is True
    assert served.servable is False, "personal_reading must NOT be publicly servable"
    assert served.full_text is None, (
        "personal_reading must NEVER return full text on the public serve path "
        "(the §9.0 leak this lane prevents)"
    )
    # And it is categorically excluded from the servable allowlist.
    assert PERSONAL_READING_CONTENT_CLASS not in SERVABLE_CONTENT_CLASSES


def test_personal_reading_serves_full_body_to_owner(db_path):
    """The lane's purpose: the OWNER reads their own fetched third-party content
    in full. owner=True returns the full body — servable stays False (not
    publicly servable / ad-eligible)."""
    with connect_write(db_path, purpose="test-seed") as con:
        _insert_personal_reading_doc(
            con,
            document_id="doc-yt-personal",
            document_type="video_transcript",
            raw_text=_PERSONAL_BODY,
        )
    served = serve_full_text(db_path_con(db_path), "doc-yt-personal", owner=True)
    assert served.found is True
    assert served.full_text == _PERSONAL_BODY, "the owner reads their reading in full"
    assert served.servable is False, (
        "owner full-read does NOT make the body publicly servable / ad-eligible"
    )


# ---------------------------------------------------------------------------
# Read side (2): the corpus_audit backstop refuses a third-party doc that ever
# lands on a SERVABLE class without a basis — the DB-level proof.
# ---------------------------------------------------------------------------


def test_corpus_audit_refuses_third_party_on_servable(db_path):
    with connect_write(db_path, purpose="test-seed") as con:
        # A third-party web_article that slipped onto the servable user_owned
        # class with no basis — the leak the lane prevents going forward.
        con.execute(
            """
            INSERT INTO documents
                (document_id, source_uri, title, author, source_tier,
                 document_type, raw_text, content_class)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                "doc-leak",
                "https://example.com/leak.html",
                "Leaked Essay",
                "An Author",
                4,
                "web_article",
                _PERSONAL_BODY,
                "user_owned",  # servable, no basis row -> offender
            ],
        )
    result = run_audit(db_path, include_binding=False)
    check = result.check(CHECK_THIRD_PARTY_SERVABLE)
    assert not check.ok
    assert any("doc-leak" in o for o in check.offending)
    assert not result.ok


def db_path_con(path):
    """Open a short-lived read connection for a serve query (read-only)."""
    from runtime.db_lock import connect_read

    return connect_read(path)
