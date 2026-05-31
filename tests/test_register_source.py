"""Tests for the unified cross-source rights registration chokepoint
(``substrate.rights.register``) — reframe finding #5.

Each test exercises one real branch of ``register_source_document``: the
LockedConnection guard, the insert-before-register precondition, deny-by-default
content_class, content_class validation, the user_content escrow-exclusion
(defense-in-depth), licensed ip-holder threading, explicit ip_holder pass-
through, the post-write serve-guard self-check on a gated doc, and idempotent
re-register (an ip_holder set once is never nulled by a later register)."""

from __future__ import annotations

import os
import tempfile

import duckdb
import pytest

from runtime.db_lock import connect_write
from substrate.constants import GATED_DEFAULT_CONTENT_CLASS
from substrate.graph.ops import insert_document
from substrate.graph.schema import init_database
from substrate.ip_holders import list_all
from substrate.rights.register import (
    SourceKind,
    register_source_document,
)


@pytest.fixture
def con():
    tmpdir = tempfile.mkdtemp(prefix="antiek-register-test-")
    c = connect_write(os.path.join(tmpdir, "test.duckdb"), purpose="register_test")
    init_database(c)
    yield c
    c.close()


def _insert(con, document_id, *, document_type="web_article", raw_text=None):
    insert_document(
        con,
        document_id=document_id,
        source_tier=3,
        document_type=document_type,
        raw_text=raw_text,
    )


def test_requires_locked_connection():
    raw = duckdb.connect(":memory:")
    try:
        with pytest.raises(TypeError, match="LockedConnection"):
            register_source_document(raw, document_id="x", source_kind=SourceKind.WEB)
    finally:
        raw.close()


def test_missing_document_raises(con):
    with pytest.raises(ValueError, match="no documents row"):
        register_source_document(
            con, document_id="ghost", source_kind=SourceKind.WEB, run_self_check=False
        )


def test_deny_by_default_when_no_content_class(con):
    _insert(con, "doc-1")
    cls = register_source_document(
        con, document_id="doc-1", source_kind=SourceKind.WEB, run_self_check=False
    )
    assert cls == GATED_DEFAULT_CONTENT_CLASS
    row = con.execute(
        "SELECT content_class FROM documents WHERE document_id='doc-1'"
    ).fetchone()
    assert row[0] == GATED_DEFAULT_CONTENT_CLASS


def test_explicit_content_class_validated(con):
    _insert(con, "doc-2")
    with pytest.raises(ValueError, match="unrecognised content_class"):
        register_source_document(
            con,
            document_id="doc-2",
            source_kind=SourceKind.WEB,
            content_class="totally_bogus",
            run_self_check=False,
        )


def test_user_content_rejects_any_rights_holder(con):
    """user_content is escrow-excluded BY CONSTRUCTION: passing a rights holder —
    name OR explicit id — is a category error and RAISES. (The b25b275 verifier-
    critic found the old silent-skip let an explicit ip_holder_id write straight
    through; the exclusion is now structural.) A user_content doc with NEITHER
    registers fine, gated, with no escrow account minted."""
    _insert(con, "doc-3")
    with pytest.raises(ValueError, match="escrow-excluded"):
        register_source_document(
            con, document_id="doc-3", source_kind=SourceKind.USER_CONTENT,
            rights_holder_name="Some Person", run_self_check=False,
        )
    with pytest.raises(ValueError, match="escrow-excluded"):
        register_source_document(
            con, document_id="doc-3", source_kind=SourceKind.USER_CONTENT,
            ip_holder_id="ipholder-x", run_self_check=False,
        )
    cls = register_source_document(
        con, document_id="doc-3", source_kind=SourceKind.USER_CONTENT,
        run_self_check=False,
    )
    assert cls == GATED_DEFAULT_CONTENT_CLASS
    assert list_all(con) == []
    assert con.execute(
        "SELECT ip_holder_id FROM documents WHERE document_id='doc-3'"
    ).fetchone()[0] is None


