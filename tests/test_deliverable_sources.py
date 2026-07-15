"""Tests for GPW SPR-04 STRETCH; rendered, §9.0-gated deliverable Sources.

``substrate/write/deliverable_sources.resolve_deliverable_sources`` turns a
deliverable's ``prose_provenance`` (paragraph_index → [block_id]) into the
ORDERED, de-duplicated TITLES of the documents that ground it, dropping any
source withheld from a non-privileged surface (``personal_reading`` /
``restricted_pending_opt_in``). The export endpoint renders that list as a
Sources section in the Markdown / HTML / Substack exports and carries it in
the JSON bundle.

The load-bearing property is §9.0 indistinguishability: a deliverable whose
only sources are withheld must export IDENTICALLY to a source-less one; no
"## Sources" heading, no hint that a personal_reading document exists.
"""

from __future__ import annotations

import os
import sys
import tempfile

import duckdb
import pytest
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from runtime.db_lock import connect_write  # noqa: E402
from substrate.graph.ops import (  # noqa: E402
    insert_deliverable,
    insert_document,
    insert_edge,
    insert_node,
    update_section_prose,
)
from substrate.graph.ops import (
    insert_section as _insert_section,
)
from substrate.graph.schema import init_database_at_path  # noqa: E402
from substrate.write.deliverable_sources import (  # noqa: E402
    resolve_deliverable_sources,
)


