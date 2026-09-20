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

from runtime.db_lock import connect_read, connect_write  # noqa: E402
from substrate.books.serve import serve_full_text  # noqa: E402
from substrate.books.serve_guard import (  # noqa: E402
    _rights_context,
    serve_full_text_guarded,
)
from substrate.constants import (  # noqa: E402
    GATED_DEFAULT_CONTENT_CLASS,
    SOURCE_DECLARED_OPEN_CONTENT_CLASS,
)
from substrate.graph.ops import insert_document  # noqa: E402
from substrate.graph.schema import init_database  # noqa: E402
from substrate.rights import RightsTier, T3BodyServeError  # noqa: E402

# A real arXiv-default (T3, link-back-only) license URI, a real CC-BY (T1) URI,
# and a real CC-BY-NC (T2, non-commercial-display-only) URI — the three tiers
# the serve contract now carries.
_T3_LICENSE = "http://arxiv.org/licenses/nonexclusive-distrib/1.0/"
_T1_LICENSE = "http://creativecommons.org/licenses/by/4.0/"
_T2_LICENSE = "http://creativecommons.org/licenses/by-nc/4.0/"
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


def _insert(
    db, document_id, *, content_class, body, license_uri=_NO_LICENSE, arxiv_id=None
):
    """Insert a documents row. ``license_uri`` omitted → no ``license_uri`` key
    in metadata (a non-arXiv book); passed → an arXiv-style metadata blob with
    that URI (and a deliberately MISLEADING stored ``rights_tier`` to prove the
    guard re-derives from the URI, not the stored value). ``arxiv_id``, when
    given, is stamped into metadata the same way the OAI persist path writes it,
    so the canonical_url projection can be exercised."""
    metadata = None
    if license_uri is not _NO_LICENSE:
        metadata = {
            "source": "arxiv_oai_pmh",
            "license_uri": license_uri,
            # A LIE: claim T1 regardless of the real license, so a test that
            # passes can only have done so by re-deriving from license_uri.
            "rights_tier": "T1",
        }
        if arxiv_id is not None:
            metadata["arxiv_id"] = arxiv_id
    con = connect_write(db, purpose="setup")
    try:
        # Deliberately bypass the normal write-time guard: these tests construct
        # corrupt persisted rows to prove the independent read guard bites.
        con.execute(
            "INSERT INTO documents "
            "(document_id,source_tier,document_type,title,author,raw_text,content_class,metadata) "
            "VALUES (?,3,'academic_paper','A Paper','Auth',?,?,?)",
            [document_id, body, content_class, None if metadata is None else json.dumps(metadata)],
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
        assert _rights_context(con, "doc-lying-tier").tier is RightsTier.T3_DEFAULT_UNKNOWN
        with pytest.raises(T3BodyServeError):
            serve_full_text_guarded(con, "doc-lying-tier")
    finally:
        con.close()


# ── T1: a genuinely redistributable body is served, no raise ────────


def test_t1_servable_body_served_no_raise(db):
    """A doc with a servable content_class AND a T1 license_uri: the body is
    served and the tier arm passes (T1 is body-servable). No raise.

    A real served T1 arXiv row always carries its ``arxiv_id`` (the OAI persist
    path stamps it), so the body ships with a canonical_url link-back — which the
    SPR-09 M2 link-back invariant now REQUIRES for any emitted arXiv body. We
    assert both the body served AND the link-back present."""
    _insert(
        db, "doc-t1",
        content_class=SOURCE_DECLARED_OPEN_CONTENT_CLASS, body=_BODY,
        license_uri=_T1_LICENSE, arxiv_id="2401.09999",
    )
    con = connect_read(db)
    try:
        result = serve_full_text_guarded(con, "doc-t1")
        assert result.servable is True
        assert result.full_text == _BODY
        assert result.canonical_url == "https://arxiv.org/abs/2401.09999"  # link-back present
        assert _rights_context(con, "doc-t1").tier is RightsTier.T1_REDISTRIBUTABLE
    finally:
        con.close()


# ── Zero regression: non-arXiv book + normal gated arXiv row ─────────


def _assert_serve_decision_equal(guarded, bare):
    """The guard now ENRICHES the result with the four rights-context fields
    (Read SPR-05), so it is no longer byte-identical to the bare gate. Its
    contract is that the SERVE-DECISION fields — what body, if any, leaves
    storage — are preserved EXACTLY. Compare those, ignoring the additive
    rights fields (tier/ad_eligible/canonical_url/license)."""
    for f in ("document_id", "found", "servability", "servable",
              "full_text", "snippet", "title", "author", "reason"):
        assert getattr(guarded, f) == getattr(bare, f), f"serve-decision field {f} drifted"


def test_non_arxiv_book_no_license_uri_serve_decision_unchanged(db):
    """A non-arXiv servable book (no license_uri in metadata): the tier arm is
    SKIPPED, so the SERVE DECISION is identical to a bare serve_full_text — ZERO
    behavioural change to what body leaves storage for the existing corpus. The
    guard additionally stamps the rights context (tier=None, ad_eligible==servable,
    canonical_url=None, license=None) — additive, not a behavioural change."""
    _insert(db, "doc-book", content_class="public_domain", body=_BODY)  # no license_uri
    con = connect_read(db)
    try:
        assert _rights_context(con, "doc-book").tier is None  # tier arm skipped
        guarded = serve_full_text_guarded(con, "doc-book")
        bare = serve_full_text(con, "doc-book")
        _assert_serve_decision_equal(guarded, bare)
        assert guarded.servable is True and guarded.full_text == _BODY
        # Additive rights context for a non-arXiv book.
        assert guarded.tier is None and guarded.license is None
        assert guarded.canonical_url is None
        assert guarded.ad_eligible == guarded.servable  # no ad regression
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
        # The guard preserves the SERVE DECISION the bare gate made (no body
        # emitted); it additionally stamps the rights context (tier='T3' here).
        _assert_serve_decision_equal(result, serve_full_text(con, "doc-gated-arxiv"))
        assert result.tier == "T3" and result.ad_eligible is False
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


# ── _rights_context tier edge cases ─────────────────────────────────


def test_tier_for_unknown_document_is_none(db):
    """No row → tier arm skipped (None), never a raise."""
    con = connect_read(db)
    try:
        assert _rights_context(con, "doc-does-not-exist").tier is None
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
        assert _rights_context(con, "doc-blank-license").tier is RightsTier.T3_DEFAULT_UNKNOWN
        with pytest.raises(T3BodyServeError):
            serve_full_text_guarded(con, "doc-blank-license")
    finally:
        con.close()


def test_whitespace_only_arxiv_id_yields_no_canonical_url(db):
    """SPR-09 round-2 — a WHITESPACE-ONLY ``arxiv_id`` is treated as absent, so it
    cannot produce a bogus ``canonical_url`` (``https://arxiv.org/abs/   ``).

    Before the ``.strip()`` gate, ``arxiv_id="   "`` was truthy, so the guard
    derived a junk link-back and would have shipped a T1 body 'attributed' to a
    meaningless URL. Now ``_rights_context`` reports ``arxiv_id=None`` for a blank
    id, so the link-back invariant REFUSES the body (deny-by-default) rather than
    serve it with a junk link.

    RED-THEN-GREEN: remove ``.strip()`` from ``_rights_context`` (revert to
    ``and arxiv_id``) and ``_rights_context`` returns ``arxiv_id='   '`` →
    ``canonical_url='https://arxiv.org/abs/   '`` → the body serves with a junk
    link and ``LinkBackMissingError`` is NOT raised → this test fails."""
    _insert(
        db, "doc-ws-id",
        content_class=SOURCE_DECLARED_OPEN_CONTENT_CLASS, body=_BODY,
        license_uri=_T1_LICENSE, arxiv_id="   ",  # whitespace-only → unusable
    )
    con = connect_read(db)
    try:
        from substrate.books.serve_guard import LinkBackMissingError

        ctx = _rights_context(con, "doc-ws-id")
        assert ctx.arxiv_id is None, (
            "a whitespace-only arxiv_id must be treated as absent, not yield a "
            f"bogus id ({ctx.arxiv_id!r})"
        )
        # The body would be emitted (servable T1), but with no usable arxiv_id the
        # canonical_url is None → the link-back invariant refuses it.
        with pytest.raises(LinkBackMissingError):
            serve_full_text_guarded(con, "doc-ws-id")
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
        assert _rights_context(con, "doc-corrupt-meta").tier is None
        # Skipped tier arm → behaves like the bare gate (body served on class).
        assert serve_full_text_guarded(con, "doc-corrupt-meta").servable is True
    finally:
        con.close()


# ── Read SPR-05: the rights context carried onto the serve contract ─────
#
# serve_full_text_guarded now stamps four rights fields onto its ServeResult so a
# data-driven reader renders tier / ad-rail / canonical link / license off the
# backend response (never a local flag). The ad_eligible rule is REGRESSION-SAFE:
# arXiv → ads_allowed(tier) (T1 only); non-arXiv → == servable (today's behaviour).


def test_arxiv_t1_servable_is_ad_eligible_with_full_context(db):
    """An arXiv T1 (CC-BY) doc at a servable class: body served, tier='T1',
    ad_eligible True (ads_allowed(T1)), canonical_url + license populated."""
    _insert(
        db, "doc-t1-ads",
        content_class=SOURCE_DECLARED_OPEN_CONTENT_CLASS, body=_BODY,
        license_uri=_T1_LICENSE, arxiv_id="2401.00001",
    )
    con = connect_read(db)
    try:
        r = serve_full_text_guarded(con, "doc-t1-ads")
        assert r.servable is True and r.full_text == _BODY
        assert r.tier == "T1"
        assert r.ad_eligible is True  # ads_allowed(T1)
        assert r.canonical_url == "https://arxiv.org/abs/2401.00001"
        assert r.license == _T1_LICENSE
    finally:
        con.close()


def test_arxiv_t1_gated_body_still_ad_eligible(db):
    """THE discriminating case for the ad-eligibility rule (kills the
    ``ad_eligible = result.servable`` mutation).

    A CC-BY (T1) arXiv doc sitting at the gated content_class floor: the
    content_class gate withholds the body (``servable=False``, ``full_text=None``),
    yet ad-eligibility is LICENSE-based, not body-presence-based — ``ads_allowed(
    T1)`` is ``True`` regardless of servability — so ``ad_eligible`` is ``True``.
    This is the ONLY shipped row where ``ads_allowed(tier) != servable``, so it is
    the only test that distinguishes the regression-safe rule
    (``ads_allowed(ctx.tier) if ctx.tier else result.servable``) from the
    ``= result.servable`` mutation: under the mutation ``ad_eligible`` would be
    ``False`` here and this assertion fails."""
    _insert(
        db, "doc-t1-gated",
        content_class=GATED_DEFAULT_CONTENT_CLASS, body=_BODY,
        license_uri=_T1_LICENSE, arxiv_id="2404.00004",
    )
    con = connect_read(db)
    try:
        r = serve_full_text_guarded(con, "doc-t1-gated")
        assert r.servable is False  # content_class gate withholds the body
        assert r.full_text is None  # ...so no body leaves storage
        assert r.tier == "T1"
        # License-based: ads_allowed(T1) is True INDEPENDENT of servability. The
        # `= result.servable` mutation would yield False here.
        assert r.ad_eligible is True
        assert r.canonical_url == "https://arxiv.org/abs/2404.00004"
        assert r.license == _T1_LICENSE
    finally:
        con.close()


def test_arxiv_t2_is_not_ad_eligible(db):
    """An arXiv T2 (CC-BY-NC) doc at the gated floor (no body emitted → no drift
    raise): tier='T2', ad_eligible False (NC is never ad-eligible)."""
    _insert(
        db, "doc-t2",
        content_class=GATED_DEFAULT_CONTENT_CLASS, body=_BODY,
        license_uri=_T2_LICENSE, arxiv_id="2402.00002",
    )
    con = connect_read(db)
    try:
        r = serve_full_text_guarded(con, "doc-t2")
        assert r.tier == "T2"
        assert r.ad_eligible is False  # CC-BY-NC: never ad-eligible
        assert r.full_text is None  # gated floor, body not emitted
        assert r.canonical_url == "https://arxiv.org/abs/2402.00002"
        assert r.license == _T2_LICENSE
    finally:
        con.close()


def test_arxiv_t3_is_not_ad_eligible(db):
    """An arXiv T3 (arXiv-default) doc at the gated floor: tier='T3',
    ad_eligible False (link-back-only, never ad-eligible)."""
    _insert(
        db, "doc-t3",
        content_class=GATED_DEFAULT_CONTENT_CLASS, body=_BODY,
        license_uri=_T3_LICENSE, arxiv_id="2403.00003",
    )
    con = connect_read(db)
    try:
        r = serve_full_text_guarded(con, "doc-t3")
        assert r.tier == "T3"
        assert r.ad_eligible is False
        assert r.full_text is None
        assert r.canonical_url == "https://arxiv.org/abs/2403.00003"
        assert r.license == _T3_LICENSE
    finally:
        con.close()


def test_non_arxiv_servable_book_stays_ad_eligible_no_regression(db):
    """REGRESSION GUARD: a non-arXiv servable book (no license_uri) keeps
    ad_eligible == servable (True here) — today's "ad rail on any servable book"
    behaviour is preserved. tier/canonical_url/license are all None."""
    _insert(db, "doc-book-servable", content_class="public_domain", body=_BODY)
    con = connect_read(db)
    try:
        r = serve_full_text_guarded(con, "doc-book-servable")
        assert r.servable is True
        assert r.ad_eligible is True  # == servable (no regression)
        assert r.tier is None
        assert r.canonical_url is None
        assert r.license is None
    finally:
        con.close()


def test_non_arxiv_gated_book_is_not_ad_eligible(db):
    """A non-arXiv GATED book (no license_uri, gated content_class) has
    ad_eligible == servable == False — a non-servable book mounts no ad rail."""
    _insert(
        db, "doc-book-gated",
        content_class=GATED_DEFAULT_CONTENT_CLASS, body=_BODY,
    )
    con = connect_read(db)
    try:
        r = serve_full_text_guarded(con, "doc-book-gated")
        assert r.servable is False
        assert r.ad_eligible is False  # == servable
        assert r.tier is None
        assert r.canonical_url is None
        assert r.license is None
    finally:
        con.close()


def test_arxiv_with_license_but_no_arxiv_id_has_null_canonical_url(db):
    """An arXiv row carrying a license_uri but (defensively) no arxiv_id key:
    tier + license still resolve, but canonical_url is None — we never fabricate
    an arxiv.org link without the id."""
    _insert(
        db, "doc-no-id",
        content_class=GATED_DEFAULT_CONTENT_CLASS, body=_BODY,
        license_uri=_T3_LICENSE,  # arxiv_id omitted
    )
    con = connect_read(db)
    try:
        r = serve_full_text_guarded(con, "doc-no-id")
        assert r.tier == "T3"
        assert r.license == _T3_LICENSE
        assert r.canonical_url is None
    finally:
        con.close()
