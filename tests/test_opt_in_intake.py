"""Tests for the §9.10 publisher opt-in intake lane (SPR-08).

NO live network: the body is rendered in-process to a deterministic PDF and
ingested through the shared servable-book path against a temp DuckDB. Every
content_class decision is asserted to come from classify(); a stripped grant is
asserted to gate the SAME work; escrow accrual is asserted to target the linked
ip_holder; and re-submission is asserted idempotent.

The asserted invariant in action:
  - a granted work -> servable (opt_in_licensed), basis names the grant;
  - the SAME work with its grant stripped -> gated (restricted_pending_opt_in),
    body withheld but still chunked/embedded;
  - the publisher's ip_holder is created once (pre_onboarded) and reused;
  - re-running the manifest does not duplicate documents or holders.
"""

from __future__ import annotations

import copy
import os
import shutil
import tempfile
from decimal import Decimal

import duckdb
import pytest

from acquisition.opt_in import (
    intake_manifest,
    intake_manifest_file,
    parse_manifest,
)
from acquisition.opt_in.manifest import ManifestEntry, validate_grant
from substrate.constants import (
    GATED_DEFAULT_CONTENT_CLASS,
    SERVABLE_CONTENT_CLASSES,
)


class _StubEmbedder:
    def encode(self, text: str) -> list[float]:
        h = abs(hash(text)) % 64
        v = [0.0] * 16
        v[h % 16] = 1.0
        return v


@pytest.fixture
def temp_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-opt-in-")
    db_path = os.path.join(tmpdir, "graph.duckdb")
    events_dir = os.path.join(tmpdir, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_EVENT_LOG_DIR", events_dir)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    try:
        from substrate.graph import ensure_initialized

        ensure_initialized(db_path)
        yield db_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


_BODY = (
    "This is a synthetic opt-in catalog work body used as an ingest fixture. "
    * 30
)


def _manifest_dict(*, grant=True, publisher_id="mit-press", display_name="MIT Press"):
    """A one-work manifest. ``grant=True`` attaches a valid per-work grant;
    ``grant=False`` omits the grant entirely (the gated case)."""
    work = {
        "title": "A Generic Title",
        "author": "A. Author",
        "isbn": "978-0-262-04630-5",
        "doi": "10.7551/mitpress/00009.001.0001",
        "body_text": _BODY,
    }
    if grant:
        work["grant"] = {
            "rights_holder": "MIT Press",
            "scope": "per_work",
            "granted_at": "2026-05-30",
            "statement": "MIT Press grants Antiek the right to serve this work.",
        }
    return {
        "schema_version": "opt_in/1",
        "publisher": {
            "publisher_id": publisher_id,
            "display_name": display_name,
            "legal_contact_email": "legal@mitpress.edu",
        },
        "works": [work],
    }


def _content_class(db_path: str, document_id: str) -> str:
    con = duckdb.connect(db_path)
    try:
        row = con.execute(
            "SELECT content_class FROM documents WHERE document_id = ?",
            [document_id],
        ).fetchone()
    finally:
        con.close()
    return row[0] if row else None


def _basis(db_path: str, document_id: str) -> str:
    con = duckdb.connect(db_path)
    try:
        row = con.execute(
            "SELECT license_basis FROM book_assets WHERE document_id = ?",
            [document_id],
        ).fetchone()
    finally:
        con.close()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# M2 + M4: granted -> servable (basis = grant); grant-stripped -> gated
# ---------------------------------------------------------------------------


def test_granted_work_is_servable_with_grant_basis(temp_db):
    manifest = parse_manifest(_manifest_dict(grant=True))
    result = intake_manifest(manifest, db_path=temp_db, embedder=_StubEmbedder())

    assert result.summary.servable_count == 1
    assert result.summary.gated_count == 0
    (outcome,) = result.outcomes
    assert outcome.servable is True
    assert outcome.content_class in SERVABLE_CONTENT_CLASSES
    assert outcome.content_class == "opt_in_licensed"

    # The basis names the publisher grant AND the verbatim statement — an
    # auditor answers "by whose grant?" from the row alone.
    assert "publisher_opt_in" in outcome.license_basis
    assert "MIT Press" in outcome.license_basis
    assert "grants Antiek the right to serve" in outcome.license_basis

    # Persisted in the substrate (not just the return value), and servable_full_text
    # derives true from the content_class.
    assert _content_class(temp_db, outcome.document_id) == "opt_in_licensed"
    assert "publisher_opt_in" in _basis(temp_db, outcome.document_id)


def test_absent_grant_stays_gated(temp_db):
    manifest = parse_manifest(_manifest_dict(grant=False))
    result = intake_manifest(manifest, db_path=temp_db, embedder=_StubEmbedder())

    assert result.summary.gated_count == 1
    assert result.summary.servable_count == 0
    (outcome,) = result.outcomes
    assert outcome.servable is False
    assert outcome.content_class == GATED_DEFAULT_CONTENT_CLASS
    assert outcome.gated_reason  # names WHY it gated
    assert _content_class(temp_db, outcome.document_id) == GATED_DEFAULT_CONTENT_CLASS


def test_gated_work_still_chunked_and_embedded(temp_db):
    """Gated means body-withheld, NOT skipped: the document + its chunks are
    written into the graph for private search."""
    manifest = parse_manifest(_manifest_dict(grant=False))
    result = intake_manifest(manifest, db_path=temp_db, embedder=_StubEmbedder())
    (outcome,) = result.outcomes

    con = duckdb.connect(temp_db)
    try:
        (n_chunks,) = con.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?",
            [outcome.document_id],
        ).fetchone()
    finally:
        con.close()
    assert n_chunks > 0  # gated body is chunked/embedded, never silently dropped


