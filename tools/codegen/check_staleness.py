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

from tools.codegen.emit_types import DEFAULT_OUTPUT, render  # noqa: E402


def main() -> int:
    try:
        expected = render()
    except Exception as exc:  # pragma: no cover — surfaces schema bugs
        print(f"FAIL: schema introspection raised: {exc}", file=sys.stderr)
        return 2

    if not DEFAULT_OUTPUT.exists():
        print(
            f"FAIL: {DEFAULT_OUTPUT} does not exist.\n"
            f"Run: python tools/codegen/emit_types.py",
            file=sys.stderr,
        )
        return 1

    actual = DEFAULT_OUTPUT.read_text(encoding="utf-8")
    if actual != expected:
        # Show a tiny diff hint so the CI log is useful.
        import difflib
        diff = "".join(
            difflib.unified_diff(
                actual.splitlines(keepends=True),
                expected.splitlines(keepends=True),
                fromfile=str(DEFAULT_OUTPUT),
                tofile="<expected from schemas>",
                n=3,
            )
        )
        # Cap the diff so a wholesale regeneration doesn't flood the log.
        if len(diff) > 4000:
            diff = diff[:4000] + "\n... (diff truncated; regen and commit)\n"
        print(
            f"FAIL: {DEFAULT_OUTPUT} is stale relative to "
            "substrate/schemas/events.py.\n\n"
            f"Run: python tools/codegen/emit_types.py\n\n"
            f"Diff:\n{diff}",
            file=sys.stderr,
        )
        return 1

    print(f"OK: {DEFAULT_OUTPUT.relative_to(_HERE.parent.parent)} in sync with schemas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
