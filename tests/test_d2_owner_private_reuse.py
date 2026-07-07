"""D2 (owner-private reuse) — the audience-aware trust gate, proven mechanically.

The flywheel's reuse gate admits a unit iff groundedness ≥ threshold AND it is
readable by the audience. Pre-D2 there was ONE audience (public): the §9.0
``serves_full_text`` bar. That bars ``personal_reading`` (owner's own fetched
third-party reading) from reuse EVEN on the owner's OWN private investigation —
so the owner's reading can never compound into the owner's research. That is the
#1 thought-partner blocker.

D2 adds a second audience (``owner=True``) that uses the OWNER-READ track
(servable ∪ personal_reading, not taken_down) — mirroring the ``owner`` switch
already shipped in books/serve.py. The owner already reads personal_reading in
full on the privileged path, so reusing an insight derived from it in a PRIVATE
investigation is consistent with the rights the owner already holds.

What this proves:
  * PUBLIC BYTE-IDENTITY — owner=False (the default) is unchanged: a
    personal_reading unit is still ``non-servable`` on the public path.
  * OWNER ADMITS personal_reading — owner=True reuses a grounded personal_reading
    unit (the thought-partner unblock).
  * OWNER DENIES the unreadable — NULL / restricted / taken_down are
    ``non-owner-readable`` even on the owner path (deny-by-default holds).
  * SERVABLE works on BOTH — a user_owned unit is reusable on public AND owner.

What this does NOT prove (honesty): the synthesis-deposit leak guard (a private
synthesis that ingested personal_reading must be deposited non-servable so it can
never go public without re-gating) is a separable deposit-path contract, scoped
in the D2 decision packet — these tests cover the GATE mechanism only.
"""

from __future__ import annotations

import substrate.context_pack.knowledge_reuse as kr
import substrate.flywheel.reuse_gate as rg
from substrate.contracts.nodes import (
    KnowledgeUnitContract,
    ProvenanceLink,
)


def _unit(
    doc_content_class: str | None, *, taken_down: bool, groundedness: float
) -> KnowledgeUnitContract:
    """A minimal knowledge unit. The §9.0 ServabilityTag is built the way the
    production deposit path builds it — via ``servability_tag_for`` projecting
    the DOCUMENT-side content_class to the serve-side PUBLIC answer. The
    document-side class itself rides separately on RetrievedUnit.content_class
    (the D2 owner-read track input)."""
    from substrate.graph.insight_question import servability_tag_for

    return KnowledgeUnitContract(
        node_id="n1",
        node_type="insight",
        text="Subclutter visibility quantifies a radar's ability to detect moving targets.",
        investigation_id="inv-prev",
        retrieval_key="n1",
        provenance=ProvenanceLink(source_document_id="doc1", chunk_id="chk1"),
        servability=servability_tag_for(doc_content_class, taken_down=taken_down),
        groundedness_score=groundedness,
    )


def _retrieved(
    content_class: str | None, *, groundedness: float, taken_down: bool = False
) -> kr.RetrievedUnit:
    """A RetrievedUnit carrying BOTH the §9.0 ServabilityTag (public answer) AND
    the D2 document-side content_class/taken_down (owner-read track inputs). The
    ``serves`` kwarg is gone — it is now DERIVED from content_class via the tag,
    exactly as production derives it (no test-only fiction)."""
    return kr.RetrievedUnit(
        unit=_unit(content_class, taken_down=taken_down, groundedness=groundedness),
        similarity=0.9,
        content_class=content_class,
        taken_down=taken_down,
    )


# --- PUBLIC path (owner=False) is byte-identical to pre-D2 --------------------

def test_public_path_excludes_personal_reading():
    """A personal_reading unit is non-servable ⇒ excluded on the PUBLIC path
    (the pre-D2 status quo, unchanged)."""
    ru = _retrieved("personal_reading", groundedness=0.9)
    d = rg.evaluate_unit(ru, threshold=0.5)
    assert not d.reusable
    assert "non-servable" in d.reasons
    assert "non-owner-readable" not in d.reasons  # public path uses the public reason only


def test_public_path_excludes_null_content_class():
    ru = _retrieved(None, groundedness=0.9)
    d = rg.evaluate_unit(ru, threshold=0.5)
    assert not d.reusable
    assert "non-servable" in d.reasons


def test_public_path_admits_servable():
    ru = _retrieved("user_owned", groundedness=0.9)
    d = rg.evaluate_unit(ru, threshold=0.5)
    assert d.reusable and not d.reasons


# --- OWNER path (owner=True) — the thought-partner unblock --------------------

