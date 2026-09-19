#!/usr/bin/env python3
"""Ratchet raw external document/chunk/edge writers in acquisition code."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_BASELINE = Path(__file__).with_name("baselines") / "legal_admission_writers.json"
_RAW_CALLS = frozenset({"insert_document", "insert_chunk", "insert_edge"})
_ADMITTED_CALLS = frozenset(
    {"insert_document_admitted", "insert_chunk_admitted", "insert_edge_admitted"}
)
_CONVERTED = {
    "acquisition/urls/adapter.py": {"insert_document_admitted", "insert_chunk_admitted"},
    "acquisition/substack/adapter.py": {
        "insert_document_admitted",
        "insert_chunk_admitted",
    },
    "acquisition/arxiv/adapter.py": {"insert_document_admitted", "insert_chunk_admitted"},
}
_RAW_SQL = re.compile(r"\bINSERT\s+INTO\s+(documents|chunks|edges)\b", re.IGNORECASE)


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


class _Inventory(ast.NodeVisitor):
    def __init__(self, relative: str) -> None:
        self.relative = relative
        self.scope = ["<module>"]
        self.raw: Counter[str] = Counter()
        self.admitted: set[str] = set()
        self.aliases: dict[str, set[str]] = {}

    def _scope(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> None:
        self.scope.append(node.name)
        for statement in node.body:
            self.visit(statement)
        self.scope.pop()

    visit_FunctionDef = _scope
    visit_AsyncFunctionDef = _scope
    visit_ClassDef = _scope

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            if alias.name in _RAW_CALLS | _ADMITTED_CALLS:
                self.aliases[alias.asname or alias.name] = {alias.name}

    def visit_Assign(self, node: ast.Assign) -> None:
        resolved: set[str] = set()
        for child in ast.walk(node.value):
            if isinstance(child, ast.Name):
                resolved.update(self.aliases.get(child.id, {child.id}))
            elif isinstance(child, ast.Attribute):
                resolved.update(self.aliases.get(child.attr, {child.attr}))
        resolved &= _RAW_CALLS | _ADMITTED_CALLS
        if resolved:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.aliases[target.id] = resolved
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node)
        names = self.aliases.get(name, {name}) if name is not None else set()
        if name == "getattr" and len(node.args) >= 2:
            attr = node.args[1]
            if isinstance(attr, ast.Constant) and isinstance(attr.value, str):
                names = {attr.value}
        self.admitted.update(names & _ADMITTED_CALLS)
        kind: str | None = None
        raw_names = sorted(names & _RAW_CALLS)
        if raw_names:
            kind = f"call:{'+'.join(raw_names)}"
        elif (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in {"execute", "executemany"}
            and node.args
        ):
            literals = " ".join(
                child.value
                for child in ast.walk(node.args[0])
                if isinstance(child, ast.Constant) and isinstance(child.value, str)
            )
            match = _RAW_SQL.search(literals)
            if match:
                kind = f"sql:{match.group(1).lower()}"
        if kind is not None:
            canonical = "\0".join(
                (
                    self.relative,
                    ".".join(self.scope),
                    kind,
                    ast.dump(node, annotate_fields=True, include_attributes=False),
                )
            )
            digest = hashlib.sha256(canonical.encode()).hexdigest()[:20]
            self.raw[f"{self.relative}:{'.'.join(self.scope)}:{kind}:{digest}"] += 1
        self.generic_visit(node)


def inventory(root: Path) -> tuple[Counter[str], dict[str, set[str]]]:
    raw: Counter[str] = Counter()
    admitted: dict[str, set[str]] = {}
    for path in sorted((root / "acquisition").rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        visitor = _Inventory(relative)
        visitor.visit(ast.parse(path.read_text(encoding="utf-8"), filename=relative))
        raw.update(visitor.raw)
        admitted[relative] = visitor.admitted
    return raw, admitted


def _read(path: Path) -> Counter[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != 1 or not isinstance(payload.get("sites"), dict):
        raise ValueError("legal admission writer baseline is invalid")
    return Counter({key: int(value) for key, value in payload["sites"].items()})


def _write(root: Path, path: Path) -> None:
    raw, _ = inventory(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"version": 1, "sites": dict(sorted(raw.items()))}, indent=2) + "\n",
        encoding="utf-8",
    )


def errors(root: Path, baseline: Path) -> list[str]:
    raw, admitted = inventory(root)
    result = [
        f"new raw external writer: {site} (+{count})"
        for site, count in sorted((raw - _read(baseline)).items())
    ]
    for relative, required in _CONVERTED.items():
        missing = required - admitted.get(relative, set())
        if missing:
            result.append(
                f"converted connector lost admitted writers: {relative}: {','.join(sorted(missing))}"
            )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=_REPO)
    parser.add_argument("--baseline", type=Path, default=_BASELINE)
    parser.add_argument("--regenerate", action="store_true")
    args = parser.parse_args(argv)
    if args.regenerate:
        _write(args.root, args.baseline)
        print(f"wrote legal admission writer baseline: {sum(_read(args.baseline).values())} sites")
        return 0
    findings = errors(args.root, args.baseline)
    if findings:
        print("Legal admission writer violations:")
        for finding in findings:
            print(f"  {finding}")
        return 1
    print("OK: external raw-writer debt did not grow and converted connectors remain admitted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
