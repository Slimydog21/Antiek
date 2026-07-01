#!/usr/bin/env python3
"""Generate TypeScript types for ``substrate.contracts`` (antiek-unified
SPR-01 M6).

A sibling of ``emit_types.py`` (which emits the event schema). Rather than
duplicate the ~100-line Python→TS type-mapper — which would drift — this reuses
``emit_types``' pure mapper (``_python_to_ts``) and interface emitter
(``_emit_interface``), and emits the *contract* models to a separate output
file: ``apps/reading/src/generated/contracts.ts``.

Why a separate emitter, not an edit to ``emit_types.py`` (a noted SPR-01
mid-flight decision): events and contracts are independent surfaces with
independent schema versions; keeping their emitters separate keeps the two
generated files independently regenerable and avoids touching the
parallel-stream-modified ``emit_types.py`` more than importing its helpers.

Discipline mirrors ``emit_types.py``: the Pydantic contract models are the
single source of truth; this file emits, never imports the TS side; the
generated output is never hand-edited; ``check_staleness.py`` enforces it.

The provisional ``ReaderSurfaceContract`` is a ``Protocol`` (behavior, not
data) and is intentionally excluded — only ``CODEGEN_CONTRACTS`` (the Pydantic
data models) are emitted, and provisional ones are marked with a TS comment.
"""

from __future__ import annotations

import dataclasses
import inspect
import json
import sys
from pathlib import Path
from typing import get_type_hints

from pydantic import BaseModel

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import tools.codegen.emit_types as et  # noqa: E402  (reuse the type-mapper)
from substrate.ad_inventory.frame_attention import (  # noqa: E402
    FRAME_TELEMETRY_SCHEMA_VERSION,
    VALID_LENSES,
    FrameAttentionSample,
    FrameSecond,
)
from substrate.contracts import CONTRACT_SCHEMA_VERSION  # noqa: E402
from substrate.contracts.accrual import AccrualContract  # noqa: E402
from substrate.contracts.context_pack import (  # noqa: E402
    AssembledLayerContract,
    ContextPackContract,
)
from substrate.contracts.interviewer import (  # noqa: E402
    ConsentContract,
    EconomicsCellContract,
    InterviewerResultContract,
)
from substrate.contracts.nodes import InsightNodeContract, QuestionNodeContract  # noqa: E402
from substrate.contracts.note_taker import NoteTakerOutputContract  # noqa: E402
from substrate.contracts.outline_block import OutlineBlockContract  # noqa: E402
from substrate.contracts.servable import ServableEntryContract  # noqa: E402

DEFAULT_OUTPUT = _REPO / "apps" / "reading" / "src" / "generated" / "contracts.ts"

GENERATED_HEADER = """\
// AUTO-GENERATED — DO NOT EDIT.
//
// Generated from substrate/contracts/ and substrate/ad_inventory/frame_attention.py
// by tools/codegen/emit_contracts.py.
// Re-run after any contract change:  python tools/codegen/emit_contracts.py
// CI gate that fails on drift:        python tools/codegen/check_staleness.py
//
// The Pydantic models in substrate/contracts/ and the frame-attention
// dataclasses in substrate/ad_inventory/frame_attention.py are the single
// sources of truth. These are the cross-workflow contracts the four products
// (Research/Read/Write/Speak) build against. The provisional
// ReaderSurfaceContract is a Python Protocol (behavior, not data) and is
// intentionally not emitted here.
"""

# Emit order: referent (nested) models before the models that reference them.
# AssembledLayerContract is nested inside ContextPackContract.
CONTRACT_MODELS: tuple[type[BaseModel], ...] = (
    AssembledLayerContract,
    InsightNodeContract,
    QuestionNodeContract,
    NoteTakerOutputContract,
    ContextPackContract,
    OutlineBlockContract,
    ServableEntryContract,
    AccrualContract,
    InterviewerResultContract,
    ConsentContract,
    EconomicsCellContract,
)

TELEMETRY_MODELS: tuple[type, ...] = (
    FrameAttentionSample,
    FrameSecond,
)

