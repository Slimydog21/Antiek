"""Per-module mock-ratio ceiling lock — one-way ratchet over SPR-01 census.

WHY THIS EXISTS
===============
SPR-01's ``tools.test_census`` measures each test module's ``mock_ratio``
(``n_mock_tests / n_tests``, 4dp). Under the parallel-stream ``/caffenagent``
model, new tests are written against mocks, so ratios drift upward sprint by
sprint. This gate **stops the ratchet**: it locks each module's measured ratio
as a committed baseline and reds on upward regression.

This gate reads the census; it does NOT re-classify mocks or recompute ratios.
Single source of truth for the ratio is SPR-01's ``ModuleRecord.mock_ratio``.

LOCK PHILOSOPHY (aligned with ``docs/craft_signature.md``)
===========================================================
Lock the **measured** value, not a chosen target. If the regression check fires,
the right response is to make the module more real — not to bump the baseline.
The lock exists to prevent silent drift.

HOW TO RE-MINT A LOCK (the rare, deliberate case)
=================================================
When a module's ratio legitimately must rise (e.g. its real integration path
moved to a dedicated integration-marked suite and only isolation unit tests
remain), re-capture and document the reason in the same commit::

    python -m tools.lint.mock_budget_check capture \\
        --baseline-file tools/lints/baselines/mock_budget.json

The baseline records ``census_tree_sha`` + ``captured_at`` so the lock is
recoverable to the exact suite state that minted it. **Do not update silently.**

MODES (mirrors ``tools/lints/cli_with_baseline.py``)
====================================================
  * ``capture`` — write current per-module ratios as the locked baseline.
  * ``enforce`` — exit 1 if any locked module's ratio exceeds its lock by more
    than ``--epsilon`` (default **0.0** — an exact ratchet: unlike the latency
    lock's 10% noise band, mock-ratio is a deterministic AST count with zero
    run-to-run noise, so the band is 0; a NEW test that mocks is a real upward
    move, not noise).
  * ``stale`` — report modules whose current ratio is BELOW their lock (got more
    real; the operator can tighten the lock down). Never auto-edits the baseline.

A NEW module (in the census, absent from the baseline) is reported as
``unlocked`` — informational; enforce does not red (no lock to regress against).

Exit codes:
    0   within budget OR capture succeeded OR stale/unlocked informational only
    1   one or more upward regressions (enforce only)
    2   usage error (missing baseline, bad census file, etc.)

``enforce`` NEVER mutates the baseline; only ``capture`` writes it.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tools.test_census import Census, ModuleRecord, TestFnRecord, build_census

__all__ = ["main"]

_DEFAULT_BASELINE = (
    Path(__file__).resolve().parent.parent / "lints" / "baselines" / "mock_budget.json"
)
_DEFAULT_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass(frozen=True)
class ModuleLock:
    locked_ratio: float
    n_tests: int


@dataclass(frozen=True)
class Regression:
    module: str
    locked_ratio: float
    current_ratio: float
    n_tests: int
    offending_tests: tuple[str, ...]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _load_census_json(path: Path) -> Census:
    """Load a census JSON file (SPR-01 shape)."""
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    modules = tuple(
        ModuleRecord(
            module=str(m["module"]),
            n_tests=int(m["n_tests"]),
            n_mock_tests=int(m["n_mock_tests"]),
            mock_ratio=float(m["mock_ratio"]),
            n_structure_only=int(m["n_structure_only"]),
            predictive_ratio=float(m["predictive_ratio"]),
        )
        for m in data.get("modules", [])
    )
    tests = tuple(
        TestFnRecord(
            file=str(t["file"]),
            name=str(t["name"]),
            lineno=int(t["lineno"]),
            uses_mock=bool(t["uses_mock"]),
            mock_targets=tuple(str(x) for x in t.get("mock_targets", ())),
            predictive=t["predictive"],  # type: ignore[arg-type]
            assert_count=int(t.get("assert_count", 0)),
            mock_setup_lines=int(t.get("mock_setup_lines", 0)),
            reason=str(t.get("reason", "")),
        )
        for t in data.get("tests", [])
    )
    totals = data.get("totals", {})
    return Census(
        tree_sha=str(data.get("tree_sha", "unknown")),
        modules=modules,
        tests=tests,
        totals=totals,
        unparseable=(),
        behavioral_files=frozenset(),
        structure_tests=(),
        none_tests=(),
    )


def load_current_census(
    *,
    root: Path,
    census_file: Path | None,
    tests_dir: Path | None,
) -> Census:
    """Current ratios from a census JSON file or a live ``build_census`` run."""
    if census_file is not None:
        return _load_census_json(census_file)
    scan = tests_dir if tests_dir is not None else (root / "tests")
    return build_census(root, scan)


def census_modules_map(census: Census) -> dict[str, ModuleRecord]:
    return {m.module: m for m in census.modules}


def write_baseline(
    path: Path,
    census: Census,
    *,
    captured_at: str | None = None,
) -> None:
    """Capture current per-module ratios. Only ``capture`` calls this."""
    captured_at = captured_at or _now_iso()
    suite_ratio = census.totals.get("suite_mock_ratio", 0.0)
    modules_payload: dict[str, dict[str, Any]] = {}
    for m in sorted(census.modules, key=lambda rec: rec.module):
        modules_payload[m.module] = {
            "locked_ratio": m.mock_ratio,
            "n_tests": m.n_tests,
        }
    payload = {
        "captured_at": captured_at,
        "census_tree_sha": census.tree_sha,
        "suite_locked_mock_ratio": suite_ratio,
        "modules": modules_payload,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")


def load_baseline(path: Path) -> tuple[str, str, float, dict[str, ModuleLock]]:
    """Return (captured_at, census_tree_sha, suite_locked_mock_ratio, locks)."""
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    captured_at = str(data.get("captured_at", ""))
    tree_sha = str(data.get("census_tree_sha", ""))
    suite_ratio = float(data.get("suite_locked_mock_ratio", 0.0))
    raw_modules = data.get("modules", {})
    locks: dict[str, ModuleLock] = {}
    for module, entry in raw_modules.items():
        locks[str(module)] = ModuleLock(
            locked_ratio=float(entry["locked_ratio"]),
            n_tests=int(entry["n_tests"]),
        )
    return captured_at, tree_sha, suite_ratio, locks


def _mock_tests_in_module(census: Census, module: str) -> tuple[str, ...]:
    """Tests in *module* that use mocks — surfaced when a ratio regresses."""
    if not census.tests:
        return ()
    lines = sorted(
        f"{t.file}:{t.lineno}  {t.name}"
        for t in census.tests
        if t.file == module and t.uses_mock
    )
    return tuple(lines)


def find_regressed(
    current: dict[str, ModuleRecord],
    locks: dict[str, ModuleLock],
    *,
    epsilon: float,
    census: Census,
) -> list[Regression]:
    """Modules whose current ratio exceeds locked_ratio + epsilon."""
    out: list[Regression] = []
    for module, lock in sorted(locks.items()):
        rec = current.get(module)
        if rec is None:
            continue
        if rec.mock_ratio > lock.locked_ratio + epsilon:
            out.append(
                Regression(
                    module=module,
                    locked_ratio=lock.locked_ratio,
                    current_ratio=rec.mock_ratio,
                    n_tests=rec.n_tests,
                    offending_tests=_mock_tests_in_module(census, module),
                )
            )
    return out


def find_stale(
    current: dict[str, ModuleRecord],
    locks: dict[str, ModuleLock],
) -> list[tuple[str, float, float]]:
    """(module, locked_ratio, current_ratio) for modules now more-real."""
    out: list[tuple[str, float, float]] = []
    for module, lock in sorted(locks.items()):
        rec = current.get(module)
        if rec is None:
            continue
        if rec.mock_ratio < lock.locked_ratio:
            out.append((module, lock.locked_ratio, rec.mock_ratio))
    return out


def find_unlocked(
    current: dict[str, ModuleRecord],
    locks: dict[str, ModuleLock],
) -> list[tuple[str, float, int]]:
    """(module, current_ratio, n_tests) for census modules absent from baseline."""
    return sorted(
        (module, rec.mock_ratio, rec.n_tests)
        for module, rec in current.items()
        if module not in locks
    )


def run_capture(
    *,
    baseline_file: Path,
    root: Path,
    census_file: Path | None,
    tests_dir: Path | None,
) -> int:
    census = load_current_census(root=root, census_file=census_file, tests_dir=tests_dir)
    write_baseline(baseline_file, census)
    n_mod = len(census.modules)
    suite = census.totals.get("suite_mock_ratio", 0.0)
    print(
        f"wrote {n_mod} module lock(s) to {baseline_file} "
        f"(suite_locked_mock_ratio={suite:.4f}, census_tree_sha={census.tree_sha})"
    )
    return 0


def run_enforce(
    *,
    baseline_file: Path,
    root: Path,
    census_file: Path | None,
    tests_dir: Path | None,
    epsilon: float,
) -> int:
    try:
        _captured_at, _tree_sha, _suite, locks = load_baseline(baseline_file)
    except FileNotFoundError:
        print(f"baseline not found: {baseline_file}", file=sys.stderr)
        return 2
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"invalid baseline {baseline_file}: {exc}", file=sys.stderr)
        return 2

    census = load_current_census(root=root, census_file=census_file, tests_dir=tests_dir)
    current = census_modules_map(census)

    for module, ratio, n_tests in find_unlocked(current, locks):
        print(f"unlocked: {module}  mock_ratio={ratio:.4f}  n_tests={n_tests}")

    regressed = find_regressed(current, locks, epsilon=epsilon, census=census)
    for r in regressed:
        print(
            f"REGRESSED: {r.module}  {r.locked_ratio:.4f} -> {r.current_ratio:.4f}  "
            f"n_tests={r.n_tests}"
        )
        for line in r.offending_tests:
            print(f"  mock test: {line}")

    if regressed:
        print(
            f"\n{len(regressed)} module(s) regressed above mock-ratio lock "
            f"({baseline_file.name}). Fix the regression or re-mint via capture "
            f"with a documented reason — do not bump silently.",
            file=sys.stderr,
        )
        return 1
    return 0


def run_stale(
    *,
    baseline_file: Path,
    root: Path,
    census_file: Path | None,
    tests_dir: Path | None,
) -> int:
    try:
        _captured_at, _tree_sha, _suite, locks = load_baseline(baseline_file)
    except FileNotFoundError:
        print(f"baseline not found: {baseline_file}", file=sys.stderr)
        return 2
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"invalid baseline {baseline_file}: {exc}", file=sys.stderr)
        return 2

    census = load_current_census(root=root, census_file=census_file, tests_dir=tests_dir)
    current = census_modules_map(census)
    stale = find_stale(current, locks)

    if not stale:
        print("no stale locks (no module is more-real than its baseline)")
        return 0

    print(
        f"{len(stale)} stale lock(s) — module(s) now more-real; tighten via capture:"
    )
    for module, locked, now in stale:
        print(f"  stale: {module}  {locked:.4f} -> {now:.4f}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tools.lint.mock_budget_check",
        description="Per-module mock-ratio ceiling lock over SPR-01 census output.",
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    def _add_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument(
            "--baseline-file",
            type=Path,
            default=_DEFAULT_BASELINE,
            help="path to mock_budget.json baseline",
        )
        sp.add_argument(
            "--root",
            type=Path,
            default=_DEFAULT_ROOT,
            help="repo root (default: parent of tools/)",
        )
        sp.add_argument(
            "--census-file",
            type=Path,
            default=None,
            help="read ratios from this census JSON instead of running build_census",
        )
        sp.add_argument(
            "--tests-dir",
            type=Path,
            default=None,
            help="tests directory for live census (default: <root>/tests)",
        )

    cap = sub.add_parser("capture", help="write current per-module ratios to baseline")
    _add_common(cap)

    enf = sub.add_parser("enforce", help="exit 1 on upward mock-ratio regression")
    _add_common(enf)
    enf.add_argument(
        "--epsilon",
        type=float,
        default=0.0,
        help="upward regression band (default 0.0 — exact ratchet; see module docstring)",
    )

    st = sub.add_parser(
        "stale",
        help="report modules more-real than their lock (tighten via capture)",
    )
    _add_common(st)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    root = args.root.resolve()
    baseline_file: Path = args.baseline_file
    census_file: Path | None = (
        args.census_file.resolve() if args.census_file is not None else None
    )
    tests_dir: Path | None = (
        args.tests_dir.resolve() if args.tests_dir is not None else None
    )

    if args.mode == "capture":
        return run_capture(
            baseline_file=baseline_file,
            root=root,
            census_file=census_file,
            tests_dir=tests_dir,
        )
    if args.mode == "enforce":
        return run_enforce(
            baseline_file=baseline_file,
            root=root,
            census_file=census_file,
            tests_dir=tests_dir,
            epsilon=args.epsilon,
        )
    if args.mode == "stale":
        return run_stale(
            baseline_file=baseline_file,
            root=root,
            census_file=census_file,
            tests_dir=tests_dir,
        )

    return 2


if __name__ == "__main__":
    raise SystemExit(main())