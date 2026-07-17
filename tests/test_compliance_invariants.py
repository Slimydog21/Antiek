"""SPR-09 M2 — the compliance invariants for the serve boundary.

Three mechanically-checkable invariants, each shipped with a red-then-green
demonstration (rigor #3 — a test that FAILS on a violating change and PASSES
once guarded):

1. **The licenses_core coupling test (the deferred SPR-02 task).** The
   body-servable CEILING (``substrate.rights.body_servable`` /
   ``_BODY_SERVABLE_TIERS``) is coupled to
   ``acquisition.licenses_core.CC_LICENSE_ROWS`` redistributable booleans, not
   pinned to a hand-written literal ``{T1}``. Two coupling forms ship together:
     * SET form — the body-servable TIER SET equals the set derived from the
       redistributable rows. Catches widening ``_BODY_SERVABLE_TIERS`` and
       demoting ALL redistributable rows at once. (Honest limitation: it does NOT
       catch a single-row flip, because the resolver aliases every redistributable
       row to T1 and {T1} is already the ceiling.)
     * PER-LICENSE form — for EVERY CC row,
       ``body_servable(resolve_tier(row.match)) == row.redistributable``. This
       bites a SINGLE-license drift in BOTH directions between the RESOLVER TABLE
       the serve path reads and the canonical redistributable flags (a CC-BY-NC
       promotion-drift, or a CC-BY demotion-drift), which the set form cannot.
   HONEST LIMITATION: neither form bites a FULLY-CONSISTENT edit of the canonical
   table (flip a row's ``redistributable`` AND let the resolver re-derive from it —
   they move in lockstep because ``resolve_tier`` derives T1 purely from that
   flag). What is mechanically defended is (i) the serve ceiling
   ``_BODY_SERVABLE_TIERS`` staying coupled to the redistributable-derived tiers,
   and (ii) the resolver table the serve path reads staying coherent with the
   canonical flags. A deliberate, self-consistent legal re-determination is an
   operator/counsel decision, not a drift this lint can or should catch.

2. **The link-back invariant.** ``serve_full_text_guarded`` REFUSES (raises
   ``LinkBackMissingError``) when it would emit a body for an arXiv document
   (tier resolved) WITHOUT a ``canonical_url``. A non-arXiv doc (tier None) is
   unconstrained.

3. **The raw-body-read scanner.** ``tools/lint/serve_invariants_check.py`` reds
   a NEW SQL read of ``documents.raw_text`` (the materialized body) outside the
   serve gate — invoked programmatically here (clean on the tree) and proven to
   have teeth against an injected violation.

4. **The retrieval-gate drift scanner.** ``tools/lint/retrieval_gate_check.py``
   reds a RESTRICTED-only chunk-gate reimplementation on the VSS substrate and
   ``GET /chunks`` surfaces — invoked programmatically here (clean on the tree)
   and proven to have teeth against an injected violation.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.licenses_core import CC_LICENSE_ROWS  # noqa: E402
from runtime.db_lock import connect_read, connect_write  # noqa: E402
from substrate.books.serve import serve_full_text  # noqa: E402
from substrate.books.serve_guard import (  # noqa: E402
    LinkBackMissingError,
    serve_full_text_guarded,
)
from substrate.constants import (  # noqa: E402
    GATED_DEFAULT_CONTENT_CLASS,
    SOURCE_DECLARED_OPEN_CONTENT_CLASS,
)
from substrate.graph.schema import init_database  # noqa: E402
from substrate.rights import RightsTier, body_servable, resolve_tier  # noqa: E402
from tools.lint import retrieval_gate_check, serve_invariants_check  # noqa: E402

_T1_LICENSE = "http://creativecommons.org/licenses/by/4.0/"
_T3_LICENSE = "http://arxiv.org/licenses/nonexclusive-distrib/1.0/"
_BODY = "THE FULL PAPER BODY. " * 30


# ════════════════════════════════════════════════════════════════════
# 1. licenses_core coupling — the ceiling is DERIVED, not literal
# ════════════════════════════════════════════════════════════════════


def _derived_body_servable_ceiling(rows=CC_LICENSE_ROWS) -> set[RightsTier]:
    """The body-servable ceiling DERIVED from the canonical legal table: the set
    of tiers that the redistributable CC rows resolve to. Each ``LicenseRow.match``
    is a license-URI fragment that ``resolve_tier`` (via the licenses_core
    resolver, substring first-match) resolves to that row — so feeding the
    fragment back through ``resolve_tier`` yields the tier that row implies. The
    body-servable ceiling MUST equal exactly the tiers whose CC rows are
    redistributable.

    ``rows`` defaults to the live ``CC_LICENSE_ROWS`` (production). A red-control
    may pass a demoted clone, but it must ALSO patch the resolver's table so the
    filter flag and ``resolve_tier`` read consistent data (see the red-control)."""
    return {resolve_tier(row.match) for row in rows if row.redistributable}


def test_body_servable_ceiling_is_derived_from_licenses_core_redistributable():
    """COUPLING (set form): the body-servable TIER SET equals the set DERIVED from
    CC_LICENSE_ROWS.redistributable — NOT a hand-written literal.

    HONEST SCOPE (round-2): this set-equality form catches exactly two violation
    classes — (a) widening ``_BODY_SERVABLE_TIERS`` (e.g. ->{T1,T2}) with no
    legal-table change, and (b) demoting ALL the redistributable CC rows at once
    (the derived set empties). It does NOT catch a SINGLE-row redistributable flip
    (because the resolver collapses every redistributable row to T1, and {T1} is
    already the ceiling, so one row moving leaves the set unchanged). The
    SINGLE-ROW flip — in BOTH directions — is caught by the stronger PER-LICENSE
    coupling test below
    (``test_per_license_servability_matches_redistributable_flag`` + its two
    red-controls). The two tests together make a redistributable-flag edit that
    the serve predicate does not track go red."""
    actual = {t for t in RightsTier if body_servable(t)}
    derived = _derived_body_servable_ceiling()
    assert actual == derived, (
        f"body-servable ceiling {actual} disagrees with the ceiling derived from "
        f"CC_LICENSE_ROWS.redistributable {derived} — the legal table and the "
        f"serve predicate have drifted"
    )
    # Sanity: on the current commercial surface both resolve to exactly {T1}.
    assert actual == {RightsTier.T1_REDISTRIBUTABLE}


# ── PER-LICENSE coupling: bites a SINGLE-row redistributable flip both ways ──


def test_per_license_servability_matches_redistributable_flag():
    """COUPLING (per-license form) — the serve predicate's verdict on each CC
    license must match that license's canonical redistributable intent.

    For EVERY canonical ``CC_LICENSE_ROWS`` row, the serve predicate's verdict on
    that license (``body_servable(resolve_tier(row.match))``) MUST equal the legal
    table's ``row.redistributable`` flag. This per-license form catches a SINGLE
    license drifting — specifically a drift in the RESOLVER TABLE the serve path
    consults (``acquisition.arxiv.licenses._LICENSE_TABLE``, which the resolver
    reads) relative to the canonical ``CC_LICENSE_ROWS`` redistributable intent:
    e.g. a row reordering that lets a CC-BY-NC URI match a redistributable row
    (promotion), or a CC-BY row losing its redistributable resolution (demotion).
    Each such drift reds for exactly the affected license, where the set-equality
    test cannot react (the resolver aliases every redistributable row to T1, so a
    single license moving leaves the {T1} set unchanged). See the two red-controls.

    HONEST SCOPE: this does NOT bite a FULLY-CONSISTENT edit of the canonical
    table — flipping a row's ``redistributable`` bool AND letting the resolver
    re-derive from it moves ``resolve_tier`` and ``body_servable`` in lockstep with
    the flag (``resolve_tier`` derives T1 purely FROM ``resolution.redistributable``,
    so ``body_servable(resolve_tier(x)) == row.redistributable`` holds by
    construction for a self-consistent table). What it protects is the COHERENCE of
    the resolver table the serve path actually reads with the canonical
    redistributable flags — a real, catchable drift class. The serve-ceiling-vs-
    table drift (widening ``_BODY_SERVABLE_TIERS``) is covered by the set test
    above + the red-control below."""
    for row in CC_LICENSE_ROWS:
        servable = body_servable(resolve_tier(row.match))
        assert servable == row.redistributable, (
            f"per-license coupling broke for {row.license_name} "
            f"(match={row.match!r}): body_servable(resolve_tier(...)) -> "
            f"{servable} but CC_LICENSE_ROWS.redistributable -> "
            f"{row.redistributable}. The resolver table the serve path reads and "
            f"the canonical legal flags disagree on whether this license is "
            f"body-servable."
        )


def test_red_control_resolver_promotes_cc_by_nc_reds_the_per_license_coupling(monkeypatch):
    """RED control (resolver-table PROMOTION drift, single row) — make the resolver
    table the serve path reads resolve CC-BY-NC as redistributable while the
    canonical ``CC_LICENSE_ROWS`` flag stays False (e.g. a careless reorder/edit of
    ``_LICENSE_TABLE`` that doesn't touch the canonical CC flag).
    ``resolve_tier('by-nc')`` then returns T1 (``body_servable`` True), but the
    canonical CC-BY-NC flag is False -> the per-license assertion fails for that
    row. This is the direction the set-equality test cannot catch (the {T1} set is
    unchanged)."""
    import dataclasses

    import acquisition.arxiv.licenses as lic

    promoted_table = tuple(
        dataclasses.replace(row, redistributable=True)
        if "by-nc" in row.match
        else row
        for row in lic._LICENSE_TABLE
    )
    monkeypatch.setattr(lic, "_LICENSE_TABLE", promoted_table)

    nc_row = next(r for r in CC_LICENSE_ROWS if r.match.endswith("by-nc"))
    assert body_servable(resolve_tier(nc_row.match)) is True  # resolver promoted it
    assert nc_row.redistributable is False  # canonical flag is still False
    desynced = body_servable(resolve_tier(nc_row.match)) != nc_row.redistributable
    assert desynced, (
        "RED control: a resolver-table promotion of CC-BY-NC while the canonical "
        "redistributable flag stays False should desync the per-license coupling; "
        "if it stays consistent the coupling has no teeth on a promotion drift"
    )


def test_red_control_resolver_demotes_cc_by_reds_the_per_license_coupling(monkeypatch):
    """RED control (resolver-table DEMOTION drift, single row) — make the resolver
    table resolve a single CC-BY URI as non-redistributable while the canonical
    flag stays True. ``resolve_tier('.../by')`` then -> T3 (``body_servable``
    False), but the canonical CC-BY flag is True -> the per-license assertion fails
    for that row. Proves teeth on a single-row demotion drift too — the set test
    would need ALL redistributable rows demoted to react; this needs only one."""
    import dataclasses

    import acquisition.arxiv.licenses as lic
    from substrate.constants import GATED_DEFAULT_CONTENT_CLASS

    # Demote ONLY the bare CC-BY row (match == '.../licenses/by') in the resolver
    # table; leave CC-BY-SA ('.../by-sa') and CC0 redistributable, so the
    # set-equality test would NOT react but the per-license one does.
    def _is_bare_by(row) -> bool:
        return row.match.endswith("/licenses/by")

    demoted_table = tuple(
        dataclasses.replace(
            row, redistributable=False, content_class=GATED_DEFAULT_CONTENT_CLASS
        )
        if _is_bare_by(row)
        else row
        for row in lic._LICENSE_TABLE
    )
    monkeypatch.setattr(lic, "_LICENSE_TABLE", demoted_table)

    by_row = next(r for r in CC_LICENSE_ROWS if r.match.endswith("/licenses/by"))
    assert body_servable(resolve_tier(by_row.match)) is False  # resolver demoted it
    assert by_row.redistributable is True  # canonical flag still True
    desynced = body_servable(resolve_tier(by_row.match)) != by_row.redistributable
    assert desynced, (
        "RED control: a resolver-table demotion of CC-BY while its canonical "
        "redistributable flag stays True should desync the per-license coupling"
    )
    # The SET-equality test stays green under this single-row demotion (CC-BY-SA +
    # CC0 still resolve T1), which is exactly why the per-license form is needed.
    actual = {t for t in RightsTier if body_servable(t)}
    assert actual == {RightsTier.T1_REDISTRIBUTABLE}, (
        "single-row CC-BY demotion should NOT empty the body-servable set "
        "(CC-BY-SA/CC0 keep T1) — confirming the set-equality test cannot catch "
        "this single-row drift, so the per-license test is load-bearing"
    )


def test_red_control_demoting_a_redistributable_row_breaks_the_coupling(monkeypatch):
    """RED control (table side) — proves the derivation tracks the LIVE legal
    table, not a constant.

    We FAITHFULLY flip a currently-redistributable row (CC-BY) to
    ``redistributable=False`` in the table ``resolve_tier`` actually consults
    (``acquisition.arxiv.licenses._LICENSE_TABLE``, which is what the resolver
    reads — patching ``CC_LICENSE_ROWS`` alone would NOT take effect because the
    arXiv table is pre-composed at import). With CC-BY demoted, ``resolve_tier``
    re-resolves the ``by`` fragment to T3 (non-redistributable), so the DERIVED
    ceiling SHRINKS — it no longer contains the T1 contributed by CC-BY — while
    ``body_servable`` still returns {T1}. Derivation != predicate -> the coupling
    test goes red. (NOTE the asymmetry the resolver enforces: any row that IS
    redistributable resolves to T1, so a *promotion* of CC-BY-NC is caught by the
    tier truth-table tests instead; the coupling test's distinct teeth are this
    demotion-desync and the _BODY_SERVABLE_TIERS-widening case below.)"""
    import dataclasses

    import acquisition.arxiv.licenses as lic

    # Demote EVERY redistributable CC row to non-redistributable + gated, in a
    # SINGLE consistent table that backs BOTH the derivation's filter flag AND
    # the resolver. Patch the resolver's live table so resolve_tier re-resolves
    # those fragments to T3, and pass the SAME rows to the derivation helper so
    # the filter (`if row.redistributable`) and the resolution agree.
    demoted_cc = tuple(
        dataclasses.replace(
            row, redistributable=False, content_class=GATED_DEFAULT_CONTENT_CLASS
        )
        if row.redistributable
        else row
        for row in CC_LICENSE_ROWS
    )
    demoted_full_table = tuple(
        dataclasses.replace(
            row, redistributable=False, content_class=GATED_DEFAULT_CONTENT_CLASS
        )
        if row.redistributable
        else row
        for row in lic._LICENSE_TABLE
    )
    monkeypatch.setattr(lic, "_LICENSE_TABLE", demoted_full_table)

    derived_after_demote = _derived_body_servable_ceiling(rows=demoted_cc)
    actual = {t for t in RightsTier if body_servable(t)}
    # Every redistributable CC row is gone -> the derived ceiling is empty, but
    # body_servable still says {T1} -> they disagree -> coupling test fails.
    assert derived_after_demote == set(), derived_after_demote
    assert actual != derived_after_demote, (
        "RED control: demoting the redistributable CC rows should empty the "
        "derived ceiling and desync it from body_servable; if they still match "
        "the coupling has no teeth"
    )


def test_red_control_widening_body_servable_alone_breaks_the_coupling(monkeypatch):
    """RED control: if someone widens the serve predicate to {T1, T2} WITHOUT a
    corresponding legal-table change, ``body_servable`` now returns True for T2
    while the DERIVED ceiling stays {T1} -> the coupling assertion goes red.

    We monkeypatch ``_BODY_SERVABLE_TIERS`` to {T1, T2} and re-run the coupling
    comparison, asserting it now fails."""
    import substrate.rights.arxiv_tiers as at

    widened = frozenset(
        {RightsTier.T1_REDISTRIBUTABLE, RightsTier.T2_NON_COMMERCIAL}
    )
    monkeypatch.setattr(at, "_BODY_SERVABLE_TIERS", widened)

    actual = {t for t in RightsTier if at.body_servable(t)}
    derived = _derived_body_servable_ceiling()
    assert RightsTier.T2_NON_COMMERCIAL in actual  # the widening took effect
    assert actual != derived, (
        "RED control: widening _BODY_SERVABLE_TIERS to {T1,T2} should desync it "
        "from the {T1} ceiling derived from CC_LICENSE_ROWS; the coupling test "
        "would then fail"
    )


# ════════════════════════════════════════════════════════════════════
# 2. link-back invariant — a served arXiv body MUST carry canonical_url
# ════════════════════════════════════════════════════════════════════


@pytest.fixture
def db(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="antiek-compliance-")
    db_path = os.path.join(tmp, "graph.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    con = connect_write(db_path, purpose="compliance-test")
    init_database(con)
    con.close()
    return db_path


def _insert(db, document_id, *, content_class, body, license_uri=None, arxiv_id=None):
    metadata = None
    if license_uri is not None:
        metadata = {"source": "arxiv_oai_pmh", "license_uri": license_uri}
        if arxiv_id is not None:
            metadata["arxiv_id"] = arxiv_id
    con = connect_write(db, purpose="setup")
    try:
        # Deliberately bypass the normal write-time guard: the fixture models
        # already-persisted drift so the independent read guard is exercised.
        con.execute(
            "INSERT INTO documents "
            "(document_id,source_tier,document_type,title,author,raw_text,content_class,metadata) "
            "VALUES (?,3,'academic_paper','A Paper','Auth',?,?,?)",
            [document_id, body, content_class, None if metadata is None else json.dumps(metadata)],
        )
    finally:
        con.close()


def test_served_arxiv_body_without_canonical_url_raises_link_back_missing(db):
    """THE link-back invariant: a body emitted for an arXiv doc (tier T1) whose
    metadata carries NO arxiv_id (so canonical_url would be None) is REFUSED with
    ``LinkBackMissingError``. A served arXiv body must always link back.

    RED-then-GREEN: the bare content_class gate WOULD emit this body (it is at a
    servable class) — proving the body is real — but the guard refuses it for
    lack of a link-back. Before this invariant existed, the guard returned a
    ServeResult with canonical_url=None and the un-attributed body would have
    shipped."""
    _insert(
        db, "doc-no-linkback",
        content_class=SOURCE_DECLARED_OPEN_CONTENT_CLASS, body=_BODY,
        license_uri=_T1_LICENSE,  # arXiv (tier resolves) ...
        arxiv_id=None,            # ... but no arxiv_id -> canonical_url would be None
    )
    con = connect_read(db)
    try:
        # The bare gate would emit the body (the drift/link-back hole is real).
        bare = serve_full_text(con, "doc-no-linkback")
        assert bare.full_text is not None and bare.servable is True
        # The guard refuses: a served arXiv body without link-back.
        with pytest.raises(LinkBackMissingError):
            serve_full_text_guarded(con, "doc-no-linkback")
    finally:
        con.close()


def test_served_arxiv_body_with_canonical_url_passes(db):
    """GREEN: the SAME servable T1 arXiv doc WITH an arxiv_id (so canonical_url is
    derived) serves the body and carries the link-back — no raise. This is the
    contrast that proves the invariant fires on the MISSING link-back, not on
    arXiv bodies in general."""
    _insert(
        db, "doc-linkback",
        content_class=SOURCE_DECLARED_OPEN_CONTENT_CLASS, body=_BODY,
        license_uri=_T1_LICENSE, arxiv_id="2401.00001",
    )
    con = connect_read(db)
    try:
        r = serve_full_text_guarded(con, "doc-linkback")
        assert r.full_text == _BODY
        assert r.canonical_url == "https://arxiv.org/abs/2401.00001"
    finally:
        con.close()


def test_non_arxiv_served_body_without_canonical_url_is_unconstrained(db):
    """A non-arXiv servable book (no license_uri -> tier None) legitimately has
    canonical_url=None and serves its body WITHOUT tripping the link-back
    invariant — the invariant constrains arXiv bodies ONLY."""
    _insert(db, "doc-book", content_class="public_domain", body=_BODY)  # no license_uri
    con = connect_read(db)
    try:
        r = serve_full_text_guarded(con, "doc-book")  # no raise
        assert r.full_text == _BODY
        assert r.canonical_url is None  # legitimately absent for a non-arXiv book
        assert r.tier is None
    finally:
        con.close()


def test_gated_arxiv_without_arxiv_id_does_not_trip_link_back(db):
    """A gated arXiv row (no body emitted) with no arxiv_id does NOT raise — the
    link-back invariant only fires when a BODY would be emitted (full_text is not
    None). This preserves the pre-existing
    test_arxiv_with_license_but_no_arxiv_id_has_null_canonical_url behaviour."""
    _insert(
        db, "doc-gated-no-id",
        content_class=GATED_DEFAULT_CONTENT_CLASS, body=_BODY,
        license_uri=_T3_LICENSE,  # arxiv_id omitted
    )
    con = connect_read(db)
    try:
        r = serve_full_text_guarded(con, "doc-gated-no-id")  # no raise
        assert r.full_text is None  # gated floor: no body emitted
        assert r.canonical_url is None
        assert r.tier == "T3"
    finally:
        con.close()


# ════════════════════════════════════════════════════════════════════
# 3. the raw-body-read scanner — clean on the tree + has teeth
# ════════════════════════════════════════════════════════════════════


def test_raw_body_scanner_reports_zero_violations_on_the_current_tree():
    """The boundary holds under a pytest-only run: ZERO new raw_text body reads
    outside the serve gate + allowlist on the real tree."""
    violations = serve_invariants_check.find_violations()
    assert violations == [], (
        "new SQL read of documents.raw_text outside the serve gate:\n"
        + "\n".join(violations)
    )


def test_raw_body_scanner_catches_an_injected_violation():
    """RIGOR #3 — prove the scanner has teeth: a synthetic non-allowlisted module
    that issues its own ``SELECT ... raw_text ... FROM documents`` is flagged at
    its exact file:line; an INSERT of raw_text and an allowlisted reader are NOT
    flagged."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # A rogue endpoint that reads the body directly (the violation).
        offender = root / "interfaces" / "research" / "api" / "rogue_body.py"
        offender.parent.mkdir(parents=True)
        offender.write_text(
            textwrap.dedent(
                '''\
                def handler(con, document_id):
                    row = con.execute(
                        "SELECT raw_text FROM documents WHERE document_id = ?",
                        [document_id],
                    ).fetchone()
                    return row[0]
                '''
            ),
            encoding="utf-8",
        )
        # An INSERT of raw_text (a WRITE) must NOT flag.
        writer = root / "acquisition" / "ingest.py"
        writer.parent.mkdir(parents=True)
        writer.write_text(
            'def store(con, did, body):\n'
            '    con.execute("INSERT INTO documents (document_id, raw_text) VALUES (?, ?)", [did, body])\n',
            encoding="utf-8",
        )
        # An allowlisted reader (serve.py) must NOT flag.
        gate = root / "substrate" / "books" / "serve.py"
        gate.parent.mkdir(parents=True)
        gate.write_text(
            'def serve_full_text(con, did):\n'
            '    return con.execute("SELECT d.raw_text FROM documents d WHERE d.document_id = ?", [did]).fetchone()\n',
            encoding="utf-8",
        )

        violations = serve_invariants_check.find_violations(root=root)

    assert len(violations) == 1, violations
    v = violations[0]
    assert v.startswith("interfaces/research/api/rogue_body.py:"), v
    flagged_paths = {line.split(":", 1)[0] for line in violations}
    assert flagged_paths == {"interfaces/research/api/rogue_body.py"}


def test_raw_body_scanner_catches_star_and_concat_body_reads():
    """RIGOR #3 (round-2 tightening) — the scanner catches the two literal-SQL
    evasions a column-name-only matcher missed:
      (a) ``SELECT * FROM documents`` (star read — pulls raw_text without naming
          it), and
      (b) ``"SELECT raw_text " + "FROM documents ..."`` (a body read split across
          ``+``-concatenated string literals).
    A ``SELECT *`` against a DIFFERENT table, and a runtime-interpolated table name
    (the accepted-limitation class), are NOT flagged."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        star = root / "interfaces" / "research" / "api" / "star_body.py"
        star.parent.mkdir(parents=True)
        star.write_text(
            'def h(con, did):\n'
            '    return con.execute("SELECT * FROM documents WHERE document_id = ?", [did]).fetchone()\n',
            encoding="utf-8",
        )
        concat = root / "interfaces" / "research" / "api" / "concat_body.py"
        concat.write_text(
            'def h(con, did):\n'
            '    q = "SELECT raw_text " + "FROM documents WHERE document_id = ?"\n'
            '    return con.execute(q, [did]).fetchone()\n',
            encoding="utf-8",
        )
        # NOT flagged: star on another table.
        star_other = root / "interfaces" / "research" / "api" / "star_other.py"
        star_other.write_text(
            'def h(con):\n'
            '    return con.execute("SELECT * FROM chunks WHERE id = ?", [1]).fetchall()\n',
            encoding="utf-8",
        )
        # NOT flagged (accepted limitation): runtime-interpolated table name.
        fstr = root / "interfaces" / "research" / "api" / "fstr_table.py"
        fstr.write_text(
            'T = "documents"\n'
            'def h(con, did):\n'
            '    return con.execute(f"SELECT raw_text FROM {T} WHERE document_id = ?", [did]).fetchone()\n',
            encoding="utf-8",
        )

        violations = serve_invariants_check.find_violations(root=root)

    flagged = {line.split(":", 1)[0].split("/")[-1] for line in violations}
    assert "star_body.py" in flagged, violations
    assert "concat_body.py" in flagged, violations
    assert "star_other.py" not in flagged, violations
    assert "fstr_table.py" not in flagged, violations


def test_raw_body_scanner_does_not_flag_an_insert_or_update(monkeypatch):
    """An INSERT/UPDATE of raw_text WRITES the body (ingestion / takedown-null) —
    it does not SERVE it, so the scanner (which requires SELECT + raw_text +
    documents) leaves it clean."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        f = root / "acquisition" / "store.py"
        f.parent.mkdir(parents=True)
        f.write_text(
            'def w(con, did, body):\n'
            '    con.execute("UPDATE documents SET raw_text = ? WHERE document_id = ?", [body, did])\n',
            encoding="utf-8",
        )
        assert serve_invariants_check.find_violations(root=root) == []


# ════════════════════════════════════════════════════════════════════
# 4. retrieval-gate drift scanner — clean on the tree + has teeth
# ════════════════════════════════════════════════════════════════════


def test_retrieval_gate_scanner_reports_zero_violations_on_the_current_tree():
    """RG-04: ZERO RESTRICTED-only chunk-gate drift on the watched surfaces."""
    violations = retrieval_gate_check.find_violations()
    assert violations == [], (
        "RESTRICTED-only chunk-gate reimplementation:\n" + "\n".join(violations)
    )


def test_retrieval_gate_scanner_catches_vss_restricted_only_sql():
    """RIGOR #3 — VSS regression shape: hand-rolled NOT IN restricted only."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        offender = root / "substrate" / "graph" / "retrieval_substrate.py"
        offender.parent.mkdir(parents=True)
        offender.write_text(
            textwrap.dedent(
                '''\
                def _vss_query(self, policy_tag):
                    excluded = list(RESTRICTED_CONTENT_CLASSES)
                    sql = (
                        " AND (d.content_class IS NULL OR "
                        "d.content_class NOT IN (?,?))"
                    )
                    return sql, excluded
                '''
            ),
            encoding="utf-8",
        )
        clean = root / "interfaces" / "research" / "api" / "app.py"
        clean.parent.mkdir(parents=True)
        clean.write_text(
            textwrap.dedent(
                '''\
                from substrate.graph.retrieval_gate import is_chunk_body_withheld

                def get_chunk(content_class, taken_down):
                    withheld, _ = is_chunk_body_withheld(
                        content_class, taken_down=taken_down,
                    )
                    return withheld
                '''
            ),
            encoding="utf-8",
        )

        violations = retrieval_gate_check.find_violations(root=root)

    assert len(violations) >= 1, violations
    flagged = {line.split(":", 1)[0] for line in violations}
    assert "substrate/graph/retrieval_substrate.py" in flagged, violations
    assert "interfaces/research/api/app.py" not in flagged, violations


def test_retrieval_gate_scanner_catches_http_restricted_only_withhold():
    """RIGOR #3 — HTTP regression shape: content_class in RESTRICTED only."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        substrate = root / "substrate" / "graph" / "retrieval_substrate.py"
        substrate.parent.mkdir(parents=True)
        substrate.write_text(
            textwrap.dedent(
                '''\
                from substrate.graph.retrieval_gate import non_privileged_chunk_sql_clause

                def _vss_query(self, policy_tag):
                    return non_privileged_chunk_sql_clause(policy_tag=policy_tag)
                '''
            ),
            encoding="utf-8",
        )
        offender = root / "interfaces" / "research" / "api" / "app.py"
        offender.parent.mkdir(parents=True)
        offender.write_text(
            textwrap.dedent(
                '''\
                from substrate.graph.search import RESTRICTED_CONTENT_CLASSES

                def withhold(content_class):
                    return content_class in RESTRICTED_CONTENT_CLASSES
                '''
            ),
            encoding="utf-8",
        )

        violations = retrieval_gate_check.find_violations(root=root)

    assert len(violations) == 1, violations
    assert violations[0].startswith("interfaces/research/api/app.py:"), violations
