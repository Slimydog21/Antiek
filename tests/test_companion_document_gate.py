"""The companion-document entry gate, the owner overlay, the content hash and
the rights switch (LB-9a; THREAD-CONTRACT §1.2 rev 6, §1.12, §2.10; signed
rev 8.10). T-a10 to T-a13.

The composer is pure, so most of this file feeds it plain verdicts. The
exhaustive test compares it against an oracle written from the signed rules,
not from the module: an entry drawn from a body is a synthesis, so it is only
``served`` or ``withheld``; the most restrictive part wins; the reason
precedence is lineage_unreconciled > unresolved > not_servable; a thread with
no sources, or one whose walk is unreadable, is ``withheld · unresolved``.
"""

from __future__ import annotations

import ast
import hashlib
import importlib
import inspect
import io
import itertools
import os
import random
import re
import tokenize
from collections.abc import Sequence
from pathlib import Path

import pytest

from runtime.db_lock import connect_read, connect_write
from substrate.ad_inventory.attribution import PUBLIC_GRAPH_CONTENT_CLASSES
from substrate.companion_document import gate as gate_module
from substrate.companion_document import rights as rights_module
from substrate.companion_document.gate import (
    ComposedEntry,
    EntryProjection,
    ProcessRef,
    SourceVerdict,
    ThreadVerdict,
    compose_entry,
    content_hash,
    source_ref,
    source_verdicts,
)
from substrate.companion_document.rights import (
    RIGHTS_BRANCHES_LANDED,
    DocumentRights,
    RightsBinding,
    bound,
    document_rights,
    is_servable,
    owner_overlay_withholds,
)
from substrate.companion_document.store import SourcePin
from substrate.constants import SERVABLE_CONTENT_CLASSES
from substrate.schemas.gated_text import GatedText, SourceAnchor, SourceRef

ROOT = Path(__file__).resolve().parents[1]
ME = "owner-a"
OTHER = "owner-b"
ADMITTED = frozenset({ME})
LABEL = "Bridge decks fail at the joints."


def _doc(
    doc_id: str, content_class: str | None, owner: str = ME, *, taken_down: bool = False
) -> DocumentRights:
    return DocumentRights(
        document_id=doc_id, content_class=content_class, owner_user_id=owner, taken_down=taken_down
    )


# name -> (verdict, expected ref gate, expected ref reason, ref keeps its document_id)
SOURCES: dict[str, tuple[SourceVerdict, str, str | None, bool]] = {
    "own_public": (
        SourceVerdict("chunk", "c-ok", _doc("d-ok", "public_domain")),
        "served",
        None,
        True,
    ),
    "unresolved": (SourceVerdict("chunk", "c-gone", None), "cite_only", "unresolved", False),
    "own_restricted": (
        SourceVerdict("chunk", "c-ns", _doc("d-ns", "restricted_pending_opt_in")),
        "cite_only",
        "not_servable",
        True,
    ),
    "foreign_user_owned": (
        SourceVerdict("chunk", "c-fuo", _doc("d-fuo", "user_owned", OTHER)),
        "withheld",
        "not_servable",
        False,
    ),
    "foreign_personal_reading": (
        SourceVerdict("chunk", "c-fpr", _doc("d-fpr", "personal_reading", OTHER)),
        "withheld",
        "not_servable",
        False,
    ),
    "foreign_public": (
        SourceVerdict("chunk", "c-fpub", _doc("d-fpub", "public_domain", OTHER)),
        "served",
        None,
        True,
    ),
    "foreign_restricted": (
        SourceVerdict("chunk", "c-frs", _doc("d-frs", "restricted_pending_opt_in", OTHER)),
        "cite_only",
        "not_servable",
        True,
    ),
    "own_null": (
        SourceVerdict("chunk", "c-null", _doc("d-null", None)),
        "cite_only",
        "not_servable",
        True,
    ),
    "own_unknown": (
        SourceVerdict("chunk", "c-unk", _doc("d-unk", "zz_unknown")),
        "cite_only",
        "not_servable",
        True,
    ),
    "foreign_null": (
        SourceVerdict("chunk", "c-fnull", _doc("d-fnull", None, OTHER)),
        "withheld",
        "not_servable",
        False,
    ),
    "foreign_unknown": (
        SourceVerdict("chunk", "c-funk", _doc("d-funk", "zz_unknown", OTHER)),
        "withheld",
        "not_servable",
        False,
    ),
    "own_personal_reading": (
        SourceVerdict("chunk", "c-opr", _doc("d-opr", "personal_reading")),
        "cite_only",
        "not_servable",
        True,
    ),
    "own_taken_down": (
        SourceVerdict("chunk", "c-td", _doc("d-td", "public_domain", taken_down=True)),
        "cite_only",
        "not_servable",
        True,
    ),
    "own_user_owned": (
        SourceVerdict("chunk", "c-ouo", _doc("d-ouo", "user_owned")),
        "served",
        None,
        True,
    ),
}

