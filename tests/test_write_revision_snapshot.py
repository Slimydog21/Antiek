"""W3-2: the pure Write revision snapshot, its renderer and its member classifier.

Spec: ``specs/antiek-mothership/cockpit/W3-WRITE-REVISION-WRITER-SPEC-2026-09-27.md``
§2 (canonical body, block identity, HTML grammar, members, manifest) and
"PR W3-2" (T2.1-T2.10, mutants M2.1-M2.9). Signed member rules: THREAD-CONTRACT
§1.11 (``unresolved`` columns hold "what is known, or null, never a guess";
a null ``investigation_id`` means "no thread recorded").

Every test runs against a real DuckDB file built by the repo's own
``init_database_at_path``, except the fail-closed test for a provenance kind
the schema CHECK does not admit, which needs a table without that CHECK.

RED on main: the module under test does not exist, so collection fails with
``ModuleNotFoundError: substrate.write.revision_snapshot``.

Mutant -> killing test (spec PR W3-2):
  M2.1 order by section_index only     -> test_t2_2_ties_order_by_id_and_inventory_...
  M2.2 no NFC                          -> test_t2_9_decomposed_input_...
  M2.3 bake cite-only                  -> test_t2_3_non_servable_source_...
  M2.4 no escaping                     -> test_t2_4_hostile_text_and_ids_...
  M2.5 any-edge resolver               -> test_t2_5_classification_matrix
  M2.6 synthesized -> user             -> test_t2_5_classification_matrix
  M2.7 generated prose -> user         -> test_t2_5_classification_matrix
  M2.8 investigation_id='__operator__' -> test_t2_5_classification_matrix
  M2.9 emit an empty prose block       -> test_t2_10_empty_prose_is_not_a_block
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import textwrap
import unicodedata
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import duckdb
import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from runtime.db_lock import connect_write, flush_warm_writers  # noqa: E402
from substrate.graph.ops import (  # noqa: E402
    attach_block_to_section,
    insert_chunk,
    insert_deliverable,
    insert_document,
    insert_edge,
    insert_node,
    insert_section,
    update_section_prose,
)
from substrate.graph.schema import init_database_at_path  # noqa: E402
from substrate.write.migrate_outline_block import migrate  # noqa: E402
from substrate.write.outline import build_outline_tree  # noqa: E402
from substrate.write.revision_snapshot import (  # noqa: E402
    WRITE_SANITIZER_POLICY,
    WRITE_SANITIZER_VERSION,
    CanonicalHtmlError,
    DeliverableNotFound,
    MemberRow,
    WriteSnapshot,
    member_key,
    snapshot_deliverable,
    verify_canonical_html,
)

MODULE_PATH = Path(_REPO) / "substrate" / "write" / "revision_snapshot.py"
HOSTILE = '<script>alert(1)</script>" onerror="x" </div><div data-block-id="x">'
DECOMPOSED = "Cafe\u0301"  # 'e' + COMBINING ACUTE ACCENT
COMPOSED = "Caf\u00e9"


# ---------------------------------------------------------------------------
# Fixtures and seed helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    path = str(tmp_path / "w3_snapshot.duckdb")
    init_database_at_path(path)
    return path


def _read(db_path: str) -> duckdb.DuckDBPyConnection:
    flush_warm_writers(db_path)
    return duckdb.connect(db_path, read_only=True)


def _snap(db_path: str, deliverable_id: str) -> WriteSnapshot:
    con = _read(db_path)
    try:
        return snapshot_deliverable(con, deliverable_id)
    finally:
        con.close()


def _block(
    con: Any,
    *,
    obid: str,
    section_id: str,
    block_index: int,
    block_kind: str,
    provenance_kind: str,
    node_id: str | None = None,
    content: str | None = None,
    metadata: str | None = None,
) -> None:
    con.execute(
        "INSERT INTO outline_blocks (outline_block_id, section_id, block_kind, "
        "provenance_kind, node_id, content, block_index, metadata) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [obid, section_id, block_kind, provenance_kind, node_id, content,
         block_index, metadata],
    )


def _user_block(con: Any, obid: str, section_id: str, block_index: int, text: str) -> None:
    _block(
        con, obid=obid, section_id=section_id, block_index=block_index,
        block_kind="user_authored", provenance_kind="user_authored", content=text,
    )


def _node(con: Any, node_id: str, label: str, *, chunk_id: str | None = None) -> None:
    insert_node(
        con, canonical_label=label, node_type="claim", graph_scope="depth",
        investigation_id="inv-seed", node_id=node_id,
        metadata=({"chunk_id": chunk_id} if chunk_id else None), emit_event=False,
    )


def _doc_chunk(
    con: Any, document_id: str, chunk_id: str, *, content_class: str = "public_domain",
    title: str = "A source", ip_holder_id: str | None = None,
) -> None:
    insert_document(
        con, document_id=document_id, source_tier=2, document_type="paper",
        title=title, content_class=content_class, ip_holder_id=ip_holder_id,
    )
    insert_chunk(con, document_id=document_id, chunk_index=0,
                 text=f"text of {chunk_id}", chunk_id=chunk_id)


def _members_by_block(snap: WriteSnapshot) -> dict[str, MemberRow]:
    return {m.block_id: m for m in snap.members}


def _block_ids(snap: WriteSnapshot) -> list[str]:
    return [b.block_id for b in snap.blocks]


def _seed_matrix(db_path: str) -> dict[str, str]:
    """One block per classification row of PR W3-2's table, plus the traps."""
    with connect_write(db_path, purpose="test/w3-2-seed") as con:
        did = insert_deliverable(
            con, title="Matrix memo", deliverable_kind="research_memo",
            investigation_root_id="inv-root", deliverable_id="dlv-matrix",
        )
        insert_section(con, deliverable_id=did, section_index=0, title="Graph",
                       section_id="sec-a")
        insert_section(con, deliverable_id=did, section_index=1, title="Mine",
                       section_id="sec-b", prose_text="I wrote this myself.")
        insert_section(con, deliverable_id=did, section_index=2, title="Legacy",
                       section_id="sec-c")
        # Generated prose: the generation path always stores a map.
        update_section_prose(
            con, section_id="sec-a", prose_text="Generated paragraph.",
            prose_provenance={"0": ["oblk-own"]},
        )
        # Graph fixtures.
        _doc_chunk(con, "doc-own", "chunk-own")
        _doc_chunk(con, "doc-contra", "chunk-contra")
        _node(con, "node-own", "Own label", chunk_id="chunk-own")
        _node(con, "node-edge-only", "Edge-only label")
        _node(con, "node-other", "Other label")
        _node(con, "node-badchunk", "Bad chunk label", chunk_id="chunk-does-not-exist")
        # The ONLY chunk reachable from node-edge-only is on a contradicts edge.
        insert_edge(
            con, source_node_id="node-edge-only", target_node_id="node-other",
            relation="contradicts", source_tier=2, extraction_confidence=0.9,
            graph_scope="depth", investigation_id="inv-seed",
            chunk_id="chunk-contra", source_document_id="doc-contra", emit_event=False,
        )
        insert_edge(
            con, source_node_id="node-other", target_node_id="node-own",
            relation="contradicts", source_tier=2, extraction_confidence=0.9,
            graph_scope="depth", investigation_id="inv-seed",
            chunk_id="chunk-contra", source_document_id="doc-contra", emit_event=False,
        )
        _block(con, obid="oblk-dangling", section_id="sec-a", block_index=0,
               block_kind="insight", provenance_kind="graph_node", node_id="node-gone")
        _block(con, obid="oblk-own", section_id="sec-a", block_index=1,
               block_kind="claim", provenance_kind="graph_node", node_id="node-own")
        _block(con, obid="oblk-edge", section_id="sec-a", block_index=2,
               block_kind="insight", provenance_kind="graph_node", node_id="node-edge-only")
        _block(con, obid="oblk-badchunk", section_id="sec-a", block_index=3,
               block_kind="open_question", provenance_kind="graph_node",
               node_id="node-badchunk")
        _user_block(con, "oblk-user", "sec-b", 0, "Typed by the operator.")
        _block(con, obid="oblk-note", section_id="sec-b", block_index=1,
               block_kind="operator_note", provenance_kind="user_authored",
               content="A note.", metadata=json.dumps({"pinned": True}))
        _block(con, obid="oblk-synth", section_id="sec-b", block_index=2,
               block_kind="synthesized", provenance_kind="synthesized",
               content="Model-written summary.")
        _block(con, obid="oblk-brain", section_id="sec-b", block_index=3,
               block_kind="insight", provenance_kind="brainstorm",
               content="Came up in a session.")
        # A real migrated operator-note placeholder, made by the real migration.
        attach_block_to_section(con, section_id="sec-c", block_kind="operator_note",
                                block_id="legacy-note-1", block_index=0)
        result = migrate(con)
        assert result.migrated == 1
        migrated_id = result.block_ids[0]
    return {"deliverable_id": did, "migrated": migrated_id}


