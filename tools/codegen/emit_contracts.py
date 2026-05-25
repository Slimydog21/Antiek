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

import sys
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import tools.codegen.emit_types as et  # noqa: E402  (reuse the type-mapper)
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
// Generated from substrate/contracts/ by tools/codegen/emit_contracts.py.
// Re-run after any contract change:  python tools/codegen/emit_contracts.py
// CI gate that fails on drift:        python tools/codegen/check_staleness.py
//
// The Pydantic models in substrate/contracts/ are the single source of truth.
// These are the cross-workflow contracts the four products (Research/Read/
// Write/Speak) build against. The provisional ReaderSurfaceContract is a
// Python Protocol (behavior, not data) and is intentionally not emitted here.
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

# Contracts whose owning sprint has not pinned the shape — emitted with a
# provisional marker comment so a TS consumer knows the shape may move.
_PROVISIONAL: frozenset[str] = frozenset(
    {"InterviewerResultContract", "ConsentContract"}
)


def render() -> str:
    """Render the complete contracts TS module as a string. Pure function —
    the staleness check compares this against the on-disk file."""
    # Register every contract name as a "known" model so cross-references
    # (ContextPackContract → AssembledLayerContract) resolve in the mapper.
    for m in CONTRACT_MODELS:
        et._KNOWN_NESTED_NAMES.add(m.__name__)

    lines: list[str] = [GENERATED_HEADER]
    lines.append(f"export const CONTRACT_SCHEMA_VERSION = {CONTRACT_SCHEMA_VERSION};")

    for model in CONTRACT_MODELS:
        if model.__name__ in _PROVISIONAL:
            lines.append("")
            lines.append(
                f"// PROVISIONAL — {model.__name__}'s owning sprint has not "
                "pinned this shape; it may change."
            )
        et._emit_interface(model, lines)

    return "\n".join(lines) + "\n"


def write(output_path: Optional[Path] = None) -> Path:
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
