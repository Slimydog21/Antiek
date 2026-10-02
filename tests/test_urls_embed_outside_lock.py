"""URL ingest must not compute embeddings while holding the write lock.

DuckDB is single-writer and the service runs one uvicorn worker, so the
exclusive flock held by ``connect_write`` serializes EVERY writer in the
system. ``ingest_url`` used to call ``emb.encode(...)`` twice per chunk inside
that block — a document's worth of model forward passes while the nightly
backup (180s deadline) and the arXiv OAI sync (300s) waited on work that needs
no database at all.

This is a source-shaped test on purpose. The property is "no encode happens
between acquiring and releasing the lock", which is a fact about where the
calls sit, not about any single run's timing — a behavioural test would have
to race the lock to observe it.
"""

from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_ADAPTER = _ROOT / "acquisition" / "urls" / "adapter.py"


def _ingest_url_node() -> ast.FunctionDef:
    tree = ast.parse(_ADAPTER.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "ingest_url":
            return node
    raise AssertionError("ingest_url not found — this test's premise is stale")


def _encode_calls(node: ast.AST) -> list[int]:
    out: list[int] = []
    for sub in ast.walk(node):
        if (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Attribute)
            and sub.func.attr == "encode"
        ):
            out.append(sub.lineno)
    return out


def _write_lock_blocks(node: ast.AST) -> list[ast.With]:
    out: list[ast.With] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.With) and any(
            "connect_write" in ast.unparse(item.context_expr) for item in sub.items
        ):
            out.append(sub)
    return out


def test_the_premise_still_holds() -> None:
    """Not vacuous: no encode calls or no lock block would pass everything."""
    fn = _ingest_url_node()
    assert _encode_calls(fn), (
        "ingest_url no longer calls .encode() at all — if embedding moved "
        "elsewhere, retarget this test rather than deleting it"
    )
    assert _write_lock_blocks(fn), (
        "ingest_url no longer opens a connect_write block; the premise changed"
    )


def test_no_embedding_is_computed_inside_the_write_lock() -> None:
    fn = _ingest_url_node()
    offenders: list[int] = []
    for block in _write_lock_blocks(fn):
        offenders.extend(_encode_calls(block))

    assert not offenders, (
        f"acquisition/urls/adapter.py computes an embedding inside the "
        f"connect_write block at line(s) {sorted(offenders)}. That holds the "
        "single-writer flock across a model forward pass per chunk and "
        "starves every other writer, including the nightly backup and the "
        "arXiv sync. Compute embeddings before taking the lock."
    )