# ---------------------------------------------------------------------------
# T2.1 — outline blocks by id, graph-node label text, exact grammar bytes
# ---------------------------------------------------------------------------


def test_t2_1_grammar_golden_bytes_and_block_ids(db_path: str) -> None:
    with connect_write(db_path, purpose="test/w3-2") as con:
        insert_deliverable(con, title="Memo & <notes>", deliverable_kind="research_memo",
                           deliverable_id="dlv-g")
        insert_section(con, deliverable_id="dlv-g", section_index=0, title="Intro",
                       section_id="sec-1", prose_text="First para.\n  \t\nSecond para.\n")
        insert_section(con, deliverable_id="dlv-g", section_index=0, title=None,
                       section_id="sec-2", parent_section_id="sec-1")
        _doc_chunk(con, "doc-g", "chunk-g")
        _node(con, "node-g", "Label", chunk_id="chunk-g")
        _block(con, obid="oblk-1", section_id="sec-1", block_index=0,
               block_kind="insight", provenance_kind="graph_node", node_id="node-g")
        _block(con, obid="oblk-gone", section_id="sec-1", block_index=1,
               block_kind="claim", provenance_kind="graph_node", node_id="node-missing")
        _user_block(con, "oblk-2", "sec-2", 0, "Mine")

    snap = _snap(db_path, "dlv-g")
    expected = (
        '<article data-antiek-write="1" data-deliverable-id="dlv-g">\n'
        "<h1>Memo &amp; &lt;notes&gt;</h1>\n"
        '<section data-section-id="sec-1" data-depth="0">\n'
        "<h2>Intro</h2>\n"
        '<div data-block-id="sprose:sec-1" data-block-role="prose">'
        "<p>First para.</p><p>Second para.</p></div>\n"
        '<div data-block-id="oblk-1" data-block-kind="insight" '
        'data-provenance-kind="graph_node"><p>Label</p></div>\n'
        '<div data-block-id="oblk-gone" data-block-kind="claim" '
        'data-provenance-kind="graph_node"></div>\n'
        "</section>\n"
        '<section data-section-id="sec-2" data-depth="1">\n'
        "<h3></h3>\n"
        '<div data-block-id="oblk-2" data-block-kind="user_authored" '
        'data-provenance-kind="user_authored"><p>Mine</p></div>\n'
        "</section>\n"
        "</article>\n"
    )
    assert snap.canonical_html == expected
    assert _block_ids(snap) == ["sprose:sec-1", "oblk-1", "oblk-gone", "oblk-2"]
    assert [(b.section_id, b.role) for b in snap.blocks] == [
        ("sec-1", "prose"), ("sec-1", "outline"), ("sec-1", "outline"), ("sec-2", "outline"),
    ]
    by_id = {b.block_id: b for b in snap.blocks}
    assert by_id["oblk-1"].text == "Label"
    assert by_id["oblk-gone"].text == ""  # dangling node renders empty
    assert (by_id["sprose:sec-1"].block_kind, by_id["sprose:sec-1"].provenance_kind) == (
        None, None,
    )
    assert snap.title == "Memo & <notes>"
    assert WRITE_SANITIZER_POLICY == "antiek-write-revision-escape"
    assert WRITE_SANITIZER_VERSION == "1"


