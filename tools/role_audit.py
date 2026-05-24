"""
Walk ``roles/`` and report each role's shape metadata.

Antiek's roles are package-shaped (Python packages under ``roles/<name>/``);
each package's ``__init__.py`` declares a module-level
``__role_metadata__`` constant of type :class:`substrate.role_shape.RoleMetadata`.
This script:

1. Imports each role package.
2. Confirms the constant exists and is well-formed.
3. Prints a table (human-readable or JSON via ``--json``).
4. Exits non-zero if any role lacks the constant — wire into pre-commit
   or CI to refuse a merge that introduces an unannotated role.

Usage::

    python -m tools.role_audit            # human table
    python -m tools.role_audit --json     # machine-readable
    python -m tools.role_audit --check    # exit 1 if any role unannotated;
                                          # silent otherwise (for CI)

Spec: ~/specs/antiek-yegge-execute/sprint-03-role-decorators.html
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from dataclasses import asdict
from typing import List, Optional

from substrate.role_shape import RoleMetadata

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ROLES_DIR = os.path.join(_REPO_ROOT, "roles")


def _discover_role_names() -> List[str]:
    """Return the set of role names by scanning ``roles/`` for subdirs
    containing an ``__init__.py``. Sorted for stable output."""
    if not os.path.isdir(_ROLES_DIR):
        return []
    out: List[str] = []
    for entry in sorted(os.listdir(_ROLES_DIR)):
        # Skip private + dunder + non-directories
        if entry.startswith(("_", ".")):
            continue
        path = os.path.join(_ROLES_DIR, entry)
        if not os.path.isdir(path):
            continue
        if not os.path.exists(os.path.join(path, "__init__.py")):
            continue
        out.append(entry)
    return out


def _load_metadata(role_name: str) -> Optional[RoleMetadata]:
    """Import ``roles.<role_name>`` and return its ``__role_metadata__``.

    Returns None if the package fails to import or lacks the attribute.
    The audit reports the failure rather than raising; surfacing every
    unannotated role in one run beats failing-fast on the first one.
    """
    # Ensure repo root is on sys.path so ``import roles.X`` works when
    # this script is invoked outside an installed-package context.
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)
    try:
        mod = importlib.import_module(f"roles.{role_name}")
    except Exception as exc:  # noqa: BLE001 — surfacing import errors to the audit
        sys.stderr.write(f"role_audit: import roles.{role_name} failed: {exc!r}\n")
        return None
    md = getattr(mod, "__role_metadata__", None)
    if md is None:
        return None
    if not isinstance(md, RoleMetadata):
        sys.stderr.write(
            f"role_audit: roles.{role_name}.__role_metadata__ is not a "
            f"RoleMetadata instance (got {type(md).__name__})\n"
        )
        return None
    return md


def audit() -> dict:
    """Return a structured audit result."""
    annotated: list[dict] = []
    unannotated: list[str] = []
    for name in _discover_role_names():
        md = _load_metadata(name)
        if md is None:
            unannotated.append(name)
            continue
        annotated.append({"name": name, **asdict(md)})
    by_shape = {
        "polecat": sum(1 for r in annotated if r["shape"] == "polecat"),
        "crew": sum(1 for r in annotated if r["shape"] == "crew"),
    }
    return {
        "annotated": annotated,
        "unannotated": unannotated,
        "total": len(annotated) + len(unannotated),
        "by_shape": by_shape,
    }


def _render_human(result: dict) -> str:
    lines: list[str] = []
    lines.append(
        f"role_audit: {len(result['annotated'])} annotated, "
        f"{len(result['unannotated'])} unannotated "
        f"(polecat={result['by_shape']['polecat']}, crew={result['by_shape']['crew']})"
    )
    if result["annotated"]:
        lines.append("")
        lines.append(f"{'NAME':<24} {'SHAPE':<8} {'IN/OUT':<14} {'IDEM':<5} DOC")
        for r in result["annotated"]:
            io = f"{r['expected_input_tokens']}/{r['expected_output_tokens']}"
            idem = "yes" if r["idempotent"] else "no"
            doc = r["spawn_pattern_doc"]
            doc_short = (doc[:60] + "...") if len(doc) > 60 else doc
            lines.append(f"{r['name']:<24} {r['shape']:<8} {io:<14} {idem:<5} {doc_short}")
    if result["unannotated"]:
        lines.append("")
        lines.append("UNANNOTATED (these will block merges once CI is wired):")
        for n in result["unannotated"]:
            lines.append(f"  - {n}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit role-shape metadata across roles/.",
    )
    parser.add_argument("--json", action="store_true",
                        help="Emit machine-readable JSON.")
    parser.add_argument("--check", action="store_true",
                        help="Silent unless unannotated roles found; exit code only.")
    args = parser.parse_args(argv)

    result = audit()

    if args.check:
        # CI mode: print only on failure. Keeps logs clean when green.
        if result["unannotated"]:
            print(
                f"role_audit: FAIL — {len(result['unannotated'])} unannotated "
                f"role(s): {', '.join(result['unannotated'])}",
                file=sys.stderr,
            )
            return 1
        return 0

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(_render_human(result))

    return 1 if result["unannotated"] else 0


if __name__ == "__main__":
    sys.exit(main())
