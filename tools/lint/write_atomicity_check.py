#!/usr/bin/env python3
"""Write-atomicity lint — forbid multi-statement writes that assume the write
lock makes them atomic.

The invariant: ``runtime.db_lock.connect_write`` gives **mutual exclusion**, not
**atomicity**. They are different properties and this codebase has conflated
them three times in comments that read like a correctness argument:

    # Atomic replace: drop all existing blocks, then re-insert in order.
    # Both operations sit inside the single connect_write lock so a
    # concurrent read never sees a partial state.
        -- interfaces/research/api/app.py, PUT /notebooks/{id}/content

    # section_blocks has a composite PK. Moving to a new section requires
    # DELETE + INSERT under the same lock.
        -- interfaces/research/api/app.py, POST /sections/reorder-block

DuckDB autocommits every statement, so the lock does nothing for the failure
that actually happens: the SECOND statement fails after the first has already
committed. Nothing was ever racing. Both examples above were reproduced as real
data loss — a 3-block notebook losing 2 of 3 blocks under fault injection, and a
block losing its section attachment on a primary-key collision.

A block is a violation when it holds a ``connect_write`` context and issues two
or more MUTATING statements (INSERT / UPDATE / DELETE / REPLACE / UPSERT /
MERGE) without an explicit transaction around them. Either form of transaction
counts as protection:

  * ``with con.transaction():``      — the LockedConnection contextmanager.
  * ``con.execute("BEGIN")``         — a hand-rolled explicit transaction, which
                                       acquisition/arxiv/store.py uses correctly.

DDL (CREATE / DROP / ALTER) is deliberately NOT counted. It appears almost
exclusively in schema setup and test fixtures, where partial application is
recoverable by re-running the migration, and counting it buried the real
findings in noise on the first pass.

Output is ``path:line: message``, one per violation, and the exit code contract
matches tools/lint/boundary_check.py: 0 clean, 1 violations.

Usage:
    python tools/lint/write_atomicity_check.py            # enforce
    python tools/lint/write_atomicity_check.py --list     # print every block

KNOWN-UNFIXED sites live in ``_ALLOWLIST`` below, each with a written reason.
The allowlist is deliberately inline rather than a JSON baseline: there are few
enough entries that each one can carry an argument, and an exemption that has to
be argued in the diff is harder to add by reflex than a regenerated file.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]

_MUTATING = {"INSERT", "UPDATE", "DELETE", "REPLACE", "UPSERT", "MERGE"}

_SKIP_PARTS = (
    ".venv/", "node_modules/", "__pycache__", "/mutants/",
    "tests/", "/worktrees/", "/.worktrees/", "benchmarks/", "scripts/",
)

# (path, first line of the `with connect_write(...)` block) -> why it is exempt.
_ALLOWLIST: dict[tuple[str, int], str] = {
    (
        "acquisition/urls/adapter.py", 253,
    ): (
        "Re-ingest replace path: DELETE chunks then re-insert them. Genuinely "
        "wants a transaction, but the block also computes an embedding per "
        "chunk inside the lock, so the correct boundary is to hoist the "
        "embeddings out first rather than hold a transaction open across N "
        "model forward passes. Needs the owner's call on whether re-ingest is "
        "idempotent enough to retry instead. Tracked, not dismissed."
    ),
    (
        "roles/note_taker/replay.py", 428,
    ): (
        "INSERT note_taker_configurations + UPDATE note_taker_windows. Partial "
        "application leaves a config row without its window state. Needs a "
        "domain judgment on whether replay is re-entrant."
    ),
    (
        "substrate/speak/async_interview.py", 212,
    ): (
        "UPDATE interview_projects.interview_guide + INSERT interviews. "
        "Partial application leaves a guide update with no interview row."
    ),
}


def _sql_head(call: ast.Call) -> str | None:
    """First SQL keyword of an ``execute`` call, when it is statically knowable."""
    if not call.args:
        return None
    parts: list[str] = []

    def walk(n: ast.AST) -> None:
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            parts.append(n.value)
        elif isinstance(n, ast.JoinedStr):
            for v in n.values:
                walk(v)
        elif isinstance(n, ast.BinOp):
            walk(n.left)
            walk(n.right)

    walk(call.args[0])
    text = " ".join(parts).strip()
    if not text:
        return None
    head = text.split(None, 1)
    return head[0].upper() if head else None


def _is_execute(node: ast.AST) -> ast.Call | None:
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr in ("execute", "executemany"):
            return node
    return None


class _Scan(ast.NodeVisitor):
    def __init__(self) -> None:
        self.blocks: list[tuple[int, list[int], bool]] = []

    def visit_With(self, node: ast.With) -> None:
        opens_write = any(
            "connect_write" in ast.unparse(item.context_expr)
            for item in node.items
        )
        if opens_write:
            mutating: list[int] = []
            protected = False
            for sub in ast.walk(node):
                if isinstance(sub, ast.With):
                    for item in sub.items:
                        if ".transaction()" in ast.unparse(item.context_expr):
                            protected = True
                call = _is_execute(sub)
                if call is None:
                    continue
                head = _sql_head(call)
                if head == "BEGIN":
                    protected = True
                elif head in _MUTATING:
                    mutating.append(getattr(sub, "lineno", node.lineno))
            self.blocks.append((node.lineno, sorted(mutating), protected))
        self.generic_visit(node)


def _candidate_files() -> list[Path]:
    out: list[Path] = []
    for path in sorted(_REPO.rglob("*.py")):
        rel = path.relative_to(_REPO).as_posix()
        if any(part in f"/{rel}" for part in _SKIP_PARTS):
            continue
        out.append(path)
    return out


def find_violations(list_all: bool = False) -> list[str]:
    findings: list[str] = []
    for path in _candidate_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        scan = _Scan()
        scan.visit(tree)
        rel = path.relative_to(_REPO).as_posix()
        for lineno, mutating, protected in scan.blocks:
            if list_all:
                findings.append(
                    f"{rel}:{lineno}: {len(mutating)} mutating stmt(s), "
                    f"protected={protected}"
                )
                continue
            if protected or len(mutating) < 2:
                continue
            if (rel, lineno) in _ALLOWLIST:
                continue
            findings.append(
                f"{rel}:{lineno}: write-atomicity — this connect_write block "
                f"issues {len(mutating)} mutating statements (lines "
                f"{mutating}) with no explicit transaction. The write lock "
                "gives mutual exclusion, NOT atomicity: DuckDB autocommits "
                "each statement, so if a later one fails the earlier ones are "
                "already durable. Wrap them in `with con.transaction():`, or "
                "add an entry to _ALLOWLIST in this file with a reason."
            )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--list", action="store_true",
        help="print every connect_write block and whether it is protected",
    )
    args = parser.parse_args(argv)

    findings = find_violations(list_all=args.list)
    for line in findings:
        print(line)
    if args.list:
        return 0
    if findings:
        print(
            f"\n{len(findings)} unprotected multi-statement write(s). "
            "See the module docstring for why the lock is not enough.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