# Contracts whose owning sprint has not pinned the shape — emitted with a
# provisional marker comment so a TS consumer knows the shape may move.
_PROVISIONAL: frozenset[str] = frozenset(
    {"InterviewerResultContract", "ConsentContract"}
)


def _emit_frame_telemetry_constants(lines: list[str]) -> None:
    lines.append("")
    lines.append("// Frame-attention telemetry input contract. Source of truth:")
    lines.append("// substrate/ad_inventory/frame_attention.py")
    lines.append(
        "export const FRAME_TELEMETRY_SCHEMA_VERSION = "
        f"{json.dumps(FRAME_TELEMETRY_SCHEMA_VERSION)};"
    )
    lenses = ", ".join(json.dumps(lens) for lens in sorted(VALID_LENSES))
    lines.append(f"export const VALID_LENSES = [{lenses}] as const;")
    lines.append("export type Lens = (typeof VALID_LENSES)[number];")


def _emit_dataclass_interface(model: type, lines: list[str]) -> None:
    name = model.__name__
    docstring = inspect.cleandoc(model.__doc__ or "")
    lines.append("")
    if docstring:
        lines.append("/**")
        for d_line in docstring.splitlines():
            stripped = d_line.rstrip()
            lines.append(f" * {stripped}" if stripped else " *")
        lines.append(" */")
    lines.append(f"export interface {name} {{")
    hints = get_type_hints(model)
    for field in dataclasses.fields(model):
        annotation = hints[field.name]
        is_opt, _ = et._is_optional(annotation)
        if model is FrameSecond and field.name == "lens":
            ts_type = "Lens"
        else:
            ts_type = et._python_to_ts(
                annotation,
                field_name=field.name,
                model_name=name,
            )
        suffix = "?" if is_opt else ""
        lines.append(f"  {field.name}{suffix}: {ts_type};")
    lines.append("}")


def _emit_window_frame_batch_inbound(lines: list[str]) -> None:
    lines.append("")
    lines.append("/**")
    lines.append(" * The compact per-window batch the SPR-07 emitter flushes.")
    lines.append(" *")
    lines.append(" * Client-inbound frame-telemetry-v2 shape: the browser sends")
    lines.append(" * attention only. ``ad_value_usd_cents`` is deliberately absent")
    lines.append(" * because the server mints/prices the window before constructing")
    lines.append(" * the server-side ``WindowFrameBatch`` dataclass.")
    lines.append(" */")
    lines.append("export interface WindowFrameBatch {")
    lines.append("  window_id: string;")
    lines.append("  seconds: FrameSecond[];")
    lines.append("  schema_version: string;")
    lines.append("}")


def render() -> str:
    """Render the complete contracts TS module as a string. Pure function —
    the staleness check compares this against the on-disk file."""
    # Register every contract name as a "known" model so cross-references
    # (ContextPackContract -> AssembledLayerContract, WindowFrameBatch ->
    # FrameSecond) resolve in the mapper.
    for m in (*CONTRACT_MODELS, *TELEMETRY_MODELS):
        et._KNOWN_NESTED_NAMES.add(m.__name__)

    lines: list[str] = [GENERATED_HEADER]
    lines.append(f"export const CONTRACT_SCHEMA_VERSION = {CONTRACT_SCHEMA_VERSION};")
    _emit_frame_telemetry_constants(lines)

    for model in CONTRACT_MODELS:
        if model.__name__ in _PROVISIONAL:
            lines.append("")
            lines.append(
                f"// PROVISIONAL — {model.__name__}'s owning sprint has not "
                "pinned this shape; it may change."
            )
        et._emit_interface(model, lines)

    for model in TELEMETRY_MODELS:
        _emit_dataclass_interface(model, lines)
    _emit_window_frame_batch_inbound(lines)

    return "\n".join(lines) + "\n"


def write(output_path: Path | None = None) -> Path:
    out = output_path or DEFAULT_OUTPUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(), encoding="utf-8")
    return out


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="Emit TypeScript types from contract schemas")
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
