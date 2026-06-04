"""The conformance-harness CONTRACT — the tests SPR-09 will fill (Reader SPR-01 M4).

The current conformance test (``tests/test_seam_reader_surface_contract.py``) is
green-but-lying: it checks two throwaway in-test classes against the (now ex-)
``Any``-typed Protocol; it never touches the real renderers. This file PINS, as
``xfail`` stubs with PRECISE assertions, what the REAL SPR-09 conformance test
must prove — so SPR-09 cannot quietly weaken it into a vague "test convergence."

These stubs DO NOT pass today (the surfaces they assert against — the one
``<Reader>``, the deleted renderers — do not exist until SPR-03/05). Each is
``xfail(strict=False)`` with a reason naming the sprint that unblocks it. SPR-09
turns each ``xfail`` into a real, green assertion and deletes the lying test.

The three doors SPR-09 must prove (master spec architecture §3, "one door"):
  (a) every door in ``migration-map.md`` routes to the one ``<Reader>``;
  (b) no second document renderer is importable in the production bundle;
  (c) a ``Document`` survives ingest → store → serve → render round-trip.

The Python side (this file) owns (c) — the substrate round-trip — plus the
machine-checkable half of (a)/(b) that lives in the migration map. The
TS/bundle half of (a)/(b) lives in
``apps/reading/src/__tests__/oneReader.conformance.test.ts``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_MIGRATION_MAP = (
    Path.home() / "specs" / "antiek-reader" / "migration-map.md"
)


# ───────────────────────────────────────────────────────────────────────────
# Door (a) — every door routes to the one Reader.
#
# The authoritative door list is ``migration-map.md``. SPR-09 asserts every row
# tagged OPEN routes through ``openDocument`` → the one ``<Reader>``. SPR-01
# pins the EXACT door set so SPR-09 cannot drop one to make the test pass.
# ───────────────────────────────────────────────────────────────────────────


# The exhaustive OPEN-door set SPR-09 must prove routes to the one Reader.
# (Cross-checked against migration-map.md; an OPEN door dropped from this set
# is a weakened gate.) Names are the door identifiers used in the map.
EXPECTED_OPEN_DOORS: frozenset[str] = frozenset(
    {
        "Library.openWork",  # modes/Library/index.tsx
        "LibraryView.open",  # components/library/LibraryView.tsx
        "Reading.openDoc",  # modes/Reading/index.tsx
        "DocumentsIndex.open",  # modes/DocumentsIndex/index.tsx (today → /wrestle)
        "CommandPalette.openDocument",  # components/CommandPalette.tsx (today → /wrestle)
        "ChunkModal.openInDocument",  # modes/ResearchWorkstation/ChunkModal.tsx (today → /wrestle)
        "MasterMdViewer.cmdClick",  # modes/ResearchWorkstation/MasterMdViewer.tsx
        "DRW.citeSource",  # modes/DeepResearchWorkspace/index.tsx (BlockCard detail)
        "Write.traceToSource",  # modes/Write/Editor/Citation.tsx + Xray.tsx + WriteHome.tsx
        "MetaReading.openCitation",  # modes/Reading/MetaReading/index.tsx
        "Route./read/:documentId",  # App.tsx — the canonical Reader route
    }
)


@pytest.mark.xfail(
    reason="SPR-05 routes every door through openDocument; SPR-09 asserts it. "
    "The one <Reader> and the routed doors do not exist yet.",
    strict=False,
)
def test_every_open_door_routes_to_the_one_reader():
    """(a) Every OPEN door routes to the one Reader via openDocument. SPR-09
    fills this by parsing each door's call site and asserting it calls
    openDocument (not navigate('/wrestle/...') and not a bespoke renderer)."""
    # SPR-09: for each door in EXPECTED_OPEN_DOORS, assert its source call site
    # invokes openDocument(documentId, ...). Today: unimplemented.
    raise NotImplementedError("SPR-09 fills door (a) against the routed call sites")


def test_expected_open_door_set_is_pinned_and_nonempty():
    """NON-xfail guard: the OPEN-door set SPR-09 must satisfy is pinned here so
    SPR-09 cannot silently shrink it. This passes today (it asserts on the
    constant, not on the surfaces) — its job is to make a weakening visible."""
    assert len(EXPECTED_OPEN_DOORS) >= 11
    # The three doors that TODAY mis-route to /wrestle (the convergence target).
    for d in (
        "DocumentsIndex.open",
        "CommandPalette.openDocument",
        "ChunkModal.openInDocument",
    ):
        assert d in EXPECTED_OPEN_DOORS


# ───────────────────────────────────────────────────────────────────────────
# Door (b) — no second document renderer is importable in the prod bundle.
# ───────────────────────────────────────────────────────────────────────────


# The renderers SPR-05 deletes / folds into the one Reader. SPR-09 asserts NONE
# of these is importable in the production bundle (a forbidden-import check).
# ``WrestleApp``/``PdfViewer`` survive ONLY behind the ingest entry point, never
# as an open-a-document renderer — SPR-09 encodes that nuance.
FORBIDDEN_PROD_RENDERERS: frozenset[str] = frozenset(
    {
        "components/reader/ReadingColumn.tsx::renderBlocks",  # the 24-line flattener
        "modes/ResearchWorkstation/MasterMdViewer.tsx",  # cannot open by id
        "modes/Reading/MetaReading/index.tsx::article",  # bespoke <article>
        "modes/DeepResearchWorkspace/index.tsx::canvasTextDiv",  # ad-hoc text div
    }
)


@pytest.mark.xfail(
    reason="SPR-05 deletes the redundant renderers; SPR-09 asserts none is "
    "importable in the prod bundle. They still exist today.",
    strict=False,
)
def test_no_second_document_renderer_in_prod_bundle():
    """(b) No second document renderer is importable in the production bundle.
    SPR-09 fills this by asserting the built bundle imports none of
    FORBIDDEN_PROD_RENDERERS (mirrors the TS-side bundle check)."""
    raise NotImplementedError("SPR-09 fills door (b) against the built bundle")


def test_forbidden_renderer_set_is_pinned():
    """NON-xfail guard: the renderer-deletion set is pinned so SPR-09 cannot
    quietly omit one and let a fork survive."""
    assert "components/reader/ReadingColumn.tsx::renderBlocks" in FORBIDDEN_PROD_RENDERERS
    assert "modes/ResearchWorkstation/MasterMdViewer.tsx" in FORBIDDEN_PROD_RENDERERS
    assert len(FORBIDDEN_PROD_RENDERERS) >= 4


# ───────────────────────────────────────────────────────────────────────────
# Door (c) — a Document survives ingest → store → serve → render round-trip.
# ───────────────────────────────────────────────────────────────────────────


@pytest.mark.xfail(
    reason="SPR-02 emits the Document at ingest and SPR-03 renders it; SPR-09 "
    "asserts the full ingest→store→serve→render round-trip. The ingest emitter "
    "and the Reader do not exist yet.",
    strict=False,
)
def test_document_survives_ingest_store_serve_render_round_trip():
    """(c) A Document survives ingest → store → serve → render with no loss.
    SPR-09 fills this: ingest a real source → assert the stored+served body is a
    valid ``Document`` whose ``model_dump()`` round-trips and whose served form
    (through the §9.0 gate) renders every block type. The CONTRACT-level
    round-trip (model_dump identity) is ALREADY proven by
    ``test_document_model.py``; this stub pins the END-TO-END leg SPR-09 adds."""
    raise NotImplementedError(
        "SPR-09 fills door (c) end-to-end once ingest (SPR-02) + Reader (SPR-03) land"
    )


def test_document_model_round_trip_leg_is_already_green_today():
    """NON-xfail anchor: the schema half of door (c) — that a Document round-trips
    — is ALREADY proven (test_document_model.py). SPR-09 only adds the
    store→serve→render legs on top; it does not need to re-prove the schema."""
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


# ───────────────────────────────────────────────────────────────────────────
# Supersession breadcrumb — the lying test is annotated, not deleted, by SPR-01.
# ───────────────────────────────────────────────────────────────────────────


def test_old_lying_conformance_test_is_annotated_as_superseded():
    """The old conformance test (``tests/test_seam_reader_surface_contract.py``)
    is annotated SUPERSEDED by SPR-01 (its docstring + the xfail'd ownership
    assertion), NOT deleted — SPR-09 deletes it once this real harness is green.
    This guards the breadcrumb so a future edit cannot silently drop it."""
    old = (_REPO / "tests" / "test_seam_reader_surface_contract.py").read_text(encoding="utf-8")
    assert "SUPERSEDED" in old
    assert "SPR-09 deletes this file" in old


def test_migration_map_exists_as_the_door_source_of_truth():
    """The migration map is the authoritative OPEN/INGEST door list door (a)
    consumes. It lives outside the worktree (a spec artifact). If it is missing
    here, SPR-09's door (a) has no source of truth — skip rather than fail in a
    checkout that does not include the spec dir."""
    if not _MIGRATION_MAP.exists():
        pytest.skip(f"migration map not present at {_MIGRATION_MAP} (spec artifact)")
    text = _MIGRATION_MAP.read_text(encoding="utf-8")
    assert "OPEN" in text and "INGEST" in text
