#!/usr/bin/env python3
"""Observability vendor lint — forbid monitoring-vendor SDKs (§16).

The invariant (Antiek §16): Antiek must not grow a hard dependency on hosted
monitoring vendor SDKs. Observability stays vendor-neutral and local-first; a
new Sentry / Datadog / New Relic / OpenTelemetry exporter / Prometheus client /
Elastic APM / statsd import or dependency is a build break.

Modeled on ``tools/lint/boundary_check.py``: repo-root resolution via the script
path, deterministic tree walk, AST-based Python import matching, ``path:line``
violations, and exit-code contract (0 = clean, 1 = violations).
"""

from __future__ import annotations

import ast
import json
import re
import sys
import tomllib
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent

_PY_IMPORT_ROOTS: frozenset[str] = frozenset(
    {
        "sentry_sdk",
        "datadog",
        "ddtrace",
        "newrelic",
        "prometheus_client",
        "elasticapm",
        "statsd",
        "opentelemetry",
    }
)

_PY_DEPS_EXACT: frozenset[str] = frozenset(
    {
        "sentry-sdk",
        "datadog",
        "ddtrace",
        "newrelic",
        "prometheus-client",
        "elastic-apm",
        "statsd",
    }
)
_PY_DEPS_PREFIX: frozenset[str] = frozenset({"opentelemetry-"})

_SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
    }
)

_JS_DEPS_EXACT: frozenset[str] = frozenset(
    {
        "@sentry/browser",
        "@sentry/react",
        "dd-trace",
        "datadog",
    }
)
_JS_DEPS_PREFIX: frozenset[str] = frozenset(
    {
        "@sentry/",
        "@datadog/",
        "@opentelemetry/",
    }
)

_REQ_GLOBS: tuple[str, ...] = ("requirements*.txt",)

_DEP_TOKEN_RE = re.compile(
    r"""
    (?P<quote>["'])?
    (?P<name>
        @?[A-Za-z0-9][A-Za-z0-9_.-]*
        (?:/[A-Za-z0-9][A-Za-z0-9_.-]*)?
    )
    (?P=quote)?
    \s*
    (?:
        $|[,;\]\)}#]|==|!=|~=|<=|>=|<|>|\[
    )
    """,
    re.VERBOSE,
)

_DEP_NAME_RE = re.compile(
    r"""
    ^\s*
    (?P<name>
        @?[A-Za-z0-9][A-Za-z0-9_.-]*
        (?:/[A-Za-z0-9][A-Za-z0-9_.-]*)?
    )
    (?:
        \s*(?:\[|@|==|!=|~=|<=|>=|<|>|=|;|,|\s|$)
    )
    """,
    re.VERBOSE,
)


def _is_forbidden_py_import(module: str | None) -> str | None:
    if not module:
        return None
    for root in _PY_IMPORT_ROOTS:
        if module == root or module.startswith(root + "."):
            return root
    return None


def _is_forbidden_py_dep(name: str) -> str | None:
    normalized = name.lower().replace("_", "-")
    if normalized in _PY_DEPS_EXACT:
        return normalized
    for prefix in _PY_DEPS_PREFIX:
        if normalized.startswith(prefix):
            return prefix.rstrip("-")
    return None


def _is_forbidden_js_dep(name: str) -> str | None:
    if name in _JS_DEPS_EXACT:
        return name
    for prefix in _JS_DEPS_PREFIX:
        if name.startswith(prefix):
            return name
    return None


def _python_dependency_files(root: Path) -> list[Path]:
    # Direct-only: lockfiles contain transitive deps; §16 blocks Antiek's direct declarations.
    files: set[Path] = {p for p in root.rglob("pyproject.toml") if not _is_skipped_path(p)}
    for req_glob in _REQ_GLOBS:
        files.update(p for p in root.rglob(req_glob) if not _is_skipped_path(p))
    return sorted(files)


def _line_for_key(path: Path, key: str) -> int:
    needle = json.dumps(key)
    try:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if needle in line:
                return lineno
    except OSError:
        pass
    return 1


def _is_skipped_path(path: Path) -> bool:
    return any(part in _SKIP_DIRS for part in path.parts)


def _strip_inline_comment(line: str) -> str:
    quote: str | None = None
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
            continue
        if char == "#":
            return line[:index]
    return line


def _dep_name_from_spec(spec: str) -> str | None:
    stripped = spec.strip()
    if not stripped or stripped.startswith(("-", "--")):
        return None
    match = _DEP_NAME_RE.match(stripped)
    if not match:
        return None
    return match.group("name")


def _dep_names_from_line(line: str) -> list[str]:
    stripped = _strip_inline_comment(line).strip()
    if not stripped or stripped.startswith("#"):
        return []
    name = _dep_name_from_spec(stripped)
    if name:
        return [name]
    return [match.group("name") for match in _DEP_TOKEN_RE.finditer(stripped)]