def test_licensed_source_threads_ip_holder(con):
    _insert(con, "doc-4")
    register_source_document(
        con,
        document_id="doc-4",
        source_kind=SourceKind.LICENSED_PUBLISHER,
        content_class="opt_in_licensed",
        rights_holder_name="MIT Press",
        run_self_check=False,
    )
    holders = list_all(con)
    assert len(holders) == 1
    assert holders[0].display_name == "MIT Press"
    row = con.execute(
        "SELECT ip_holder_id, content_class FROM documents WHERE document_id='doc-4'"
    ).fetchone()
    assert row[0] == holders[0].ip_holder_id
    assert row[1] == "opt_in_licensed"


def test_explicit_ip_holder_id_used_directly(con):
    _insert(con, "doc-6")
    register_source_document(
        con,
        document_id="doc-6",
        source_kind=SourceKind.ACADEMIC_PREPRINT,
        ip_holder_id="ipholder-fixed",
        run_self_check=False,
    )
    row = con.execute(
        "SELECT ip_holder_id FROM documents WHERE document_id='doc-6'"
    ).fetchone()
    assert row[0] == "ipholder-fixed"


def test_self_check_passes_through_gated_doc(con):
    """run_self_check=True on a deny-by-default doc with no servable body is a
    safe no-op: serve_full_text emits no body, so the serve-guard drift arm
    never fires."""
    _insert(con, "doc-5", raw_text=None)
    cls = register_source_document(
        con, document_id="doc-5", source_kind=SourceKind.WEB, run_self_check=True
    )
    assert cls == GATED_DEFAULT_CONTENT_CLASS


def test_idempotent_reregister_preserves_ip_holder(con):
    """A re-register with no rights_holder must not null out an ip_holder set by
    a prior register — the gate primitive writes ip_holder only when resolved."""
    _insert(con, "doc-7")
    register_source_document(
        con,
        document_id="doc-7",
        source_kind=SourceKind.LICENSED_PUBLISHER,
        content_class="opt_in_licensed",
        rights_holder_name="MIT Press",
        run_self_check=False,
    )
    first = con.execute(
        "SELECT ip_holder_id FROM documents WHERE document_id='doc-7'"
    ).fetchone()[0]
    assert first is not None
    register_source_document(
        con,
        document_id="doc-7",
        source_kind=SourceKind.LICENSED_PUBLISHER,
        content_class="restricted_pending_opt_in",
        run_self_check=False,
    )
    row = con.execute(
        "SELECT ip_holder_id, content_class FROM documents WHERE document_id='doc-7'"
    ).fetchone()
    assert row[0] == first
    assert row[1] == "restricted_pending_opt_in"


def test_self_check_raises_on_t3_license_drift(con):
    """The self-check's ENFORCING branch (the one that protects rights): stamping a
    SERVABLE content_class on a doc whose arXiv <license> resolves to T3 is rights
    drift — register_source_document(run_self_check=True) must RAISE at write time
    (generalizing acquisition/arxiv/store.py), not silently persist a mis-stamp the
    serve gate would later reject. RED-THEN-GREEN: with run_self_check=False the
    same mis-stamp persists with NO raise — proving the self-check is load-bearing."""
    from substrate.rights import T3BodyServeError

    t3_license = "http://arxiv.org/licenses/nonexclusive-distrib/1.0/"
    insert_document(
        con,
        document_id="doc-drift",
        source_tier=3,
        document_type="academic_paper",
        raw_text="THE FULL PAPER BODY THAT MUST NOT LEAK FOR A T3 PAPER. " * 30,
        metadata={"license_uri": t3_license},
    )
    with pytest.raises(T3BodyServeError):
        register_source_document(
            con,
            document_id="doc-drift",
            source_kind=SourceKind.ACADEMIC_PREPRINT,
            content_class="source_declared_open",  # servable stamp — but license is T3
            run_self_check=True,
        )
