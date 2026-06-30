"""The REAL conformance harness — antiek-reader SPR-09 (capstone).

Imports the production source tree (the shipped renderers/doors) and asserts:
  (a) every OPEN door in ``migration-map.md`` routes through ``openDocument`` →
      the one ``<Reader>``;
  (b) no second document renderer is reachable as an open-a-document seam;
  (c) a ``Document`` survives ingest → store → serve → render validation.

The old green-but-lying test (``tests/test_seam_reader_surface_contract.py``)
checked throwaway in-test classes against the Protocol — SPR-09 DELETED it.
This file is the standing regression guard; weakening any assertion must fail
the suite (verified by the catch-test on the TS side and the pinned sets here).
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

import pytest

# Repo root: ``substrate/contracts/__tests__/`` → four parents up.
_REPO = Path(__file__).resolve().parents[3]
_READING_SRC = _REPO / "apps" / "reading" / "src"
_MIGRATION_MAP = _REPO / "docs/specs/antiek-reader/migration-map.md"


# ───────────────────────────────────────────────────────────────────────────
# Door (a) — every door routes to the one Reader (lockstep with TS stub).
# ───────────────────────────────────────────────────────────────────────────

EXPECTED_OPEN_DOORS: frozenset[str] = frozenset(
    {
        "Library.openWork",
        "LibraryView.open",
        "Reading.openDoc",
        "DocumentsIndex.open",
        "CommandPalette.openDocument",
        "ChunkModal.openInDocument",
        "MasterMdViewer.cmdClick",
        "DRW.citeSource",
        "Write.traceToSource",
        "MetaReading.openCitation",
        "Route./read/:documentId",
    }
)

# Door id → relative path under apps/reading/src (mirrors oneReader.conformance.test.ts).
_DOOR_FILE: dict[str, str] = {
    "Library.openWork": "modes/Library/index.tsx",
    "LibraryView.open": "components/library/LibraryView.tsx",
    "DocumentsIndex.open": "modes/DocumentsIndex/index.tsx",
    "CommandPalette.openDocument": "components/CommandPalette.tsx",
    "ChunkModal.openInDocument": "modes/ResearchWorkstation/ChunkModal.tsx",
    "MasterMdViewer.cmdClick": "modes/ResearchWorkstation/MasterMdViewer.tsx",
    "DRW.citeSource": "modes/DeepResearchWorkspace/index.tsx",
    "Write.traceToSource": "modes/Write/WriteHome.tsx",
    "MetaReading.openCitation": "modes/Reading/MetaReading/index.tsx",
}

_PALETTE_ROUTE_DOORS = frozenset({"CommandPalette.openDocument"})

# Forbidden open-a-document seams (lockstep with TS + migration-map §5).
FORBIDDEN_PROD_RENDERERS: frozenset[str] = frozenset(
    {
        "modes/ResearchWorkstation/MasterMdViewer.tsx::openByIdSeam",
        "modes/Reading/MetaReading/index.tsx::article",
        "modes/DeepResearchWorkspace/index.tsx::canvasTextDiv",
        "components/PdfViewer.tsx::asOpenTarget",
    }
)

_INGEST_EXEMPT = frozenset(
    {
        "workspace/actions.ts",
        "components/PdfViewer.tsx",
        "components/PdfViewer.stories.tsx",
        "workspace/PanelRegistry.tsx",
        "workspace/panel.types.ts",
        "components/ai/aiActions.ts",
    }
)

_OPEN_BY_ID_SEAM_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openPdfPanel(", re.compile(r"openPdfPanel\(")),
    ('open("PdfViewer"', re.compile(r'\.open\(\s*["\']PdfViewer["\']')),
)


def _strip_comments(src: str) -> str:
    """Crude comment strip — matches the TS ``readSrc`` helper."""
    src = re.sub(r"\{/\*[\s\S]*?\*/\}", "", src)
    src = re.sub(r"/\*[\s\S]*?\*/", "", src)
    src = re.sub(r"(^|[^:])//[^\n]*", r"\1", src, flags=re.MULTILINE)
    return src


def _read_src(rel: str) -> str:
    return _strip_comments((_READING_SRC / rel).read_text(encoding="utf-8"))


def _list_src_files() -> list[str]:
    out: list[str] = []
    for root, dirs, files in os.walk(_READING_SRC):
        dirs[:] = [d for d in dirs if d != "node_modules"]
        for name in files:
            if name.endswith((".ts", ".tsx")):
                full = Path(root) / name
                out.append(str(full.relative_to(_READING_SRC)).replace("\\", "/"))
    return out


def _is_exempt(rel: str) -> bool:
    if rel in _INGEST_EXEMPT:
        return True
    if rel.startswith("modes/WrestleApp/"):
        return True
    if ".test." in rel or "/__tests__/" in rel:
        return True
    return False


def test_expected_open_door_set_is_pinned_and_nonempty():
    """NON-xfail guard: the OPEN-door set SPR-09 must satisfy is pinned here."""
    assert len(EXPECTED_OPEN_DOORS) >= 11
    for d in (
        "DocumentsIndex.open",
        "CommandPalette.openDocument",
        "ChunkModal.openInDocument",
    ):
        assert d in EXPECTED_OPEN_DOORS


def test_every_open_door_routes_to_the_one_reader():
    """(a) Every OPEN door routes to the one Reader via openDocument."""
    for door, rel in _DOOR_FILE.items():
        src = _read_src(rel)
        assert not re.search(r"navigate\([`'\"]/wrestle/\$\{", src), door
        assert not re.search(r"navigate\([`'\"]/wrestle/:", src), door
        assert not re.search(r"path:\s*[`'\"]/wrestle/\$\{", src), door
        if door in _PALETTE_ROUTE_DOORS:
            assert re.search(
                r"/read/\$\{encodeURIComponent\(doc\.document_id\)\}", src
            ), door
        else:
            assert "useOpenDocument()" in src, door
            assert "openDocument(" in src, door

    app = _read_src("App.tsx")
    assert re.search(
        r'path="/read/:documentId"\s+element=\{<BookReader\s*/>\}', app
    )
    reading = _read_src("modes/Reading/index.tsx")
    assert re.search(
        r'import\s+Reader.*from\s+["\']\.\./\.\./components/reader/Reader["\']',
        reading,
    )


def test_forbidden_renderer_set_is_pinned():
    """NON-xfail guard: forbidden DOCUMENT-OPEN seam set is pinned."""
    assert "modes/ResearchWorkstation/MasterMdViewer.tsx::openByIdSeam" in FORBIDDEN_PROD_RENDERERS
    assert "modes/Reading/MetaReading/index.tsx::article" in FORBIDDEN_PROD_RENDERERS
    assert len(FORBIDDEN_PROD_RENDERERS) >= 4
    assert "components/reader/ReadingColumn.tsx" not in FORBIDDEN_PROD_RENDERERS
    assert "components/reader/ReadingColumn.tsx::renderBlocks" not in FORBIDDEN_PROD_RENDERERS


def test_no_second_document_renderer_in_prod_bundle():
    """(b) No second document renderer is reachable from an OPEN door."""
    master = _read_src("modes/ResearchWorkstation/MasterMdViewer.tsx")
    assert "openPdfPanel(" not in master
    assert not re.search(r'from\s+["\'][^"\']*workspace/actions["\']', master)
    assert "useOpenDocument()" in master
    assert "openDocument(chunk.document_id" in master

    meta = _read_src("modes/Reading/MetaReading/index.tsx")
    assert not re.search(r"<article[^>]*whitespace-pre-wrap", meta)
    assert "import ReadingColumn from" in meta
    assert "<ReadingColumn assetId={null} text={deliverable.report}" in meta

    app = _read_src("App.tsx")
    assert 'path="/wrestle/:documentId"' not in app
    legacy = _read_src("AppLegacy.tsx")
    assert 'path="/wrestle/:documentId"' not in legacy
    assert re.search(r'path="/wrestle"\s+element=\{<WrestleApp\s*/>\}', app)

    tree = _read_src("shell/ProjectTree.tsx")
    assert "/wrestle/${" not in tree
    assert "openDocument(n.id" in tree

    drw = _read_src("modes/DeepResearchWorkspace/index.tsx")
    assert "useOpenDocument()" in drw
    assert re.search(r"openDocument\(\s*node\.source_document_id", drw)
    assert "onCiteSource={onCiteSource}" in drw

    hits: list[tuple[str, str]] = []
    for rel in _list_src_files():
        if _is_exempt(rel):
            continue
        src = _read_src(rel)
        for name, pat in _OPEN_BY_ID_SEAM_PATTERNS:
            if pat.search(src):
                hits.append((rel, name))
    assert hits == [], f"open-a-document fork(s) survive:\n{hits}"


def test_forbidden_import_catch_proves_guard_bites():
    """Re-introducing a forbidden openPdfPanel caller is caught (guard is real)."""
    reintroduced = {
        "modes/Notebook/blocks/RegionEmbedBlock.tsx": (
            "onClick={() => openPdfPanel({ documentId, page })}"
        ),
        "modes/WrestleApp/index.tsx": "openPdfPanel({ documentId })",
        "workspace/actions.ts": "export function openPdfPanel(opts) { … }",
        "modes/Library/index.tsx": "openDocument(documentId)",
    }
    caught: list[tuple[str, str]] = []
    for rel, src in reintroduced.items():
        if _is_exempt(rel):
            continue
        for name, pat in _OPEN_BY_ID_SEAM_PATTERNS:
            if pat.search(src):
                caught.append((rel, name))
    assert caught == [("modes/Notebook/blocks/RegionEmbedBlock.tsx", "openPdfPanel(")]


# ───────────────────────────────────────────────────────────────────────────
# Door (c) — ingest → store → serve → render validation round-trip.
# ───────────────────────────────────────────────────────────────────────────

_HTML = b"""<!DOCTYPE html>
<html lang="en"><head>
  <meta charset="utf-8"><title>Conformance Round Trip</title>