def _line_for_pyproject_dep(path: Path, name: str, spec: str | None = None) -> int:
    normalized = name.lower().replace("_", "-")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 1
    for lineno, line in enumerate(lines, 1):
        stripped = _strip_inline_comment(line)
        if spec and spec in stripped:
            return lineno
        for found in _dep_names_from_line(stripped):
            if found.lower().replace("_", "-") == normalized:
                return lineno
        if re.search(rf"^\s*['\"]?{re.escape(name)}['\"]?\s*=", stripped):
            return lineno
    return 1


def _pyproject_dependency_entries(path: Path) -> list[tuple[str, int]]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return []

    entries: list[tuple[str, int]] = []

    def add_spec(spec: object) -> None:
        if not isinstance(spec, str):
            return
        name = _dep_name_from_spec(spec)
        if name:
            entries.append((name, _line_for_pyproject_dep(path, name, spec)))

    def add_table(table: object) -> None:
        if not isinstance(table, dict):
            return
        for name, value in table.items():
            if name == "python":
                continue
            if isinstance(value, str):
                entries.append((name, _line_for_pyproject_dep(path, name, value)))
            elif isinstance(value, dict):
                dep_name = value.get("name")
                if isinstance(dep_name, str):
                    entries.append((dep_name, _line_for_pyproject_dep(path, dep_name)))
                else:
                    entries.append((name, _line_for_pyproject_dep(path, name)))

    project = data.get("project", {})
    if isinstance(project, dict):
        dependencies = project.get("dependencies", [])
        if isinstance(dependencies, list):
            for spec in dependencies:
                add_spec(spec)
        optional = project.get("optional-dependencies", {})
        if isinstance(optional, dict):
            for group in optional.values():
                if isinstance(group, list):
                    for spec in group:
                        add_spec(spec)

    dependency_groups = data.get("dependency-groups", {})
    if isinstance(dependency_groups, dict):
        for group in dependency_groups.values():
            if isinstance(group, list):
                for spec in group:
                    add_spec(spec)
            else:
                add_table(group)

    poetry = data.get("tool", {}).get("poetry", {}) if isinstance(data.get("tool"), dict) else {}
    if isinstance(poetry, dict):
        add_table(poetry.get("dependencies", {}))
        add_table(poetry.get("dev-dependencies", {}))
        groups = poetry.get("group", {})
        if isinstance(groups, dict):
            for group in groups.values():
                if isinstance(group, dict):
                    add_table(group.get("dependencies", {}))

    return entries


def _find_python_import_violations(root: Path) -> list[str]:
    out: list[str] = []
    for py in sorted(root.rglob("*.py")):
        if _is_skipped_path(py):
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        rel = py.relative_to(root).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    forbidden = _is_forbidden_py_import(alias.name)
                    if forbidden:
                        out.append(f"{rel}:{node.lineno} — {forbidden} (§16)")
            elif isinstance(node, ast.ImportFrom):
                forbidden = _is_forbidden_py_import(node.module)
                if forbidden:
                    out.append(f"{rel}:{node.lineno} — {forbidden} (§16)")
    return out


def _find_python_dependency_violations(root: Path) -> list[str]:
    out: list[str] = []
    for dep_file in _python_dependency_files(root):
        rel = dep_file.relative_to(root).as_posix()
        if dep_file.name == "pyproject.toml":
            entries = _pyproject_dependency_entries(dep_file)
        else:
            try:
                lines = dep_file.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            entries = [
                (name, lineno)
                for lineno, line in enumerate(lines, 1)
                for name in _dep_names_from_line(line)
            ]
        for name, lineno in entries:
            forbidden = _is_forbidden_py_dep(name)
            if forbidden:
                out.append(f"{rel}:{lineno} — {forbidden} (§16)")
    return out


def _find_js_dependency_violations(root: Path) -> list[str]:
    out: list[str] = []
    for package_json in sorted((root / "apps").glob("*/package.json")):
        if _is_skipped_path(package_json):
            continue
        try:
            package = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rel = package_json.relative_to(root).as_posix()
        for section in (
            "dependencies",
            "devDependencies",
            "peerDependencies",
            "optionalDependencies",
        ):
            deps = package.get(section, {})
            if not isinstance(deps, dict):
                continue
            for name in sorted(deps):
                forbidden = _is_forbidden_js_dep(name)
                if forbidden:
                    out.append(f"{rel}:{_line_for_key(package_json, name)} — {forbidden} (§16)")
    return out


def find_violations(root: Path = _REPO) -> list[str]:
    return (
        _find_python_dependency_violations(root)
        + _find_python_import_violations(root)
        + _find_js_dependency_violations(root)
    )


def main() -> int:
    violations = find_violations()
    if violations:
        for line in violations:
            print(line)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