PRECEDENCE = ("lineage_unreconciled", "unresolved", "not_servable")


def _v(name: str) -> SourceVerdict:
    return SOURCES[name][0]


def _thread(
    tid: str, *names: str, unreadable: bool = False, lineage: bool = False
) -> ThreadVerdict:
    return ThreadVerdict(
        thread_id=tid,
        sources=tuple(_v(n) for n in names),
        unreadable=unreadable,
        lineage_unreconciled=lineage,
    )


# ── The oracle: the signed rules, restated without the module ────────────


def _expected_ref(name: str) -> SourceRef:
    verdict, gate, reason, keeps = SOURCES[name]
    doc_id = verdict.rights.document_id if (keeps and verdict.rights is not None) else None
    return SourceRef(kind=verdict.kind, id=verdict.id, document_id=doc_id, gate=gate, reason=reason)  # type: ignore[arg-type]


def _part_reason(name: str) -> str | None:
    _, gate, reason, _ = SOURCES[name]
    return None if gate == "served" else reason


def _oracle(
    own: Sequence[str], threads: Sequence[tuple[Sequence[str], bool, bool]], text: str | None
) -> ComposedEntry:
    reasons: list[str] = []
    if not threads:
        reasons.append("unresolved")
    for names, unreadable, lineage in threads:
        if lineage:
            reasons.append("lineage_unreconciled")
        if unreadable or not names:
            reasons.append("unresolved")
        reasons.extend(r for r in (_part_reason(n) for n in names) if r is not None)
    reasons.extend(r for r in (_part_reason(n) for n in own) if r is not None)
    if not reasons and text is None:
        reasons.append("unresolved")
    refs: list[SourceRef] = []
    for name in [*own, *(n for names, _, _ in threads for n in names if SOURCES[n][1] != "served")]:
        ref = _expected_ref(name)
        if ref not in refs:
            refs.append(ref)
    origin = "source" if own else "unsourced"
    doc_ids = tuple(
        sorted(
            {r.document_id for r in (_expected_ref(n) for n in own) if r.document_id is not None}
        )
    )
    worst = min(reasons, key=PRECEDENCE.index) if reasons else None
    content = GatedText.model_validate(
        {
            "text": None if worst else text,
            "gate": "withheld" if worst else "served",
            "reason": worst,
            "origin": origin,
            "source_refs": refs,
        }
    )
    return ComposedEntry(content=content, doc_ids=doc_ids)


def _compose(
    own: Sequence[str], threads: Sequence[tuple[Sequence[str], bool, bool]], text: str | None
) -> ComposedEntry:
    return compose_entry(
        text=text,
        own_pins=[_v(n) for n in own],
        threads=[
            ThreadVerdict(
                f"inv-{i}", tuple(_v(n) for n in names), unreadable=u, lineage_unreconciled=lin
            )
            for i, (names, u, lin) in enumerate(threads)
        ],
        admitted_owners=ADMITTED,
    )


# ── T-a10: exhaustive over small combinations ─────────────────────────────


def test_source_ref_follows_the_quotation_rule_and_the_overlay() -> None:
    for name, (verdict, gate, reason, keeps) in SOURCES.items():
        ref = source_ref(verdict, ADMITTED)
        assert (ref.gate, ref.reason) == (gate, reason), name
        assert (ref.document_id is not None) is keeps, name
        assert ref == _expected_ref(name), name


