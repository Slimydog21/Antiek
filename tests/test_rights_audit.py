"""Per-batch rights audit (SPR-02 M5).

``substrate.rights_audit.audit_batch`` asserts two zero-tolerance properties
over a batch's rows and fails the batch on a SINGLE violation:

  (a) zero servable works with a missing/empty license_basis
      (reason ``missing_license_basis``);
  (b) zero gated bodies reachable through the public serve path
      (reason ``gated_body_reachable``).

These tests run it against a clean batch (pass), a batch with a seeded
servable-without-basis row (fail, that id listed), and a batch with a seeded
gated-body-leak (fail, that id listed). The audit VERIFIES through the same
servability projection the gate uses — it does not re-classify.
"""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest

from runtime.db_lock import connect_read, connect_write
from substrate.books import ingest as bingest
from substrate.books.serve import ServeResult, serve_full_text
from substrate.books.servability import ServabilityStatus
from substrate.graph.ops import insert_document
from substrate.rights_audit import (
    REASON_GATED_BODY_REACHABLE,
    REASON_MISSING_LICENSE_BASIS,
    audit_batch,
)


@pytest.fixture()
def db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-rights-audit-")
    db_path = os.path.join(tmpdir, "antiek.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    try:
        from substrate.graph import ensure_initialized

        ensure_initialized(db_path)
        yield db_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _seed(db_path, *, document_id, content_class, raw_text="body text " * 40, license_basis=None):
    with connect_write(db_path, purpose="test:audit-seed") as con:
        insert_document(
            con,
            document_id=document_id,
            source_tier=2,
            document_type="book",
            title=f"Title {document_id}",
            author="Auth",
            raw_text=raw_text,
        )
        bingest.register_book(
            con,
            document_id=document_id,
            content_class=content_class,
            license_basis=license_basis,
        )


# ---------------------------------------------------------------------------
# Clean batch passes
# ---------------------------------------------------------------------------


def test_clean_batch_passes(db):
    """A batch of properly-classified rows (servable with a basis, gated with a
    withheld body) passes with zero violations."""
    _seed(db, document_id="pd-1", content_class="public_domain",
          license_basis="public_domain: US pre-1929")
    _seed(db, document_id="oa-1", content_class="source_declared_open",
          license_basis="CC BY (https://creativecommons.org/licenses/by/4.0/)")
    _seed(db, document_id="gated-1", content_class="restricted_pending_opt_in")

    with connect_read(db) as con:
        result = audit_batch(con, ["pd-1", "oa-1", "gated-1"])

    assert result.passed is True
    assert result.violations == []
    assert result.audited == 3
    assert result.servable == 2
    assert result.gated == 1


def test_unknown_document_id_is_skipped_not_counted(db):
    _seed(db, document_id="pd-2", content_class="public_domain", license_basis="PD")
    with connect_read(db) as con:
        result = audit_batch(con, ["pd-2", "does-not-exist"])
    assert result.audited == 1
    assert result.passed is True


# ---------------------------------------------------------------------------
# Seeded servable-without-basis  (gate: -k missing_basis)
# ---------------------------------------------------------------------------


def test_audit_catches_seeded_servable_missing_basis(db):
    """A servable work registered with NO license_basis fails the batch with
    reason missing_license_basis, and the offending id is listed."""
    _seed(db, document_id="ok-srv", content_class="public_domain",
          license_basis="public_domain: US pre-1929")
    # The seeded defect: servable class, empty basis.
    _seed(db, document_id="bad-no-basis", content_class="public_domain",
          license_basis=None)

    with connect_read(db) as con:
        result = audit_batch(con, ["ok-srv", "bad-no-basis"])

    assert result.passed is False
    assert "bad-no-basis" in result.violation_ids(REASON_MISSING_LICENSE_BASIS)
    assert "ok-srv" not in result.violation_ids()
    violation = next(v for v in result.violations if v.document_id == "bad-no-basis")
    assert violation.reason == REASON_MISSING_LICENSE_BASIS


def test_blank_basis_also_fails_missing_basis(db):
    """A whitespace-only basis is as good as missing — fails the batch."""
    _seed(db, document_id="blank-basis", content_class="opt_in_licensed",
          license_basis="   ")
    with connect_read(db) as con:
        result = audit_batch(con, ["blank-basis"])
    assert result.passed is False
    assert result.violation_ids(REASON_MISSING_LICENSE_BASIS) == ["blank-basis"]


# ---------------------------------------------------------------------------
# Seeded gated-body-leak  (gate: -k gated_leak)
# ---------------------------------------------------------------------------


def test_audit_catches_seeded_gated_leak(db):
    """A gated-by-class work whose body is reachable through the (modelled-as-
    leaky) public serve path fails the batch with reason gated_body_reachable.

    We seed the leak the way a real regression would manifest: the work's
    stored content_class is gated (so servability_of derives GATED), but the
    serve path hands back its full body. The audit derives 'gated' from the
    CLASS independently of the probe, so it catches the disagreement — proving
    the cross-check is genuine, not a tautology over the serve path's own flag.
    """
    _seed(db, document_id="gated-leaky", content_class="restricted_pending_opt_in",
          raw_text="THE WITHHELD BODY " * 50)
    _seed(db, document_id="clean-gated", content_class="restricted_pending_opt_in")

    leaked_body = "THE WITHHELD BODY " * 50

    def leaky_probe(con, document_id: str) -> ServeResult:
        # Model the regression ONLY for the seeded id: a gated work whose serve
        # path wrongly returns full_text. Every other id routes through the real
        # gate, so clean-gated is correctly withheld.
        if document_id == "gated-leaky":
            return ServeResult(
                document_id=document_id, found=True,
                servability=ServabilityStatus.GATED_METADATA_ONLY,
                servable=False,  # the class still says gated...
                full_text=leaked_body,  # ...but the body leaked out
                snippet=None, title="t", author="a", reason="leak",
            )
        return serve_full_text(con, document_id)

    with connect_read(db) as con:
        result = audit_batch(con, ["gated-leaky", "clean-gated"], serve_probe=leaky_probe)

    assert result.passed is False
    assert "gated-leaky" in result.violation_ids(REASON_GATED_BODY_REACHABLE)
    assert "clean-gated" not in result.violation_ids()
    violation = next(v for v in result.violations if v.document_id == "gated-leaky")
    assert violation.reason == REASON_GATED_BODY_REACHABLE


def test_real_serve_path_has_no_gated_leak(db):
    """Belt-and-suspenders: with the REAL serve path (no injected leak), a batch
    of gated works passes — the production gate does not leak."""
    _seed(db, document_id="g-a", content_class="restricted_pending_opt_in")
    _seed(db, document_id="g-b", content_class="restricted_pending_opt_in")
    with connect_read(db) as con:
        result = audit_batch(con, ["g-a", "g-b"])  # real serve_full_text
    assert result.passed is True
    assert result.gated == 2


# ---------------------------------------------------------------------------
# Both defects in one batch — a single violation of either fails it
# ---------------------------------------------------------------------------


def test_both_defects_listed_separately(db):
    _seed(db, document_id="srv-nobasis", content_class="public_domain", license_basis=None)
    _seed(db, document_id="g-leak", content_class="restricted_pending_opt_in",
          raw_text="LEAK BODY " * 30)

    def leaky_probe(con, document_id: str):
        if document_id == "g-leak":
            return ServeResult(
                document_id=document_id, found=True,
                servability=ServabilityStatus.GATED_METADATA_ONLY,
                servable=False, full_text="LEAK BODY " * 30, snippet=None,
                title="t", author="a", reason="leak",
            )
        return serve_full_text(con, document_id)

    with connect_read(db) as con:
        result = audit_batch(con, ["srv-nobasis", "g-leak"], serve_probe=leaky_probe)

    assert result.passed is False
    assert result.violation_ids(REASON_MISSING_LICENSE_BASIS) == ["srv-nobasis"]
    assert result.violation_ids(REASON_GATED_BODY_REACHABLE) == ["g-leak"]
    assert len(result.violations) == 2


def test_audit_does_not_reclassify_only_verifies(db):
    """The audit reads the stored class + serves through the gate; it never
    assigns a content_class. A gated work stays gated after an audit run."""
    _seed(db, document_id="verify-only", content_class="restricted_pending_opt_in")
    with connect_read(db) as con:
        audit_batch(con, ["verify-only"])
        cc = con.execute(
            "SELECT content_class FROM documents WHERE document_id=?", ["verify-only"]
        ).fetchone()[0]
    assert cc == "restricted_pending_opt_in"
