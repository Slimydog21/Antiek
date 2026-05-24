"""mypy_strict_baseline — capture/enforce mypy --strict errors against a baseline.

ARE-01 enforcement slice. Reuses tools/lints/baseline.py: a mypy error
becomes a ViolationKey with ``kind = "mypy:<error-code>"``. Grandfathers
existing strict errors; fails CI only on NEW ones. As the operator fixes
errors, --check-stale surfaces the shrinking baseline.

See docs/decisions/are-01-mypy-strict-guardrail.md.

Usage::

    python -m tools.lints.mypy_strict_baseline capture \\
        --paths runtime/db_lock.py substrate/event_log/ \\
        --baseline-file tools/lints/baselines/mypy_strict_substrate_core.json

    python -m tools.lints.mypy_strict_baseline enforce \\
        --paths runtime/db_lock.py substrate/event_log/ \\
        --baseline-file tools/lints/baselines/mypy_strict_substrate_core.json \\
        --check-stale

Exit codes: 0 no NEW errors; 1 NEW errors or stale entries; 2 usage/mypy failure.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from tools.lints.baseline import (
    ViolationKey,
    compute_keys,
    filter_to_new_only,
    find_stale_baseline_entries,
    load_baseline,
    write_baseline,
)

__all__ = [
    "MypyError",
    "parse_mypy_output",
    "run_mypy_strict",
    "mypy_error_to_key",
    "main",
]


_MYPY_LINE = re.compile(
    r"^(?P<path>[^:]+):(?P<line>\d+)(?::(?P<col>\d+))?:\s+error:\s+"
    r"(?P<message>.*?)(?:\s+\[(?P<code>[a-z0-9-]+)\])?$"
)


@dataclass(frozen=True)
class MypyError:
    path: str
    line: int
    col: int
    code: str
    message: str


def parse_mypy_output(output: str) -> list[MypyError]:
    """Parse mypy stdout into structured errors. Ignores note: lines
    and the summary. Unmatched lines skipped (version-drift defensive)."""
    errors: list[MypyError] = []
    for raw_line in output.splitlines():
        m = _MYPY_LINE.match(raw_line.strip())
        if not m:
            continue
        errors.append(
            MypyError(
                path=m.group("path"),
                line=int(m.group("line")),
                col=int(m.group("col")) if m.group("col") else 0,
                code=m.group("code") or "no-code",
                message=m.group("message").strip(),
            )
        )
    return errors


def run_mypy_strict(
    paths: Iterable[str],
    mypy_bin: str = "./.venv/bin/mypy",
    cwd: Path | None = None,
) -> list[MypyError]:
    """Run mypy --strict and return parsed errors. Raises RuntimeError
    only if mypy can't be invoked (binary missing)."""
    argv = [mypy_bin, "--strict", *paths]
    try:
        proc = subprocess.run(
            argv, cwd=cwd, capture_output=True, text=True, check=False
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"mypy binary not found at {mypy_bin!r}: {exc}. "
            f"Install via `pip install -e '.[dev]'`."
        ) from exc
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    return parse_mypy_output(combined)


def mypy_error_to_key(e: object) -> ViolationKey:
    """Project a MypyError to a baseline ViolationKey. Excludes the
    human-readable message — code + location is the stable identity,
    robust to mypy wording changes across versions."""
    assert isinstance(e, MypyError)
    return ViolationKey(path=e.path, line=e.line, col=e.col, kind=f"mypy:{e.code}")


def _cmd_capture(paths: list[str], baseline_file: Path) -> int:
    try:
        errors = run_mypy_strict(paths)
    except RuntimeError as exc:
        print(f"mypy invocation failed: {exc}", file=sys.stderr)
        return 2
    keys = compute_keys(errors, mypy_error_to_key)
    write_baseline(baseline_file, lint="mypy_strict_substrate_core", violations=keys)
    print(f"wrote {len(keys)} mypy --strict error(s) to {baseline_file}")
    return 0


def _cmd_enforce(paths: list[str], baseline_file: Path, check_stale: bool) -> int:
    try:
        baseline = load_baseline(baseline_file)
    except FileNotFoundError:
        print(f"baseline not found: {baseline_file}", file=sys.stderr)
        return 2
    try:
        errors = run_mypy_strict(paths)
    except RuntimeError as exc:
        print(f"mypy invocation failed: {exc}", file=sys.stderr)
        return 2

    current = compute_keys(errors, mypy_error_to_key)
    new_only = filter_to_new_only(current, baseline)
    for k in new_only:
        print(f"{k.path}:{k.line}:{k.col}: NEW {k.kind}")

    rc = 1 if new_only else 0

    if check_stale:
        stale = find_stale_baseline_entries(current, baseline)
        if stale:
            print(
                f"\n{len(stale)} stale baseline entr"
                f"{'y' if len(stale) == 1 else 'ies'} "
                f"(fixed — re-capture to ratchet the floor down)",
                file=sys.stderr,
            )
            for k in stale:
                print(f"  - {k.path}:{k.line}:{k.col} {k.kind}", file=sys.stderr)
            rc = max(rc, 1)

    if new_only:
        print(
            f"\n{len(new_only)} NEW mypy --strict error(s) since baseline",
            file=sys.stderr,
        )

    return rc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mypy_strict_baseline",
        description="Capture/enforce mypy --strict errors against a baseline.",
    )
    sub = parser.add_subparsers(dest="mode", required=True)
    for mode in ("capture", "enforce"):
        sp = sub.add_parser(mode, help=f"{mode} mode")
        sp.add_argument("--paths", nargs="+", required=True,
                        help="files / packages to type-check")
        sp.add_argument("--baseline-file", required=True, type=Path,
                        help="baseline JSON file")
        if mode == "enforce":
            sp.add_argument("--check-stale", action="store_true",
                            help="also report fixed baseline entries")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.mode == "capture":
        return _cmd_capture(paths=list(args.paths), baseline_file=args.baseline_file)
    if args.mode == "enforce":
        return _cmd_enforce(
            paths=list(args.paths),
            baseline_file=args.baseline_file,
            check_stale=args.check_stale,
        )
    parser.print_usage(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
