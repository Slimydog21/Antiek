#!/usr/bin/env python3
"""CI gate: fail when ``apps/reading/src/generated/types.ts`` is out of
sync with the Pydantic schemas.

Wire into CI as::

    python tools/codegen/check_staleness.py

Exit codes:
    0 — generated file matches the schema (clean).
    1 — generated file missing or stale. Re-run ``python tools/codegen/emit_types.py``.
    2 — schema introspection failed (genuine bug in schemas; fix before regen).

Why a separate file instead of a pytest test: this runs in CI environments
that may not have pytest installed (deploy pipelines, hook scripts). One
script, two return codes, no test framework.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent))

from tools.codegen import emit_contracts, emit_document_model, emit_types  # noqa: E402

# Each codegen target: a label, the pure render function, the on-disk file,
# the source it's generated from, and the regen command. The events target
# (emit_types) and the contracts target (emit_contracts, antiek-unified SPR-01)
# are checked the same way; the document-model target (emit_document_model,
# antiek-reader SPR-01) joins them — same gate, no second drift mechanism.
_TARGETS = (
    (
        "events",
        emit_types.render,
        emit_types.DEFAULT_OUTPUT,
        "substrate/schemas/events.py",
        "python tools/codegen/emit_types.py",
    ),
    (
        "contracts",
        emit_contracts.render,
        emit_contracts.DEFAULT_OUTPUT,
        "substrate/contracts/",
        "python tools/codegen/emit_contracts.py",
    ),
    (
        "document_model",
        emit_document_model.render,
        emit_document_model.DEFAULT_OUTPUT,
        "substrate/contracts/document_model.py + reading_surface.py",
        "python tools/codegen/emit_document_model.py",
    ),
)


def _check_target(label, render, output, source, regen_cmd) -> int:
    try:
        expected = render()
    except Exception as exc:  # pragma: no cover — surfaces schema bugs
        print(f"FAIL [{label}]: schema introspection raised: {exc}", file=sys.stderr)
        return 2

    if not output.exists():
        print(f"FAIL [{label}]: {output} does not exist.\nRun: {regen_cmd}", file=sys.stderr)
        return 1

    actual = output.read_text(encoding="utf-8")
    if actual != expected:
        import difflib
        diff = "".join(
            difflib.unified_diff(
                actual.splitlines(keepends=True),
                expected.splitlines(keepends=True),
                fromfile=str(output),
                tofile=f"<expected from {source}>",
                n=3,
            )
        )
        if len(diff) > 4000:
            diff = diff[:4000] + "\n... (diff truncated; regen and commit)\n"
        print(
            f"FAIL [{label}]: {output} is stale relative to {source}.\n\n"
            f"Run: {regen_cmd}\n\nDiff:\n{diff}",
            file=sys.stderr,
        )
        return 1

    print(f"OK [{label}]: {output.relative_to(_HERE.parent.parent)} in sync with {source}.")
    return 0


def main() -> int:
    worst = 0
    for target in _TARGETS:
        rc = _check_target(*target)
        worst = max(worst, rc)
    return worst


if __name__ == "__main__":
    sys.exit(main())