def test_composer_matches_the_signed_rules_exhaustively() -> None:
    names = list(SOURCES)
    thread_shapes: list[tuple[tuple[str, ...], bool, bool]] = [
        (combo, unreadable, lineage)
        for size in (0, 1, 2)
        for combo in itertools.combinations_with_replacement(names, size)
        for unreadable in (False, True)
        for lineage in (False, True)
    ]
    own_choices: list[tuple[str, ...]] = [(), *((n,) for n in names)]
    checked = 0
    gates_seen: set[str] = set()
    for own in own_choices:
        for shape in thread_shapes:
            for text in (LABEL, None):
                got = _compose(own, [shape], text)
                assert got == _oracle(own, [shape], text), (own, shape, text)
                gates_seen.add(got.content.gate)
                checked += 1
    small = ["own_public", "unresolved", "own_restricted", "foreign_user_owned", "foreign_public"]
    two_shapes = [
        ((n,) if n else (), u, lin)
        for n in [None, *small]
        for u in (False, True)
        for lin in (False, True)
    ]
    for own in [(), ("own_public",), ("foreign_user_owned",), ("own_restricted",)]:
        for first, second in itertools.product(two_shapes, repeat=2):
            got = _compose(own, [first, second], LABEL)
            assert got == _oracle(own, [first, second], LABEL), (own, first, second)
            gates_seen.add(got.content.gate)
            checked += 1
    assert checked > 10_000
    # Non-vacuous: both legal synthesis gates occur, and cite_only never does.
    assert gates_seen == {"served", "withheld"}


def test_synthesis_is_never_cite_only() -> None:
    """A thread whose only source is resolved but not servable reduces its
    REF to a citation, but the entry, a synthesis, is withheld."""
    got = _compose([], [(("own_restricted",), False, False)], LABEL)
    assert (got.content.gate, got.content.reason, got.content.text) == (
        "withheld",
        "not_servable",
        None,
    )
    assert [(r.gate, r.reason) for r in got.content.source_refs] == [("cite_only", "not_servable")]


def test_most_restrictive_thread_wins() -> None:
    got = _compose(
        [], [(("own_public",), False, False), (("own_restricted",), False, False)], LABEL
    )
    assert (got.content.gate, got.content.reason) == ("withheld", "not_servable")
    served = _compose(
        [], [(("own_public",), False, False), (("foreign_public",), False, False)], LABEL
    )
    assert (served.content.gate, served.content.text) == ("served", LABEL)


@pytest.mark.parametrize(
    ("threads", "reason"),
    [
        ([(("own_restricted", "unresolved"), False, False)], "unresolved"),
        ([(("unresolved", "own_restricted"), False, False)], "unresolved"),
        ([(("own_restricted",), False, False), (("unresolved",), False, False)], "unresolved"),
        ([(("unresolved",), False, False), (("own_restricted",), False, False)], "unresolved"),
        ([(("foreign_user_owned",), False, False), (("unresolved",), False, False)], "unresolved"),
        ([(("unresolved",), False, True)], "lineage_unreconciled"),
        (
            [(("own_restricted",), False, False), (("own_public",), False, True)],
            "lineage_unreconciled",
        ),
        ([(("own_public",), True, False), (("own_restricted",), False, False)], "unresolved"),
    ],
)
def test_reason_precedence(threads: list[tuple[tuple[str, ...], bool, bool]], reason: str) -> None:
    got = _compose([], threads, LABEL)
    assert (got.content.gate, got.content.reason) == ("withheld", reason)


def test_thread_with_no_sources_is_withheld_unresolved() -> None:
    got = _compose(["own_public"], [((), False, False)], LABEL)
    assert (got.content.gate, got.content.reason, got.content.text) == (
        "withheld",
        "unresolved",
        None,
    )


def test_unreadable_thread_is_withheld_unresolved() -> None:
    got = _compose(["own_public"], [(("own_public",), True, False)], LABEL)
    assert (got.content.gate, got.content.reason, got.content.text) == (
        "withheld",
        "unresolved",
        None,
    )


def test_entry_with_no_contributing_thread_is_withheld_unresolved() -> None:
    got = compose_entry(
        text=LABEL, own_pins=[_v("own_public")], threads=[], admitted_owners=ADMITTED
    )
    assert (got.content.gate, got.content.reason) == ("withheld", "unresolved")


def test_served_entry_without_recoverable_text_is_withheld_unresolved() -> None:
    got = _compose(["own_public"], [(("own_public",), False, False)], None)
    assert (got.content.gate, got.content.reason) == ("withheld", "unresolved")


