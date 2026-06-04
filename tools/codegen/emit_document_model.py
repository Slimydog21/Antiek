#!/usr/bin/env python3
"""Generate the TypeScript document-model types (antiek-reader SPR-01 M3).

Reads ``substrate/contracts/document_model.py`` (+ ``Region`` /
``RenderedRegion`` / ``AnchoredNote`` from ``reading_surface.py``, the
``openDocument`` highlight shape) and emits
``apps/reading/src/types/document_model.gen.ts``.

A SIBLING of ``emit_types.py`` / ``emit_contracts.py`` — it does NOT stand up a
second codegen engine. It REUSES ``emit_types``' pure Python→TS mapper
(``_python_to_ts``) and interface emitter (``_emit_interface``), plus the
discriminated-union-alias hook (``_UNION_ALIASES``) and ``Annotated`` unwrapping
that SPR-01 added to that shared mapper. The drift gate is the SAME one
(``check_staleness.py``), which this target is wired into.

Discipline (mirrors the two existing emitters): the Pydantic models in
``substrate/contracts/document_model.py`` + the three ``reading_surface`` data
types are the single source of truth; this file emits, never imports the TS
side; the generated output is never hand-edited.

Output path note: the spec names ``apps/reading/src/types/document_model.gen.ts``
(distinct from the ``src/generated/`` directory the events/contracts emitters
use) so the Reader's document types sit beside the Reader code that imports
them. The drift gate covers all three targets identically.
"""

from __future__ import annotations

import sys
from pathlib import Path

from pydantic import BaseModel

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import tools.codegen.emit_types as et  # noqa: E402  (reuse the shared mapper)
from substrate.contracts.document_model import (  # noqa: E402
    DOCUMENT_MODEL_SCHEMA_VERSION,
    BlockquoteBlock,
    CitationSpan,
    CodeBlock,
    CodeSpan,
    Document,
    DocumentAttribution,
    EmphasisSpan,
    FigureBlock,
    FootnoteBlock,
    HeadingBlock,
    LinkSpan,
    ListBlock,
    ListItem,
    MathBlock,
    MathSpan,
    ParagraphBlock,
    StrongSpan,
    TableBlock,
    TextSpan,
    TocEntry,
)
from substrate.contracts.reading_surface import (  # noqa: E402
    AnchoredNote,
    Region,
    RenderedRegion,
)

DEFAULT_OUTPUT = _REPO / "apps" / "reading" / "src" / "types" / "document_model.gen.ts"

GENERATED_HEADER = """\
// AUTO-GENERATED — DO NOT EDIT.
//
// Generated from substrate/contracts/document_model.py + reading_surface.py
// by tools/codegen/emit_document_model.py.
// Re-run after any change:   python tools/codegen/emit_document_model.py
// CI gate that fails on drift: python tools/codegen/check_staleness.py
//
// The Pydantic models are the single source of truth. This is the typed-block
// document the one <Reader> renders and openDocument resolves to (antiek-reader
// SPR-01). The InlineSpan / Block discriminated unions narrow on `type`.
"""

# Inline span members, in declaration order (must precede the InlineSpan alias).
_SPAN_MODELS: tuple[type[BaseModel], ...] = (
    TextSpan,
    StrongSpan,
    EmphasisSpan,
    LinkSpan,
    CodeSpan,
    MathSpan,
    CitationSpan,
)

# Block members, in declaration order (must precede the Block alias). ``ListItem``
# is the structural child of ``ListBlock`` (emitted, but not a union member).
_BLOCK_MODELS: tuple[type[BaseModel], ...] = (
    HeadingBlock,
    ParagraphBlock,
    ListBlock,
    TableBlock,
    CodeBlock,
    MathBlock,
    FigureBlock,
    BlockquoteBlock,
    FootnoteBlock,
)