def test_t2_1_heading_level_caps_at_h6(db_path: str) -> None:
    with connect_write(db_path, purpose="test/w3-2") as con:
        insert_deliverable(con, title="Deep", deliverable_kind="research_memo",
                           deliverable_id="dlv-deep")
        parent = None
        for depth in range(6):
            parent = insert_section(con, deliverable_id="dlv-deep", section_index=0,
                                    title=f"d{depth}", section_id=f"sec-d{depth}",
                                    parent_section_id=parent)
    html_text = _snap(db_path, "dlv-deep").canonical_html
    levels = re.findall(r'data-depth="(\d+)">\n<h(\d)>', html_text)
    assert levels == [("0", "2"), ("1", "3"), ("2", "4"), ("3", "5"), ("4", "6"), ("5", "6")]


# ---------------------------------------------------------------------------
# T2.2 — deterministic order and byte stability
# ---------------------------------------------------------------------------


def _seed_ordering(db_path: str) -> str:
    # Every tie group appears twice: once inserted in id order, once in reverse
    # id order. A tie-break by insertion order fails the reversed groups and a
    # tie-break by reverse insertion order fails the forward ones, so only an
    # order by the id itself (M2.1's missing second key) passes.
    with connect_write(db_path, purpose="test/w3-2") as con:
        insert_deliverable(con, title="Order", deliverable_kind="research_memo",
                           deliverable_id="dlv-o")
        # Root tie at section_index 0, reversed.
        insert_section(con, deliverable_id="dlv-o", section_index=0, title="Z",
                       section_id="sec-z")
        insert_section(con, deliverable_id="dlv-o", section_index=0, title="A",
                       section_id="sec-a")
        insert_section(con, deliverable_id="dlv-o", section_index=-1, title="First",
                       section_id="sec-first")
        # Root tie at section_index 7, forward.
        insert_section(con, deliverable_id="dlv-o", section_index=7, title="M",
                       section_id="sec-m")
        insert_section(con, deliverable_id="dlv-o", section_index=7, title="N",
                       section_id="sec-n")
        # Child tie under sec-a, reversed; child tie under sec-z, forward.
        insert_section(con, deliverable_id="dlv-o", section_index=0, title="A.2",
                       section_id="sec-a2", parent_section_id="sec-a")
        insert_section(con, deliverable_id="dlv-o", section_index=0, title="A.1",
                       section_id="sec-a1", parent_section_id="sec-a")
        insert_section(con, deliverable_id="dlv-o", section_index=0, title="Z.1",
                       section_id="sec-z1", parent_section_id="sec-z")
        insert_section(con, deliverable_id="dlv-o", section_index=0, title="Z.2",
                       section_id="sec-z2", parent_section_id="sec-z")
        # A parent outside this deliverable surfaces the section at the root,
        # exactly as build_outline_tree does.
        insert_deliverable(con, title="Elsewhere", deliverable_kind="research_memo",
                           deliverable_id="dlv-elsewhere")
        insert_section(con, deliverable_id="dlv-elsewhere", section_index=0,
                       title="Elsewhere", section_id="sec-elsewhere")
        insert_section(con, deliverable_id="dlv-o", section_index=5, title="Orphan",
                       section_id="sec-orphan", parent_section_id="sec-elsewhere")
        # Block tie in sec-a, reversed; block tie in sec-a1, forward.
        for obid in ("oblk-c", "oblk-b", "oblk-a"):
            _user_block(con, obid, "sec-a", 3, f"text {obid}")
        _user_block(con, "oblk-0", "sec-a", 1, "text oblk-0")
        _user_block(con, "oblk-z0", "sec-a1", 0, "in a1")
        _user_block(con, "oblk-z1", "sec-a1", 0, "in a1 too")
    return "dlv-o"