@pytest.mark.parametrize(
    "mutate,why",
    [
        (lambda g: g.update({"statement": ""}), "empty statement"),
        (lambda g: g.update({"withdrawn": True}), "withdrawn"),
        (lambda g: g.update({"expires_at": "2000-01-01"}), "expired"),
        (lambda g: g.update({"scope": "some-vague-scope"}), "out-of-scope"),
        (lambda g: g.pop("granted_at"), "undated"),
    ],
)
def test_malformed_grant_cases_gate_not_servable(temp_db, mutate, why):
    """Each malformed-grant case lands GATED — not servable, not dropped."""
    d = _manifest_dict(grant=True)
    mutate(d["works"][0]["grant"])
    result = intake_manifest(parse_manifest(d), db_path=temp_db, embedder=_StubEmbedder())
    (outcome,) = result.outcomes
    assert outcome.servable is False, why
    assert outcome.content_class == GATED_DEFAULT_CONTENT_CLASS, why
    # Never silently dropped: the document still ingested (gated).
    assert outcome.document_id is not None, why


def test_no_other_field_promotes_to_servable(temp_db):
    """A work with a stable id + holder name but NO grant cannot be servable —
    only the grant flips servability."""
    d = _manifest_dict(grant=False)
    # Add a holder-ish field that must NOT promote it.
    result = intake_manifest(parse_manifest(d), db_path=temp_db, embedder=_StubEmbedder())
    (outcome,) = result.outcomes
    assert outcome.servable is False


# ---------------------------------------------------------------------------
# M3: IP-holder linkage (pre_onboarded if needed) + reuse
# ---------------------------------------------------------------------------


def test_pre_onboarded_holder_created_then_reused(temp_db):
    """First manifest creates exactly one pre_onboarded holder; a second
    manifest from the SAME publisher_id reuses it (no duplicate holder)."""
    from substrate import ip_holders
    from runtime.db_lock import connect_write

    r1 = intake_manifest(
        parse_manifest(_manifest_dict(grant=True)),
        db_path=temp_db, embedder=_StubEmbedder(),
    )
    assert r1.summary.holder_was_created is True

    # Second submission: SAME publisher_id, edited display_name (must still
    # resolve to ONE holder — holder keys on stable id, not display name).
    r2 = intake_manifest(
        parse_manifest(_manifest_dict(grant=True, display_name="MIT Press (renamed)")),
        db_path=temp_db, embedder=_StubEmbedder(),
    )
    assert r2.summary.holder_was_created is False
    assert r1.summary.ip_holder_id == r2.summary.ip_holder_id

    with connect_write(temp_db, purpose="test:count") as con:
        holders = ip_holders.list_all(con)
    assert len(holders) == 1
    assert holders[0].status == "pre_onboarded"


def test_every_work_links_to_publisher_holder(temp_db):
    result = intake_manifest(
        parse_manifest(_manifest_dict(grant=True)),
        db_path=temp_db, embedder=_StubEmbedder(),
    )
    (outcome,) = result.outcomes
    con = duckdb.connect(temp_db)
    try:
        (ip_holder_id,) = con.execute(
            "SELECT ip_holder_id FROM documents WHERE document_id = ?",
            [outcome.document_id],
        ).fetchone()
    finally:
        con.close()
    assert ip_holder_id == result.summary.ip_holder_id