# Standalone / nested support models.
_SUPPORT_MODELS: tuple[type[BaseModel], ...] = (
    ListItem,
    DocumentAttribution,
    TocEntry,
    Region,
    RenderedRegion,
    AnchoredNote,
)

_SPAN_NAMES = frozenset(m.__name__ for m in _SPAN_MODELS)
_BLOCK_NAMES = frozenset(m.__name__ for m in _BLOCK_MODELS)

# Every model name that may be cross-referenced by a field.
_ALL_MODELS: tuple[type[BaseModel], ...] = (
    _SPAN_MODELS + _BLOCK_MODELS + _SUPPORT_MODELS + (Document,)
)


def render() -> str:
    """Render the complete document-model TS module. Pure function — the
    staleness check compares this against the on-disk file.

    The discriminated-union aliases (``InlineSpan`` / ``Block``) and the set of
    "known" model names this emitter needs live on ``emit_types``' SHARED module
    globals (``_UNION_ALIASES`` / ``_KNOWN_NESTED_NAMES``). We register ours for
    the duration of the render and RESTORE the originals in ``finally`` so a
    future third emitter that reuses ``emit_types`` does not silently inherit
    document_model's aliases (and so re-running this emitter is idempotent)."""
    # Snapshot the shared globals so we can restore them — never leak our
    # registrations into the shared mapper.
    saved_aliases = dict(et._UNION_ALIASES)
    saved_known = set(et._KNOWN_NESTED_NAMES)
    try:
        # Register the discriminated-union aliases so a field typed
        # ``list[InlineSpan]`` / ``list[Block]`` emits the alias name, and
        # register every model name as "known" so cross-references resolve.
        et._UNION_ALIASES[_SPAN_NAMES] = "InlineSpan"
        et._UNION_ALIASES[_BLOCK_NAMES] = "Block"
        for m in _ALL_MODELS:
            et._KNOWN_NESTED_NAMES.add(m.__name__)

        lines: list[str] = [GENERATED_HEADER]
        lines.append(
            f"export const DOCUMENT_MODEL_SCHEMA_VERSION = {DOCUMENT_MODEL_SCHEMA_VERSION};"
        )

        # Span interfaces, then the InlineSpan alias.
        for model in _SPAN_MODELS:
            et._emit_interface(model, lines)
        lines.append("")
        lines.append("/** Inline span — narrow on `type`. */")
        lines.append("export type InlineSpan =\n  | " + "\n  | ".join(m.__name__ for m in _SPAN_MODELS) + ";")

        # ListItem (structural child of ListBlock) must precede the block
        # interfaces that reference it.
        et._emit_interface(ListItem, lines)

        # Block interfaces, then the Block alias.
        for model in _BLOCK_MODELS:
            et._emit_interface(model, lines)
        lines.append("")
        lines.append("/** Block — narrow on `type`. */")
        lines.append("export type Block =\n  | " + "\n  | ".join(m.__name__ for m in _BLOCK_MODELS) + ";")

        # Document + attribution + ToC + the reading-surface data types.
        for model in (DocumentAttribution, TocEntry, Document, Region, RenderedRegion, AnchoredNote):
            et._emit_interface(model, lines)

        return "\n".join(lines) + "\n"
    finally:
        # Restore the shared globals to exactly what we found.
        et._UNION_ALIASES.clear()
        et._UNION_ALIASES.update(saved_aliases)
        et._KNOWN_NESTED_NAMES.clear()
        et._KNOWN_NESTED_NAMES.update(saved_known)


def write(output_path: Path | None = None) -> Path:
    out = output_path or DEFAULT_OUTPUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(), encoding="utf-8")
    return out


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="Emit TypeScript document-model types")
    p.add_argument("--output", "-o", type=Path, default=None)
    p.add_argument("--stdout", action="store_true")
    args = p.parse_args()
    if args.stdout:
        print(render(), end="")
        return 0
    written = write(args.output)
    print(f"wrote {written}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
