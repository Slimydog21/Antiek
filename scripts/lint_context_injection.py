#!/usr/bin/env python3
"""lint_context_injection — surface substrate code paths that mutate context behind callers."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

Severity = Literal["low", "medium", "high"]

_R1_ALLOWLIST_PREFIXES = (
    "substrate/hooks/",
    "substrate/conversation/",
)
_R2_ALLOWLIST_PREFIXES = (
    "substrate/config/",
    "substrate/observability/",
    "substrate/constants.py",
    "substrate/tools/run_script.py",
    "substrate/edit/transaction.py",
)
_R3_ALLOWED_GLOBAL_NAMES = frozenset(
    {
        "logger", "log", "_LOG", "_LOGGER", "__all__", "_DISABLE_ENV", "_PROTOCOLS",
        "_SCHEMA_PATH", "_burn_context", "_VERSION_RE", "_SINCE_RE",
        "_USAGE_MARKER_PREFIX", "_R1_ALLOWLIST_PREFIXES", "_R2_ALLOWLIST_PREFIXES",
        "_R3_ALLOWED_GLOBAL_NAMES", "_R5_ALLOWED_PREFIXES", "_COMPACTION_MARKER",
        "_VALID_KINDS", "_branches_file", "_checkpoints_file", "_conversation_dir",
    }
)
_R5_ALLOWED_PREFIXES = ("substrate/hooks/", "substrate/prompts/")


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: Severity
    file: str
    line: int
    message: str
    context: str = ""


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _allow_prefix(rel: str, allowlist: tuple[str, ...]) -> bool:
    return any(rel.startswith(p) or rel == p.rstrip("/") for p in allowlist)


def _file_uses_hook_dispatch(source: str) -> bool:
    return "registry.dispatch" in source or "HookContext" in source


def _check_r1_message_mutation(tree, source, rel) -> list[Finding]:
    if _allow_prefix(rel, _R1_ALLOWLIST_PREFIXES):
        return []
    findings: list[Finding] = []

    class _Visitor(ast.NodeVisitor):
        def visit_Assign(self, node: ast.Assign) -> None:
            for target in node.targets:
                if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                    if target.value.id == "self" and target.attr in {"_messages", "_context", "messages", "system_prompt"}:
                        findings.append(
                            Finding(
                                rule="R1", severity="high", file=rel, line=node.lineno,
                                message=f"assigns to self.{target.attr} outside hook dispatch",
                                context=ast.unparse(node)[:120],
                            )
                        )
            self.generic_visit(node)

        def visit_Call(self, node: ast.Call) -> None:
            if isinstance(node.func, ast.Attribute) and node.func.attr in {"append", "extend", "insert"}:
                if isinstance(node.func.value, ast.Name) and node.func.value.id in {
                    "messages", "msgs", "ctx_messages", "system_messages",
                }:
                    findings.append(
                        Finding(
                            rule="R1", severity="medium", file=rel, line=node.lineno,
                            message=(
                                f"{node.func.value.id}.{node.func.attr}(...) "
                                f"mutates a messages collection in scope; should pass through hook lifecycle"
                            ),
                            context=ast.unparse(node)[:120],
                        )
                    )
            self.generic_visit(node)

    _Visitor().visit(tree)
    return findings


def _check_r2_os_environ(tree, rel) -> list[Finding]:
    if _allow_prefix(rel, _R2_ALLOWLIST_PREFIXES):
        return []
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id == "os" and node.attr == "environ":
                findings.append(
                    Finding(
                        rule="R2", severity="medium", file=rel, line=node.lineno,
                        message="reads os.environ outside substrate/config/ or substrate/observability/",
                    )
                )
    return findings


def _check_r3_module_globals(tree, rel) -> list[Finding]:
    if "constants.py" in rel or "schemas/" in rel or "tests/" in rel:
        return []
    findings: list[Finding] = []
    for node in tree.body if isinstance(tree, ast.Module) else []:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    if target.id in _R3_ALLOWED_GLOBAL_NAMES:
                        continue
                    if isinstance(node.value, (ast.List, ast.Dict, ast.Set)):
                        findings.append(
                            Finding(
                                rule="R3", severity="low", file=rel, line=node.lineno,
                                message=(
                                    f"module-level mutable global {target.id!r} ({type(node.value).__name__})"
                                ),
                            )
                        )
    return findings


_R4_NAME_PATTERNS = ("_inject", "_augment_context", "_patch_system_prompt")


def _check_r4_suspicious_names(tree, source, rel) -> list[Finding]:
    findings: list[Finding] = []
    uses_dispatch = _file_uses_hook_dispatch(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if any(pat in node.name for pat in _R4_NAME_PATTERNS):
                if not uses_dispatch:
                    findings.append(
                        Finding(
                            rule="R4", severity="high", file=rel, line=node.lineno,
                            message=(
                                f"function {node.name!r} matches anti-pattern name "
                                f"but file does not dispatch through hook lifecycle"
                            ),
                        )
                    )
    return findings


def _check_r5_system_prompt(tree, rel) -> list[Finding]:
    if _allow_prefix(rel, _R5_ALLOWED_PREFIXES):
        return []
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                name: str | None = None
                if isinstance(target, ast.Name):
                    name = target.id
                elif isinstance(target, ast.Attribute):
                    name = target.attr
                if name == "system_prompt":
                    findings.append(
                        Finding(
                            rule="R5", severity="high", file=rel, line=node.lineno,
                            message="assigns to system_prompt outside substrate/hooks/ or substrate/prompts/",
                        )
                    )
    return findings


ALL_RULES = (
    _check_r1_message_mutation,
    _check_r2_os_environ,
    _check_r3_module_globals,
    _check_r4_suspicious_names,
    _check_r5_system_prompt,
)


def lint_file(path: Path, root: Path) -> list[Finding]:
    rel = _rel(path, root)
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (UnicodeDecodeError, SyntaxError):
        return []
    findings: list[Finding] = []
    for rule in ALL_RULES:
        try:
            if rule.__name__ == "_check_r1_message_mutation":
                findings.extend(rule(tree, source, rel))
            elif rule.__name__ == "_check_r2_os_environ":
                findings.extend(rule(tree, rel))
            elif rule.__name__ == "_check_r3_module_globals":
                findings.extend(rule(tree, rel))
            elif rule.__name__ == "_check_r4_suspicious_names":
                findings.extend(rule(tree, source, rel))
            elif rule.__name__ == "_check_r5_system_prompt":
                findings.extend(rule(tree, rel))
        except Exception as exc:
            findings.append(
                Finding(rule="LINT_ERROR", severity="low", file=rel, line=0,
                       message=f"linter rule {rule.__name__} raised: {exc!r}")
            )
    return findings


def walk_targets(targets: list[Path]) -> list[Path]:
    files: list[Path] = []
    for t in targets:
        if t.is_file() and t.suffix == ".py":
            files.append(t)
        elif t.is_dir():
            files.extend(sorted(t.rglob("*.py")))
    return [
        f for f in files
        if "__pycache__" not in f.parts and ".venv" not in f.parts and "node_modules" not in f.parts
    ]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="lint_context_injection")
    p.add_argument("paths", nargs="*")
    p.add_argument("--json", action="store_true")
    p.add_argument("--severity", choices=["low", "medium", "high"], default="low")
    p.add_argument("--root", type=Path, default=Path.cwd())
    args = p.parse_args(argv)

    severity_rank = {"low": 0, "medium": 1, "high": 2}
    targets = [Path(t) for t in args.paths] if args.paths else [args.root / "substrate"]

    findings: list[Finding] = []
    for f in walk_targets(targets):
        findings.extend(lint_file(f, args.root))

    findings = [f for f in findings if severity_rank[f.severity] >= severity_rank[args.severity]]
    findings.sort(key=lambda f: (-severity_rank[f.severity], f.file, f.line))

    if args.json:
        sys.stdout.write(json.dumps([asdict(f) for f in findings], indent=2) + "\n")
    else:
        if not findings:
            sys.stdout.write("(no findings)\n")
        else:
            for f in findings:
                sys.stdout.write(f"[{f.severity.upper()}] {f.rule} {f.file}:{f.line}  {f.message}\n")
                if f.context:
                    sys.stdout.write(f"        {f.context}\n")
            sys.stdout.write(f"\n{len(findings)} finding(s)\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