def test_t2_2_ties_order_by_id_and_inventory_matches_build_outline_tree(db_path: str) -> None:
    did = _seed_ordering(db_path)
    snap = _snap(db_path, did)
    section_order = []
    for b in re.finditer(r'<section data-section-id="([^"]+)" data-depth="(\d+)"',
                         snap.canonical_html):
        section_order.append((b.group(1), int(b.group(2))))
    assert section_order == [
        ("sec-first", 0), ("sec-a", 0), ("sec-a1", 1), ("sec-a2", 1),
        ("sec-z", 0), ("sec-z1", 1), ("sec-z2", 1), ("sec-orphan", 0),
        ("sec-m", 0), ("sec-n", 0),
    ]
    assert _block_ids(snap) == ["oblk-0", "oblk-a", "oblk-b", "oblk-c", "oblk-z0", "oblk-z1"]

    # The inventory is exactly build_outline_tree's pre-order (the editor's order).
    con = _read(db_path)
    try:
        roots = build_outline_tree(con, did)
    finally:
        con.close()
    editor_order: list[str] = []
    editor_sections: list[tuple[str, int]] = []

    def walk(nodes: Sequence[Any]) -> None:
        for n in nodes:
            editor_sections.append((n.section_id, n.depth))
            editor_order.extend(b.outline_block_id for b in n.blocks)
            walk(n.children)

    walk(roots)
    assert editor_sections == section_order
    assert editor_order == _block_ids(snap)


@pytest.mark.parametrize("seed", ["matrix", "ordering"])
def test_t2_2_bytes_identical_across_calls_and_fresh_subprocesses(
    db_path: str, seed: str,
) -> None:
    did = _seed_matrix(db_path)["deliverable_id"] if seed == "matrix" else _seed_ordering(db_path)
    for deliverable_id in (did,):
        first = _snap(db_path, deliverable_id)
        second = _snap(db_path, deliverable_id)
        assert first == second
        script = textwrap.dedent(
            """
            import sys
            import duckdb
            from substrate.write.revision_snapshot import snapshot_deliverable
            con = duckdb.connect(sys.argv[1], read_only=True)
            s = snapshot_deliverable(con, sys.argv[2])
            con.close()
            sys.stdout.buffer.write(
                s.canonical_html.encode("utf-8") + b"\\x00"
                + s.manifest_json.encode("utf-8") + b"\\x00"
                + s.content_sha256.encode() + b"\\x00" + s.manifest_sha256.encode()
            )
            """
        )
        in_process = b"\x00".join([
            first.canonical_html.encode("utf-8"), first.manifest_json.encode("utf-8"),
            first.content_sha256.encode(), first.manifest_sha256.encode(),
        ])
        for seed in ("1", "2"):
            env = {**os.environ, "PYTHONPATH": _REPO, "PYTHONHASHSEED": seed}
            proc = subprocess.run(
                [sys.executable, "-c", script, db_path, deliverable_id],
                cwd=_REPO, env=env, capture_output=True, timeout=180, check=False,
            )
            assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")[-2000:]
            assert proc.stdout == in_process


# ---------------------------------------------------------------------------
# T2.3 — rights are a serve-time concern; the stored bytes keep the text
# ---------------------------------------------------------------------------


def test_t2_3_non_servable_source_keeps_text_without_cite_only_notice(db_path: str) -> None:
    with connect_write(db_path, purpose="test/w3-2") as con:
        insert_deliverable(con, title="Rights", deliverable_kind="research_memo",
                           deliverable_id="dlv-r")
        insert_section(con, deliverable_id="dlv-r", section_index=0, title="S",
                       section_id="sec-r")
        _doc_chunk(con, "doc-paywalled", "chunk-paywalled",
                   content_class="restricted_pending_opt_in",
                   title="Paywalled Source", ip_holder_id="pub-x")
        _node(con, "node-r", "Restricted claim text", chunk_id="chunk-paywalled")
        _block(con, obid="oblk-r", section_id="sec-r", block_index=0,
               block_kind="claim", provenance_kind="graph_node", node_id="node-r")
    snap = _snap(db_path, "dlv-r")
    assert (
        '<div data-block-id="oblk-r" data-block-kind="claim" '
        'data-provenance-kind="graph_node"><p>Restricted claim text</p></div>\n'
    ) in snap.canonical_html
    lowered = snap.canonical_html.lower()
    for marker in ("cite-only", "cite_only", "withheld", "paywalled source", "pub-x"):
        assert marker not in lowered
    member = _members_by_block(snap)["oblk-r"]
    assert (member.source_kind, member.unresolved_reason, member.source_document_id) == (
        "unresolved", "projection_missing", "doc-paywalled",
    )


# ---------------------------------------------------------------------------
# T2.4 — escaping: content cannot forge structure or block identity
# ---------------------------------------------------------------------------


