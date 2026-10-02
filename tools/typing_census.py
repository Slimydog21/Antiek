"""Census source files using the declared mypy gate's target definition.

Replaces the copied-root snippet in
``docs/decisions/declared-typing-status-2026-09-26.md``. Importing the gate's
``DECLARED_MYPY_TARGETS`` prevents the census roots from drifting separately.
The document's .py source filter is retained: tests and cache/vendor folders
are excluded. The unfiltered target .py count is reported separately because
the gate does not exclude tests. This reads the saved baseline, not mypy;
an empty baseline is not proof that a file currently passes strict typing.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from tools.lints import declared_bar
from tools.lints.baseline import BaselineSchema

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_BASELINE = Path("tools/lints/baselines/declared_mypy.json")
_SKIP_DIRS = {"node_modules", ".venv", "__pycache__", ".git"}


@dataclass(frozen=True)
class TypingCensus:
    total_files: int
    empty_baseline_files: int
    non_empty_baseline_files: int
    baseline_files_outside_scope: int
    target_python_files_including_tests: int


def _raise_walk_error(error: OSError) -> None:
    raise error


def target_python_files(repo_root: Path, targets: Iterable[str]) -> set[str]:
    """Expand the gate targets to distinct repo-relative .py paths."""
    files: set[str] = set()
    for target in targets:
        path = repo_root / target
        if path.is_file():
            if path.suffix != ".py":
                raise ValueError(f"target is not a .py file: {target}")
            files.add(path.relative_to(repo_root).as_posix())
        elif path.is_dir():
            for directory, dirs, names in os.walk(path, onerror=_raise_walk_error):
                dirs[:] = [name for name in dirs if name not in _SKIP_DIRS]
                for name in names:
                    if name.endswith(".py"):
                        files.add((Path(directory) / name).relative_to(repo_root).as_posix())
        else:
            raise ValueError(f"declared mypy target does not exist: {target}")
    if not files:
        raise ValueError("declared mypy targets contain no .py files")
    return files


def build_census(python_files: set[str], baseline_paths: set[str]) -> TypingCensus:
    """Apply the documented source-file filter and partition by baseline path."""
    source_files = {
        path for path in python_files
        if "tests" not in Path(path).parts
        and not Path(path).name.startswith("test_")
        and not path.endswith("_test.py")
    }
    non_empty = source_files & baseline_paths
    return TypingCensus(
        total_files=len(source_files),
        empty_baseline_files=len(source_files - baseline_paths),
        non_empty_baseline_files=len(non_empty),
        baseline_files_outside_scope=len(baseline_paths - source_files),
        target_python_files_including_tests=len(python_files),
    )


def read_baseline(path: Path) -> BaselineSchema:
    """Use the gate schema, but reject missing records rather than report all empty."""
    with path.open(encoding="utf-8") as stream:
        data = json.load(stream)
    if not isinstance(data, dict) or not isinstance(data.get("violations"), list):
        raise ValueError("baseline must contain a violations list")
    if data.get("lint") != "declared_bar_mypy":
        raise ValueError("baseline lint must be declared_bar_mypy")
    for entry in data["violations"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise ValueError("each baseline violation must contain a string path")
        if not entry["path"]:
            raise ValueError("baseline violation path must not be empty")
    return BaselineSchema.from_json(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline-file", type=Path, default=_DEFAULT_BASELINE,
        help="baseline JSON; relative paths are resolved from the checkout root",
    )
    args = parser.parse_args(argv)
    baseline_file = _REPO_ROOT / args.baseline_file
    targets = declared_bar.DECLARED_MYPY_TARGETS
    try:
        baseline = read_baseline(baseline_file)
        python_files = target_python_files(_REPO_ROOT, targets)
        census = build_census(python_files, {key.path for key in baseline.violations})
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"typing census failed: {exc}", file=sys.stderr)
        return 2
    print("targets: " + ", ".join(targets))
    print("scope: .py source files; excludes tests/, test_*.py, *_test.py")
    print("also excludes: " + ", ".join(sorted(_SKIP_DIRS)))
    print(f"baseline: {baseline_file}")
    print(f"baseline generated at: {baseline.generated_at}")
    print(f"total files in scope: {census.total_files}")
    print(f"files with an empty baseline: {census.empty_baseline_files}")
    print(f"files with a non-empty baseline: {census.non_empty_baseline_files}")
    print(f"baseline files outside scope: {census.baseline_files_outside_scope}")
    print(f"target .py files including tests: {census.target_python_files_including_tests}")
    print("Empty baseline means no saved entry; this command does not run mypy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
