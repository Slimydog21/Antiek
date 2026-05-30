"""Tests for the SPR-02 serving-boundary guard (M2).

The guard ``substrate.books.serve_guard.serve_full_text_guarded`` (re-exported
through the ``interfaces.research.api.serve_guard`` shim for the API layer)
composes two independent deny-by-default gates: the content_class gate (the
binding ``substrate.books.serve.serve_full_text``) AND an independent
license-tier cross-check keyed off the immutable arXiv ``<license>`` URI stored
in ``documents.metadata``.

The load-bearing assertion is the SYNTHETIC DRIFT case: a document whose
``content_class`` is servable but whose ``license_uri`` resolves to T3 — the
exact corruption the guard exists to catch — must RAISE ``T3BodyServeError``.
Natural data has no such drift (every arXiv row sits at the gated floor), so
constructing it is the only honest way to exercise the invariant; we construct
it and observe the raise.

The remaining cases prove ZERO regression: a non-arXiv book (no ``license_uri``)
and a normal gated arXiv row both behave EXACTLY as a bare ``serve_full_text``
would — the guard is a transparent pass-through until SPR-04 promotes a body.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.books.serve_guard import (  # noqa: E402
    _tier_for_document,
    serve_full_text_guarded,
)
from runtime.db_lock import connect_read, connect_write  # noqa: E402
from substrate.books.serve import serve_full_text  # noqa: E402
from substrate.constants import (  # noqa: E402
    GATED_DEFAULT_CONTENT_CLASS,
    SOURCE_DECLARED_OPEN_CONTENT_CLASS,
)
from substrate.graph.ops import insert_document  # noqa: E402
from substrate.graph.schema import init_database  # noqa: E402
from substrate.rights import RightsTier, T3BodyServeError  # noqa: E402

# A real arXiv-default (T3, link-back-only) license URI, and a real CC-BY (T1)
# URI — the two endpoints of the rights model the guard cross-checks against.
_T3_LICENSE = "http://arxiv.org/licenses/nonexclusive-distrib/1.0/"
_T1_LICENSE = "http://creativecommons.org/licenses/by/4.0/"
_BODY = "THE FULL PAPER BODY THAT MUST NOT LEAK FOR A T3 PAPER. " * 30

# Sentinel distinguishing "license_uri omitted" (non-arXiv book → no key in
# metadata) from "license_uri passed as None/''" (an arXiv row with an
# absent/blank license, which must still flow through resolve_tier to T3).
_NO_LICENSE = object()


@pytest.fixture
def db(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="antiek-serve-guard-")
    db_path = os.path.join(tmp, "graph.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    con = connect_write(db_path, purpose="serve-guard-test")
    init_database(con)
    con.close()
    return db_path


def _insert(db, document_id, *, content_class, body, license_uri=_NO_LICENSE):
    """Insert a documents row. ``license_uri`` omitted → no ``license_uri`` key
    in metadata (a non-arXiv book); passed → an arXiv-style metadata blob with
    that URI (and a deliberately MISLEADING stored ``rights_tier`` to prove the
    guard re-derives from the URI, not the stored value)."""
    metadata = None
    if license_uri is not _NO_LICENSE:
        metadata = {
            "source": "arxiv_oai_pmh",
            "license_uri": license_uri,
            # A LIE: claim T1 regardless of the real license, so a test that
            # passes can only have done so by re-deriving from license_uri.
            "rights_tier": "T1",
        }
    con = connect_write(db, purpose="setup")
    try:
        insert_document(
            con, document_id=document_id, source_tier=3,
            document_type="academic_paper", title="A Paper", author="Auth",
            raw_text=body, content_class=content_class, metadata=metadata,
        )
    finally:
        con.close()


# ── THE load-bearing negative: synthetic rights drift ───────────────


def test_synthetic_drift_t3_license_with_servable_class_raises(db):
    """THE invariant: a document whose content_class is SERVABLE but whose
    arXiv <license> resolves to T3 is silent rights drift — the cardinal sin —
    and the guard RAISES rather than emitting the body. We CONSTRUCT the drift
    (it does not occur naturally) and observe the raise."""
    _insert(
        db, "doc-drift",
        content_class=SOURCE_DECLARED_OPEN_CONTENT_CLASS,  # gate would serve it
        body=_BODY,
        license_uri=_T3_LICENSE,  # ...but the license says link-back only
    )
    con = connect_read(db)
    try:
        # The bare content_class gate WOULD emit the body — proving the drift is
        # real and the tier arm is what stops it.
        bare = serve_full_text(con, "doc-drift")
        assert bare.full_text is not None and bare.servable is True
        with pytest.raises(T3BodyServeError):
            serve_full_text_guarded(con, "doc-drift")
    finally:
        con.close()


def test_drift_raise_is_independent_of_the_stored_rights_tier(db):
    """The guard re-derives the tier from the raw license_uri, NOT from the
    stored ``rights_tier``. The fixture stores a LYING ``rights_tier='T1'``; the
    guard still raises because the URI resolves to T3. (If it trusted the stored
    value it would wrongly pass.)"""
    _insert(
        db, "doc-lying-tier",
        content_class=SOURCE_DECLARED_OPEN_CONTENT_CLASS, body=_BODY,
        license_uri=_T3_LICENSE,
    )
    con = connect_read(db)
    try:
        meta = json.loads(
            con.execute(
                "SELECT metadata FROM documents WHERE document_id = ?",
                ["doc-lying-tier"],
            ).fetchone()[0]
        )
        assert meta["rights_tier"] == "T1"  # the stored lie
        assert _tier_for_document(con, "doc-lying-tier") is RightsTier.T3_DEFAULT_UNKNOWN
        with pytest.raises(T3BodyServeError):
            serve_full_text_guarded(con, "doc-lying-tier")
    finally:
        con.close()


# ── T1: a genuinely redistributable body is served, no raise ────────


def test_t1_servable_body_served_no_raise(db):
    """A doc with a servable content_class AND a T1 license_uri: the body is
    served and the tier arm passes (T1 is body-servable). No raise."""
    _insert(
        db, "doc-t1",
        content_class=SOURCE_DECLARED_OPEN_CONTENT_CLASS, body=_BODY,
        license_uri=_T1_LICENSE,
    )
    con = connect_read(db)
    try:
        result = serve_full_text_guarded(con, "doc-t1")
        assert result.servable is True
        assert result.full_text == _BODY
        assert _tier_for_document(con, "doc-t1") is RightsTier.T1_REDISTRIBUTABLE
    finally:
        con.close()


# ── Zero regression: non-arXiv book + normal gated arXiv row ─────────


def test_non_arxiv_book_no_license_uri_served_unchanged(db):
    """A non-arXiv servable book (no license_uri in metadata) is served
    identically to a bare serve_full_text — the tier arm is SKIPPED, so there is
    ZERO behavioural change for the existing book corpus."""
    _insert(db, "doc-book", content_class="public_domain", body=_BODY)  # no license_uri
    con = connect_read(db)
    try:
        assert _tier_for_document(con, "doc-book") is None  # tier arm skipped
        guarded = serve_full_text_guarded(con, "doc-book")
        bare = serve_full_text(con, "doc-book")
        assert guarded == bare
        assert guarded.servable is True and guarded.full_text == _BODY
    finally:
        con.close()


def test_normal_gated_arxiv_doc_returns_snippet_no_raise(db):
    """A normal arXiv row at the gated floor (restricted_pending_opt_in) with a
    T3 license: serve_full_text returns full_text=None + a snippet, so NO body is
    emitted, so the tier arm NEVER fires — no raise. This is the common case for
    every arXiv row today; the guard is a transparent pass-through for it."""
    _insert(
        db, "doc-gated-arxiv",
        content_class=GATED_DEFAULT_CONTENT_CLASS, body=_BODY,
        license_uri=_T3_LICENSE,
    )
    con = connect_read(db)
    try:
        result = serve_full_text_guarded(con, "doc-gated-arxiv")
        assert result.full_text is None
        assert result.snippet is not None  # bounded snippet, fair-use regime
        assert result.servable is False
        # The guard returns the SAME object the bare gate would.
        assert result == serve_full_text(con, "doc-gated-arxiv")
    finally:
        con.close()


def test_gated_arxiv_with_t1_license_still_snippet_no_body(db):
    """Defense-in-depth ordering: even with a T1 license, a row still at the
    gated content_class floor emits NO body (content_class gate dominates). The
    guard does not PROMOTE — it only refuses drift. So full_text stays None."""
    _insert(
        db, "doc-gated-t1",
        content_class=GATED_DEFAULT_CONTENT_CLASS, body=_BODY,
        license_uri=_T1_LICENSE,
    )
    con = connect_read(db)
    try:
        result = serve_full_text_guarded(con, "doc-gated-t1")
        assert result.full_text is None and result.snippet is not None
    finally:
        con.close()


# ── _tier_for_document edge cases ───────────────────────────────────


def test_tier_for_unknown_document_is_none(db):
    """No row → tier arm skipped (None), never a raise."""
    con = connect_read(db)
    try:
        assert _tier_for_document(con, "doc-does-not-exist") is None
    finally:
        con.close()


def test_tier_for_document_blank_license_uri_is_t3(db):
    """A present-but-empty license_uri is NOT skipped: it flows through
    resolve_tier, which deny-by-defaults a blank license to T3. A blanked-out
    license is treated as the most restrictive tier, not as 'non-arXiv'."""
    _insert(
        db, "doc-blank-license",
        content_class=SOURCE_DECLARED_OPEN_CONTENT_CLASS, body=_BODY,
        license_uri="   ",
    )
    con = connect_read(db)
    try:
        assert _tier_for_document(con, "doc-blank-license") is RightsTier.T3_DEFAULT_UNKNOWN
        with pytest.raises(T3BodyServeError):
            serve_full_text_guarded(con, "doc-blank-license")
    finally:
        con.close()


def test_tier_for_document_unparseable_metadata_is_none(db):
    """Corrupt (non-JSON) metadata is not a license signal → tier arm skipped
    (None), the content_class gate stands alone. We write a non-JSON metadata
    string directly to force the json.loads failure path."""
    con = connect_write(db, purpose="setup")
    try:
        insert_document(
            con, document_id="doc-corrupt-meta", source_tier=3,
            document_type="academic_paper", title="A Paper",
            raw_text=_BODY, content_class=SOURCE_DECLARED_OPEN_CONTENT_CLASS,
        )
        # Overwrite metadata with a non-JSON blob (bypasses _maybe_json).
        con.execute(
            "UPDATE documents SET metadata = ? WHERE document_id = ?",
            ["{not valid json", "doc-corrupt-meta"],
        )
    finally:
        con.close()
    con = connect_read(db)
    try:
        assert _tier_for_document(con, "doc-corrupt-meta") is None
        # Skipped tier arm → behaves like the bare gate (body served on class).
        assert serve_full_text_guarded(con, "doc-corrupt-meta").servable is True
    finally:
        con.close()