def test_t2_4_hostile_text_and_ids_are_escaped_and_inventory_is_unchanged(
    db_path: str,
) -> None:
    hostile_sid = 'sec-"><script>'
    hostile_obid = 'oblk-" data-block-id="forged'
    with connect_write(db_path, purpose="test/w3-2") as con:
        insert_deliverable(con, title=HOSTILE, deliverable_kind="research_memo",
                           deliverable_id='dlv-"h')
        insert_section(con, deliverable_id='dlv-"h', section_index=0, title=HOSTILE,
                       section_id=hostile_sid, prose_text=f"{HOSTILE}\n\n{HOSTILE}")
        _node(con, "node-h", HOSTILE)
        _block(con, obid="oblk-h-node", section_id=hostile_sid, block_index=0,
               block_kind="insight", provenance_kind="graph_node", node_id="node-h")
        _user_block(con, "oblk-h-user", hostile_sid, 1, HOSTILE)
        _user_block(con, hostile_obid, hostile_sid, 2, "plain")

    snap = _snap(db_path, 'dlv-"h')
    expected_ids = [f"sprose:{hostile_sid}", "oblk-h-node", "oblk-h-user", hostile_obid]
    assert _block_ids(snap) == expected_ids
    assert [m.block_id for m in snap.members] == expected_ids
    verify_canonical_html(snap.canonical_html, expected_ids)

    out = snap.canonical_html
    assert "<script>" not in out
    assert "</script>" not in out
    assert '" onerror=' not in out
    assert 'data-block-id="x"' not in out
    assert 'data-block-id="forged"' not in out
    escaped = "&lt;script&gt;alert(1)&lt;/script&gt;&quot; onerror=&quot;x&quot; "
    # title, section heading, two prose paragraphs, node label, user content
    assert out.count(escaped) == 6
    # Exactly one start tag per inventory block; nothing else carries the id attribute.
    assert len(re.findall(r"<div data-block-id=", out)) == len(expected_ids)
    assert out.count('data-block-id="') == len(expected_ids)
    assert 'data-deliverable-id="dlv-&quot;h"' in out
    assert 'data-block-id="oblk-&quot; data-block-id=&quot;forged"' in out


@pytest.mark.parametrize(
    ("label", "mutate", "ids"),
    [
        ("extra block id", lambda h: h, ["sprose:s", "b1"]),
        ("missing block id", lambda h: h, ["sprose:s", "b1", "b2", "b3"]),
        ("reordered ids", lambda h: h, ["sprose:s", "b2", "b1"]),
        ("script tag", lambda h: h.replace("<p>one</p>", "<p>one</p><script>x</script>"), None),
        ("event attribute", lambda h: h.replace('<div data-block-id="b1"',
                                                 '<div onclick="x" data-block-id="b1"'), None),
        ("comment", lambda h: h.replace("</article>", "<!-- c --></article>"), None),
        ("forged block div", lambda h: h.replace(
            "<p>one</p>", '<p>one</p></div><div data-block-id="b9" data-block-kind="claim" '
            'data-provenance-kind="graph_node">'), None),
        ("duplicate attribute", lambda h: h.replace(
            'data-block-id="b1"', 'data-block-id="b1" data-block-id="b1"'), None),
        ("prose id for another section", lambda h: h.replace("sprose:s", "sprose:t"),
         ["sprose:t", "b1", "b2"]),
        ("text outside a text element", lambda h: h.replace(
            "<h2>S</h2>\n", "<h2>S</h2>\nloose"), None),
        ("wrong heading level", lambda h: h.replace("<h2>S</h2>", "<h3>S</h3>"), None),
        ("self-closing tag", lambda h: h.replace("</article>", "<p/></article>"), None),
        ("unclosed element", lambda h: h.replace("</section>\n", ""), None),
        ("empty prose div", lambda h: h.replace("<p>para</p>", ""), None),
    ],
)
def test_t2_4_verifier_rejects_non_canonical_input(
    label: str, mutate: Any, ids: list[str] | None,
) -> None:
    good = (
        '<article data-antiek-write="1" data-deliverable-id="d">\n<h1>T</h1>\n'
        '<section data-section-id="s" data-depth="0">\n<h2>S</h2>\n'
        '<div data-block-id="sprose:s" data-block-role="prose"><p>para</p></div>\n'
        '<div data-block-id="b1" data-block-kind="insight" '
        'data-provenance-kind="graph_node"><p>one</p></div>\n'
        '<div data-block-id="b2" data-block-kind="user_authored" '
        'data-provenance-kind="user_authored"></div>\n'
        "</section>\n</article>\n"
    )
    good_ids = ["sprose:s", "b1", "b2"]
    verify_canonical_html(good, good_ids)  # the control passes
    with pytest.raises(CanonicalHtmlError):
        verify_canonical_html(mutate(good), good_ids if ids is None else ids)


# ---------------------------------------------------------------------------
# T2.5 — the classification matrix, one case per row
# ---------------------------------------------------------------------------


