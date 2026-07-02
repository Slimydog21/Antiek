#!/usr/bin/env python3
"""Model-emitted reference validation lint.

KDL provenance sprint invariant: role parsers that accept model-emitted
``*_id`` / ``*_ids`` fields must route those references through the shared
``substrate.provenance.validate_refs`` helpers, or be an explicitly
grandfathered legacy parser with a separate owner.

This is intentionally narrow: it scans ``roles/**/parser.py`` only. It is not
a full taint analyzer; it is the mechanical tripwire that makes future parser
surfaces stop and choose an explicit validation strategy instead of silently
trusting model-emitted provenance IDs.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
_ROLES = _REPO / "roles"

_ID_FIELD = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:_id|_ids)$")

# Existing parser surfaces that predate the KDL sprint or validate against a
# local domain contract rather than the generic provenance helper. New entries
# require an owner decision; do not add to this list to silence a regression.
_GRANDFATHERED = frozenset({
    "roles/decomposer/parser.py",          # investigation_id echo check
    "roles/thought_partner/parser.py",     # note memory references
    "roles/voice_note_followup/parser.py", # block anchor suggestions
    "roles/visual/parser.py",              # page/frame envelope id
    "roles/creative_writer/parser.py",     # local block-id validation
})


def _rel(path: Path, repo: Path) -> str:
    return path.relative_to(repo).as_posix()


def _has_parser_entrypoint(tree: ast.AST) -> bool:
    return any(
        isinstance(node, ast.FunctionDef) and node.name.startswith("parse_")
        for node in ast.walk(tree)
    )


def _has_provenance_validator_import(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "substrate.provenance.validate_refs":
                imported = {alias.name for alias in node.names}
                if {"validate_ref", "validate_refs"} & imported:
                    return True
    return False


def _model_id_fields(tree: ast.AST) -> list[tuple[int, str]]:
    fields: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and _ID_FIELD.match(node.value)
        ):
            fields.append((node.lineno, node.value))
    return fields


def find_violations(*, repo: Path = _REPO) -> list[str]:
    out: list[str] = []
    roles = repo / "roles"
    if not roles.exists():
        return out
    for py in sorted(roles.rglob("parser.py")):
        rel = _rel(py, repo)
        if rel in _GRANDFATHERED:
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        if not _has_parser_entrypoint(tree):
            continue
        fields = _model_id_fields(tree)
        if not fields or _has_provenance_validator_import(tree):
            continue
        first_line, first_field = fields[0]
        out.append(
            f"{rel}:{first_line}: parser reads model-emitted {first_field!r} "
            "without importing substrate.provenance.validate_refs"
        )
    return out


def main(argv: list[str] | None = None) -> int:
    argv = argv or []
    repo = Path(argv[0]).resolve() if argv else _REPO
    violations = find_violations(repo=repo)
    if violations:
        print("Model reference validation violations:")
        for line in violations:
            print(f"  {line}")
        print(
            "\nRole parsers that accept model-emitted *_id/*_ids fields must "
            "validate against a canonical set via "
            "substrate.provenance.validate_refs, or receive an explicit "
            "grandfather/owner decision in this lint."
        )
        return 1
    print("OK: model-emitted parser refs are validated or explicitly grandfathered.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
