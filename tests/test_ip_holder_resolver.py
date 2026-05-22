"""IP-holder resolver middleware tests (master-spec §9.6 + §9.10)."""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from middleware.ip_holder_resolver import (
    apply_resolved_ip_holder,
    resolve_and_apply,
    resolve_ip_holder,
)
from runtime.db_lock import connect_write
from substrate.graph.schema import init_database


@pytest.fixture
def db():
    tmpdir = tempfile.mkdtemp(prefix="antiek-ipholder-test-")
    db_path = os.path.join(tmpdir, "test.duckdb")
    con = connect_write(db_path, purpose="ip_holder_test")
    init_database(con)
    yield con
    con.close()


def _seed_holder(
    con, *, ip_holder_id: str, display_name: str,
    isbns=None, domains=None,
) -> None:
    md = {}
    if isbns:
        md["isbns"] = isbns
    if domains:
        md["domains"] = domains
    con.execute(
        """
        INSERT INTO ip_holders (
            ip_holder_id, display_name, legal_contact_email,
            status, escrow_balance_usd, metadata
        ) VALUES (?, ?, '', 'pre_onboarded', 0.0, ?)
        """,
        [ip_holder_id, display_name, json.dumps(md)],
    )


def _seed_document(
    con, *, document_id: str, source_uri="", author="",
) -> None:
    con.execute(
        """
        INSERT INTO documents (
            document_id, source_uri, title, author,
            source_tier, document_type
        ) VALUES (?, ?, '', ?, 3, 'web')
        """,
        [document_id, source_uri, author],
    )


# ── Resolution by ISBN ─────────────────────────────────────────────


def test_resolve_by_isbn_exact_match(db):
    _seed_holder(
        db, ip_holder_id="ip-mit",
        display_name="MIT Press",
        isbns=["9780262035613"],
    )
    resolved = resolve_ip_holder(db, isbn="9780262035613")
    assert resolved == "ip-mit"


def test_resolve_by_isbn_normalizes_hyphens(db):
    _seed_holder(
        db, ip_holder_id="ip-mit", display_name="MIT Press",
        isbns=["9780262035613"],
    )
    # Hyphenated and lowercase → normalized to match.
    resolved = resolve_ip_holder(db, isbn="978-0-262-03561-3")
    assert resolved == "ip-mit"


def test_resolve_by_isbn_no_match_returns_none(db):
    _seed_holder(
        db, ip_holder_id="ip-mit", display_name="MIT Press",
        isbns=["9780262035613"],
    )
    assert resolve_ip_holder(db, isbn="9999999999999") is None


# ── Resolution by domain ───────────────────────────────────────────


def test_resolve_by_domain_exact(db):
    _seed_holder(
        db, ip_holder_id="ip-camb",
        display_name="Cambridge University Press",
        domains=["cambridge.org"],
    )
    resolved = resolve_ip_holder(
        db, source_uri="https://www.cambridge.org/some-paper",
    )
    assert resolved == "ip-camb"


def test_resolve_by_subdomain(db):
    _seed_holder(
        db, ip_holder_id="ip-camb",
        display_name="Cambridge UP",
        domains=["cambridge.org"],
    )
    resolved = resolve_ip_holder(
        db, source_uri="https://press.cambridge.org/x",
    )
    assert resolved == "ip-camb"


def test_resolve_no_domain_match_returns_none(db):
    _seed_holder(
        db, ip_holder_id="ip-camb", display_name="Cambridge",
        domains=["cambridge.org"],
    )
    assert resolve_ip_holder(
        db, source_uri="https://elsevier.com/x",
    ) is None


# ── Resolution by author ───────────────────────────────────────────


def test_resolve_by_author_case_insensitive(db):
    _seed_holder(
        db, ip_holder_id="ip-princeton",
        display_name="Princeton University Press",
    )
    resolved = resolve_ip_holder(
        db, author="princeton university press",
    )
    assert resolved == "ip-princeton"


# ── Resolution order ───────────────────────────────────────────────


def test_isbn_beats_domain(db):
    """When both ISBN and domain match different holders, ISBN wins."""
    _seed_holder(
        db, ip_holder_id="ip-isbn-winner",
        display_name="X", isbns=["9999999999999"],
    )
    _seed_holder(
        db, ip_holder_id="ip-domain-loser",
        display_name="Y", domains=["example.com"],
    )
    resolved = resolve_ip_holder(
        db, isbn="9999999999999",
        source_uri="https://example.com/x",
    )
    assert resolved == "ip-isbn-winner"


def test_no_match_at_all_returns_none(db):
    _seed_holder(
        db, ip_holder_id="ip-x", display_name="X",
        isbns=["1234"], domains=["x.com"],
    )
    assert resolve_ip_holder(
        db,
        isbn="9999", source_uri="https://y.com/", author="Z",
    ) is None


# ── Apply ──────────────────────────────────────────────────────────


def test_apply_persists_ip_holder_id(db):
    _seed_holder(
        db, ip_holder_id="ip-mit", display_name="MIT Press",
    )
    _seed_document(db, document_id="doc-1")
    apply_resolved_ip_holder(
        db, document_id="doc-1", ip_holder_id="ip-mit",
    )
    row = db.execute(
        "SELECT ip_holder_id FROM documents WHERE document_id = 'doc-1'",
    ).fetchone()
    assert row[0] == "ip-mit"


def test_apply_does_not_overwrite_existing(db):
    _seed_holder(db, ip_holder_id="ip-a", display_name="A")
    _seed_holder(db, ip_holder_id="ip-b", display_name="B")
    _seed_document(db, document_id="doc-1")
    apply_resolved_ip_holder(
        db, document_id="doc-1", ip_holder_id="ip-a",
    )
    # Second apply with different holder → no overwrite.
    apply_resolved_ip_holder(
        db, document_id="doc-1", ip_holder_id="ip-b",
    )
    row = db.execute(
        "SELECT ip_holder_id FROM documents WHERE document_id = 'doc-1'",
    ).fetchone()
    assert row[0] == "ip-a"


def test_apply_unknown_document_raises(db):
    with pytest.raises(ValueError, match="not found"):
        apply_resolved_ip_holder(
            db, document_id="doc-ghost", ip_holder_id="ip-x",
        )


def test_resolve_and_apply_end_to_end(db):
    _seed_holder(
        db, ip_holder_id="ip-mit", display_name="MIT Press",
        domains=["mitpress.mit.edu"],
    )
    _seed_document(
        db, document_id="doc-1",
        source_uri="https://mitpress.mit.edu/books/foo",
    )
    resolved = resolve_and_apply(
        db, document_id="doc-1",
        source_uri="https://mitpress.mit.edu/books/foo",
    )
    assert resolved == "ip-mit"


def test_resolve_and_apply_no_match_skips_persist(db):
    _seed_document(db, document_id="doc-1")
    resolved = resolve_and_apply(
        db, document_id="doc-1", source_uri="https://unknown.example/x",
    )
    assert resolved is None
    row = db.execute(
        "SELECT ip_holder_id FROM documents WHERE document_id = 'doc-1'",
    ).fetchone()
    assert row[0] is None