def test_t2_5_classification_matrix(db_path: str) -> None:
    ids = _seed_matrix(db_path)
    snap = _snap(db_path, ids["deliverable_id"])
    got = {
        m.block_id: (m.source_kind, m.unresolved_reason, m.source_document_id)
        for m in snap.members
    }
    assert got == {
        "sprose:sec-a": ("unresolved", "no_provenance", None),   # generated prose
        "oblk-dangling": ("unresolved", "source_missing", None),
        "oblk-own": ("unresolved", "projection_missing", "doc-own"),
        # only a contradicts-edge chunk reaches a document: never used
        "oblk-edge": ("unresolved", "no_provenance", None),
        "oblk-badchunk": ("unresolved", "no_provenance", None),
        "sprose:sec-b": ("user", None, None),                    # never generated
        "oblk-user": ("user", None, None),
        "oblk-note": ("user", None, None),
        "oblk-synth": ("unresolved", "no_provenance", None),
        "oblk-brain": ("unresolved", "no_provenance", None),
        ids["migrated"]: ("unresolved", "no_provenance", None),  # migrated placeholder
    }
    # Attribution: no outline_block_attribution table on this schema, so every
    # member records "no thread" — never the operator sentinel, never the root.
    assert [m.investigation_id for m in snap.members] == [None] * len(snap.members)
    assert [m.member_index for m in snap.members] == list(range(len(snap.members)))
    assert [m.block_id for m in snap.members] == _block_ids(snap)


def test_t2_5_prose_patch_keeps_generated_provenance_unresolved(db_path: str) -> None:
    ids = _seed_matrix(db_path)
    with connect_write(db_path, purpose="test/w3-2") as con:
        # The PATCH path preserves the stored map (update_section_prose default).
        update_section_prose(con, section_id="sec-a", prose_text="Operator rewrote it.")
    member = _members_by_block(_snap(db_path, ids["deliverable_id"]))["sprose:sec-a"]
    assert (member.source_kind, member.unresolved_reason) == ("unresolved", "no_provenance")


def test_t2_5_attribution_is_read_only_from_the_attribution_table(db_path: str) -> None:
    ids = _seed_matrix(db_path)
    with connect_write(db_path, purpose="test/w3-2") as con:
        # W3-1's side table (spec §4 PR W3-1); absent on main, present later.
        con.execute(
            "CREATE TABLE outline_block_attribution (outline_block_id TEXT PRIMARY KEY, "
            "investigation_id TEXT NOT NULL, parent_event_id TEXT, "
            "recorded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        for obid, inv in (
            ("oblk-own", "inv-found-it"),
            ("oblk-synth", "inv-synth"),
            ("oblk-user", "inv-user-must-not-show"),
            ("oblk-edge", "__operator__"),
        ):
            con.execute("INSERT INTO outline_block_attribution "
                        "(outline_block_id, investigation_id) VALUES (?, ?)", [obid, inv])
    by_block = _members_by_block(_snap(db_path, ids["deliverable_id"]))
    assert by_block["oblk-own"].investigation_id == "inv-found-it"
    assert by_block["oblk-synth"].investigation_id == "inv-synth"
    assert by_block["oblk-user"].investigation_id is None      # user rows never carry one
    assert by_block["oblk-edge"].investigation_id is None      # sentinel is not a thread
    assert by_block["oblk-dangling"].investigation_id is None  # no row recorded
    assert by_block["sprose:sec-a"].investigation_id is None
    assert all(m.investigation_id != "inv-root" for m in by_block.values())


def test_t2_5_unknown_provenance_kind_fails_closed() -> None:
    # The real schema's CHECK refuses an unknown provenance_kind, so this uses a
    # table without that CHECK — the case a future kind added without a
    # classifier update would reach.
    con = duckdb.connect(":memory:")
    try:
        con.execute("CREATE TABLE deliverables (deliverable_id TEXT, title TEXT)")
        con.execute(
            "CREATE TABLE deliverable_sections (section_id TEXT, deliverable_id TEXT, "
            "parent_section_id TEXT, section_index INTEGER, title TEXT, prose_text TEXT, "
            "prose_provenance TEXT)"
        )
        con.execute(
            "CREATE TABLE outline_blocks (outline_block_id TEXT, section_id TEXT, "
            "block_kind TEXT, provenance_kind TEXT, node_id TEXT, content TEXT, "
            "block_index INTEGER, metadata TEXT)"
        )
        con.execute("CREATE TABLE nodes (node_id TEXT, canonical_label TEXT, metadata TEXT)")
        con.execute("CREATE TABLE chunks (chunk_id TEXT, document_id TEXT)")
        con.execute("INSERT INTO deliverables VALUES ('d', 'T')")
        con.execute("INSERT INTO deliverable_sections VALUES ('s', 'd', NULL, 0, 'S', NULL, NULL)")
        rows = [
            ("b-future", "user_authored", "future_kind", None, "text", 0, None),
            ("b-badmeta", "user_authored", "user_authored", None, "text", 1, "{not json"),
            ("b-nullnode", "insight", "graph_node", None, None, 2, None),
            ("b-control", "user_authored", "user_authored", None, "text", 3, None),
        ]
        for obid, kind, pk, node, content, idx, meta in rows:
            con.execute("INSERT INTO outline_blocks VALUES (?, 's', ?, ?, ?, ?, ?, ?)",
                        [obid, kind, pk, node, content, idx, meta])
        by_block = _members_by_block(snapshot_deliverable(con, "d"))
    finally:
        con.close()
    for obid in ("b-future", "b-badmeta", "b-nullnode"):
        assert (by_block[obid].source_kind, by_block[obid].unresolved_reason) == (
            "unresolved", "no_provenance",
        ), obid
    assert by_block["b-control"].source_kind == "user"


# ---------------------------------------------------------------------------
# T2.6 — member_key is sha256 of the literal compact JSON bytes
# ---------------------------------------------------------------------------