@pytest.mark.parametrize("name", ["foreign_personal_reading", "foreign_user_owned"])
def test_foreign_private_document_is_withheld_and_opaque(name: str) -> None:
    """D8: a pin into another owner's private document withholds the entry,
    and its ref names neither the document nor the passage."""
    base = _v(name)
    assert base.rights is not None
    anchored = SourceVerdict(
        base.kind,
        base.id,
        base.rights,
        anchor=SourceAnchor(document_id=base.rights.document_id, page_index=4),
    )
    got = compose_entry(
        text=LABEL,
        own_pins=[anchored],
        threads=[ThreadVerdict("inv-1", (anchored,))],
        admitted_owners=ADMITTED,
    )
    assert (got.content.gate, got.content.reason, got.content.text) == (
        "withheld",
        "not_servable",
        None,
    )
    (ref,) = got.content.source_refs
    assert (ref.gate, ref.reason, ref.document_id, ref.anchor) == (
        "withheld",
        "not_servable",
        None,
        None,
    )
    assert got.doc_ids == ()
    assert base.rights.document_id not in got.content.model_dump_json()
    # The same document admitted as the requester's own is not overlaid.
    mine = compose_entry(
        text=LABEL,
        own_pins=[anchored],
        threads=[ThreadVerdict("inv-1", (anchored,))],
        admitted_owners=frozenset({ME, OTHER}),
    )
    assert mine.content.source_refs[0].document_id == base.rights.document_id


@pytest.mark.parametrize("name", ["own_unknown", "own_null", "foreign_unknown", "foreign_null"])
def test_unknown_and_null_classes_are_not_servable(name: str) -> None:
    got = _compose([name], [((name,), False, False)], LABEL)
    assert (got.content.gate, got.content.reason, got.content.text) == (
        "withheld",
        "not_servable",
        None,
    )


def test_owners_own_personal_reading_is_not_servable_under_8_10() -> None:
    """Pinned to signed rev 8.10, which has no owner path for personal_reading."""
    got = _compose(["own_personal_reading"], [(("own_personal_reading",), False, False)], LABEL)
    assert (got.content.gate, got.content.reason) == ("withheld", "not_servable")
    assert [(r.gate, r.document_id) for r in got.content.source_refs] == [("cite_only", "d-opr")]


def test_foreign_public_domain_is_not_overlaid() -> None:
    got = _compose(["foreign_public"], [(("foreign_public",), False, False)], LABEL)
    assert (got.content.gate, got.content.text) == ("served", LABEL)
    assert [(r.gate, r.document_id) for r in got.content.source_refs] == [("served", "d-fpub")]
    assert got.doc_ids == ("d-fpub",)


def test_origin_is_source_with_an_own_pin_and_unsourced_without() -> None:
    assert (
        _compose(["own_public"], [(("own_public",), False, False)], LABEL).content.origin
        == "source"
    )
    assert _compose([], [(("own_public",), False, False)], LABEL).content.origin == "unsourced"
    assert (
        _compose(["unresolved"], [(("own_public",), False, False)], LABEL).content.origin
        == "source"
    )


def test_source_refs_list_own_pins_then_held_back_thread_sources_once() -> None:
    got = _compose(
        ["own_public"],
        [
            (("own_public", "own_restricted"), False, False),
            (("own_restricted", "unresolved"), False, False),
        ],
        LABEL,
    )
    assert [(r.id, r.gate) for r in got.content.source_refs] == [
        ("c-ok", "served"),
        ("c-ns", "cite_only"),
        ("c-gone", "cite_only"),
    ]


def test_admission_by_any_requester_identity() -> None:
    """The requester may hold more than one identity (D9); a document owned
    by any of them is the requester's own."""
    verdict = SourceVerdict("chunk", "c1", _doc("d1", "user_owned", "email-derived-id"))
    assert source_ref(verdict, frozenset({ME})).gate == "withheld"
    assert source_ref(verdict, frozenset({ME, "email-derived-id"})).gate == "served"


# ── rights.py: predicates, join and the real read ─────────────────────────


