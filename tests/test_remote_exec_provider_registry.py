"""Registry guard: the remote-exec factory has exactly ONE provider (Daytona).

``runtime/remote_exec/prime_exec.py`` (``PrimeExecProvider``) is a dark,
default-off adapter. It must stay unreferenced by the factory: the §16
research-fanout exemption ratifies Daytona as *the one* live provider, so a
second one may not be wired in — via import, registry entry, env-selected
branch, or string/importlib registration — without first amending
``docs/decisions/s16-research-fanout-exemption.md``. These tests are stronger
than ``test_prime_exec_provider.py::test_default_factory_never_registers_prime``
(which only inspects the default factory's return value): they go red on any
reference to ``prime_exec`` inside ``factory.py`` and on any production module
importing it, even while the default stays Daytona. All static, hermetic, no
network, no DB.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

from runtime.remote_exec.daytona import DaytonaProvider
from runtime.remote_exec.factory import ENABLE_ENV, _default_provider_factory
from runtime.remote_exec.prime_exec import PRIME_EXEC_ENABLE_ENV, PrimeExecProvider

REPO_ROOT = Path(__file__).resolve().parents[1]
FACTORY_PATH = REPO_ROOT / "runtime" / "remote_exec" / "factory.py"

REMOTE_EXEC_PACKAGE = "runtime.remote_exec"
PRIME_EXEC_MODULE = f"{REMOTE_EXEC_PACKAGE}.prime_exec"

# Interface / infrastructure modules of runtime.remote_exec that the factory
# legitimately imports; they are not provider implementations.
_NON_PROVIDER_SIBLINGS = frozenset({"provider", "runner", "cost", "funnel"})

# Production modules allowed to import prime_exec (currently: only the dark
# adapter itself). ADDING AN ENTRY HERE REQUIRES FIRST AMENDING
# docs/decisions/s16-research-fanout-exemption.md — a new entry means a second
# RemoteExecProvider is going live, which the exemption does not authorize.
_MODULES_ALLOWED_TO_IMPORT_PRIME = frozenset(
    {
        "runtime/remote_exec/prime_exec.py",
    }
)

# Directories whose production modules must never import prime_exec.
_SCANNED_DIRECTORIES = ("runtime", "interfaces", "orchestration", "services")


def _iter_imports(tree: ast.Module) -> Iterator[ast.Import | ast.ImportFrom]:
    """Every import node in the tree, including ones nested inside function
    bodies (``ast.walk`` reaches the whole tree, so a lazy import inside
    ``_default_provider_factory`` is collected exactly like a module-level
    one)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            yield node


def _first_component(dotted: str) -> str:
    return dotted.split(".")[0]


