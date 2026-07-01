"""cli_with_baseline.py — runner that wraps the two substrate lints
with baseline-mode support.

ARE-11 of the Antiek Rust-Execution Spec. The original lints
(``no_raise_in_substrate_writers``, ``unannotated_bypass``) ship a
default mode (scan + print + exit 1 on any violation). This runner
adds the third mode required to wire the lints into CI without
flag-day pain:

  * ``capture`` — write current violations to a baseline JSON file
    (the operator commits this file; today's violations are
    grandfathered).
  * ``enforce`` — read the baseline; report only violations NOT in
    it; exit 1 only on NEW violations.
  * ``stale`` — same as enforce but also report baseline entries
    whose violation has been fixed (operator can shrink the
    baseline).

The runner exists as a separate module so we don't disturb the
lint mains — those have grown a `--help` shape that downstream tools
depend on. This is the standard "facade over stable libraries"
pattern.

Usage::

    python -m tools.lints.cli_with_baseline capture no_raise \\
        --paths substrate/ --baseline-file tools/lints/baselines/no_raise.json

    python -m tools.lints.cli_with_baseline enforce no_raise \\
        --paths substrate/ --baseline-file tools/lints/baselines/no_raise.json

    python -m tools.lints.cli_with_baseline enforce bypass \\
        --paths substrate/ --baseline-file tools/lints/baselines/bypass.json \\
        --check-stale

Exit codes:
    0   no violations OR all violations grandfathered
    1   one or more NEW violations (or stale entries with --check-stale)
    2   usage error
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tools.lints.baseline import (
    ViolationKey,
    compute_keys,
    filter_to_new_only,
    find_stale_baseline_entries,
    load_baseline,
    write_baseline,
)
from tools.lints.no_raise_in_substrate_writers import (
    Violation,
)
from tools.lints.no_raise_in_substrate_writers import (
    scan_paths as scan_no_raise,
)
from tools.lints.no_unbounded_external_call import (
    Violation as UnboundedExternalCallViolation,
)
from tools.lints.no_unbounded_external_call import (
    scan_paths as scan_unbounded_external_call,
)
from tools.lints.no_seam_call_under_write_lock import (
    Violation as SeamUnderLockViolation,
)
from tools.lints.no_seam_call_under_write_lock import (
    scan_paths as scan_seam_under_lock,
)
from tools.lints.unannotated_bypass import (
    BypassViolation,
)
from tools.lints.unannotated_bypass import (
    scan_paths as scan_bypass,
)

__all__ = ["main", "LINT_REGISTRY"]


def _no_raise_to_key(v: object) -> ViolationKey:
    assert isinstance(v, Violation)
    return ViolationKey(
        path=str(v.path), line=v.line, col=v.col,
        kind=f"raise:{v.exception_name}",
    )


def _bypass_to_key(v: object) -> ViolationKey:
    assert isinstance(v, BypassViolation)
    return ViolationKey(
        path=str(v.path), line=v.line, col=v.col,
        kind=f"bypass:{v.qualifier}.{v.method}",
    )


def _unbounded_external_call_to_key(v: object) -> ViolationKey:
    assert isinstance(v, UnboundedExternalCallViolation)
    return ViolationKey(
        path=str(v.path), line=v.line, col=v.col,
        kind=f"unbounded-external-call:{v.call}",
    )


def _seam_under_lock_to_key(v: object) -> ViolationKey:
    assert isinstance(v, SeamUnderLockViolation)
    return ViolationKey(
        path=str(v.path), line=v.line, col=v.col,
        kind=f"seam-under-write-lock:{v.seam}",
    )


# Registry: lint-name → (scan-function, key-adapter, friendly-name).
# Adding a new lint = add an entry here + import the scan_paths
# function. The CLI is registry-driven; subcommands list current
# names dynamically.
LINT_REGISTRY: dict[str, tuple[
    Callable[[list[Path | str]], list[Any]],
    Callable[[object], ViolationKey],
    str,
]] = {
    "no_raise": (scan_no_raise, _no_raise_to_key, "no_raise_in_substrate_writers"),
    "bypass": (scan_bypass, _bypass_to_key, "unannotated_bypass"),
    "unbounded_external_call": (
        scan_unbounded_external_call,
        _unbounded_external_call_to_key,
        "no_unbounded_external_call",
    ),
    "seam_under_write_lock": (
        scan_seam_under_lock,
        _seam_under_lock_to_key,
        "no_seam_call_under_write_lock",
    ),
}


def _run_capture(
    paths: list[Path | str],
    baseline_file: Path,
    lint_name: str,
) -> int:
    scan_fn, key_fn, full_name = LINT_REGISTRY[lint_name]
    violations = scan_fn(paths)
    keys = compute_keys(violations, key_fn)
    write_baseline(baseline_file, lint=full_name, violations=keys)
    print(f"wrote {len(keys)} violation(s) to {baseline_file}")
    return 0


def _run_enforce(
    paths: list[Path | str],
    baseline_file: Path,
    lint_name: str,
    check_stale: bool,
) -> int:
    scan_fn, key_fn, _ = LINT_REGISTRY[lint_name]
    try:
        baseline = load_baseline(baseline_file)
    except FileNotFoundError:
        print(f"baseline not found: {baseline_file}", file=sys.stderr)
        return 2

    violations = scan_fn(paths)
    current_keys = compute_keys(violations, key_fn)
    new_only = filter_to_new_only(current_keys, baseline)
    for k in new_only:
        print(f"{k.path}:{k.line}:{k.col}: NEW {k.kind}")

    rc = 1 if new_only else 0

    if check_stale:
        stale = find_stale_baseline_entries(current_keys, baseline)
        if stale:
            print(
                f"\n{len(stale)} stale baseline entr"
                f"{'y' if len(stale) == 1 else 'ies'} "
                f"(fixed — baseline can shrink)",
                file=sys.stderr,
            )
            for k in stale:
                print(f"  - {k.path}:{k.line}:{k.col} {k.kind}",
                      file=sys.stderr)
            # Stale-only condition still exits non-zero so CI prompts
            # the operator to refresh; consistent with "drift is a
            # finding."
            rc = max(rc, 1)

    if new_only:
        print(
            f"\n{len(new_only)} NEW violation(s) since baseline "
            f"({baseline_file.name})",
            file=sys.stderr,
        )

    return rc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli_with_baseline",
        description="Baseline-mode runner for the substrate lints.",
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    for mode in ("capture", "enforce"):
        sp = sub.add_parser(
            mode, help=f"{mode} mode against a baseline file"
        )
        sp.add_argument(
            "lint", choices=sorted(LINT_REGISTRY.keys()),
            help="which lint to run",
        )
        sp.add_argument(
            "--paths", nargs="+", required=True, type=str,
            help="files / directories to scan",
        )
        sp.add_argument(
            "--baseline-file", required=True, type=Path,
            help="path to the baseline JSON file",
        )
        if mode == "enforce":
            sp.add_argument(
                "--check-stale", action="store_true",
                help="also report baseline entries that no longer match",
            )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    paths_list: list[Path | str] = list(args.paths)

    if args.mode == "capture":
        return _run_capture(
            paths=paths_list,
            baseline_file=args.baseline_file,
            lint_name=args.lint,
        )

    if args.mode == "enforce":
        return _run_enforce(
            paths=paths_list,
            baseline_file=args.baseline_file,
            lint_name=args.lint,
            check_stale=args.check_stale,
        )

    parser.print_usage(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
