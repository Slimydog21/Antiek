"""Mechanical guard against reintroducing globally keyed artifact paths."""

from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_PRODUCTION = [
    *_ROOT.joinpath("substrate/research_artifact").glob("*.py"),
    _ROOT / "interfaces/research/api/artifact_routes.py",
]
_FORBIDDEN = {"artifact_path_for", "compose_path_for"}


def test_no_production_call_or_import_uses_global_artifact_path_helpers():
    violations: list[str] = []
    for path in _PRODUCTION:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else None
                if name in _FORBIDDEN:
                    violations.append(f"{path.relative_to(_ROOT)}:{node.lineno}:{name}")
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name in _FORBIDDEN:
                        violations.append(f"{path.relative_to(_ROOT)}:{node.lineno}:{alias.name}")
    assert violations == []


def test_http_authority_has_no_owner_input_surface():
    path = _ROOT / "interfaces/research/api/artifact_routes.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    route_functions = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr in {"get", "post", "put", "patch", "delete"}
            for decorator in node.decorator_list
        )
    ]
    for function in route_functions:
        names = {argument.arg for argument in function.args.args}
        assert not names.intersection({"account_id", "owner_id", "user_id"}), function.name


def test_bare_body_source_reads_are_confined_to_named_operator_compatibility():
    path = _ROOT / "substrate/research_artifact/build_body.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    bare_calls = {
        "distillation_for",
        "problem_question_from_events",
        "synthesis_from_events",
    }
    violations: list[str] = []
    for function in (node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)):
        for node in ast.walk(function):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in bare_calls
                and function.name != "_operator_compatibility_sources"
            ):
                violations.append(f"{function.name}:{node.lineno}:{node.func.id}")
    assert violations == []


def test_legacy_body_reads_require_explicit_operator_capability_not_account_name():
    path = _ROOT / "substrate/research_artifact/build_body.py"
    source = path.read_text(encoding="utf-8")
    assert "if authority.local_operator_compatibility:" in source
    assert 'if authority.account_id == "__operator__":' not in source