@pytest.fixture
def env(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="antiek-gpw-sources-")
    db_path = os.path.join(tmp, "graph.duckdb")
    events_dir = os.path.join(tmp, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    init_database_at_path(db_path)
    return {"db_path": db_path, "events_dir": events_dir}


def _read(db_path: str) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(db_path, read_only=True)


def _grounded_node(con, *, label, document_id, node_type="insight"):
    """An insight/claim node grounded to a document via node metadata --
    the primary linkage the deposit path writes (insight_question.py)."""
    return insert_node(
        con, canonical_label=label, node_type=node_type,
        graph_scope="cross_domain", investigation_id="__operator__",
        metadata={"source_document_id": document_id},
    )


def _doc(con, *, document_id, title, content_class=None):
    return insert_document(
        con, document_id=document_id, source_tier=2, document_type="paper",
        title=title, content_class=content_class,
    )


def insert_section(con, **kwargs):
    """Seed a genuinely current generated section for source-resolution tests."""
    provenance = kwargs.pop("prose_provenance", None)
    if not provenance or not isinstance(provenance, dict):
        return _insert_section(con, prose_provenance=provenance, **kwargs)
    paragraph_count = max(int(key) for key in provenance) + 1
    prose = kwargs.pop("prose_text", None) or "\n\n".join(
        f"Grounded paragraph {index}." for index in range(paragraph_count)
    )
    section_id = _insert_section(con, prose_text=None, prose_provenance=None, **kwargs)
    update_section_prose(
        con,
        section_id=section_id,
        prose_text=prose,
        prose_provenance=provenance,
        mutation_origin="generated",
    )
    return section_id


# ── unit: resolve_deliverable_sources ──────────────────────────────────


def test_resolves_grounded_titles_in_first_appearance_order(env):
    with connect_write(env["db_path"], purpose="test/seed") as con:
        _doc(con, document_id="doc-alpha", title="Alpha Paper")
        _doc(con, document_id="doc-beta", title="Beta Paper")
        na = _grounded_node(con, label="insight a", document_id="doc-alpha")
        nb = _grounded_node(con, label="insight b", document_id="doc-beta")
        did = insert_deliverable(
            con, title="Memo", deliverable_kind="research_memo")
        # paragraph "1" cites beta, paragraph "0" cites alpha; the result
        # must follow paragraph order (0 then 1), NOT dict/insertion order.
        insert_section(
            con, deliverable_id=did, section_index=0, title="S",
            prose_provenance={"1": [nb], "0": [na]},
        )
    with _read(env["db_path"]) as con:
        assert resolve_deliverable_sources(con, did) == [
            "Alpha Paper", "Beta Paper",
        ]


def test_dedupes_document_across_paragraphs_and_sections(env):
    with connect_write(env["db_path"], purpose="test/seed") as con:
        _doc(con, document_id="doc-1", title="One Source")
        n1 = _grounded_node(con, label="i1", document_id="doc-1")
        n2 = _grounded_node(con, label="i2", document_id="doc-1")  # same doc
        did = insert_deliverable(
            con, title="Memo", deliverable_kind="research_memo")
        insert_section(
            con, deliverable_id=did, section_index=0, title="A",
            prose_provenance={"0": [n1], "1": [n2]},
        )
        insert_section(
            con, deliverable_id=did, section_index=1, title="B",
            prose_provenance={"0": [n1]},
        )
    with _read(env["db_path"]) as con:
        # Cited by three blocks across two sections; named exactly once.
        assert resolve_deliverable_sources(con, did) == ["One Source"]


def test_personal_reading_source_is_never_named(env):
    with connect_write(env["db_path"], purpose="test/seed") as con:
        _doc(con, document_id="doc-pub", title="Public Paper")
        _doc(con, document_id="doc-priv", title="A Private Essay",
             content_class="personal_reading")
        npub = _grounded_node(con, label="i-pub", document_id="doc-pub")
        npriv = _grounded_node(con, label="i-priv", document_id="doc-priv")
        did = insert_deliverable(
            con, title="Memo", deliverable_kind="research_memo")
        insert_section(
            con, deliverable_id=did, section_index=0, title="S",
            prose_provenance={"0": [npub, npriv]},
        )
    with _read(env["db_path"]) as con:
        # personal_reading title dropped; only the eligible source surfaces.
        assert resolve_deliverable_sources(con, did) == ["Public Paper"]


def test_restricted_pending_opt_in_source_is_never_named(env):
    with connect_write(env["db_path"], purpose="test/seed") as con:
        _doc(con, document_id="doc-gated", title="A Copyrighted Book",
             content_class="restricted_pending_opt_in")
        n = _grounded_node(con, label="i", document_id="doc-gated")
        did = insert_deliverable(
            con, title="Memo", deliverable_kind="research_memo")
        insert_section(
            con, deliverable_id=did, section_index=0, title="S",
            prose_provenance={"0": [n]},
        )
    with _read(env["db_path"]) as con:
        assert resolve_deliverable_sources(con, did) == []


def test_supported_by_edge_fallback_resolves_document(env):
    with connect_write(env["db_path"], purpose="test/seed") as con:
        _doc(con, document_id="doc-e", title="Edge-Grounded Paper")
        # Node WITHOUT metadata.source_document_id; grounding lives only on
        # a supported_by edge (the resolver's documented fallback).
        n = insert_node(
            con, canonical_label="ungrounded-in-meta", node_type="insight",
            graph_scope="cross_domain", investigation_id="__operator__",
            metadata={"note": "no source_document_id here"},
        )
        target = insert_node(
            con, canonical_label="claim target", node_type="claim",
            graph_scope="cross_domain", investigation_id="__operator__",
        )
        insert_edge(
            con, source_node_id=n, target_node_id=target,
            relation="supported_by", source_tier=2, extraction_confidence=0.9,
            graph_scope="cross_domain", investigation_id="__operator__",
            source_document_id="doc-e",
        )
        did = insert_deliverable(
            con, title="Memo", deliverable_kind="research_memo")
        insert_section(
            con, deliverable_id=did, section_index=0, title="S",
            prose_provenance={"0": [n]},
        )
    with _read(env["db_path"]) as con:
        assert resolve_deliverable_sources(con, did) == ["Edge-Grounded Paper"]


def test_empty_title_document_is_dropped_not_fabricated(env):
    with connect_write(env["db_path"], purpose="test/seed") as con:
        _doc(con, document_id="doc-untitled", title=None)  # eligible, no title
        n = _grounded_node(con, label="i", document_id="doc-untitled")
        did = insert_deliverable(
            con, title="Memo", deliverable_kind="research_memo")
        insert_section(
            con, deliverable_id=did, section_index=0, title="S",
            prose_provenance={"0": [n]},
        )
    with _read(env["db_path"]) as con:
        # Never fabricate an "Untitled" bullet; drop it.
        assert resolve_deliverable_sources(con, did) == []


def test_user_originated_and_unknown_blocks_contribute_no_source(env):
    with connect_write(env["db_path"], purpose="test/seed") as con:
        did = insert_deliverable(
            con, title="Memo", deliverable_kind="research_memo")
        # block_ids that are not graph nodes (user-authored outline ids).
        insert_section(
            con, deliverable_id=did, section_index=0, title="S",
            prose_provenance={"0": ["oblk-user-1", "oblk-user-2"]},
        )
    with _read(env["db_path"]) as con:
        assert resolve_deliverable_sources(con, did) == []


def test_no_provenance_and_malformed_provenance_return_empty(env):
    with connect_write(env["db_path"], purpose="test/seed") as con:
        did = insert_deliverable(
            con, title="Memo", deliverable_kind="research_memo")
        insert_section(  # NULL provenance
            con, deliverable_id=did, section_index=0, title="A")
        insert_section(  # provenance is a JSON list, not a dict → degrade
            con, deliverable_id=did, section_index=1, title="B",
            prose_provenance=["not", "a", "map"],
        )
    with _read(env["db_path"]) as con:
        assert resolve_deliverable_sources(con, did) == []


# ── integration: the export endpoint renders Sources ───────────────────


def _client():
    from interfaces.research.api.app import create_app
    app = create_app(
        register_wrestling=False, register_providers=False, cors_origins=[],
    )
    return TestClient(app)


def _seed_two_source_memo(db_path) -> str:
    with connect_write(db_path, purpose="test/seed") as con:
        _doc(con, document_id="doc-pub", title="Public Paper")
        _doc(con, document_id="doc-priv", title="Leaky Private Essay",
             content_class="personal_reading")
        npub = _grounded_node(con, label="i-pub", document_id="doc-pub")
        npriv = _grounded_node(con, label="i-priv", document_id="doc-priv")
        did = insert_deliverable(
            con, title="Field Memo", deliverable_kind="research_memo")
        insert_section(
            con, deliverable_id=did, section_index=0, title="Intro",
            prose_text="A paragraph.", prose_provenance={"0": [npub, npriv]},
        )
    return did


def test_markdown_export_renders_sources_and_withholds_personal(env):
    did = _seed_two_source_memo(env["db_path"])
    client = _client()
    body = client.get(f"/deliverables/{did}/export?format=markdown").json()
    content = body["content"]
    assert "## Sources" in content
    assert "- Public Paper" in content
    # §9.0: the personal_reading title must NEVER appear in a public export.
    assert "Leaky Private Essay" not in content


def test_html_export_renders_sources_list_and_withholds_personal(env):
    did = _seed_two_source_memo(env["db_path"])
    client = _client()
    body = client.get(f"/deliverables/{did}/export?format=html").json()
    content = body["content"]
    assert "<h2>Sources</h2>" in content
    assert "<li>Public Paper</li>" in content
    assert "Leaky Private Essay" not in content


def test_json_export_carries_gated_sources_list(env):
    did = _seed_two_source_memo(env["db_path"])
    client = _client()
    body = client.get(f"/deliverables/{did}/export?format=json").json()
    import json as _json
    bundle = _json.loads(body["content"])
    assert bundle["sources"] == ["Public Paper"]


def test_epub_export_includes_sources_chapter_and_withholds_personal(env):
    """EPUB Sources render as their own chapter, §9.0-gated. Skip-gated on
    the export extra (same convention as every pdf/epub test; CI does not
    install it). Where it runs, the zip is DECOMPRESSED and every entry
    scanned, so the personal_reading title's absence is a real guarantee,
    not a false-negative off compressed bytes."""
    try:
        import ebooklib  # noqa: F401
    except ImportError:
        pytest.skip("ebooklib not installed; pip install -e '.[export]'")
    import base64
    import io
    import zipfile
    did = _seed_two_source_memo(env["db_path"])
    client = _client()
    body = client.get(f"/deliverables/{did}/export?format=epub").json()
    decoded = base64.b64decode(body["content"])
    with zipfile.ZipFile(io.BytesIO(decoded)) as zf:
        names = zf.namelist()
        all_text = "\n".join(
            zf.read(n).decode("utf-8", "replace") for n in names
        )
    assert any(n.endswith("sources.xhtml") for n in names)
    assert "Public Paper" in all_text
    assert "Leaky Private Essay" not in all_text  # §9.0


def test_pdf_export_with_sources_renders(env):
    """PDF Sources template must not break rendering. Skip-gated on the
    export extra. This asserts render-success (the §9.0 text-level guarantee
    is inherited from the same gated ``sources`` list the executed
    markdown/html/resolver tests already prove; PDF is a binary re-render of
    the identical list)."""
    try:
        import xhtml2pdf  # noqa: F401
    except ImportError:
        pytest.skip("xhtml2pdf not installed; pip install -e '.[export]'")
    import base64
    did = _seed_two_source_memo(env["db_path"])
    client = _client()
    resp = client.get(f"/deliverables/{did}/export?format=pdf")
    assert resp.status_code == 200
    decoded = base64.b64decode(resp.json()["content"])
    assert decoded.startswith(b"%PDF-")
    assert len(decoded) > 500


def test_withheld_only_deliverable_exports_identically_to_sourceless(env):
    """The §9.0 keystone: a deliverable whose ONLY source is personal_reading
    must export byte-for-byte like one with no sources; no Sources heading,
    nothing that betrays a withheld document exists."""
    with connect_write(env["db_path"], purpose="test/seed") as con:
        _doc(con, document_id="doc-priv", title="Secret Diary",
             content_class="personal_reading")
        npriv = _grounded_node(con, label="i", document_id="doc-priv")
        # withheld-only deliverable
        withheld = insert_deliverable(
            con, title="Memo", deliverable_kind="research_memo")
        insert_section(
            con, deliverable_id=withheld, section_index=0, title="Intro",
            prose_text="A paragraph.", prose_provenance={"0": [npriv]},
        )
        # a genuinely source-less deliverable with identical prose/structure
        sourceless = insert_deliverable(
            con, title="Memo", deliverable_kind="research_memo")
        insert_section(
            con, deliverable_id=sourceless, section_index=0, title="Intro",
            prose_text="A paragraph.",
        )
    client = _client()
    a = client.get(
        f"/deliverables/{withheld}/export?format=markdown").json()["content"]
    b = client.get(
        f"/deliverables/{sourceless}/export?format=markdown").json()["content"]
    assert "## Sources" not in a
    # Same modulo the deliverable_id-independent body; the section content is
    # identical, so the withheld export carries no extra bytes.
    assert a == b
