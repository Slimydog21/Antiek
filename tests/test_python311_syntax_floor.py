"""Keep tracked Python source parseable at the declared Python 3.11 floor."""

from __future__ import annotations

import ast
import os
import subprocess
import tokenize
from pathlib import Path

import pytest


def test_tracked_python_files_parse_on_python311() -> None:
    root = Path(__file__).resolve().parents[1]
    if not (root / ".git").exists():
        pytest.skip("requires a source checkout")

    paths = subprocess.check_output(["git", "ls-files", "-z", "--", "*.py"], cwd=root).split(b"\0")
    assert any(paths), "no tracked Python files found"
    failures: list[str] = []
    for raw_path in paths:
        if not raw_path:
            continue
        relative = Path(os.fsdecode(raw_path))
        with tokenize.open(root / relative) as source_file:
            source = source_file.read()
        try:
            ast.parse(source, filename=str(relative), feature_version=(3, 11))
        except SyntaxError as exc:
            failures.append(f"{relative}:{exc.lineno}: {exc.msg}")

    assert not failures, "Python 3.11 syntax failures:\n" + "\n".join(failures)