def test_servable_and_public_sets_are_mains_constants() -> None:
    assert rights_module.SERVABLE_CONTENT_CLASSES is SERVABLE_CONTENT_CLASSES
    assert rights_module.PUBLIC_GRAPH_CONTENT_CLASSES is PUBLIC_GRAPH_CONTENT_CLASSES
    for cls in SERVABLE_CONTENT_CLASSES:
        assert is_servable(_doc("d", cls))
        assert not is_servable(_doc("d", cls, taken_down=True))
    for gated in (None, "zz_unknown", "personal_reading", "restricted_pending_opt_in"):
        assert not is_servable(_doc("d", gated))


def test_overlay_predicate() -> None:
    assert not owner_overlay_withholds(_doc("d", "user_owned", ME), ADMITTED)
    assert owner_overlay_withholds(_doc("d", "user_owned", OTHER), ADMITTED)
    for cls in PUBLIC_GRAPH_CONTENT_CLASSES:
        assert not owner_overlay_withholds(_doc("d", cls, OTHER), ADMITTED)
    for private in (None, "zz_unknown", "personal_reading", "user_owned"):
        assert owner_overlay_withholds(_doc("d", private, OTHER), ADMITTED)
    # A missing owner is nobody's: fail closed.
    assert owner_overlay_withholds(
        DocumentRights(document_id="d", content_class="user_owned", owner_user_id=None), ADMITTED
    )


def test_source_verdicts_join_fails_closed() -> None:
    pins = [
        SourcePin("node", "n1", "d1"),
        SourcePin("node", "n2", None),
        SourcePin("chunk", "c3", "d-missing"),
        SourcePin("chunk", "c4", "d-not-read"),
    ]
    rights = {"d1": _doc("d1", "public_domain"), "d-missing": None}
    got = source_verdicts(pins, rights)
    assert [(v.kind, v.id, v.rights) for v in got] == [
        ("node", "n1", rights["d1"]),
        ("node", "n2", None),
        ("chunk", "c3", None),
        ("chunk", "c4", None),
    ]


def _db() -> str:
    return os.environ["ANTIEK_DUCKDB_PATH"]


def test_document_rights_reads_class_owner_existence_and_takedown() -> None:
    db = _db()
    with connect_write(db, purpose="test/lb9a-rights", keepalive_s=0) as con:
        rows = [
            ("d-pd", "public_domain", "__operator__"),
            ("d-uo", "user_owned", "owner-b"),
            ("d-null", None, "owner-a"),
            ("d-td", "restricted_pending_opt_in", "owner-a"),
        ]
        for doc_id, cls, owner in rows:
            con.execute(
                "INSERT INTO documents (document_id, source_tier, document_type, content_class, owner_user_id) "
                "VALUES (?, 2, 'book', ?, ?)",
                [doc_id, cls, owner],
            )
        con.execute(
            "INSERT INTO book_assets (document_id, taken_down, pre_takedown_content_class) "
            "VALUES ('d-td', TRUE, 'public_domain')"
        )
    reader = connect_read(db)
    try:
        got = document_rights(reader, ["d-pd", "d-uo", "d-null", "d-td", "d-gone", "d-pd"])
    finally:
        reader.close()
    assert got == {
        "d-pd": DocumentRights("d-pd", "public_domain", "__operator__", False),
        "d-uo": DocumentRights("d-uo", "user_owned", "owner-b", False),
        "d-null": DocumentRights("d-null", None, "owner-a", False),
        "d-td": DocumentRights("d-td", "restricted_pending_opt_in", "owner-a", True),
        "d-gone": None,
    }


def test_document_rights_on_a_database_without_documents(tmp_path: Path) -> None:
    db = str(tmp_path / "empty.duckdb")
    with connect_write(db, purpose="test/lb9a-empty", keepalive_s=0) as con:
        con.execute("CREATE TABLE marker (x INTEGER)")
    reader = connect_read(db)
    try:
        assert document_rights(reader, ["d1"]) == {"d1": None}
        assert document_rights(reader, []) == {}
    finally:
        reader.close()


# ── T-a11: content_hash ───────────────────────────────────────────────────


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _projection(
    eid: str, label: str | None, composed: ComposedEntry, *, kind: str = "insight"
) -> EntryProjection:
    return EntryProjection(
        entry_id=eid,
        kind=kind,  # type: ignore[arg-type]
        content=composed.content,
        thread_ids=("inv-0",),
        doc_ids=composed.doc_ids,
        process_ref=ProcessRef(thread_id="inv-0", event_id="evt-1"),
        confidence="high",
        text_sha256=None if label is None else _sha(label),
    )