def test_owner_path_admits_personal_reading():
    """D2 keystone: on the owner path a grounded personal_reading unit IS
    reusable — the owner's own reading compounds into the owner's own research."""
    ru = _retrieved("personal_reading", groundedness=0.9)
    d = rg.evaluate_unit(ru, threshold=0.5, owner=True)
    assert d.reusable, f"owner path should admit personal_reading; reasons={d.reasons}"
    assert not d.reasons


def test_owner_path_still_gates_below_threshold():
    """Groundedness is INDEPENDENT of audience: a below-threshold personal_reading
    unit is excluded on the owner path too (the trust bar does not relax)."""
    ru = _retrieved("personal_reading", groundedness=0.3)
    d = rg.evaluate_unit(ru, threshold=0.5, owner=True)
    assert not d.reusable
    assert "below-threshold" in d.reasons


def test_owner_path_denies_null_content_class():
    """NULL content_class ⇒ non-owner-readable: the owner cannot lawfully reuse
    what they cannot read (deny-by-default holds on the owner path)."""
    ru = _retrieved(None, groundedness=0.9)
    d = rg.evaluate_unit(ru, threshold=0.5, owner=True)
    assert not d.reusable
    assert "non-owner-readable" in d.reasons


def test_owner_path_denies_restricted():
    """restricted_pending_opt_in is NOT owner-readable (it's not in
    PERSONAL_READABLE_CONTENT_CLASSES) ⇒ excluded even on the owner path."""
    ru = _retrieved("restricted_pending_opt_in", groundedness=0.9)
    d = rg.evaluate_unit(ru, threshold=0.5, owner=True)
    assert not d.reusable
    assert "non-owner-readable" in d.reasons


def test_owner_path_denies_taken_down_absolutely():
    """Taken-down is ABSOLUTE (mirrors serve.py): a taken-down personal_reading
    unit is non-owner-readable even on the owner path — removal wins for everyone."""
    ru = _retrieved("personal_reading", groundedness=0.9, taken_down=True)
    d = rg.evaluate_unit(ru, threshold=0.5, owner=True)
    assert not d.reusable
    assert "non-owner-readable" in d.reasons


def test_owner_path_admits_servable():
    """A publicly-servable unit is reusable on the owner path too (owner-readable
    is a SUPERSET of servable)."""
    ru = _retrieved("user_owned", groundedness=0.9)
    d = rg.evaluate_unit(ru, threshold=0.5, owner=True)
    assert d.reusable and not d.reasons


# --- filter_reusable threads owner + partitions correctly --------------------

def test_filter_reusable_owner_vs_public_partition(tmp_path, monkeypatch):
    """The full gate partitions a mixed set differently by audience: public keeps
    only the servable unit; owner keeps servable + personal_reading; both drop
    NULL + below-threshold. One event per excluded unit, carrying the audience's
    reason vocabulary."""
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    units = [
        _retrieved("user_owned", groundedness=0.9),          # both admit
        _retrieved("personal_reading", groundedness=0.9),   # owner only
        _retrieved(None, groundedness=0.9),                 # neither
        _retrieved("personal_reading", groundedness=0.3),   # neither (below)
    ]
    # PUBLIC
    reusable_pub, dec_pub = rg.filter_reusable(
        units, investigation_id="inv", events_dir=str(tmp_path / "events"), emit=False,
    )
    assert [ru.content_class for ru in reusable_pub] == ["user_owned"]
    # OWNER
    reusable_own, dec_own = rg.filter_reusable(
        units, investigation_id="inv", events_dir=str(tmp_path / "events"), emit=False, owner=True,
    )
    assert [ru.content_class for ru in reusable_own] == ["user_owned", "personal_reading"]
    # the owner partition admits strictly more (the thought-partner unblock), never less
    assert set(u.content_class for u in reusable_own) >= set(u.content_class for u in reusable_pub)


def test_owner_readable_property_reflects_track():
    """The RetrievedUnit.owner_readable predicate is the owner-read track:
    servable ∪ personal_reading, minus taken_down, minus NULL/restricted."""
    assert _retrieved("user_owned", groundedness=0.9).owner_readable is True
    assert _retrieved("personal_reading", groundedness=0.9).owner_readable is True
    assert _retrieved("public_domain", groundedness=0.9).owner_readable is True
    assert _retrieved(None, groundedness=0.9).owner_readable is False
    assert _retrieved("restricted_pending_opt_in", groundedness=0.9).owner_readable is False
    assert _retrieved("personal_reading", groundedness=0.9, taken_down=True).owner_readable is False

