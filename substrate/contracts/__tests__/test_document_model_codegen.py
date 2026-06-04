"""Drift test for the document-model TS codegen (Reader SPR-01 M3).

The gate (spec M3 acceptance): the committed
``apps/reading/src/types/document_model.gen.ts`` is GENERATED FROM the Pydantic
source via the existing codegen path (``emit_document_model`` reusing
``emit_types``' mapper) — a drift test fails if they diverge.

Scope note (intellectual honesty): this test asserts the *document-model*
target is in sync. The repo's other two codegen targets (events, contracts) are
STALE on origin/main@80cc3a4 BEFORE this sprint — a pre-existing docstring-
indentation artifact, NOT introduced here (proven: zero non-docstring lines
differ). ``tests/test_codegen.py::test_committed_ts_matches_current_schema``
already covers/red-flags that whole-repo gate; this test does not paper over it,
it just pins the new target independently so SPR-03/05 inherit a known-clean
document-model contract.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tools.codegen import emit_document_model  # noqa: E402


def test_committed_document_model_ts_matches_source():
    """The committed .gen.ts equals the current render of the Pydantic source.
    Edit the Pydantic model without regenerating → this reds."""
    rendered = emit_document_model.render()
    committed = emit_document_model.DEFAULT_OUTPUT.read_text(encoding="utf-8")
    assert committed == rendered, (
        "document_model.gen.ts is stale relative to document_model.py / "
        "reading_surface.py. Run: python tools/codegen/emit_document_model.py"
    )


def test_render_is_deterministic():
    """Two renders byte-identical — no set/dict iteration nondeterminism that
    the drift gate could not catch."""
    assert emit_document_model.render() == emit_document_model.render()


def test_staleness_checker_passes_for_document_model_target():
    """The shared CI gate (``check_staleness.py``) carries the document_model
    target and reports it OK. We assert on the target's OK line so a pre-existing
    staleness in another target does not mask a real document-model drift."""
    result = subprocess.run(
        [sys.executable, str(_REPO / "tools" / "codegen" / "check_staleness.py")],
        capture_output=True,
        text=True,
    )
    combined = result.stdout + result.stderr
    assert "OK [document_model]" in combined, (
        "check_staleness.py did not report the document_model target as OK.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "FAIL [document_model]" not in combined


def test_generated_header_marks_auto_generated_and_names_regen():
    ts = emit_document_model.render()
    first = ts.splitlines()[0]
    assert "AUTO-GENERATED" in first and "DO NOT EDIT" in first
    assert "python tools/codegen/emit_document_model.py" in ts


def test_every_block_and_span_interface_is_emitted():
    ts = emit_document_model.render()
    for name in (
        # spans
        "TextSpan", "StrongSpan", "EmphasisSpan", "LinkSpan", "CodeSpan",
        "MathSpan", "CitationSpan",
        # blocks
        "HeadingBlock", "ParagraphBlock", "ListItem", "ListBlock", "TableBlock",
        "CodeBlock", "MathBlock", "FigureBlock", "BlockquoteBlock", "FootnoteBlock",
        # document + reading-surface data types
        "DocumentAttribution", "TocEntry", "Document",
        "Region", "RenderedRegion", "AnchoredNote",
    ):
        assert f"export interface {name} {{" in ts, f"missing interface {name}"


def test_named_union_aliases_emitted():
    ts = emit_document_model.render()
    assert "export type InlineSpan =" in ts
    assert "export type Block =" in ts


def test_discriminator_field_is_required_for_narrowing():
    """The ``type`` discriminator must be REQUIRED (no ``?``) so TS can narrow a
    ``Block`` / ``InlineSpan`` on ``.type``. A ``type?:`` would break narrowing."""
    ts = emit_document_model.render()
    assert 'type: "text";' in ts
    assert 'type: "heading";' in ts
    assert "type?:" not in ts  # no optional discriminator anywhere


def test_citation_carries_the_provenance_triple_in_ts():
    """The first-class citation span surfaces source_document_id + chunk_id +
    marker + the optional char range in the generated TS."""
    ts = emit_document_model.render()
    start = ts.index("export interface CitationSpan {")
    end = ts.index("}", start)
    block = ts[start:end]
    for field in ("source_document_id: string;", "chunk_id: string;", "marker: string;"):
        assert field in block, f"CitationSpan missing {field!r}"
    assert "char_start?: number | null;" in block
