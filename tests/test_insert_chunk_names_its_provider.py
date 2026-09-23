"""Every production producer that stores a chunk vector names the provider
that produced it (audit wave 3, #1).

``insert_chunk`` pins a vector's provider identity only when the caller
passes ``embedding_provider=`` — it cannot infer the producer from the
floats, and stamping the process default would fabricate provenance (a
hash vector pinned as MiniLM is exactly the silent mismatch the pin
exists to make loud). 15 of 16 producers omitted it. This test walks the
AST of every non-test module so a 16th cannot.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _production_python_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "*.py"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    return [
        ROOT / f
        for f in out
        if not (f.startswith("tests/") or "/tests/" in f or "/test_" in f or f.startswith("test_"))
    ]


def _unpinned_insert_chunk_calls(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bad: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
        if name != "insert_chunk":
            continue
        kws = {k.arg: k for k in node.keywords if k.arg}
        emb = kws.get("embedding")
        if emb is None:
            continue
        if isinstance(emb.value, ast.Constant) and emb.value.value is None:
            continue
        if "embedding_provider" not in kws:
            bad.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    return bad


def test_every_production_chunk_vector_names_its_provider() -> None:
    unpinned: list[str] = []
    for path in _production_python_files():
        unpinned.extend(_unpinned_insert_chunk_calls(path))
    assert unpinned == [], (
        "insert_chunk(embedding=...) without embedding_provider= stores an "
        f"unpinned vector at: {unpinned}"
    )


@pytest.mark.parametrize(
    ("src", "expected"),
    [
        ("insert_chunk(con, embedding=v)", 1),
        ("ops.insert_chunk(con, embedding=v, embedding_provider=p)", 0),
        ("insert_chunk(con, embedding=None)", 0),
        ("insert_chunk(con, text='x')", 0),
    ],
)
def test_detector_control(tmp_path: Path, src: str, expected: int) -> None:
    f = tmp_path / "m.py"
    f.write_text(src + "\n", encoding="utf-8")
    tree = ast.parse(f.read_text())
    calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and (getattr(n.func, "attr", None) or getattr(n.func, "id", "")) == "insert_chunk"
    ]
    kws = {k.arg: k for k in calls[0].keywords if k.arg}
    emb = kws.get("embedding")
    flagged = int(
        emb is not None
        and not (isinstance(emb.value, ast.Constant) and emb.value.value is None)
        and "embedding_provider" not in kws
    )
    assert flagged == expected