</head><body>
  <article>
    <h1>Round Trip Heading</h1>
    <p>First paragraph with enough words to clear the ingest gate threshold so
    the adapter writes the document and chunks it for the conformance test.</p>
    <h2>Subsection</h2>
    <p>Second paragraph adding detail for multiple structured blocks.</p>
    <p>Third paragraph so the word count comfortably clears the minimum.</p>
  </article>
</body></html>"""


class _StubEmbedder:
    def encode(self, text: str) -> list[float]:
        v = [0.0] * 16
        v[abs(hash(text)) % 16] = 1.0
        return v


@pytest.fixture
def temp_substrate(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-spr09-rt-")
    db_path = os.path.join(tmpdir, "graph.duckdb")
    events_dir = os.path.join(tmpdir, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_EVENT_LOG_DIR", events_dir)
    yield {"db_path": db_path}


def test_document_survives_ingest_store_serve_render_round_trip(temp_substrate):
    """(c) Document survives ingest → store → serve with no schema loss."""
    import duckdb

    from acquisition.urls.adapter import ingest_url
    from acquisition.urls.client import FetchedHtml
    from substrate.books.serve import serve_full_text
    from substrate.contracts.document_model import Document

    fetched = FetchedHtml(
        requested_url="https://example.com/conformance-rt",
        final_url="https://example.com/conformance-rt",
        status_code=200,
        content_type="text/html; charset=utf-8",
        charset="utf-8",
        body=_HTML,
    )
    res = ingest_url(
        "https://example.com/conformance-rt",
        investigation_id="inv-spr09",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        fetched=fetched,
    )
    assert res.skipped_reason is None

    con = duckdb.connect(temp_substrate["db_path"], read_only=True)
    try:
        served = serve_full_text(con, res.document_id, owner=True)
    finally:
        con.close()

    assert served.found is True
    assert served.structured_blocks is not None
    assert served.full_text is not None
    assert "Round Trip Heading" in served.full_text

    doc = Document.model_validate_json(served.structured_blocks)
    assert doc.id == res.document_id
    kinds = {b.type for b in doc.blocks}
    assert "heading" in kinds
    assert "paragraph" in kinds

    # Render leg: every block type is known to the Reader gate (SPR-03).
    for block in doc.blocks:
        assert block.type in {
            "heading",
            "paragraph",
            "list",
            "table",
            "code",
            "math",
            "figure",
            "blockquote",
            "footnote",
        }

    # model_dump identity (schema round-trip) on the served form.
    round_tripped = Document.model_validate(doc.model_dump())
    assert round_tripped.model_dump() == doc.model_dump()


def test_document_model_round_trip_leg_is_already_green_today():
    """NON-xfail anchor: schema half of door (c) already proven."""
    from substrate.contracts.document_model import (
        Document,
        HeadingBlock,
        ParagraphBlock,
        TextSpan,
    )

    doc = Document(
        id="rt",
        title="round-trip leg",
        blocks=[
            HeadingBlock(level=1, spans=[TextSpan(text="H")]),
            ParagraphBlock(spans=[TextSpan(text="body")]),
        ],
    )
    assert Document.model_validate(doc.model_dump()).model_dump() == doc.model_dump()


def test_old_lying_conformance_test_is_deleted():
    """The superseded seam test is GONE — not skipped."""
    old = _REPO / "tests" / "test_seam_reader_surface_contract.py"
    assert not old.exists(), (
        "SPR-09 deletes tests/test_seam_reader_surface_contract.py once the real "
        "harness is green"
    )


def test_migration_map_exists_as_the_door_source_of_truth():
    """The migration map is the authoritative OPEN/INGEST door list."""
    if not _MIGRATION_MAP.exists():
        pytest.skip(f"migration map not present at {_MIGRATION_MAP} (spec artifact)")
    text = _MIGRATION_MAP.read_text(encoding="utf-8")
    assert "OPEN" in text and "INGEST" in text
    for door in EXPECTED_OPEN_DOORS:
        assert door in text, f"migration-map.md must name door {door}"