def test_t2_6_member_key_literal_bytes(db_path: str) -> None:
    assert member_key(["user", "oblk-1"]) == hashlib.sha256(b'["user","oblk-1"]').hexdigest()
    assert member_key(["unresolved", "oblk-\u00e9"]) == hashlib.sha256(
        '["unresolved","oblk-\u00e9"]'.encode()
    ).hexdigest()
    assert member_key(["evidence", "quote", "prj-1", None]) == hashlib.sha256(
        b'["evidence","quote","prj-1",null]'
    ).hexdigest()
    ids = _seed_matrix(db_path)
    snap = _snap(db_path, ids["deliverable_id"])
    for m in snap.members:
        assert re.fullmatch(r"[0-9a-f]{64}", m.member_key)
        assert m.member_key == member_key([m.source_kind, m.block_id])
    assert len({m.member_key for m in snap.members}) == len(snap.members)


# ---------------------------------------------------------------------------
# T2.7 — manifest: canonical JSON, members and blocks in order, hashes
# ---------------------------------------------------------------------------


def test_t2_7_manifest_is_canonical_and_hashes_match_duckdb(db_path: str) -> None:
    ids = _seed_matrix(db_path)
    with connect_write(db_path, purpose="test/w3-2") as con:
        _user_block(con, "oblk-\u00fc", "sec-b", 9, "\u00fcber")
    snap = _snap(db_path, ids["deliverable_id"])
    manifest = json.loads(snap.manifest_json)
    assert snap.manifest_json == json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    assert "oblk-\u00fc" in snap.manifest_json and "\\u00fc" not in snap.manifest_json
    assert list(manifest) == ["blocks", "deliverable_id", "members", "schema"]
    assert manifest["schema"] == "antiek.write_revision.v1"
    assert manifest["deliverable_id"] == ids["deliverable_id"]
    assert manifest["members"] == [
        {
            "member_index": m.member_index, "member_key": m.member_key,
            "source_kind": m.source_kind, "block_id": m.block_id,
            "unresolved_reason": m.unresolved_reason,
            "source_document_id": m.source_document_id,
            "investigation_id": m.investigation_id,
        }
        for m in snap.members
    ]
    assert len(manifest["members"]) == len(snap.members) == len(snap.blocks)
    assert manifest["blocks"] == [
        {
            "block_id": b.block_id, "section_id": b.section_id, "role": b.role,
            "block_kind": b.block_kind, "provenance_kind": b.provenance_kind,
            "text_sha256": hashlib.sha256(b.text.encode("utf-8")).hexdigest(),
        }
        for b in snap.blocks
    ]
    assert snap.manifest_sha256 == hashlib.sha256(snap.manifest_json.encode("utf-8")).hexdigest()
    assert snap.content_sha256 == hashlib.sha256(snap.canonical_html.encode("utf-8")).hexdigest()
    mem = duckdb.connect(":memory:")
    try:
        duck_row = mem.execute(
            "SELECT sha256(?), sha256(?)", [snap.manifest_json, snap.canonical_html],
        ).fetchone()
    finally:
        mem.close()
    assert duck_row is not None
    duck_manifest, duck_content = duck_row
    assert (duck_manifest, duck_content) == (snap.manifest_sha256, snap.content_sha256)


# ---------------------------------------------------------------------------
# T2.8 — reads never write, and the snapshot never opens its own connection
# ---------------------------------------------------------------------------


class _ReadResult:
    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor

    def fetchone(self) -> Any:
        return self._cursor.fetchone()

    def fetchall(self) -> Any:
        return self._cursor.fetchall()


class _SelectOnlyConnection:
    """Admits only statements that start with SELECT or WITH AND that DuckDB
    itself parses as SELECT; any other statement or attribute raises."""

    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self._con = con
        self.statements: list[str] = []

    def execute(self, sql: str, parameters: Sequence[Any] | None = None) -> _ReadResult:
        head = sql.lstrip().split(None, 1)[0].upper() if sql.strip() else ""
        if head not in {"SELECT", "WITH"}:
            raise AssertionError(f"snapshot issued a non-read statement: {sql[:80]!r}")
        kinds = {s.type.name for s in self._con.extract_statements(sql)}
        if kinds != {"SELECT"}:
            raise AssertionError(f"snapshot issued statement kinds {kinds}: {sql[:80]!r}")
        self.statements.append(sql)
        return _ReadResult(self._con.execute(sql, parameters))

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"snapshot touched connection attribute {name!r}")


