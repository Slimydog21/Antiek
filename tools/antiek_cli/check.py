"""``antiek check`` — consolidated verification entry point.

ARE-09 of the Antiek Rust-Execution Spec. The Cargo-equivalent for
Antiek: one CLI wrapping ruff, the two ASR lints, mypy, pytest,
doctest, property tests, and the substrate invariants suite under named
subcommands. Built on argparse (stdlib) so no new dep is introduced.

The CLI does NOT modify any existing tool configuration — it composes
what's already in the venv. Today's CI workflow is unchanged; the
operator decides if/when to refactor CI to delegate to
``antiek check all``.

Usage::

    python -m tools.antiek_cli check --help
    python -m tools.antiek_cli check lint --scope substrate/
    python -m tools.antiek_cli check types --scope substrate/results.py --strict
    python -m tools.antiek_cli check tests --scope tests/test_results.py
    python -m tools.antiek_cli check doctest --scope substrate/
    python -m tools.antiek_cli check props
    python -m tools.antiek_cli check invariants
    python -m tools.antiek_cli check all --scope substrate/

Each subcommand exits 0 on success, non-zero on failure. ``all`` runs
each stage in order and stops at first failure unless
``--continue-on-error`` is set.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "StageResult",
    "run_lint",
    "run_types",
    "run_tests",
    "run_doctest",
    "run_props",
    "run_invariants",
    "main",
    "RUNNERS",
    "ALL_ORDER",
    "DEFAULT_SCOPE",
    "PROJECT_ROOT",
]


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCOPE = "substrate/"


@dataclass
class StageResult:
    name: str
    rc: int
    elapsed_s: float
    skipped_reason: str | None = None

    @property
    def is_pass(self) -> bool:
        return self.rc == 0

    @property
    def is_skip(self) -> bool:
        return self.rc == -1

    @property
    def is_fail(self) -> bool:
        return self.rc not in (0, -1)

    def format_report_line(self) -> str:
        if self.is_skip:
            return f"[stage] {self.name:<10} SKIP ({self.skipped_reason})"
        status = "PASS" if self.is_pass else "FAIL"
        return f"[stage] {self.name:<10} {status} ({self.elapsed_s:.2f}s)"


def _run(name: str, argv: Sequence[str], cwd: Path = PROJECT_ROOT) -> StageResult:
    t0 = time.monotonic()
    try:
        proc = subprocess.run(argv, cwd=cwd, check=False)
    except FileNotFoundError as exc:
        return StageResult(
            name=name, rc=127, elapsed_s=time.monotonic() - t0,
            skipped_reason=f"tool not found: {exc.filename}",
        )
    return StageResult(name=name, rc=proc.returncode, elapsed_s=time.monotonic() - t0)


def run_lint(scope: str, strict: bool = False) -> StageResult:
    """Run ruff + the two AST lints. Short-circuits at first failure."""
    r1 = _run("lint:ruff", ["./.venv/bin/ruff", "check", scope])
    if r1.rc != 0:
        return StageResult(name="lint", rc=r1.rc, elapsed_s=r1.elapsed_s)
    r2 = _run("lint:no_raise",
              ["./.venv/bin/python", "-m",
               "tools.lints.no_raise_in_substrate_writers", scope])
    if r2.rc != 0:
        return StageResult(name="lint", rc=r2.rc,
                           elapsed_s=r1.elapsed_s + r2.elapsed_s)
    r3 = _run("lint:bypass",
              ["./.venv/bin/python", "-m",
               "tools.lints.unannotated_bypass", scope])
    return StageResult(name="lint", rc=r3.rc,
                       elapsed_s=r1.elapsed_s + r2.elapsed_s + r3.elapsed_s)


def run_types(scope: str, strict: bool = False) -> StageResult:
    argv = ["./.venv/bin/mypy"]
    if strict:
        argv.append("--strict")
    argv.append(scope)
    return _run("types", argv)


def run_tests(scope: str, strict: bool = False) -> StageResult:
    return _run("tests", ["./.venv/bin/python", "-m", "pytest", scope, "-q"])


def run_doctest(scope: str, strict: bool = False) -> StageResult:
    return _run("doctest",
                ["./.venv/bin/python", "-m", "pytest",
                 "--doctest-modules", scope, "-q"])


def run_props(scope: str, strict: bool = False) -> StageResult:
    props_dir = PROJECT_ROOT / "tests" / "properties"
    if not props_dir.exists():
        return StageResult(name="props", rc=-1, elapsed_s=0.0,
                           skipped_reason="no tests/properties/")
    return _run("props",
                ["./.venv/bin/python", "-m", "pytest", str(props_dir), "-q"])


def run_invariants(scope: str, strict: bool = False) -> StageResult:
    invariants_path = PROJECT_ROOT / "substrate" / "invariants.py"
    if not invariants_path.exists():
        return StageResult(
            name="invariants", rc=-1, elapsed_s=0.0,
            skipped_reason="substrate/invariants.py absent on this branch",
        )
    return _run("invariants",
                ["./.venv/bin/python", "-m", "substrate.invariants"])


RUNNERS = {
    "lint": run_lint,
    "types": run_types,
    "tests": run_tests,
    "doctest": run_doctest,
    "props": run_props,
    "invariants": run_invariants,
}

ALL_ORDER = ("lint", "types", "tests", "doctest", "props", "invariants")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="antiek-check",
        description="Consolidated verification entry point for Antiek substrate.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in (*RUNNERS.keys(), "all"):
        sp = sub.add_parser(name, help=f"run the {name} stage")
        sp.add_argument("--scope", default=DEFAULT_SCOPE,
                        help=f"target path; default {DEFAULT_SCOPE!r}")
        sp.add_argument("--strict", action="store_true",
                        help="enable strict mode (mypy --strict)")
        if name == "all":
            sp.add_argument("--continue-on-error", action="store_true",
                            help="run every stage even if an earlier one fails")
    return parser


def _run_all(scope: str, strict: bool, continue_on_error: bool) -> int:
    results: list[StageResult] = []
    for stage_name in ALL_ORDER:
        result = RUNNERS[stage_name](scope, strict=strict)
        print(result.format_report_line())
        results.append(result)
        if result.is_fail and not continue_on_error:
            break

    n_pass = sum(1 for r in results if r.is_pass)
    n_fail = sum(1 for r in results if r.is_fail)
    n_skip = sum(1 for r in results if r.is_skip)
    overall = "PASS" if n_fail == 0 else "FAIL"
    print(f"\nSummary: {n_pass} pass, {n_fail} fail, {n_skip} skip — overall {overall}")
    return 0 if n_fail == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "all":
        return _run_all(scope=args.scope, strict=args.strict,
                        continue_on_error=args.continue_on_error)
    result = RUNNERS[args.cmd](args.scope, strict=args.strict)
    print(result.format_report_line())
    if result.is_skip:
        return 0
    return result.rc


if __name__ == "__main__":
    sys.exit(main())
