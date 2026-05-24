"""
Run every heresy detector against a set of files.

Two entry points:

  ``python -m tools.heresy_detectors.run_all <file> <file> ...``
      Use this from ``.githooks/pre-commit`` (which passes the staged
      Python files). Exit code is non-zero if any blocking detector
      found a violation; warn-only detectors print to stderr but never
      flip the exit code by themselves.

  ``python -m tools.heresy_detectors.run_all --all``
      Scan every ``*.py`` file tracked by git. Useful for periodic
      audits and for CI's full-repo sweep.

Environment toggles:

  ``ANTIEK_HERESY_SKIP=1`` — exit 0 unconditionally, but print a clear
  notice to stderr. Designed as the operator's per-commit override
  knob (``ANTIEK_HERESY_SKIP=1 git commit ...``). The notice is
  intentionally visible so periodic audits of skip-rate are possible
  via ``grep`` over operator session logs.
"""

from __future__ import annotations

import argparse
import importlib
import os
import subprocess
import sys
from typing import Iterable, List, Sequence, Tuple

from ._common import Violation

# (module name, detector ID). Order is the canonical reporting order.
_DETECTORS: Sequence[Tuple[str, str]] = (
    ("tools.heresy_detectors.h001_single_writer_syntheses", "H-001"),
    ("tools.heresy_detectors.h002_missing_db_lock", "H-002"),
    ("tools.heresy_detectors.h003_fake_quack_db", "H-003"),
    ("tools.heresy_detectors.h004_unobservable_spawn", "H-004"),
)


def _all_tracked_python_files() -> List[str]:
    """Return every Python file tracked by git (i.e. excluding venv, build)."""
    out = subprocess.run(
        ["git", "ls-files", "*.py"],
        capture_output=True, text=True, check=True,
    )
    return [line for line in out.stdout.splitlines() if line.endswith(".py")]


def _run_one(module_name: str, files: Iterable[str]) -> Tuple[str, List[Violation]]:
    """Import the detector module and call its ``run`` function. Returns the
    detector's MODE and the list of violations.
    """
    mod = importlib.import_module(module_name)
    return mod.MODE, mod.run(list(files))


def main(argv: Sequence[str] | None = None) -> int:
    if os.environ.get("ANTIEK_HERESY_SKIP") in ("1", "true", "yes"):
        print(
            "heresy_detectors: skipped (ANTIEK_HERESY_SKIP set). "
            "Operator override — audit periodically.",
            file=sys.stderr,
        )
        return 0

    parser = argparse.ArgumentParser(
        description="Run Antiek heresy detectors against staged or all tracked Python files.",
    )
    parser.add_argument(
        "files", nargs="*",
        help="Python files to check. Defaults to nothing — pass --all "
             "or pre-commit-supplied file list.",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Scan every Python file tracked by git.",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Emit machine-readable JSON instead of human-readable text.",
    )
    args = parser.parse_args(argv)

    files: List[str]
    if args.all:
        files = _all_tracked_python_files()
    else:
        files = list(args.files)

    if not files:
        # Empty stage = nothing to do; not an error.
        return 0

    blocking_violations: List[Violation] = []
    warn_violations: List[Violation] = []

    for mod_name, _hid in _DETECTORS:
        mode, viols = _run_one(mod_name, files)
        if mode == "blocking":
            blocking_violations.extend(viols)
        else:
            warn_violations.extend(viols)

    if args.json:
        import json
        print(json.dumps({
            "blocking": [v.__dict__ for v in blocking_violations],
            "warn_only": [v.__dict__ for v in warn_violations],
        }, indent=2))
    else:
        for v in warn_violations:
            print(f"[WARN-ONLY] {v.render()}", file=sys.stderr)
        for v in blocking_violations:
            print(v.render(), file=sys.stderr)
        if blocking_violations:
            print(
                f"\nheresy_detectors: {len(blocking_violations)} blocking "
                f"violation(s) found. Fix or add a per-line "
                "# noqa: H00N -- <reason ≥12 chars> escape hatch. "
                "Operator override: ANTIEK_HERESY_SKIP=1 git commit ...",
                file=sys.stderr,
            )

    return 1 if blocking_violations else 0


if __name__ == "__main__":
    sys.exit(main())
