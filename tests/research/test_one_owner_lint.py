"""One-owner CI lint — enforces INV-1 mechanically.

INV-1: "The research-execution layer has exactly one owner — the
ResearchRunner. Exa Deep and Parallel are tools behind
ResearchProvider; no module outside the adapter package imports an
engine SDK."

This test walks the repo's ``.py`` files with ``ast`` and fails if any
module OUTSIDE the allowed locations imports a provider engine SDK.

Exact rule
----------
A "provider engine SDK" is any of these root packages / subpackages:
* ``acquisition.search.exa`` (the Exa client stack)
* ``acquisition.search.parallel`` (the future Parallel SDK — none yet,
  but the lint is ready for it)

A module may import one of these ONLY if it lives in one of these
ALLOWED locations:

1. ``research/providers/`` — the new adapter package this sprint
   creates. The whole point: SDK imports live here.
2. ``acquisition/search/exa/`` — the existing Exa client package owns
   its own SDK (``acquisition/search/exa/client.py`` imports httpx and
   the Exa REST API; the package is its own boundary). Same for
   ``acquisition/search/parallel/`` when it exists.
3. ``tests/`` — the provider's own unit tests import the SDK to test
   it. Tests are not "the research-execution layer"; they do not run in
   the execution path.
4. ``acquisition/search/`` top-level glue (``acquisition/search/__init__.py``,
   ``acquisition/search/retention.py``) — the search-package own
   re-exports and retention tooling. These are part of the acquisition
   layer, not the research-execution layer; they sit beside the SDK,
   not above it.
5. **Documented pre-existing violation:** ``runtime/research_runner/host_local.py``
   imports ``acquisition.search.exa`` inside ``make_exa_gather_loop``
   (line ~564). This is the INV-1/INV-4 violation SPR-01 *identifies*
   and SPR-03 *fixes* (by routing that gather loop through the new
   provider interface). It is allowlisted here with a loud comment so
   the lint is green today; SPR-03 removes the import AND removes the
   allowlist entry. A lint that failed today would block the sprint
   whose entire purpose is to enable the fix.

Anything else importing an engine SDK is a violation: the runner, the
cascade routes, the API layer, etc. must go through
``ResearchProvider`` behind ``research/providers/``.

Why ast, not grep
-----------------
``ast`` parses imports precisely (``ast.Import`` / ``ast.ImportFrom``),
so a string ``"exa"`` inside a docstring or a variable name does not
false-positive. grep would catch ``from acquisition.search.exa import``
but also a comment mentioning it; ast is the defensible tool.

Proven to fire
--------------
This lint was proven to fire by creating a scratch file
``_scratch_smuggle.py`` at the REPO ROOT (deliberately outside every
allowed prefix — placing it under ``tests/`` would NOT fire because
``tests/`` is allowlisted, a trap an earlier draft of this comment
fell into) containing ``from acquisition.search.exa import discover``,
running the lint, and observing it fail with:

    _scratch_smuggle.py:4 imports provider SDK 'acquisition.search.exa'
    outside research/providers/ (INV-1: one owner — use ResearchProvider)

The scratch file was then deleted so the lint is green. See the comment
block at the bottom of this file for the recorded transcript.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

# ── The set of provider engine SDK import roots the lint guards. ───────
# Each entry is a dotted module prefix. An import whose resolved module
# starts with one of these is a "provider SDK import" for this lint.
_PROVIDER_SDK_ROOTS: tuple[str, ...] = (
    "acquisition.search.exa",
    "acquisition.search.parallel",
)

# ── Allowed locations for provider SDK imports. ────────────────────────
# A violating file is one whose repo-relative path is NOT under any of
# these prefixes. (Path matching uses POSIX separators; resolved below.)
_REPO_ROOT = Path(__file__).resolve().parents[2]

# Path prefixes (POSIX, repo-relative) where SDK imports are permitted.
_ALLOWED_PREFIXES: tuple[str, ...] = (
    "research/providers/",          # the new adapter package (M2–M6)
    "acquisition/search/exa/",      # the Exa client package owns its SDK
    "acquisition/search/parallel/", # the future Parallel SDK owns itself
    "acquisition/search/__init__",  # search-package top-level re-exports
    "acquisition/search/retention", # search-package retention tooling
    "tests/",                       # provider unit tests test the SDK
)

# Documented pre-existing violation: the exa gather loop in the runner.
# SPR-03 removes this import AND this allowlist entry. NOT a permanent
# carve-out — flagged loud so a reviewer notices it.
_PRE_EXISTING_VIOLATIONS: frozenset[str] = frozenset(
    {
        # runtime/research_runner/host_local.py: make_exa_gather_loop does
        # `from acquisition.search.exa import discover, promote_discovery`.
        # Out of scope for SPR-01 (do not rewrite); SPR-03 routes through
        # the ResearchProvider interface and deletes this entry.
        "runtime/research_runner/host_local.py",
    }
)

# Directories to skip entirely (vendored / scratch / build artifacts).
_SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".venv",
        "__pycache__",
        ".caffenagent",   # scratch / agent working dirs, not shipped code
        ".git",
        "node_modules",
        ".pytest_cache",
    }
)


def _repo_relative(p: Path) -> str:
    return p.relative_to(_REPO_ROOT).as_posix()


def _is_allowed(rel: str) -> bool:
    if rel in _PRE_EXISTING_VIOLATIONS:
        return True
    return any(rel.startswith(prefix) for prefix in _ALLOWED_PREFIXES)


def _imported_roots(tree: ast.AST) -> list[tuple[str, int]]:
    """Return ``(dotted_module, lineno)`` for every Import/ImportFrom."""
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            # module is None for relative ``from . import x``; level is
            # the number of leading dots. We only flag absolute imports
            # of the provider SDK roots (level 0, resolved module).
            if node.level == 0 and node.module:
                out.append((node.module, node.lineno))
    return out


def _violations() -> list[str]:
    """Walk the repo; return a list of violation strings (path:line — detail)."""
    bad: list[str] = []
    for dirpath, dirnames, filenames in os.walk(_REPO_ROOT):
        # prune skipped dirs in-place so os.walk doesn't descend
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            fpath = Path(dirpath) / fname
            rel = _repo_relative(fpath)
            if _is_allowed(rel):
                continue
            try:
                src = fpath.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            try:
                tree = ast.parse(src, filename=rel)
            except SyntaxError:
                # A syntax error is a different problem; don't let it
                # mask the lint. Skip (the file's own tests will fail).
                continue
            for mod, lineno in _imported_roots(tree):
                if any(
                    mod == root or mod.startswith(root + ".")
                    for root in _PROVIDER_SDK_ROOTS
                ):
                    bad.append(
                        f"{rel}:{lineno} imports provider SDK "
                        f"'{mod}' outside research/providers/ "
                        f"(INV-1: one owner — use ResearchProvider)"
                    )
    return bad


def test_no_module_outside_adapters_imports_engine_sdk():
    """The one-owner lint. Fails listing every violating path:line.

    If this test fails, a module outside ``research/providers/`` (and
    outside the other allowed locations documented above) imports an
    engine SDK directly. Fix it by routing the call through a
    ``ResearchProvider`` adapter behind ``research/providers/``.

    Proven to fire: see the comment block at the bottom of this file.
    """
    bad = _violations()
    if bad:
        lines = "\n".join(f"  - {b}" for b in bad)
        pytest.fail(
            "INV-1 one-owner lint: found provider SDK imports outside "
            "the adapter package:\n" + lines
        )


# ---------------------------------------------------------------------------
# Proof the lint fires (rigor #3 — a green lint alone proves nothing).
#
# Procedure run during SPR-01:
#   1. Created /Users/slimydog/Desktop/Antiek/_scratch_smuggle.py (repo ROOT,
#      outside every allowed prefix) with body:
#        from acquisition.search.exa import discover
#   2. Ran `.venv/bin/python -m pytest tests/research/test_one_owner_lint.py -q`
#   3. Observed FAILURE:
#        _scratch_smuggle.py:4 imports provider SDK 'acquisition.search.exa'
#        outside research/providers/ (INV-1: one owner — use ResearchProvider)
#   4. Deleted /Users/slimydog/Desktop/Antiek/_scratch_smuggle.py.
#   5. Re-ran; lint green (1 passed).
#
# NOTE: an earlier draft placed the scratch under tests/research/ and claimed
# it fired. That was FALSE — tests/ is an allowed prefix, so the lint would
# NOT fire there. The scratch MUST sit outside every allowed prefix for the
# proof to be real. A lint that cannot fire is security theater; this one does.
# ---------------------------------------------------------------------------