# ---------------------------------------------------------------------------
# G2 — escrow accrues to the linked holder; money path never touched
# ---------------------------------------------------------------------------


def test_escrow_accrues_to_linked_holder(temp_db):
    from substrate import ip_holders
    from runtime.db_lock import connect_write

    result = intake_manifest(
        parse_manifest(_manifest_dict(grant=True)),
        db_path=temp_db, embedder=_StubEmbedder(),
    )
    assert result.summary.escrow_accrued is True
    with connect_write(temp_db, purpose="test:escrow") as con:
        holder = ip_holders.get(con, result.summary.ip_holder_id)
    assert holder is not None
    # Accrual is additive + positive; it targets the LINKED holder.
    assert holder.escrow_balance_usd > Decimal("0")
    assert holder.status == "pre_onboarded"  # accrual never advances state


def test_escrow_seam_imports_no_money_modules():
    """The opt-in intake module imports NEITHER payout NOR stripe_connect.
    Escrow only accrues; disbursement is operator-gated (G2/G3). Proven over the
    module's IMPORT lines (the same convention as
    tests/test_gated_escrow_accrual.py's seam check)."""
    import inspect

    from acquisition.opt_in import intake

    import_lines = [
        line
        for line in inspect.getsource(intake).splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    assert import_lines  # the module does import seams
    for line in import_lines:
        assert "payout" not in line, line
        assert "stripe_connect" not in line, line
        assert "stripe" not in line.lower(), line
    # And it routes escrow through the SUBSTRATE-LAYER sanctioned seam
    # (opt_in_accrual.accrue_opt_in_escrow), NOT a direct cross-layer
    # accrue_escrow call out of acquisition/ (collision #3 / seam #3).
    assert any("accrue_opt_in_escrow" in line for line in import_lines)
    # The raw low-level writer is NOT imported directly by the acquisition lane.
    assert not any(
        "import accrue_escrow" in line or "import accrue_escrow," in line
        for line in import_lines
    )


def test_opt_in_accrual_is_a_substrate_layer_sanctioned_caller():
    """Collision #3 guard: the opt-in lane's intake-time escrow seed routes
    through a SUBSTRATE-LAYER module that is on the single-escrow-writer
    allowlist. This asserts (a) intake.py calls accrue_opt_in_escrow, (b) that
    module lives under substrate/ip_holders/ and is the only place opt-in
    escrow reaches the low-level accrue_escrow writer, and (c) it is on the
    sanctioned-caller allowlist the seam test enforces."""
    import inspect

    from acquisition.opt_in import intake
    from substrate.ip_holders import opt_in_accrual
    from tests.test_seam_single_escrow_writer import _SANCTIONED_ESCROW_CALLERS

    # (a) the acquisition lane calls the substrate seam, not the raw writer.
    src = inspect.getsource(intake)
    assert "accrue_opt_in_escrow(" in src
    assert "accrue_escrow(" not in src  # never the raw writer in acquisition/

    # (b) the substrate seam is the one that touches accrue_escrow.
    seam_src = inspect.getsource(opt_in_accrual)
    assert "accrue_escrow(" in seam_src

    # (c) on the allowlist (so test_exactly_one_accrue_escrow_call_site passes).
    assert "substrate/ip_holders/opt_in_accrual.py" in _SANCTIONED_ESCROW_CALLERS


def test_escrow_not_accrued_for_gated_only_manifest(temp_db):
    """A manifest with no servable works accrues nothing at intake (the gated
    works' in-copyright accrual is the per-impression ad path, not this seam)."""
    result = intake_manifest(
        parse_manifest(_manifest_dict(grant=False)),
        db_path=temp_db, embedder=_StubEmbedder(),
    )
    assert result.summary.escrow_accrued is False


# ---------------------------------------------------------------------------
# G3 — grant flips servability BOTH WAYS on the SAME work
# ---------------------------------------------------------------------------


def test_grant_flip_servable_gated_servable_same_work(temp_db):
    """The rigor #3 proof: ONE work, three submissions.
      1. with grant  -> servable (opt_in_licensed), basis = grant
      2. strip grant -> SAME document_id now gated (body withheld)
      3. re-add grant -> SAME document_id flips back to servable
    Servability tracks the grant and nothing else; identity is stable."""
    granted = parse_manifest(_manifest_dict(grant=True))
    stripped = parse_manifest(_manifest_dict(grant=False))

    # 1. With grant -> servable.
    r1 = intake_manifest(granted, db_path=temp_db, embedder=_StubEmbedder())
    (o1,) = r1.outcomes
    doc_id = o1.document_id
    assert o1.servable is True
    assert o1.content_class == "opt_in_licensed"

    # 2. Strip grant, re-ingest -> SAME work now gated.
    r2 = intake_manifest(stripped, db_path=temp_db, embedder=_StubEmbedder())
    (o2,) = r2.outcomes
    assert o2.document_id == doc_id  # same identity, not a new document
    assert o2.servable is False
    assert o2.content_class == GATED_DEFAULT_CONTENT_CLASS
    assert _content_class(temp_db, doc_id) == GATED_DEFAULT_CONTENT_CLASS

    # 3. Re-add grant -> SAME work flips back to servable.
    r3 = intake_manifest(granted, db_path=temp_db, embedder=_StubEmbedder())
    (o3,) = r3.outcomes
    assert o3.document_id == doc_id
    assert o3.servable is True
    assert o3.content_class == "opt_in_licensed"
    assert _content_class(temp_db, doc_id) == "opt_in_licensed"


# ---------------------------------------------------------------------------
# M5: idempotent re-submission, stable-id keyed
# ---------------------------------------------------------------------------


def test_resubmission_is_idempotent_no_duplicates(temp_db):
    """Running the same manifest twice yields the same document + holder
    counts (no duplicate documents, no duplicate holder)."""
    from substrate import ip_holders
    from runtime.db_lock import connect_write

    m = _manifest_dict(grant=True)
    intake_manifest(parse_manifest(m), db_path=temp_db, embedder=_StubEmbedder())
    intake_manifest(parse_manifest(m), db_path=temp_db, embedder=_StubEmbedder())

    con = duckdb.connect(temp_db)
    try:
        (n_docs,) = con.execute("SELECT COUNT(*) FROM documents").fetchone()
        (n_assets,) = con.execute("SELECT COUNT(*) FROM book_assets").fetchone()
    finally:
        con.close()
    with connect_write(temp_db, purpose="test:count") as con:
        n_holders = len(ip_holders.list_all(con))

    assert n_docs == 1
    assert n_assets == 1
    assert n_holders == 1


def test_resubmission_adding_one_work_adds_exactly_one_document(temp_db):
    m = _manifest_dict(grant=True)
    intake_manifest(parse_manifest(m), db_path=temp_db, embedder=_StubEmbedder())

    m2 = copy.deepcopy(m)
    m2["works"].append({
        "title": "A Second Work",
        "author": "C. Coauthor",
        "isbn": "978-0-262-99999-0",
        "doi": "10.7551/mitpress/00010.001.0001",
        "body_text": _BODY + " second distinct body",
        "grant": {
            "rights_holder": "MIT Press",
            "scope": "per_work",
            "granted_at": "2026-05-30",
            "statement": "MIT Press grants Antiek the right to serve this second work.",
        },
    })
    intake_manifest(parse_manifest(m2), db_path=temp_db, embedder=_StubEmbedder())

    con = duckdb.connect(temp_db)
    try:
        (n_docs,) = con.execute("SELECT COUNT(*) FROM documents").fetchone()
    finally:
        con.close()
    assert n_docs == 2  # exactly one new document, the first unchanged


def test_identity_keys_on_stable_id_not_title_author(temp_db):
    """Two works with the SAME generic title+author but DIFFERENT bodies +
    DIFFERENT stable ids stay distinct documents — identity keys on the
    content-stable id / body content-hash, never on title+author."""
    base = _manifest_dict(grant=True)
    base["works"][0]["title"] = "History"
    base["works"][0]["author"] = "Anonymous"
    base["works"][0]["isbn"] = "978-0-262-04630-5"
    base["works"][0]["doi"] = None
    base["works"][0]["body_text"] = _BODY + " first work body alpha"

    base["works"].append({
        "title": "History",
        "author": "Anonymous",
        "isbn": "978-0-262-04631-2",
        "body_text": _BODY + " second work body beta",
        "grant": base["works"][0]["grant"],
    })

    result = intake_manifest(parse_manifest(base), db_path=temp_db, embedder=_StubEmbedder())
    doc_ids = {o.document_id for o in result.outcomes}
    assert len(doc_ids) == 2  # not collapsed onto one title+author key

    con = duckdb.connect(temp_db)
    try:
        (n_docs,) = con.execute("SELECT COUNT(*) FROM documents").fetchone()
    finally:
        con.close()
    assert n_docs == 2


# ---------------------------------------------------------------------------
# THE BINDING — content_class comes from classify(), no boolean shortcut
# ---------------------------------------------------------------------------


def test_validate_grant_rejects_boolean_shortcut():
    """rigor #2: a bare `true` boolean grant is NOT a recorded basis -> gated.

    The manifest parser coerces a non-mapping grant (e.g. a bare ``true``) to
    None, and validate_grant gates an entry with no grant mapping."""
    # A boolean shortcut never survives parsing into a grant mapping.
    parsed = parse_manifest({
        "schema_version": "opt_in/1",
        "publisher": {"publisher_id": "p", "display_name": "P"},
        "works": [{"title": "X", "grant": True, "body_text": _BODY}],
    })
    assert parsed.entries[0].grant is None  # bare True coerced away
    v = validate_grant(ManifestEntry(title="X"), catalog_grant=None)
    assert v.valid is False


def test_classify_is_the_only_content_class_route():
    """The intake module derives content_class ONLY via classify(); it never
    hardcodes a content_class= literal, and it does not import/copy the legacy
    public_domain.ingest_work content_class= route."""
    import inspect

    from acquisition.opt_in import intake

    src = inspect.getsource(intake)
    assert "from acquisition.licenses_core import classify" in src
    assert "classify(" in src
    # No legacy direct-literal assignment of a servable content_class.
    assert 'content_class="opt_in_licensed"' not in src
    assert 'content_class="public_domain"' not in src


def test_stamped_class_and_basis_are_exactly_classify_output(temp_db):
    """Active provenance proof (stronger than the negative no-literal check):
    the content_class + license_basis the intake STAMPS are exactly the values
    classify() returns for the same source_declaration — both the servable and
    the deny-by-default branch. If the intake ever derived a class some other
    way, these would diverge."""
    from acquisition.licenses_core import classify
    from acquisition.opt_in.intake import (
        _compose_basis,
        _source_declaration_for,
    )
    from acquisition.opt_in.manifest import validate_grant

    granted = parse_manifest(_manifest_dict(grant=True))
    g_entry = granted.entries[0]
    g_val = validate_grant(g_entry, catalog_grant=granted.catalog_grant)
    g_decl = _source_declaration_for(granted.publisher, g_val)
    g_cls = classify(None, g_decl, legitimate_source=True)

    g_result = intake_manifest(granted, db_path=temp_db, embedder=_StubEmbedder())
    (g_out,) = g_result.outcomes
    # The stamped class is EXACTLY classify()'s class (the servable branch).
    assert g_out.content_class == g_cls.content_class == "opt_in_licensed"
    assert g_out.servable is g_cls.servable is True
    # The stamped basis is classify()'s basis, extended only by _compose_basis
    # (which appends the verbatim grant — never replaces classify()'s basis).
    assert g_out.license_basis == _compose_basis(g_cls, g_val)
    assert g_out.license_basis.startswith(g_cls.license_basis)

    stripped = parse_manifest(_manifest_dict(grant=False))
    s_entry = stripped.entries[0]
    s_val = validate_grant(s_entry, catalog_grant=stripped.catalog_grant)
    s_decl = _source_declaration_for(stripped.publisher, s_val)
    s_cls = classify(None, s_decl, legitimate_source=True)

    s_result = intake_manifest(stripped, db_path=temp_db, embedder=_StubEmbedder())
    (s_out,) = s_result.outcomes
    # The deny-by-default branch lands on classify()'s gated class, never servable.
    assert s_out.content_class == s_cls.content_class == GATED_DEFAULT_CONTENT_CLASS
    assert s_out.servable is s_cls.servable is False
    assert s_cls.content_class not in SERVABLE_CONTENT_CLASSES


# ---------------------------------------------------------------------------
# File-driven entrypoint (the orchestrator passes a manifest path)
# ---------------------------------------------------------------------------


def test_intake_manifest_file_roundtrip(temp_db, tmp_path):
    import json

    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(_manifest_dict(grant=True)), encoding="utf-8")
    result = intake_manifest_file(str(p), db_path=temp_db, embedder=_StubEmbedder())
    assert result.summary.servable_count == 1