def _factory_provider_siblings(source: str) -> set[str]:
    """Sibling modules of ``runtime.remote_exec`` that ``source`` imports,
    minus the interface/infrastructure modules.

    Covers every import form that can reach a sibling:

    * ``from .daytona import DaytonaProvider``  (relative, named module)
    * ``from . import daytona``                (relative, aliased module)
    * ``import runtime.remote_exec.daytona``   (absolute plain import)
    * ``from runtime.remote_exec.daytona import X``  (absolute, named module)
    * ``from runtime.remote_exec import daytona``    (absolute, aliased module)

    Imports under ``runtime.research_runner`` (``from ..research_runner.x``)
    are structurally excluded: they resolve into the parent package and are
    never siblings of ``runtime.remote_exec``.
    """
    siblings: set[str] = set()
    for node in _iter_imports(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(f"{REMOTE_EXEC_PACKAGE}."):
                    siblings.add(
                        _first_component(alias.name[len(REMOTE_EXEC_PACKAGE) + 1 :])
                    )
        elif node.level >= 1:
            # Relative import. Only level 1 lands inside runtime.remote_exec;
            # deeper levels resolve into the parent package and above.
            if node.level == 1:
                if node.module:
                    siblings.add(_first_component(node.module))
                else:
                    siblings.update(_first_component(a.name) for a in node.names)
        elif node.module == REMOTE_EXEC_PACKAGE:
            siblings.update(_first_component(a.name) for a in node.names)
        elif node.module is not None and node.module.startswith(
            f"{REMOTE_EXEC_PACKAGE}."
        ):
            siblings.add(_first_component(node.module[len(REMOTE_EXEC_PACKAGE) + 1 :]))
    return siblings - _NON_PROVIDER_SIBLINGS


def test_factory_provider_registry_is_exactly_daytona() -> None:
    """AST scan of factory.py: the live provider registry (every sibling
    provider module the factory references, at any nesting depth) has exactly
    one entry, and it is daytona."""
    siblings = _factory_provider_siblings(FACTORY_PATH.read_text(encoding="utf-8"))
    assert siblings == {"daytona"}, (
        f"a second RemoteExecProvider was wired into the factory (provider "
        f"modules found: {sorted(siblings)}); the registry must be exactly "
        "{'daytona'} — amend docs/decisions/s16-research-fanout-exemption.md "
        "first"
    )
    assert "prime_exec" not in siblings, (
        "a second RemoteExecProvider (prime_exec) was wired into the factory; "
        "amend docs/decisions/s16-research-fanout-exemption.md first"
    )


def test_factory_source_never_mentions_prime() -> None:
    """Raw-source scan: neither identifier may appear anywhere in factory.py,
    which also catches string-based / importlib registration schemes the AST
    import walk cannot see."""
    source = FACTORY_PATH.read_text(encoding="utf-8")
    for identifier in ("prime_exec", "PrimeExecProvider"):
        assert identifier not in source, (
            f"'{identifier}' appears in factory.py source — a second "
            "RemoteExecProvider was wired into the factory (possibly via a "
            "string/importlib registration); amend "
            "docs/decisions/s16-research-fanout-exemption.md first"
        )


def test_default_factory_is_daytona_even_with_prime_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Behavioural: with BOTH enable flags truthy, the default provider
    factory still returns exactly a DaytonaProvider — no env-selected branch
    may hand back the dark adapter. (Construction is cheap and offline; the
    SDK loads lazily.)"""
    monkeypatch.setenv(ENABLE_ENV, "1")
    monkeypatch.setenv(PRIME_EXEC_ENABLE_ENV, "1")
    provider = _default_provider_factory()
    assert type(provider) is DaytonaProvider, (
        f"a second RemoteExecProvider was wired into the factory "
        f"(got {type(provider).__name__}); the default must stay Daytona "
        "even with every enable flag set — amend "
        "docs/decisions/s16-research-fanout-exemption.md first"
    )
    assert not isinstance(provider, PrimeExecProvider), (
        "a second RemoteExecProvider (PrimeExecProvider) was returned by the "
        "default factory; amend docs/decisions/s16-research-fanout-exemption.md "
        "first"
    )


def _imports_prime_exec(path: Path) -> bool:
    """Whether the module at ``path`` imports prime_exec — AST import scan
    (relative and absolute, module-level and nested), not a substring grep.

    The file's package is derived from its path relative to the repo root
    (which is right for both regular modules and ``__init__.py`` files), and a
    relative import climbs one package per dot beyond the first, so
    ``from ..remote_exec import prime_exec`` in ``runtime/research_runner/``
    resolves to ``runtime.remote_exec``.
    """
    directory_parts = path.relative_to(REPO_ROOT).with_suffix("").parts[:-1]
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in _iter_imports(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == PRIME_EXEC_MODULE or alias.name.startswith(
                    f"{PRIME_EXEC_MODULE}."
                ):
                    return True
        else:
            if node.level >= 1:
                # ``from ..x import y`` climbs one package per extra dot; a
                # level-1 import resolves against the file's own package.
                anchor_parts = directory_parts[: len(directory_parts) - (node.level - 1)]
                anchor = ".".join(anchor_parts)
                module = anchor + (f".{node.module}" if node.module else "")
            else:
                module = node.module or ""
            if module == PRIME_EXEC_MODULE or module.startswith(
                f"{PRIME_EXEC_MODULE}."
            ):
                return True
            if module == REMOTE_EXEC_PACKAGE and any(
                _first_component(alias.name) == "prime_exec" for alias in node.names
            ):
                return True
    return False


def test_no_production_module_imports_prime_exec() -> None:
    """Repo-wide scan: no production module outside the dark adapter itself
    imports prime_exec, so the adapter cannot be wired in from anywhere —
    not just from the factory."""
    offenders: list[str] = []
    scanned = 0
    for directory in _SCANNED_DIRECTORIES:
        for path in sorted((REPO_ROOT / directory).rglob("*.py")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if rel in _MODULES_ALLOWED_TO_IMPORT_PRIME:
                continue
            scanned += 1
            if _imports_prime_exec(path):
                offenders.append(rel)
    assert scanned > 0, (
        "scanned 0 production files — the guard went vacuous; update "
        "_SCANNED_DIRECTORIES to match the repo layout"
    )
    assert offenders == [], (
        f"production module(s) {offenders} import prime_exec — a second "
        "RemoteExecProvider is being wired in; amend "
        "docs/decisions/s16-research-fanout-exemption.md first, and only then "
        "extend _MODULES_ALLOWED_TO_IMPORT_PRIME"
    )