def _served(label: str) -> ComposedEntry:
    return _compose(["own_public"], [(("own_public",), False, False)], label)


def _withheld(label: str) -> ComposedEntry:
    return _compose(["own_restricted"], [(("own_restricted",), False, False)], label)


def test_content_hash_is_order_independent() -> None:
    entries = [
        _projection("ev-a", "one", _served("one")),
        _projection("ev-b", "two", _withheld("two")),
        _projection("ev-c", "three", _served("three")),
    ]
    hashes = {content_hash(list(p)) for p in itertools.permutations(entries)}
    assert len(hashes) == 1
    (only,) = hashes
    assert re.fullmatch(r"[0-9a-f]{64}", only)


def test_content_hash_ignores_withheld_text() -> None:
    """The hash cannot confirm a guess at withheld text: two projections that
    differ only in a withheld entry's label hash identically."""
    served = _projection("ev-a", "one", _served("one"))
    guess_1 = _projection("ev-b", "the real withheld words", _withheld("the real withheld words"))
    guess_2 = _projection("ev-b", "a wrong guess", _withheld("a wrong guess"))
    assert guess_1.text_sha256 != guess_2.text_sha256
    assert content_hash([served, guess_1]) == content_hash([served, guess_2])


def test_content_hash_moves_with_served_text_and_with_a_gate() -> None:
    base = [_projection("ev-a", "one", _served("one"))]
    assert content_hash(base) != content_hash([_projection("ev-a", "uno", _served("uno"))])
    assert content_hash(base) != content_hash([_projection("ev-a", "one", _withheld("one"))])
    assert content_hash(base) != content_hash(
        [_projection("ev-a", "one", _served("one"), kind="open_question")]
    )
    assert content_hash(base) != content_hash([*base, _projection("ev-b", "two", _withheld("two"))])
    assert content_hash(base) == content_hash([_projection("ev-a", "one", _served("one"))])


def test_content_hash_is_stable_across_ref_and_id_ordering() -> None:
    refs = [
        SourceRef(kind="chunk", id="c1", document_id="d1", gate="cite_only", reason="not_servable"),
        SourceRef(kind="chunk", id="c2", gate="cite_only", reason="unresolved"),
    ]
    content = GatedText(
        text=None, gate="withheld", reason="unresolved", origin="source", source_refs=refs
    )
    flipped = GatedText(
        text=None, gate="withheld", reason="unresolved", origin="source", source_refs=refs[::-1]
    )
    one = EntryProjection(
        "ev-a",
        "insight",
        content,
        ("inv-1", "inv-2"),
        ("d1", "d2"),
        ProcessRef("inv-1", "e"),
        None,
        None,
    )
    two = EntryProjection(
        "ev-a",
        "insight",
        flipped,
        ("inv-2", "inv-1"),
        ("d2", "d1"),
        ProcessRef("inv-1", "e"),
        None,
        None,
    )
    assert content_hash([one]) == content_hash([two])


def test_projection_refuses_a_served_hash_that_is_not_the_served_text() -> None:
    with pytest.raises(ValueError):
        EntryProjection(
            "ev-a",
            "insight",
            _served("one").content,
            (),
            (),
            ProcessRef("inv-1", "e"),
            None,
            _sha("two"),
        )


def test_content_hash_of_randomised_projections_is_deterministic() -> None:
    rng = random.Random(9)
    entries = [
        _projection(
            f"ev-{i:03d}",
            f"label {i}",
            _served(f"label {i}") if rng.random() < 0.5 else _withheld(f"label {i}"),
        )
        for i in range(40)
    ]
    first = content_hash(entries)
    rng.shuffle(entries)
    assert content_hash(entries) == first


# ── T-a12: the rights switch ──────────────────────────────────────────────


def test_rights_switch_is_off_and_unbound() -> None:
    """LB-9d is the only change that flips this; a stray flip fails here."""
    assert RIGHTS_BRANCHES_LANDED is False
    assert rights_module.RIGHTS_BRANCHES_LANDED is False
    assert bound() is None


