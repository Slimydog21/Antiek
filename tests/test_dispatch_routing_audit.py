"""Mechanical audit: investigation-scoped dispatch() uses routing kwargs.

ATSB SPR-02 gate — fails if a production module calls dispatch with
investigation_id but omits dispatch_routing_kwargs (or explicit brain/latency).
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]

_SCAN_ROOTS = (
    "substrate",
    "interfaces",
    "roles",
    "processing",
    "orchestration",
    "skills",
)

# Paths that legitimately call dispatch without routing (tests, scripts, router).
_SKIP_PREFIXES = (
    "substrate/dispatch/router.py",
    "substrate/dispatch/__init__.py",
)

def _rel(path: Path) -> str:
    return path.relative_to(_REPO).as_posix()


def _dispatch_calls_missing_routing(source: str, rel: str) -> list[str]:
    tree = ast.parse(source, filename=rel)
    issues: list[str] = []

    class V(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> None:
            func = node.func
            name = None
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name != "dispatch":
                self.generic_visit(node)
                return

            kw = {k.arg: k for k in node.keywords if k.arg}
            has_inv = "investigation_id" in kw
            has_routing = any(
                k in kw
                for k in (
                    "latency_mode",
                    "brain",
                    "deliverable_speed_preference",
                )
            )
            # **dispatch_routing_kwargs(...) appears as keyword splat — detect in source slice
            line = ast.get_source_segment(source, node) or ""
            has_splat_routing = "dispatch_routing_kwargs" in line

            if has_inv and not (has_routing or has_splat_routing):
                issues.append(f"{rel}: dispatch() with investigation_id lacks routing kwargs")
            self.generic_visit(node)

    V().visit(tree)
    return issues


def test_production_dispatch_sites_use_routing_kwargs():
    all_issues: list[str] = []
    paths: list[Path] = []
    for root in _SCAN_ROOTS:
        base = _REPO / root
        if base.is_dir():
            paths.extend(base.rglob("*.py"))
    for path in paths:
        rel = _rel(path)
        if any(rel.startswith(p) or rel == p for p in _SKIP_PREFIXES):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "dispatch(" not in text:
            continue
        if "investigation_id" not in text:
            continue
        all_issues.extend(_dispatch_calls_missing_routing(text, rel))

    assert not all_issues, "SPR-02 routing gaps:\n" + "\n".join(sorted(all_issues))