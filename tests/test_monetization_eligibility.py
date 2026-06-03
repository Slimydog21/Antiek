"""Monetization-eligibility (the EARN gate) — SPR-04 M2.

Eligibility is DERIVED from documents.content_class, the same field §9.0
servability derives from. These tests lock the orthogonality: a gated-but-public
asset earns while its body stays non-servable; a private upload earns nothing
even though (as a public-domain work) its body WOULD be servable if it were in
the public graph.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from runtime.db_lock import connect_write
from substrate.ad_inventory.attribution import (
    PRIVATE_GRAPH_CONTENT_CLASS,
    eligibility_decision,
    eligible_shares,
    monetization_eligible,
)
from substrate.books.servability import ServabilityStatus, servability_of
from substrate.graph.ops import insert_document
from substrate.graph.schema import init_database_at_path


@pytest.fixture
def seeded_db():
    """Seed documents spanning the content_class vocabulary, including the
    load-bearing private-upload fixture the acceptance criteria require."""
    tmp = tempfile.mkdtemp(prefix="antiek-elig-")
    db_path = os.path.join(tmp, "graph.duckdb")
    init_database_at_path(db_path)
    with connect_write(db_path, purpose="elig_seed") as con:
        # Public-domain servable.
        insert_document(
            con, document_id="doc-public-domain", source_tier=1,
            document_type="book", title="Public Domain Book",
            content_class="public_domain",
        )
        # Gated-but-public: copyrighted, body withheld, but IN the public graph.
        insert_document(
            con, document_id="doc-gated-public", source_tier=2,
            document_type="book", title="Copyrighted Gated Book",
            content_class="restricted_pending_opt_in",
        )
        # Private upload: a public-domain work the user uploaded privately.
        # Servable-by-license, but NOT in the public graph → ineligible to earn.
        insert_document(
            con, document_id="doc-private-upload", source_tier=1,
            document_type="book", title="Private Upload",
            content_class=PRIVATE_GRAPH_CONTENT_CLASS,
        )
    yield {"db_path": db_path}


def _content_class_of(db_path: str, document_id: str):
    import duckdb
    con = duckdb.connect(db_path, read_only=True)
    try:
        row = con.execute(
            "SELECT content_class FROM documents WHERE document_id = ?",
            [document_id],
        ).fetchone()
        return row[0] if row else None
    finally:
        con.close()


# ── Eligibility per content_class ──────────────────────────────────────────


def test_public_domain_is_eligible(seeded_db):
    cc = _content_class_of(seeded_db["db_path"], "doc-public-domain")
    assert monetization_eligible(cc) is True


def test_gated_but_public_is_eligible_to_earn(seeded_db):
    """A gated copyrighted-but-public asset earns into escrow even though its
    body is withheld (§9.10 pre-onboarded holder)."""
    cc = _content_class_of(seeded_db["db_path"], "doc-gated-public")
    assert monetization_eligible(cc) is True


def test_private_upload_is_ineligible(seeded_db):
    cc = _content_class_of(seeded_db["db_path"], "doc-private-upload")
    assert monetization_eligible(cc) is False


def test_unknown_content_class_is_ineligible_deny_by_default():
    assert monetization_eligible(None) is False
    assert monetization_eligible("some_future_unrecognised_class") is False


# ── Decoupling from §9.0 servability (assert BOTH ways) ─────────────────────


def test_gated_public_earns_while_body_non_servable(seeded_db):
    """The orthogonality the acceptance criteria demand: a gated-but-public
    fixture is eligible-to-earn (M2) AND its body stays non-servable (§9.0)."""
    cc = _content_class_of(seeded_db["db_path"], "doc-gated-public")
    # EARN gate: eligible.
    assert monetization_eligible(cc) is True
    # §9.0 RENDER gate: the gated class is NOT full-text servable.
    status = servability_of(content_class=cc, taken_down=False)
    assert status == ServabilityStatus.GATED_METADATA_ONLY


def test_private_public_domain_is_servable_by_license_but_ineligible(seeded_db):
    """The reverse: a private upload of a public-domain work would render full
    text by §9.0 (servable license), yet earns nothing (not in the public
    graph). Earn gate and render gate disagree — that is the point."""
    cc = _content_class_of(seeded_db["db_path"], "doc-private-upload")
    # EARN gate: ineligible.
    assert monetization_eligible(cc) is False
    # §9.0 RENDER gate on the SAME private doc, were it surfaced: 'user_owned'
    # maps to ServabilityStatus.PLATFORM_AUTHORED (servability.py L67) — a
    # non-servable status, so its body is never publicly rendered; what matters
    # is the EARN decision is independent of any render answer.
    decision = eligibility_decision(cc)
    assert decision.eligible is False
    assert decision.deciding_field == "content_class"
    assert decision.deciding_value == PRIVATE_GRAPH_CONTENT_CLASS


# ── The decision records WHICH field made it (in)eligible ───────────────────


def test_decision_names_the_deciding_field_for_dispute(seeded_db):
    cc = _content_class_of(seeded_db["db_path"], "doc-private-upload")
    decision = eligibility_decision(cc)
    assert decision.deciding_field == "content_class"
    assert decision.deciding_value == "user_owned"
    assert "private upload" in decision.reason


# ── Ineligible assets never appear in an attribution split ──────────────────


def test_eligible_shares_drops_private_upload_and_renormalizes(seeded_db):
    """An ineligible asset accrues nothing and is removed (not zero-weighted)
    before the split; survivors renormalize to sum to 1.0 (conservation)."""
    db_path = seeded_db["db_path"]
    shares = {
        "doc-public-domain": 0.5,
        "doc-gated-public": 0.3,
        "doc-private-upload": 0.2,  # ineligible — must be dropped
    }
    cc_map = {
        d: _content_class_of(db_path, d) for d in shares
    }
    kept = eligible_shares(shares, cc_map)
    # Private upload gone entirely (accrues nothing, never in the split).
    assert "doc-private-upload" not in kept
    # Conservation: survivors renormalize to 1.0.
    assert sum(kept.values()) == pytest.approx(1.0)
    # Relative ratio of the survivors is preserved (0.5 : 0.3 → 0.625 : 0.375).
    assert kept["doc-public-domain"] == pytest.approx(0.5 / 0.8)
    assert kept["doc-gated-public"] == pytest.approx(0.3 / 0.8)


def test_eligible_shares_all_ineligible_returns_empty(seeded_db):
    db_path = seeded_db["db_path"]
    shares = {"doc-private-upload": 1.0}
    cc_map = {"doc-private-upload": _content_class_of(db_path, "doc-private-upload")}
    assert eligible_shares(shares, cc_map) == {}