def test_rights_binding_protocol_names_the_four_reads() -> None:
    members = {name for name in vars(RightsBinding) if not name.startswith("_")}
    assert members == {"read_log", "body", "thread_sources", "node_pins"}


# ── T-a13: naming ─────────────────────────────────────────────────────────

NEW_MODULES = [
    ROOT / "substrate/schemas/gated_text.py",
    ROOT / "substrate/companion_document/__init__.py",
    ROOT / "substrate/companion_document/store.py",
    ROOT / "substrate/companion_document/gate.py",
    ROOT / "substrate/companion_document/rights.py",
]
_BARE = re.compile(r"companion(?![ _-]?document)", re.IGNORECASE)


def _bare_uses(source: str) -> list[str]:
    hits = []
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type in (tokenize.NAME, tokenize.STRING, tokenize.COMMENT) and _BARE.search(
            tok.string
        ):
            hits.append(f"{tok.start[0]}: {tok.string[:60]!r}")
    return hits


def test_new_modules_use_only_the_compound_term() -> None:
    """T-a13 (TC §1.0, Q-A3): "companion" already means five things, so the
    new modules say "companion document" and never the bare word, in code,
    strings or comments."""
    assert all(p.exists() for p in NEW_MODULES)
    for path in NEW_MODULES:
        assert _bare_uses(path.read_text(encoding="utf-8")) == [], path


def test_naming_check_is_live() -> None:
    assert _bare_uses("companion = 1\n") != []
    assert _bare_uses("x = 'companions'\n") != []
    assert _bare_uses("# the companion rail\n") != []
    assert _bare_uses("companion_document = CompanionDocument\n") == []
    assert _bare_uses("x = 'companion-document-abc'  # a companion document\n") == []


# What gate.py may import: the standard library it needs, the shared type, and
# only the pure names of its sibling modules (dataclasses, literal types and
# predicates that take no connection). Anything else is a way to read.
_PURE_IMPORTS: dict[str, frozenset[str] | None] = {
    "__future__": None,
    "hashlib": None,
    "json": None,
    "collections.abc": None,
    "dataclasses": None,
    "typing": None,
    "substrate.schemas.gated_text": None,
    "substrate.companion_document.rights": frozenset(
        {"DocumentRights", "is_servable", "owner_overlay_withholds"}
    ),
    "substrate.companion_document.store": frozenset({"EntryKind", "SourcePin"}),
}
_READING_BUILTINS = frozenset({"open", "exec", "eval", "compile", "__import__", "input"})


def _impurities(source: str) -> list[str]:
    """Every import outside the allowlist, and every call of a builtin that
    reads or runs code, found by walking the syntax tree."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name not in _PURE_IMPORTS:
                    found.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module not in _PURE_IMPORTS:
                found.append(f"from {module}")
                continue
            allowed = _PURE_IMPORTS[module]
            for alias in node.names:
                if allowed is not None and alias.name not in allowed:
                    found.append(f"from {module} import {alias.name}")
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in _READING_BUILTINS
        ):
            found.append(f"call {node.func.id}")
    return found


def test_gate_module_is_pure() -> None:
    """The composer reads nothing: its imports are an allowlist of the
    standard library, the shared type and pure sibling names, and it calls
    no builtin that reads or runs code."""
    assert _impurities(Path(gate_module.__file__).read_text(encoding="utf-8")) == []
    # The sibling names it may import really are pure: none takes a connection.
    for module, names in _PURE_IMPORTS.items():
        if names is None or not module.startswith("substrate.companion_document"):
            continue
        loaded = importlib.import_module(module)
        for name in names:
            obj = getattr(loaded, name)
            if inspect.isfunction(obj):
                assert "con" not in inspect.signature(obj).parameters, f"{module}.{name}"


def test_purity_check_is_live() -> None:
    assert _impurities("from substrate.companion_document.store import read_scope\n") != []
    assert _impurities("from substrate.companion_document.rights import document_rights\n") != []
    assert _impurities("from pathlib import Path\n") != []
    assert _impurities("import duckdb\n") != []
    assert _impurities("from runtime.db_lock import connect_read\n") != []
    assert _impurities("x = open('f')\n") != []
    assert _impurities("import json\nfrom substrate.schemas.gated_text import GatedText\n") == []
