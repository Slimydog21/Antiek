"""Role coverage for the dispatch router — the missing gate.

WHAT THIS PROVES
----------------
Every string-literal role passed to ``dispatch()`` anywhere in ``substrate/`` or
``interfaces/`` has an entry in ``substrate/dispatch/config.yaml`` under
``role_tiers``. Without the entry, ``router.dispatch`` raises

    KeyError("Role 'X' not in config.role_tiers. Known: [...]")

and because most call sites catch only their own domain error, that KeyError
escapes as an unhandled 500.

WHY A TEST AND NOT SIX FIXES
----------------------------
This defect has now occurred **six** times, each fixed one line at a time:
``knowledge_extractor``, ``thought_partner``, ``creative_writer``,
``autocomplete`` and ``interviewer`` — the comments in ``config.yaml`` record
each one — and ``reformat``, which shipped and was not fixed. Six occurrences
of one bug is a missing gate, not missing diligence. This file is the gate.

The check is static (AST), so it needs no provider, no network and no keys.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / "substrate" / "dispatch" / "config.yaml"

# The whole first-party tree, not just the two directories the defect was first
# seen in. An independent critic showed the narrower scan missed eight further
# call sites (four with literal roles) under tools/, scripts/, skills/, roles/
# and processing/ — all configured today, all invisible to a two-root scan.
# Exclusions are vendored, generated, or test trees: tests legitimately call
# dispatch with non-literal roles through mocks.
SCAN_EXCLUDE = {
    ".git", ".venv", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "node_modules", "worktrees", "clones", "third_party", "tests",
    "site-packages", "__pycache__",
}


def _literal_roles() -> list[tuple[str, int, str]]:
    """Every ``dispatch(<prompt>, "<role>", ...)`` literal call site."""
    found: list[tuple[str, int, str]] = []
    for path in sorted(REPO.rglob("*.py")):
        if set(path.relative_to(REPO).parts) & SCAN_EXCLUDE:
            continue
        try:
            tree = ast.parse(path.read_text(errors="replace"))
        except SyntaxError:  # a file that does not parse is another test's business
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if name != "dispatch":
                continue
            role: str | None = None
            if (
                len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)
            ):
                role = node.args[1].value
            for kw in node.keywords:
                if (
                    kw.arg == "role"
                    and isinstance(kw.value, ast.Constant)
                    and isinstance(kw.value.value, str)
                ):
                    role = kw.value.value
            if role is not None:
                found.append((str(path.relative_to(REPO)), node.lineno, role))
    return found


@pytest.fixture(scope="module")
def configured_roles() -> set[str]:
    """The role_tiers keys, read the way the router reads them."""
    from substrate.dispatch.router import DispatchConfig

    return set(DispatchConfig.from_yaml(CONFIG).role_tiers)


def test_the_scanner_actually_finds_call_sites() -> None:
    """A vacuous scan would make every assertion below pass for the wrong reason."""
    sites = _literal_roles()
    assert len(sites) >= 15, (
        f"only {len(sites)} literal dispatch() call sites found — the scanner is "
        "blind, so the coverage assertion below proves nothing"
    )
    assert any(role == "creative_writer" for _, _, role in sites), (
        "the known-literal 'creative_writer' call site was not found"
    )


def test_every_literal_dispatch_role_is_configured(configured_roles: set[str]) -> None:
    """The gate. Each unconfigured role is named with its call site."""
    missing = [
        (path, line, role)
        for path, line, role in _literal_roles()
        if role not in configured_roles
    ]
    assert not missing, (
        "dispatch() is called with roles that config.yaml does not route, so the "
        "router will raise an uncaught KeyError and the endpoint will 500:\n"
        + "\n".join(
            f"  {role!r} at {path}:{line} — add `{role}: <tier>` under role_tiers"
            for path, line, role in missing
        )
    )


def test_reformat_is_configured(configured_roles: set[str]) -> None:
    """The specific regression: ``substrate/reformat/pipeline.py`` dispatches this role."""
    assert "reformat" in configured_roles, (
        "substrate/reformat/pipeline.py:180 dispatches role='reformat'; without a "
        "role_tiers entry every real POST /books/{id}/reformats raises KeyError "
        "from substrate/dispatch/router.py:610-615 and returns 500"
    )