def test_t2_8_reads_never_write(db_path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    ids = _seed_matrix(db_path)
    with connect_write(db_path, purpose="test/w3-2") as con:
        con.execute(
            "CREATE TABLE outline_block_attribution (outline_block_id TEXT PRIMARY KEY, "
            "investigation_id TEXT NOT NULL, parent_event_id TEXT, "
            "recorded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        con.execute("INSERT INTO outline_block_attribution (outline_block_id, "
                    "investigation_id) VALUES ('oblk-own', 'inv-x')")
    raw = _read(db_path)

    def _refuse(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("snapshot opened its own connection")

    try:
        guarded = _SelectOnlyConnection(raw)
        with monkeypatch.context() as m:
            m.setattr(duckdb, "connect", _refuse)
            m.setattr("runtime.db_lock.connect_read", _refuse)
            m.setattr("runtime.db_lock.connect_write", _refuse)
            snap = snapshot_deliverable(guarded, ids["deliverable_id"])
        # Non-vacuous: the guard saw real reads, including the attribution read.
        assert len(guarded.statements) >= 5
        assert any("outline_block_attribution" in s for s in guarded.statements)
        assert len(snap.blocks) == 11
        assert _members_by_block(snap)["oblk-own"].investigation_id == "inv-x"
        # The same bytes come out of a plain read-only DuckDB handle.
        assert snapshot_deliverable(raw, ids["deliverable_id"]) == snap
    finally:
        raw.close()


def test_t2_8_snapshot_inside_a_write_transaction_leaves_it_committable(db_path: str) -> None:
    # W3-3 snapshots inside its write transaction. A read that raised there
    # (for example probing a missing attribution table) would abort the whole
    # transaction, even if the probe caught the error; LockedConnection.transaction()
    # would then raise TransactionAborted on exit instead of committing.
    ids = _seed_matrix(db_path)
    with connect_write(db_path, purpose="test/w3-2") as con, con.transaction():
        _user_block(con, "oblk-in-txn", "sec-b", 7, "placed in the txn")
        snap = snapshot_deliverable(con, ids["deliverable_id"])
        assert "oblk-in-txn" in _block_ids(snap)  # sees its own txn's write
        _user_block(con, "oblk-after-snapshot", "sec-b", 8, "still writable")
    after = _snap(db_path, ids["deliverable_id"])
    assert {"oblk-in-txn", "oblk-after-snapshot"} <= set(_block_ids(after))


def test_t2_8_module_source_is_select_only_and_opens_nothing() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    for keyword in ("INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER", "BEGIN",
                    "COMMIT", "ROLLBACK", "ATTACH", "COPY", "PRAGMA", "CHECKPOINT"):
        assert re.search(rf"\b{keyword}\b", source) is None, keyword
    for forbidden in ("connect_write", "connect_read", "duckdb.connect", "import duckdb",
                      ".transaction(", "open(", "write_text", "write_bytes"):
        assert forbidden not in source, forbidden


def test_snapshot_of_a_missing_deliverable_raises(db_path: str) -> None:
    con = _read(db_path)
    try:
        with pytest.raises(DeliverableNotFound):
            snapshot_deliverable(con, "dlv-does-not-exist")
    finally:
        con.close()


# ---------------------------------------------------------------------------
# T2.9 — NFC
# ---------------------------------------------------------------------------


def test_t2_9_decomposed_input_yields_composed_bytes_and_hashes(db_path: str) -> None:
    assert unicodedata.normalize("NFC", DECOMPOSED) == COMPOSED != DECOMPOSED
    with connect_write(db_path, purpose="test/w3-2") as con:
        insert_deliverable(con, title=DECOMPOSED, deliverable_kind="research_memo",
                           deliverable_id="dlv-n")
        insert_section(con, deliverable_id="dlv-n", section_index=0, title=DECOMPOSED,
                       section_id="sec-n", prose_text=DECOMPOSED)
        _node(con, "node-n", DECOMPOSED)
        _block(con, obid="oblk-n-node", section_id="sec-n", block_index=0,
               block_kind="insight", provenance_kind="graph_node", node_id="node-n")
        _user_block(con, "oblk-n-user", "sec-n", 1, DECOMPOSED)
    snap = _snap(db_path, "dlv-n")
    assert "\u0301" not in snap.canonical_html
    assert snap.canonical_html.count(COMPOSED) == 5
    assert snap.title == COMPOSED
    composed_sha = hashlib.sha256(COMPOSED.encode("utf-8")).hexdigest()
    manifest = json.loads(snap.manifest_json)
    assert [b.text for b in snap.blocks] == [COMPOSED, COMPOSED, COMPOSED]
    assert [b["text_sha256"] for b in manifest["blocks"]] == [composed_sha] * 3


# ---------------------------------------------------------------------------
# T2.10 — empty prose is not a block
# ---------------------------------------------------------------------------


def test_t2_10_empty_prose_is_not_a_block(db_path: str) -> None:
    with connect_write(db_path, purpose="test/w3-2") as con:
        insert_deliverable(con, title="Empty", deliverable_kind="research_memo",
                           deliverable_id="dlv-e")
        insert_section(con, deliverable_id="dlv-e", section_index=0, title="None",
                       section_id="sec-none", prose_text=None)
        insert_section(con, deliverable_id="dlv-e", section_index=1, title="Blank",
                       section_id="sec-blank", prose_text="")
        insert_section(con, deliverable_id="dlv-e", section_index=2, title="Space",
                       section_id="sec-space", prose_text="  \n\n\t \n ")
        insert_section(con, deliverable_id="dlv-e", section_index=3, title="Gen",
                       section_id="sec-gen-empty", prose_text="",
                       prose_provenance={"0": ["oblk-x"]})
        insert_section(con, deliverable_id="dlv-e", section_index=4, title="Real",
                       section_id="sec-real", prose_text="Kept.")
    snap = _snap(db_path, "dlv-e")
    assert _block_ids(snap) == ["sprose:sec-real"]
    assert [m.block_id for m in snap.members] == ["sprose:sec-real"]
    assert snap.canonical_html.count("data-block-role=") == 1

